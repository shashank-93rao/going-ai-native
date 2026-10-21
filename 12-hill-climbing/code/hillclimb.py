"""A disciplined hill-climb runner: one change per round, keep/revert by statistics.

    python hillclimb.py data/variants.json --out runs/demo

The variants file (JSON, or YAML if PyYAML is installed) holds the baseline
config, the run settings and an ordered list of rounds. Each round is ONE
change applied to the current best config, or a `sweep` of alternatives.

For every round the runner:
  1. checks the frozen evaluator's fingerprint (grader + dataset unchanged),
  2. refuses changes that paste eval items into the prompt (unless allowed),
  3. runs the candidate on dev and test with fresh seeds and `repeats` repeats,
  4. computes paired, cluster-robust differences against the current best,
  5. keeps or reverts by the rules in `decide()`,
  6. appends a row to experiments.md and results.tsv.
"""

from __future__ import annotations

import argparse
import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from incident_router import build_system
from noise_check import run_noise_check
from router_eval import (DATA, ClientFactory, RunResult, by_tag, evaluate, fingerprint, load_split, sim_factory,
                         sim_factory_for)
from stats import Estimate, clustered_se, paired_bootstrap, paired_diff


@dataclass
class Rules:
    """Keep/revert policy. Defaults follow Anthropic's hillclimb rules, made numeric."""
    test_ratio: float = 0.5          # test gain must be >= this share of the dev gain
    require_test_significant: bool = False
    max_cost_ratio: float | None = None
    block_leaks: bool = True         # refuse configs that contain eval item text


@dataclass
class Trial:
    round: int
    name: str
    change: str
    hypothesis: str
    dev: RunResult
    test: RunResult
    d_dev: Estimate | None
    d_test: Estimate | None
    p_boot: float | None
    decision: str
    reason: str


