"""Noise check: run the baseline N times BEFORE round 1 and ask whether the eval
can see the smallest change you would act on.

Rule (from Anthropic's hillclimb workflow): the eval's noise must be smaller
than the smallest improvement you'd act on. If not, add repeats or items
before you change anything, or every "win" in your log is a coin flip.

    python noise_check.py --runs 6 --min-effect 0.05
"""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from typing import Any, Callable

from router_eval import ClientFactory, evaluate, load_split, sim_factory
from stats import clustered_se, mean_se, min_detectable_effect, paired_diff


@dataclass
class NoiseReport:
    runs: int
    n_items: int
    run_means: list[float]
    run_sd: float                 # SD of the run-level accuracy across runs
    flip_rate: float              # share of items whose verdict changed across runs
    naive_se: float               # SE of one run, treating items as independent
    clustered_se: float           # SE of one run, clustered by incident
    null_diff: float              # paired diff between two halves of the SAME config
    null_se_planned: float        # SE of a paired diff at the planned repeats
    mde_planned: float            # minimum detectable effect, 80% power, alpha .05
    min_effect: float
    planned_repeats: int

    @property
    def ok(self) -> bool:
        return self.mde_planned <= self.min_effect

    def repeats_needed(self) -> int:
        """Repeats per variant that bring the MDE under min_effect (within-item noise only)."""
        if self.ok:
            return self.planned_repeats
        return math.ceil(self.planned_repeats * (self.mde_planned / self.min_effect) ** 2)

    def to_markdown(self) -> str:
        verdict = ("OK: the eval can resolve the smallest effect you'd act on." if self.ok else
                   f"TOO NOISY: raise repeats to ~{self.repeats_needed()} or add items/clusters before round 1.")
        pct = lambda x: f"{100 * x:.1f}"  # noqa: E731
        return "\n".join([
            "## Noise check (baseline, before round 1)",
            "",
            "| metric | value |", "|---|---|",
            f"| runs x items | {self.runs} x {self.n_items} |",
            f"| run accuracies | {', '.join(pct(m) for m in self.run_means)} |",
            f"| SD of run accuracy | {pct(self.run_sd)} pts |",
            f"| items that flipped across runs | {pct(self.flip_rate)}% |",
            f"| SE of one run: naive / clustered | {pct(self.naive_se)} / {pct(self.clustered_se)} pts |",
            f"| null paired diff (same config, two halves) | {pct(self.null_diff)} pts |",
            f"| paired SE at {self.planned_repeats} repeats | {pct(self.null_se_planned)} pts |",
            f"| minimum detectable effect (80% power) | {pct(self.mde_planned)} pts |",
            f"| smallest effect you'd act on | {pct(self.min_effect)} pts |",
            "", f"**Verdict:** {verdict}", "",
        ])


def run_noise_check(config: dict[str, Any], items: list[dict], runs: int = 6, planned_repeats: int = 3,
                    min_effect: float = 0.05, seed: int = 7, client_factory: ClientFactory = sim_factory) -> NoiseReport:
    if runs < 2 or runs % 2:
        raise ValueError("use an even number of runs >= 2 (they are split into two halves)")
    res = evaluate(config, items, repeats=runs, seed=seed, client_factory=client_factory, split="noise")
    run_means = res.run_means
    sd = mean_se(run_means).se * math.sqrt(runs)  # SD = SE * sqrt(n)
    n = len(items)
    flips = sum(1 for i in range(n) if len({rep[i] for rep in res.per_repeat}) > 1) / n
    one_run = [float(x) for x in res.per_repeat[0]]
    half = runs // 2
    a = [sum(rep[i] for rep in res.per_repeat[:half]) / half for i in range(n)]
    b = [sum(rep[i] for rep in res.per_repeat[half:]) / half for i in range(n)]
    null = paired_diff(a, b, res.clusters)
    # Each half averaged `half` repeats; per-item noise variance scales as 1/repeats.
    se_planned = null.se * math.sqrt(half / planned_repeats)
    return NoiseReport(
        runs=runs, n_items=n, run_means=run_means, run_sd=sd, flip_rate=flips,
        naive_se=mean_se(one_run).se, clustered_se=clustered_se(one_run, res.clusters).se,
        null_diff=null.mean, null_se_planned=se_planned, mde_planned=min_detectable_effect(se_planned),
        min_effect=min_effect, planned_repeats=planned_repeats,
    )


def grader_flip_rate(grade: Callable[[Any, Any], Any], pairs: list[tuple[Any, Any]]) -> float:
    """Grade each (output, reference) twice; return the share of verdicts that changed.

    Exact-match graders score 0. An LLM judge that flips more than a few percent
    is adding noise you will mistake for signal (see Module 11).
    """
    if not pairs:
        return 0.0
    return sum(1 for o, ref in pairs if grade(o, ref) != grade(o, ref)) / len(pairs)


def main() -> None:
    import json

    from incident_router import DEFAULT_CONFIG

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", help="JSON config file; defaults to the baseline")
    ap.add_argument("--split", default="dev")
    ap.add_argument("--runs", type=int, default=6)
    ap.add_argument("--repeats", type=int, default=3, help="repeats you plan to use per variant")
    ap.add_argument("--min-effect", type=float, default=0.05)
    args = ap.parse_args()
    cfg = json.loads(open(args.config).read()) if args.config else DEFAULT_CONFIG
    rep = run_noise_check(cfg, load_split(args.split), args.runs, args.repeats, args.min_effect)
    print(rep.to_markdown())


if __name__ == "__main__":
    main()
