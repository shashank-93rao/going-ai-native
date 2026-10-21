"""Fan-out driver: run a headless coding agent once per target, in parallel, then verify each.

The agent is just a shell command template, so the same driver works with
`claude -p`, `codex exec`, or a fake script in tests:

    python fanout.py --targets files.txt --concurrency 6 --retries 1 \
      --agent 'claude --bare -p "$(cat prompt.md)
Target: $FANOUT_TARGET
Verifier feedback from the last attempt (may be empty): $(cat "$FANOUT_FEEDBACK")" \
               --allowedTools "Read,Edit" --permission-mode dontAsk --output-format json' \
      --verify 'pytest -q tests/ -k {stem}' \
      --results results.jsonl

Design choices (each maps to a distributed-systems habit):
- Bounded concurrency (a worker pool), so you never hit rate limits or exhaust the box.
- The verify command decides success, never the agent's own "OK" (trust the oracle).
- Retries re-run the agent with the verifier's output in {feedback} (generate -> verify -> fix),
  capped like Stripe's "at most two CI rounds".
- A circuit breaker (--max-failures) and a canary phase (--canary N) stop a bad prompt
  from burning money across 40 targets.
- --on-success runs under a global lock: one writer for shared state such as git commits.
- --resume skips targets already "ok" in a previous results file, so re-runs are idempotent.

Placeholders available in every template: {target} {stem} {name} {dir} {feedback} {attempt}.
Values are shell-quoted before substitution, so write {target}, not '{target}'.
Inside a double-quoted prompt, use the environment variables instead:
"$FANOUT_TARGET", "$FANOUT_FEEDBACK", "$FANOUT_ATTEMPT" are set for every command.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import os
import shlex
import signal
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

TAIL = 2000  # characters of output kept per command
_PLACEHOLDER = re.compile(r"\{(target|stem|name|dir|feedback|attempt)\}")


@dataclass
class CmdResult:
    exit_code: int | None  # None means killed on timeout
    output: str
    seconds: float

    @property
    def timed_out(self) -> bool:
        return self.exit_code is None


@dataclass
class TargetResult:
    target: str
    status: str = "pending"  # ok | agent_failed | verify_failed | timeout | cancelled | skipped
    attempts: int = 0
    agent_exit: int | None = None
    verify_exit: int | None = None
    agent_seconds: float = 0.0
    verify_seconds: float = 0.0
    cost_usd: float = 0.0
    agent_claimed_ok: bool | None = None  # what the agent *said*; recorded, never trusted
    agent_tail: str = ""
    verify_tail: str = ""


@dataclass
class FanoutConfig:
    agent_cmd: str
    verify_cmd: str | None = None
    on_success_cmd: str | None = None
    concurrency: int = 4
    retries: int = 1
    agent_timeout: float = 900.0
    verify_timeout: float = 300.0
    max_failures: int | None = None
    canary: int = 0
    cwd: str | None = None
    env: dict[str, str] = field(default_factory=dict)


def render(template: str, target: str, feedback: str = "", attempt: int = 1) -> str:
    """Substitute shell-quoted placeholders into a command template."""
    p = Path(target)
    values = {
        "target": target, "stem": p.stem, "name": p.name,
        "dir": str(p.parent), "feedback": feedback, "attempt": str(attempt),
    }
    # Only known {placeholders} are replaced, so JSON in a template (e.g. --json-schema '{...}') survives.
    return _PLACEHOLDER.sub(lambda m: shlex.quote(values[m[1]]), template)


def run_cmd(cmd: str, timeout: float, cwd: str | None, env: dict[str, str]) -> CmdResult:
    """Run a shell command in its own process group; kill the whole group on timeout."""
    start = time.monotonic()
    proc = subprocess.Popen(
        cmd, shell=True, cwd=cwd, env={**os.environ, **env}, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True,
    )
    try:
        out, _ = proc.communicate(timeout=timeout)
        code: int | None = proc.returncode
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        out, _ = proc.communicate()
        code = None
    return CmdResult(code, (out or "")[-TAIL:], time.monotonic() - start)


def parse_agent_output(output: str) -> tuple[dict[str, Any] | None, bool | None]:
    """Best effort: read `claude -p --output-format json`-style JSON and an OK/FAIL claim."""
    data: dict[str, Any] | None = None
    for candidate in (output.strip(), *reversed(output.strip().splitlines())):
        try:
            parsed = json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(parsed, dict):
            data = parsed
            break
    text = str(data.get("result", "")) if data else output
    last = text.strip().splitlines()[-1].strip().upper() if text.strip() else ""
    claim = True if re.search(r"\bOK\W*$", last) else False if re.search(r"\bFAIL\W*$", last) else None
    return data, claim


class Fanout:
    """Runs the pipeline. Thread-safe bookkeeping lives behind one lock."""

    def __init__(self, cfg: FanoutConfig, results_path: str | Path | None = None):
        self.cfg = cfg
        self.results_path = Path(results_path) if results_path else None
        self._lock = threading.Lock()         # guards counters and the results file
        self._writer_lock = threading.Lock()  # serializes on_success (single writer)
        self._failures = 0
        self._tripped = False
        self._tmp = Path(tempfile.mkdtemp(prefix="fanout-"))

    # -- one target ---------------------------------------------------------
    def process(self, target: str) -> TargetResult:
        r = TargetResult(target)
        if self._tripped:
            r.status = "cancelled"
            return self._record(r)
        feedback = self._tmp / f"{hashlib.sha1(target.encode()).hexdigest()[:12]}.feedback.txt"
        feedback.write_text("")
        for attempt in range(1, self.cfg.retries + 2):
            r.attempts = attempt
            env = {**self.cfg.env, "FANOUT_TARGET": target, "FANOUT_FEEDBACK": str(feedback),
                   "FANOUT_ATTEMPT": str(attempt)}
            a = run_cmd(render(self.cfg.agent_cmd, target, str(feedback), attempt),
                        self.cfg.agent_timeout, self.cfg.cwd, env)
            data, r.agent_claimed_ok = parse_agent_output(a.output)
            r.agent_exit, r.agent_tail = a.exit_code, a.output
            r.agent_seconds += a.seconds
            if data and isinstance(data.get("total_cost_usd"), (int, float)):
                r.cost_usd += float(data["total_cost_usd"])
            if a.timed_out:
                r.status = "timeout"
                break
            if a.exit_code != 0 or (data or {}).get("is_error") is True:
                r.status = "agent_failed"
                break
            if not self.cfg.verify_cmd:
                r.status = "ok"
                break
            v = run_cmd(render(self.cfg.verify_cmd, target, str(feedback), attempt),
                        self.cfg.verify_timeout, self.cfg.cwd, env)
            r.verify_exit, r.verify_tail = v.exit_code, v.output
            r.verify_seconds += v.seconds
            if v.exit_code == 0:
                r.status = "ok"
                break
            r.status = "timeout" if v.timed_out else "verify_failed"
            feedback.write_text(f"Verification failed on attempt {attempt}:\n{v.output}")
        if r.status == "ok" and self.cfg.on_success_cmd:
            with self._writer_lock:
                s = run_cmd(render(self.cfg.on_success_cmd, target), self.cfg.verify_timeout,
                            self.cfg.cwd, {**self.cfg.env, "FANOUT_TARGET": target})
            if s.exit_code != 0:
                r.status, r.verify_tail = "verify_failed", f"on_success failed:\n{s.output}"
        return self._record(r)

    def _record(self, r: TargetResult) -> TargetResult:
        with self._lock:
            if r.status not in ("ok", "cancelled", "skipped"):
                self._failures += 1
                if self.cfg.max_failures is not None and self._failures >= self.cfg.max_failures:
                    self._tripped = True
            if self.results_path:
                with self.results_path.open("a") as f:
                    f.write(json.dumps(asdict(r)) + "\n")
        return r

    # -- the whole batch ----------------------------------------------------
    def run(self, targets: list[str], skip: set[str] | None = None) -> list[TargetResult]:
        skip = skip or set()
        todo = [t for t in targets if t not in skip]
        results = {t: TargetResult(t, status="skipped") for t in targets if t in skip}
        canary, rest = todo[: self.cfg.canary], todo[self.cfg.canary:]
        with ThreadPoolExecutor(max_workers=max(1, self.cfg.concurrency)) as pool:
            for r in pool.map(self.process, canary):
                results[r.target] = r
            if any(results[t].status != "ok" for t in canary):
                self._tripped = True  # a failed canary means: fix the prompt, not the targets
            for r in pool.map(self.process, rest):
                results[r.target] = r
        return [results[t] for t in targets]


def summarize(results: list[TargetResult], wall_seconds: float = 0.0) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1
    return {
        "targets": len(results),
        "by_status": counts,
        "claimed_ok_but_not_ok": sum(1 for r in results if r.agent_claimed_ok and r.status != "ok"),
        "needed_retry": sum(1 for r in results if r.status == "ok" and r.attempts > 1),
        "cost_usd": round(sum(r.cost_usd for r in results), 4),
        "agent_seconds": round(sum(r.agent_seconds for r in results), 2),
        "wall_seconds": round(wall_seconds, 2),
    }


def load_ok_targets(path: str | Path) -> set[str]:
    """Targets recorded as ok in an earlier results file (last record per target wins)."""
    p, last = Path(path), {}
    if not p.exists():
        return set()
    for line in p.read_text().splitlines():
        if line.strip():
            row = json.loads(line)
            last[row["target"]] = row["status"]
    return {t for t, s in last.items() if s == "ok"}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--targets", required=True, help="file with one target per line")
    ap.add_argument("--agent", required=True, help="agent command template")
    ap.add_argument("--verify", help="verify command template (exit 0 = pass)")
    ap.add_argument("--on-success", help="command run under a global lock after a pass")
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--retries", type=int, default=1, help="extra agent attempts after a failed verify")
    ap.add_argument("--agent-timeout", type=float, default=900.0)
    ap.add_argument("--verify-timeout", type=float, default=300.0)
    ap.add_argument("--max-failures", type=int, help="circuit breaker: stop starting new targets")
    ap.add_argument("--canary", type=int, default=0, help="run the first N first; abort if any fails")
    ap.add_argument("--cwd")
    ap.add_argument("--results", help="append one JSON line per target here")
    ap.add_argument("--resume", action="store_true", help="skip targets already ok in --results")
    ap.add_argument("--dry-run", action="store_true", help="print rendered commands and exit")
    a = ap.parse_args(argv)

    targets = [t.strip() for t in Path(a.targets).read_text().splitlines()
               if t.strip() and not t.startswith("#")]
    if a.dry_run:
        for t in targets:
            print(render(a.agent, t, "<feedback-file>"))
            if a.verify:
                print("  verify:", render(a.verify, t))
        return 0
    cfg = FanoutConfig(a.agent, a.verify, a.on_success, a.concurrency, a.retries,
                       a.agent_timeout, a.verify_timeout, a.max_failures, a.canary, a.cwd)
    skip = load_ok_targets(a.results) if (a.resume and a.results) else set()
    start = time.monotonic()
    results = Fanout(cfg, a.results).run(targets, skip)
    for r in results:
        print(f"{r.status:14} attempts={r.attempts} {r.target}")
    summary = summarize(results, time.monotonic() - start)
    print(json.dumps(summary, indent=2))
    return 0 if all(r.status in ("ok", "skipped") for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