def load_variants(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if p.suffix in (".yaml", ".yml"):
        try:
            import yaml  # optional dependency
        except ImportError as e:  # pragma: no cover
            raise SystemExit("YAML variants need PyYAML; use the JSON form instead") from e
        return yaml.safe_load(p.read_text())
    return json.loads(p.read_text())


def apply_change(best: dict[str, Any], change: dict[str, Any], dev_failures: list[dict]) -> dict[str, Any]:
    """Return a new config = best + ONE change. Supported change keys below."""
    cfg = copy.deepcopy(best)
    if "add_section" in change:
        cfg["sections"] = cfg["sections"] + [change["add_section"]]
    if "add_tool" in change:
        cfg["tools"] = sorted(set(cfg.get("tools", [])) | {change["add_tool"]})
    if "set" in change:
        cfg.update(change["set"])
    if "paste_dev_failures" in change:  # the anti-pattern, kept so you can watch it fail
        shots = dev_failures[: change["paste_dev_failures"]]
        lines = ["## Examples"] + [f"{f['text']}\nteam: {f['label']}" for f in shots]
        cfg["extra_prompt"] = (cfg.get("extra_prompt", "") + "\n\n" + "\n\n".join(lines)).strip()
    return cfg


def leaked_items(cfg: dict[str, Any], items: list[dict]) -> list[str]:
    system = build_system(cfg)
    return [it["id"] for it in items if it["text"] in system]


def decide(d_dev: Estimate, d_test: Estimate, cost_ratio: float, rules: Rules) -> tuple[str, str]:
    """keep / revert, with the reason that goes in the log."""
    if d_dev.hi < 0:
        return "revert", "dev regression (CI below 0)"
    if d_dev.lo <= 0:
        return "revert", "dev change within noise (CI spans 0); simpler config wins ties"
    if d_test.hi < 0:
        return "revert", "dev up but test significantly DOWN: overfit to dev"
    if d_test.mean <= 0 or d_test.mean < rules.test_ratio * d_dev.mean:
        return "revert", "dev up but test flat: overfit to dev"
    if rules.require_test_significant and d_test.lo <= 0:
        return "revert", "test gain not significant"
    if rules.max_cost_ratio and cost_ratio > rules.max_cost_ratio:
        return "revert", f"cost x{cost_ratio:.1f} exceeds budget x{rules.max_cost_ratio}"
    sig = "significant" if d_test.lo > 0 else "directional"
    return "keep", f"dev up (significant), test up ({sig})"


class Climb:
    def __init__(self, spec: dict[str, Any], client_factory: ClientFactory = sim_factory):
        self.spec = spec
        self.factory = client_factory
        self.repeats = spec.get("repeats", 3)
        self.seed = spec.get("seed", 0)
        self.rules = Rules(**spec.get("rules", {}))
        self.data = Path(spec.get("dataset") or DATA)
        self.dev, self.test = load_split("dev", self.data), load_split("test", self.data)
        if client_factory is sim_factory and spec.get("dataset"):
            self.factory = sim_factory_for(self.dev + self.test)
        self.fp = self._fingerprint()
        self.trials: list[Trial] = []
        self.best_cfg = dict(spec["baseline"])
        self._seed_i = 0
        self.best_dev = self._eval(self.best_cfg, self.dev, "dev")
        self.best_test = self._eval(self.best_cfg, self.test, "test")
        self.base_dev, self.base_test = self.best_dev, self.best_test
        self.trials.append(Trial(0, self.best_cfg["name"], "baseline", spec.get("baseline_note", ""),
                                 self.best_dev, self.best_test, None, None, None, "baseline", "starting point"))

    def _eval(self, cfg: dict[str, Any], items: list[dict], split: str) -> RunResult:
        self._seed_i += 1  # fresh seeds per evaluation: no common random numbers
        return evaluate(cfg, items, self.repeats, self.seed + 7919 * self._seed_i, self.factory, split)

    def _fingerprint(self) -> str:
        return fingerprint([Path(__file__).with_name("router_eval.py"), self.data])

    def _check_frozen(self) -> None:
        if self._fingerprint() != self.fp:
            raise RuntimeError("evaluator or dataset changed during the climb; results are void")

    def try_variant(self, rnd: int, v: dict[str, Any]) -> tuple[Trial, dict[str, Any]]:
        self._check_frozen()
        cfg = apply_change(self.best_cfg, v["change"], self.best_dev.failures(self.dev))
        cfg["name"] = v["name"]
        leaks = leaked_items(cfg, self.dev + self.test)
        change = json.dumps(v["change"])
        if leaks and self.rules.block_leaks:
            empty = RunResult(v["name"], "-", [], [], [], [])
            return Trial(rnd, v["name"], change, v.get("hypothesis", ""), empty, empty, None, None, None,
                         "blocked", f"config contains {len(leaks)} eval items verbatim"), cfg
        dev, test = self._eval(cfg, self.dev, "dev"), self._eval(cfg, self.test, "test")
        d_dev = paired_diff(self.best_dev.item_scores, dev.item_scores, dev.clusters)
        d_test = paired_diff(self.best_test.item_scores, test.item_scores, test.clusters)
        _, _, p_boot = paired_bootstrap(self.best_dev.item_scores, dev.item_scores, dev.clusters, n_boot=1000)
        cost_ratio = dev.cost_per_item / max(self.best_dev.cost_per_item, 1e-12)
        decision, reason = decide(d_dev, d_test, cost_ratio, self.rules)
        if leaks:
            reason += f"; WARNING {len(leaks)} eval items pasted into prompt"
        return Trial(rnd, v["name"], change, v.get("hypothesis", ""), dev, test, d_dev, d_test, p_boot,
                     decision, reason), cfg

    def run(self) -> None:
        for rnd, v in enumerate(self.spec["rounds"], start=1):
            group = v["sweep"] if "sweep" in v else [v]
            results = [self.try_variant(rnd, x) for x in group]
            keeps = [(t, c) for t, c in results if t.decision == "keep"]
            winner = max(keeps, key=lambda tc: tc[0].d_dev.mean, default=None)
            for t, c in results:
                if winner and t is not winner[0] and t.decision == "keep":
                    t.decision, t.reason = "revert", "passed rules but lost the sweep to " + winner[0].name
                self.trials.append(t)
            if winner:
                t, c = winner
                self.best_cfg, self.best_dev, self.best_test = c, t.dev, t.test

    def summary(self) -> dict[str, Any]:
        d = paired_diff(self.base_test.item_scores, self.best_test.item_scores, self.best_test.clusters)
        return {"best": self.best_cfg["name"],
                "baseline_test": clustered_se(self.base_test.item_scores, self.base_test.clusters),
                "best_test": clustered_se(self.best_test.item_scores, self.best_test.clusters),
                "gain_test": d}


def _row(t: Trial) -> str:
    if t.decision == "blocked":
        return f"| {t.round} | {t.name} | `{t.change}` | - | - | - | - | - | **blocked** | {t.reason} |"
    dev = clustered_se(t.dev.item_scores, t.dev.clusters)
    test = clustered_se(t.test.item_scores, t.test.clusters)
    dd = t.d_dev.fmt() if t.d_dev else "-"
    dt = t.d_test.fmt() if t.d_test else "-"
    cost = f"{1000 * t.dev.cost_per_item:.2f}"
    return (f"| {t.round} | {t.name} | `{t.change}` | {100 * dev.mean:.1f} | {dd} | {100 * test.mean:.1f} | {dt} "
            f"| {cost} | **{t.decision}** | {t.reason} |")


def write_log(climb: Climb, out: Path, noise_md: str = "") -> Path:
    out.mkdir(parents=True, exist_ok=True)
    s = climb.summary()
    lines = [
        "# Experiment log: incident-router hill-climb", "",
        f"- evaluator fingerprint: `{climb.fp}` (grader + dataset, checked every round)",
        f"- dev: {len(climb.dev)} alerts in {len({i['cluster'] for i in climb.dev})} incidents; "
        f"test: {len(climb.test)} alerts in {len({i['cluster'] for i in climb.test})} incidents",
        f"- repeats per variant: {climb.repeats}; base seed {climb.seed}; fresh seeds per evaluation",
        "- deltas are paired against the CURRENT BEST, with incident-clustered 95% CIs, in points",
        "- cost column is $ per 1k alerts at the list prices in incident_router.py (simulated token counts)", "", noise_md,
        "## Rounds", "",
        "| # | variant | change | dev % | Δdev [95% CI] | test % | Δtest [95% CI] | $/1k | decision | reason |",
        "|---|---|---|---|---|---|---|---|---|---|",
        *[_row(t) for t in climb.trials], "",
        "## Hypotheses and error analysis", "",
    ]
    for t in climb.trials[1:]:
        lines.append(f"- **{t.name}**: {t.hypothesis}")
    lines += ["", "Dev accuracy by failure family for the final best config:", ""]
    lines += [f"- {k}: {100 * v:.0f}%" for k, v in by_tag(climb.best_dev, climb.dev).items()]
    lines += ["", "## Result", "",
              f"- best config: `{s['best']}`",
              f"- test accuracy: baseline {s['baseline_test'].fmt()} -> best {s['best_test'].fmt()}",
              f"- paired test gain: {s['gain_test'].fmt()} points (incident-clustered)",
              f"- verdict: {'ship it' if s['gain_test'].lo > 0 else 'gain within noise: do not merge'}", ""]
    path = out / "experiments.md"
    path.write_text("\n".join(lines))
    (out / "best_config.json").write_text(json.dumps(climb.best_cfg, indent=2) + "\n")
    tsv = ["round\tname\tdev_acc\ttest_acc\td_dev\td_test\tcost_per_1k\tdecision"]
    for t in climb.trials:
        if t.decision != "blocked":
            tsv.append(f"{t.round}\t{t.name}\t{t.dev.accuracy:.4f}\t{t.test.accuracy:.4f}\t"
                       f"{t.d_dev.mean if t.d_dev else 0:.4f}\t{t.d_test.mean if t.d_test else 0:.4f}\t"
                       f"{1000 * t.dev.cost_per_item:.3f}\t{t.decision}")
    (out / "results.tsv").write_text("\n".join(tsv) + "\n")
    return path


def main() -> None:
    from ainative_kit import get_client

    ap = argparse.ArgumentParser(description="Run a hill-climb from a variants file")
    ap.add_argument("variants")
    ap.add_argument("--out", default="runs/latest")
    ap.add_argument("--skip-noise-check", action="store_true")
    args = ap.parse_args()
    spec = load_variants(args.variants)
    factory = sim_factory
    try:  # real API when a key is set; the simulated model otherwise
        real = get_client(fake=None)
        factory = lambda cfg, seed: real  # noqa: E731
    except RuntimeError:
        pass
    noise_md = ""
    if not args.skip_noise_check:
        dev = load_split("dev", spec.get("dataset"))
        if factory is sim_factory and spec.get("dataset"):
            factory = sim_factory_for(load_split("all", spec["dataset"]))
        rep = run_noise_check(spec["baseline"], dev, runs=6, planned_repeats=spec.get("repeats", 3),
                              min_effect=spec.get("min_effect", 0.05), client_factory=factory)
        noise_md = rep.to_markdown()
        print(noise_md)
        if not rep.ok and not spec.get("proceed_if_noisy", False):
            raise SystemExit("noise check failed; raise `repeats` in the variants file and re-run")
    climb = Climb(spec, factory)
    climb.run()
    path = write_log(climb, Path(args.out), noise_md)
    print(path.read_text())


if __name__ == "__main__":
    main()
