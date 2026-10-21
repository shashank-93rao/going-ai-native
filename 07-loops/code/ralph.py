"""A fresh-context Ralph loop driver: one fix_plan item per iteration, the oracle as backpressure.

Each iteration starts a NEW agent process with the SAME prompt (PROMPT.md). Nothing carries
over in context: state lives on disk (specs/, fix_plan.md, git history, .ralph/log.jsonl).
The harness, not the agent, decides what was kept:

    measure -> run agent (fresh context) -> measure -> accept (commit) or reject (revert) -> governor

Done requires two independent signals to agree: every fix_plan item ticked (agent-writable)
AND the oracle passing (agent-unwritable). A tick without a green oracle is logged as a
premature completion claim, reverted, and the loop continues.

    python ralph.py --workspace ./ws --agent-cmd "claude -p --dangerously-skip-permissions --max-turns 40" \\
        --oracle-cmd "python -m pytest -q spec_tokenbucket.py" --max-iterations 20

Only run an agent with skipped permissions inside a container or disposable VM.
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from governor import ExitCode, Governor, GovernorTripped, Limits
from oracle import CommandOracle, OracleResult, PytestOracle

STATE_DIR = ".ralph"
_ITEM = re.compile(r"^- \[( |x)\] (\S+)", re.M)

# An agent is either a shell command (prompt on stdin, cwd = workspace) or a Python callable.
Agent = str | Callable[[str, Path], int]


@dataclass
class RalphResult:
    exit_code: ExitCode
    reason: str
    iterations: int
    log: list[dict]


def plan_items(workspace: Path) -> tuple[list[str], list[str]]:
    """(open, done) item ids from fix_plan.md checkboxes."""
    text = (workspace / "fix_plan.md").read_text()
    open_, done = [], []
    for mark, item in _ITEM.findall(text):
        (done if mark == "x" else open_).append(item)
    return open_, done


def _git(workspace: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-c", "user.name=ralph", "-c", "user.email=ralph@localhost", *args],
                          cwd=workspace, capture_output=True, text=True)


def _has_git(workspace: Path) -> bool:
    return (workspace / ".git").exists()


def _run_agent(agent: Agent, prompt: str, workspace: Path, log_path: Path, timeout_s: float) -> int:
    if callable(agent):
        return agent(prompt, workspace)
    with log_path.open("w") as log:
        try:
            proc = subprocess.run(shlex.split(agent), input=prompt, cwd=workspace, stdout=log,
                                  stderr=subprocess.STDOUT, text=True, timeout=timeout_s)
            return proc.returncode
        except subprocess.TimeoutExpired:
            log.write(f"\n[ralph] agent timed out after {timeout_s}s\n")
            return 124


def progress_key(r: OracleResult) -> float:
    """What counts as progress: the oracle score only. Ticks in fix_plan.md are agent-writable,
    so closing items without moving the oracle is not progress (Kinney: kept AND improved)."""
    return r.score


def run_ralph(
    workspace: str | Path,
    agent: Agent,
    oracle,
    limits: Limits | None = None,
    prompt_file: str = "PROMPT.md",
    agent_timeout_s: float = 1800,
    clock: Callable[[], float] = time.monotonic,
) -> RalphResult:
    ws = Path(workspace).resolve()
    state = ws / STATE_DIR
    (state / "logs").mkdir(parents=True, exist_ok=True)
    limits = limits or Limits(max_iterations=20, max_cost_usd=None, max_input_tokens=None,
                              max_output_tokens=None, stall_patience=3)
    if limits.stop_file is None:
        limits.stop_file = state / "STOP"
    gov = Governor(limits, clock=clock)
    log: list[dict] = []
    git = _has_git(ws)
    if git:
        (ws / ".gitignore").write_text(f"{STATE_DIR}/\n__pycache__/\n")
        _git(ws, "add", "-A")
        _git(ws, "commit", "-q", "-m", "ralph: baseline", "--allow-empty")

    baseline = oracle.run(ws)
    if baseline.broken:  # fail closed: never loop against a broken oracle
        return RalphResult(ExitCode.BROKEN, f"oracle broken before first iteration:\n{baseline.output[-500:]}", 0, log)
    best = progress_key(baseline)
    gov.record_metric(best)

    def finish(code: ExitCode, reason: str) -> RalphResult:
        return RalphResult(code, reason, gov.iterations, log)

    try:
        while True:
            open_items, _ = plan_items(ws)
            if not open_items and oracle.run(ws).ok:
                return finish(ExitCode.SUCCESS, "plan empty and oracle green")
            gov.tick()
            i = gov.iterations
            prompt = (ws / prompt_file).read_text()  # same prompt every time; re-read so edits apply
            t0 = clock()
            rc = _run_agent(agent, prompt, ws, state / "logs" / f"iter_{i:03d}.log", agent_timeout_s)
            gov.record_outcome(rc == 0)

            if (state / "BLOCKED").exists():
                return finish(ExitCode.BLOCKED, (state / "BLOCKED").read_text().strip()[:300])

            r = oracle.run(ws)
            if r.broken:
                return finish(ExitCode.BROKEN, f"oracle broke at iteration {i}:\n{r.output[-500:]}")
            open_after, _ = plan_items(ws)
            key = progress_key(r)
            entry = {"iter": i, "agent_rc": rc, "score": round(r.score, 3), "failed": r.failed,
                     "open": len(open_after), "secs": round(clock() - t0, 2)}

            premature = not open_after and not r.ok  # agent ticked everything; the oracle disagrees
            if premature:
                entry["premature_claim"] = True
            if key < best or premature:  # backpressure: regressions and false claims are not committed
                entry["decision"] = "reverted" if git else "rejected (no git to revert)"
                if git:
                    _git(ws, "checkout", "--", ".")
                    _git(ws, "clean", "-fdq", "-e", STATE_DIR)
            else:
                entry["decision"] = "kept"
                if git:
                    _git(ws, "add", "-A")
                    _git(ws, "commit", "-q", "-m", f"ralph: iter {i} score={r.score:.3f}")
                best = max(best, key)
            log.append(entry)
            with (state / "log.jsonl").open("a") as f:
                f.write(json.dumps(entry) + "\n")
            gov.record_metric(key if entry["decision"] == "kept" else best)
            gov.check()
    except GovernorTripped as t:
        return finish(t.code, t.reason)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--workspace", default=".")
    ap.add_argument("--agent-cmd", required=True, help="prompt is piped to stdin; cwd is the workspace")
    ap.add_argument("--oracle-cmd", required=True, help="e.g. 'python -m pytest -q spec_x.py' or 'make check'")
    ap.add_argument("--max-iterations", type=int, default=20)
    ap.add_argument("--max-hours", type=float, default=8.0)
    ap.add_argument("--stall-patience", type=int, default=3)
    ap.add_argument("--agent-timeout-min", type=float, default=30)
    a = ap.parse_args(argv)
    parts = shlex.split(a.oracle_cmd)
    if "pytest" in parts:  # parse counts for a graded score; otherwise exit code only
        files = [p for p in parts if p.endswith(".py")]
        oracle = PytestOracle(files)
    else:
        oracle = CommandOracle(a.oracle_cmd)
    limits = Limits(max_iterations=a.max_iterations, max_wall_seconds=a.max_hours * 3600, max_cost_usd=None,
                    max_input_tokens=None, max_output_tokens=None, stall_patience=a.stall_patience)
    res = run_ralph(a.workspace, a.agent_cmd, oracle, limits, agent_timeout_s=a.agent_timeout_min * 60)
    for e in res.log:
        print(json.dumps(e))
    print(f"[ralph] exit={res.exit_code.name}({int(res.exit_code)}) after {res.iterations} iterations: {res.reason}")
    return int(res.exit_code)


if __name__ == "__main__":
    sys.exit(main())
