"""CI eval gate: run the eval, then pass/fail against thresholds that use CIs.

    python ci_gate.py run   --config data/climbed_config.json --split test --repeats 3 --out results.json
    python ci_gate.py check --results results.json --baseline ci/baseline_results.json \
                            --floor 0.85 --max-drop 0.02 --max-cost-ratio 1.5

`check` fails (exit 1) when any of these hold:
  1. the evaluator fingerprint differs from the baseline's (re-baseline first),
  2. the LOWER 95% bound of accuracy is under --floor (not the point estimate),
  3. the paired difference vs baseline is a significant regression (CI upper < 0)
     or its point estimate drops more than --max-drop,
  4. cost per item exceeds --max-cost-ratio x baseline.
It writes a markdown summary to $GITHUB_STEP_SUMMARY when that is set.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from router_eval import evaluate, fingerprint, load_split, sim_factory
from stats import clustered_se, paired_diff


def make_factory(kind: str):
    """sim (offline simulated model), replay:<cassette.jsonl>, or real (needs ANTHROPIC_API_KEY)."""
    if kind == "sim":
        return sim_factory
    if kind.startswith("replay:"):
        from ainative_kit import ReplayClient

        client = ReplayClient(kind.split(":", 1)[1])
        return lambda cfg, seed: client
    if kind == "real":
        from ainative_kit import AnthropicClient

        client = AnthropicClient()
        return lambda cfg, seed: client
    raise ValueError(f"unknown client kind {kind!r}")


def run(config: dict[str, Any], split: str, repeats: int, seed: int, client: str = "sim") -> dict[str, Any]:
    items = load_split(split)
    r = evaluate(config, items, repeats, seed, make_factory(client), split)
    return {"config": config, "fingerprint": fingerprint(), "split": split, "repeats": repeats,
            "client": client, "ids": r.ids, "clusters": r.clusters, "item_scores": r.item_scores,
            "accuracy": r.accuracy, "cost_per_item": r.cost_per_item, "truncated": r.truncated}


def check(cand: dict[str, Any], base: dict[str, Any] | None, floor: float, max_drop: float,
          max_cost_ratio: float | None) -> tuple[bool, list[tuple[str, bool, str]]]:
    """Return (passed, [(check, ok, detail)])."""
    out: list[tuple[str, bool, str]] = []
    acc = clustered_se(cand["item_scores"], cand["clusters"])
    out.append(("accuracy floor (lower 95% bound)", acc.lo >= floor,
                f"{acc.fmt()} vs floor {100 * floor:.1f}"))
    if base is not None:
        same = base["fingerprint"] == cand["fingerprint"] and base["ids"] == cand["ids"]
        out.append(("same frozen evaluator as baseline", same,
                    f"{cand['fingerprint']} vs {base['fingerprint']}" + ("" if same else ": re-baseline first")))
        if same:
            d = paired_diff(base["item_scores"], cand["item_scores"], cand["clusters"])
            ok = d.hi >= 0 and d.mean >= -max_drop
            out.append(("no regression vs baseline (paired, clustered)", ok,
                        f"{d.fmt()} pts; fail if CI < 0 or drop > {100 * max_drop:.1f}"))
        if max_cost_ratio:
            ratio = cand["cost_per_item"] / max(base["cost_per_item"], 1e-12)
            out.append(("cost per item", ratio <= max_cost_ratio, f"x{ratio:.2f} vs limit x{max_cost_ratio}"))
    return all(ok for _, ok, _ in out), out


def summary_md(passed: bool, rows: list[tuple[str, bool, str]], cand: dict[str, Any]) -> str:
    lines = [f"## Eval gate: {'PASS' if passed else 'FAIL'}", "",
             f"config `{cand['config'].get('name')}` on `{cand['split']}` x{cand['repeats']} ({cand['client']})", "",
             "| check | result | detail |", "|---|---|---|"]
    lines += [f"| {name} | {'pass' if ok else '**FAIL**'} | {detail} |" for name, ok, detail in rows]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="eval gate")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--config", required=True)
    r.add_argument("--split", default="test")
    r.add_argument("--repeats", type=int, default=3)
    r.add_argument("--seed", type=int, default=0)
    r.add_argument("--client", default="sim", help="sim | real | replay:<cassette>")
    r.add_argument("--out", required=True)
    c = sub.add_parser("check")
    c.add_argument("--results", required=True)
    c.add_argument("--baseline")
    c.add_argument("--floor", type=float, default=0.85)
    c.add_argument("--max-drop", type=float, default=0.02)
    c.add_argument("--max-cost-ratio", type=float)
    a = ap.parse_args(argv)
    if a.cmd == "run":
        res = run(json.loads(Path(a.config).read_text()), a.split, a.repeats, a.seed, a.client)
        Path(a.out).write_text(json.dumps(res) + "\n")
        print(f"accuracy {100 * res['accuracy']:.1f}% on {len(res['ids'])} items -> {a.out}")
        return 0
    cand = json.loads(Path(a.results).read_text())
    base = json.loads(Path(a.baseline).read_text()) if a.baseline else None
    passed, rows = check(cand, base, a.floor, a.max_drop, a.max_cost_ratio)
    md = summary_md(passed, rows, cand)
    print(md)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
            f.write(md)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
