"""Eval harness: dataset JSONL -> run system (n trials per case) -> graders -> results JSONL + summary.

    python eval_harness.py                       # router suite, fake model, 5 trials
    python eval_harness.py --trials 8 --k 1 3 5 --split test --traces traces.jsonl

The harness is generic: `run_suite(cases, run_fn, grade_fn, trials)` works for the
single-turn router and for the coding agent (see coding_task.py). The summary
reports pass rate, pass@k, pass^k, the correct/abstain/wrong split with an
abstention-aware score, and the same numbers per slice and per split.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from math import comb
from pathlib import Path
from typing import Any, Callable, Iterable

from ainative_kit import Tracer, get_client

from graders import grade_router
from ticket_router import fake_router_client, route_alert

HERE = Path(__file__).parent
RunFn = Callable[[dict[str, Any], int], dict[str, Any]]
GradeFn = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def write_jsonl(path: str | Path, rows: Iterable[dict[str, Any]]) -> None:
    with Path(path).open("w") as f:
        for r in rows:
            f.write(json.dumps(r, default=str) + "\n")


def run_suite(cases: list[dict[str, Any]], run_fn: RunFn, grade_fn: GradeFn, trials: int = 1,
              tracer: Tracer | None = None) -> list[dict[str, Any]]:
    """Run every case `trials` times. One record per (case, trial). Exceptions are graded as failures."""
    tracer = tracer or Tracer()
    records = []
    for case in cases:
        for t in range(trials):
            with tracer.span("eval_trial", case_id=case["id"], trial=t, slice=case.get("slice")) as span:
                start = time.perf_counter()
                try:
                    result = run_fn(case, t)
                    graded = grade_fn(case, result)
                except Exception as e:  # a crash is a failed trial, not a crashed eval
                    result = {"error": f"{type(e).__name__}: {e}"}
                    graded = {"grades": [], "passed": False, "outcome": "wrong"}
                span.attrs.update(passed=graded["passed"], outcome=graded["outcome"])
            records.append({
                "case_id": case["id"], "trial": t, "slice": case.get("slice", "all"),
                "split": case.get("split", "all"), "passed": graded["passed"],
                "outcome": graded["outcome"], "grades": graded["grades"],
                "output": result.get("parsed", result.get("final_text")),
                "error": result.get("error") or result.get("parse_error"),
                "prompt_hash": result.get("prompt_hash"), "trace_id": span.trace_id,
                "latency_s": round(time.perf_counter() - start, 4),
            })
    return records


def pass_at_k(n: int, c: int, k: int) -> float:
    """Unbiased estimate of P(at least one of k trials passes), from n trials with c passes."""
    if k > n:
        raise ValueError(f"need n >= k trials (n={n}, k={k})")
    return 1.0 - comb(n - c, k) / comb(n, k)


def pass_hat_k(n: int, c: int, k: int) -> float:
    """Unbiased estimate of P(all k trials pass) (tau-bench's pass^k), from n trials with c passes."""
    if k > n:
        raise ValueError(f"need n >= k trials (n={n}, k={k})")
    return comb(c, k) / comb(n, k)


def _metrics(records: list[dict[str, Any]], ks: tuple[int, ...], penalty: float) -> dict[str, Any]:
    by_case: dict[str, list[bool]] = defaultdict(list)
    for r in records:
        by_case[r["case_id"]].append(r["passed"])
    out: dict[str, Any] = {
        "cases": len(by_case), "trials": len(records),
        "pass_rate": round(sum(r["passed"] for r in records) / max(len(records), 1), 4),
    }
    for k in ks:
        usable = [v for v in by_case.values() if len(v) >= k]
        if usable:
            out[f"pass@{k}"] = round(sum(pass_at_k(len(v), sum(v), k) for v in usable) / len(usable), 4)
            out[f"pass^{k}"] = round(sum(pass_hat_k(len(v), sum(v), k) for v in usable) / len(usable), 4)
    oc = Counter(r["outcome"] for r in records)
    n = max(len(records), 1)
    out.update(correct=round(oc["correct"] / n, 4), abstain=round(oc["abstain"] / n, 4),
               wrong=round(oc["wrong"] / n, 4))
    out["abstention_aware_score"] = round((oc["correct"] - penalty * oc["wrong"]) / n, 4)
    return out


def summarize(records: list[dict[str, Any]], ks: tuple[int, ...] = (1, 3),
              penalty: float = 3.0) -> dict[str, Any]:
    """Overall, per-slice and per-split metrics, plus which gating graders fail most."""
    summary: dict[str, Any] = {"overall": _metrics(records, ks, penalty), "penalty": penalty}
    for key in ("slice", "split"):
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for r in records:
            groups[r[key]].append(r)
        summary[f"by_{key}"] = {g: _metrics(rs, ks, penalty) for g, rs in sorted(groups.items())}
    fails = Counter(g["name"] for r in records for g in r["grades"] if g["gating"] and not g["passed"])
    summary["failing_graders"] = dict(fails.most_common())
    hashes = {r["prompt_hash"] for r in records if r.get("prompt_hash")}
    summary["prompt_hashes"] = sorted(hashes)
    return summary


def format_summary(summary: dict[str, Any], ks: tuple[int, ...] = (1, 3)) -> str:
    cols = ["cases", "pass_rate"] + [f"{m}{k}" for k in ks for m in ("pass@", "pass^")] + \
           ["correct", "abstain", "wrong", "abstention_aware_score"]
    head = f"{'group':<28}" + "".join(f"{c.replace('abstention_aware_score', 'aa_score'):>10}" for c in cols)
    lines = [head, "-" * len(head)]

    def row(name: str, m: dict[str, Any]) -> str:
        return f"{name:<28}" + "".join(f"{m.get(c, ''):>10}" for c in cols)

    lines.append(row("OVERALL", summary["overall"]))
    for key in ("split", "slice"):
        for g, m in summary[f"by_{key}"].items():
            lines.append(row(f"{key}={g}", m))
    lines.append(f"\nfailing gating graders (trial count): {summary['failing_graders']}")
    lines.append(f"prompt hashes: {summary['prompt_hashes']}   wrong-answer penalty: {summary['penalty']}")
    return "\n".join(lines)


def router_run_fn(model: str | None = None, tracer: Tracer | None = None, cautious: bool = False) -> RunFn:
    """Real API if ANTHROPIC_API_KEY is set (and AINATIVE_FAKE is not), else the flawed fake."""
    def run(case: dict[str, Any], trial: int) -> dict[str, Any]:
        client = get_client(fake=fake_router_client(trial, cautious))
        return route_alert(client, case["input"], tracer=tracer, model=model, case_id=case["id"])
    return run


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", default=str(HERE / "data" / "router_cases.jsonl"))
    ap.add_argument("--trials", type=int, default=5)
    ap.add_argument("--k", type=int, nargs="+", default=[1, 3])
    ap.add_argument("--split", choices=["dev", "test", "all"], default="all")
    ap.add_argument("--penalty", type=float, default=3.0, help="points lost per wrong answer (t/(1-t))")
    ap.add_argument("--out", default="results.jsonl")
    ap.add_argument("--traces", default=None, help="write ainative_kit spans here for error_analysis.py")
    ap.add_argument("--model", default=None)
    ap.add_argument("--cautious", action="store_true", help="fake only: the variant that abstains on ambiguity")
    args = ap.parse_args(argv)

    cases = load_jsonl(args.dataset)
    if args.split != "all":
        cases = [c for c in cases if c.get("split") == args.split]
    if args.traces:
        Path(args.traces).unlink(missing_ok=True)
    tracer = Tracer(args.traces)
    ks = tuple(k for k in args.k if k <= args.trials)
    records = run_suite(cases, router_run_fn(args.model, tracer, args.cautious), grade_router, args.trials, tracer)
    write_jsonl(args.out, records)
    summary = summarize(records, ks, args.penalty)
    print(format_summary(summary, ks))
    Path(args.out).with_suffix(".summary.json").write_text(json.dumps(summary, indent=2))
    print(f"\nwrote {len(records)} trial records to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
