#!/usr/bin/env python3
"""Autonomy-rate eval: run an agent on each seeded task in a fresh copy, grade with hidden tests.

    python autonomy_eval.py --agent "{python} {here}/fake_agent.py --policy harness-aware {workdir} {prompt}"
    python autonomy_eval.py --agent "..." --ablate diagnose,invariants --trials 3 --json out.json

Placeholders: `{workdir}` is the repo copy (the agent's cwd), `{prompt}` a file outside it,
`{python}` this interpreter, `{here}` this directory. Run real agents in a sandbox that
cannot read tasks/ (hidden tests and reference fixes live there).
A task succeeds only if, after the agent exits:
  1. the hidden tests pass (the agent never saw them),
  2. the ORIGINAL visible tests pass (restored over whatever the agent left), and
  3. the ORIGINAL invariant lint passes (run from this checkout, not the agent's copy).
Graders live outside the agent's reach, so editing tests or the lint cannot buy a pass.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path

from task_suite import ABLATIONS, HERE, PROTECTED, SERVICE, Task, build_workspace, load_tasks


@dataclass
class TrialResult:
    task_id: str
    kind: str
    trial: int
    success: bool
    hidden_ok: bool
    visible_ok: bool
    lint_ok: bool
    tampered: list[str] = field(default_factory=list)
    agent_rc: int | None = None
    timed_out: bool = False
    seconds: float = 0.0
    detail: str = ""


def wilson(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval. Better than the normal approximation at small n or extreme p."""
    if n == 0:
        return (0.0, 1.0)
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def _pytest(repo: Path, target: str) -> tuple[bool, str]:
    p = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", target],
                       cwd=repo, capture_output=True, text=True, timeout=300)
    lines = (p.stdout + p.stderr).strip().splitlines()
    return p.returncode == 0, (lines[-1] if lines else "")


def grade(task: Task, repo: Path) -> tuple[bool, bool, bool, list[str], str]:
    tampered = []
    for rel in PROTECTED:
        original, current = SERVICE / rel, repo / rel
        if not current.exists() or current.read_bytes() != original.read_bytes():
            tampered.append(rel)
        current.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(original, current)
    hidden_dir = repo / "_hidden_tests"
    hidden_dir.mkdir(exist_ok=True)
    shutil.copy(task.hidden_test, hidden_dir / "test_hidden.py")
    hidden_ok, hidden_line = _pytest(repo, "_hidden_tests")
    visible_ok, visible_line = _pytest(repo, "tests")
    lint = subprocess.run([sys.executable, str(SERVICE / "tools/lint_invariants.py"), "orders"],
                          cwd=repo, capture_output=True, text=True)
    lint_ok = lint.returncode == 0
    detail = f"hidden: {hidden_line} | visible: {visible_line} | lint: {lint.stdout.strip().splitlines()[-1]}"
    return hidden_ok, visible_ok, lint_ok, tampered, detail


def run_trial(task: Task, trial: int, agent: str, ablate: list[str], timeout: float, keep: Path | None) -> TrialResult:
    t0 = time.time()
    tmp = Path(tempfile.mkdtemp(prefix=f"autonomy-{task.id}-"))
    try:
        repo = build_workspace(task, tmp, ablate)
        cmd = agent.format(workdir=shlex.quote(str(repo)), prompt=shlex.quote(str(tmp / "PROMPT.md")),
                           python=shlex.quote(sys.executable), here=shlex.quote(str(HERE)))
        env = {**os.environ, "AUTONOMY_TASK_ID": task.id, "AUTONOMY_TRIAL": str(trial)}
        rc, timed_out = None, False
        with open(tmp / "agent.log", "w") as log:
            try:
                rc = subprocess.run(shlex.split(cmd), cwd=repo, env=env, stdout=log, stderr=subprocess.STDOUT,
                                    timeout=timeout).returncode
            except subprocess.TimeoutExpired:
                timed_out = True
        hidden_ok, visible_ok, lint_ok, tampered, detail = grade(task, repo)
        ok = hidden_ok and visible_ok and lint_ok and not timed_out
        return TrialResult(task.id, task.kind, trial, ok, hidden_ok, visible_ok, lint_ok, tampered, rc,
                           timed_out, round(time.time() - t0, 2), detail)
    finally:
        if keep:
            shutil.copytree(tmp, keep / f"{task.id}-t{trial}", dirs_exist_ok=True)
        shutil.rmtree(tmp, ignore_errors=True)


def summarize(results: list[TrialResult]) -> dict:
    def block(rs: list[TrialResult]) -> dict:
        s, n = sum(r.success for r in rs), len(rs)
        lo, hi = wilson(s, n)
        return {"successes": s, "trials": n, "rate": round(s / n, 3) if n else 0.0, "ci95": [round(lo, 3), round(hi, 3)]}
    by_task: dict[str, list[TrialResult]] = {}
    for r in results:
        by_task.setdefault(r.task_id, []).append(r)
    return {
        "overall": block(results),
        "by_kind": {k: block([r for r in results if r.kind == k]) for k in ("feature", "bug", "incident")
                    if any(r.kind == k for r in results)},
        "pass_all_trials": sum(all(r.success for r in rs) for rs in by_task.values()),
        "tasks": len(by_task),
        "tampered_tests": sorted({r.task_id for r in results if r.tampered}),
    }


def render(results: list[TrialResult], summary: dict, ablate: list[str]) -> str:
    out = [f"{'task':26} {'kind':9} {'ok':4} {'hidden':7} {'visible':8} {'lint':5} {'tamper':7} secs"]
    for r in sorted(results, key=lambda r: (r.kind, r.task_id, r.trial)):
        out.append(f"{r.task_id:26} {r.kind:9} {'PASS' if r.success else 'FAIL':4} {str(r.hidden_ok):7} "
                   f"{str(r.visible_ok):8} {str(r.lint_ok):5} {('yes' if r.tampered else '-'):7} {r.seconds}")
    o = summary["overall"]
    out.append("")
    out.append(f"harness ablated: {', '.join(ablate) or 'none'}")
    out.append(f"autonomy rate: {o['successes']}/{o['trials']} = {o['rate']:.0%}  "
               f"(95% Wilson CI {o['ci95'][0]:.0%}-{o['ci95'][1]:.0%})")
    for k, b in summary["by_kind"].items():
        out.append(f"  {k:9} {b['successes']}/{b['trials']}  CI {b['ci95'][0]:.0%}-{b['ci95'][1]:.0%}")
    out.append(f"tasks passing every trial (pass^k): {summary['pass_all_trials']}/{summary['tasks']}")
    if summary["tampered_tests"]:
        out.append(f"WARN agent modified protected tests in: {', '.join(summary['tampered_tests'])}")
    return "\n".join(out)


def evaluate(agent: str, task_ids: list[str] | None = None, ablate: list[str] | None = None, trials: int = 1,
             jobs: int = 4, timeout: float = 900, keep: Path | None = None) -> tuple[list[TrialResult], dict]:
    ablate = ablate or []
    tasks = load_tasks(only=task_ids)
    work = [(t, i) for t in tasks for i in range(trials)]
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        results = list(pool.map(lambda ti: run_trial(ti[0], ti[1], agent, ablate, timeout, keep), work))
    return results, summarize(results)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Measure the autonomy rate of an agent + harness.")
    ap.add_argument("--agent", required=True, help="command template with {workdir} {prompt} {python} {here}")
    ap.add_argument("--tasks", help="comma-separated task ids (default: all)")
    ap.add_argument("--ablate", default="", help=f"remove harness components: {','.join(ABLATIONS)} or 'all'")
    ap.add_argument("--trials", type=int, default=1)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--timeout", type=float, default=900, help="seconds per agent run")
    ap.add_argument("--keep", type=Path, help="copy each trial's workspace and agent.log here")
    ap.add_argument("--json", type=Path, help="write per-trial results and summary")
    args = ap.parse_args(argv)
    ablate = list(ABLATIONS) if args.ablate == "all" else [a for a in args.ablate.split(",") if a]
    results, summary = evaluate(args.agent, args.tasks.split(",") if args.tasks else None, ablate,
                                args.trials, args.jobs, args.timeout, args.keep)
    print(render(results, summary, ablate))
    if args.json:
        args.json.write_text(json.dumps({"ablate": ablate, "summary": summary,
                                         "results": [asdict(r) for r in results]}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
