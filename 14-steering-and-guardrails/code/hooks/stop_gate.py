"""Stop-hook verification gate for Claude Code: no "done" until the oracle passes.

On every Stop event it:
  1. checks the working-tree diff for test tampering (test_tamper_check.py),
  2. runs the oracle command (default: pytest),
  3. blocks the stop with {"decision": "block", "reason": <compact failure>} if either fails.

Governors, because a gate without a budget is a runaway loop:
  - Its own consecutive-block budget per session (STOP_GATE_MAX_BLOCKS, default 5).
    Claude Code's built-in cap (8 consecutive continuations) resets whenever Claude
    calls a tool, so a gate where Claude keeps editing and failing is never capped
    by it. You need your own counter.
  - No-progress detection: the same failure twice in a row gets a "change approach" note.
  - A broken oracle (timeout, command not found) halts the run with continue:false and
    tells the human, instead of making the agent "fix" the measuring instrument.

Config (env): STOP_GATE_CMD, STOP_GATE_MAX_BLOCKS, STOP_GATE_TIMEOUT, STOP_GATE_BASE,
STOP_GATE_TAMPER (1/0), STOP_GATE_ONE_SHOT (1 = exit when stop_hook_active, the docs' simple pattern).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_tamper_check import blocking, check_diff, format_findings, git_diff, load_approvals  # noqa: E402


@dataclass
class OracleResult:
    ok: bool
    exit_code: int
    output: str
    broken: bool = False  # the instrument failed, not the code


@dataclass
class GateConfig:
    cmd: str = "python3 -m pytest -q -x"
    max_blocks: int = 5
    timeout: int = 540  # keep under the hook's own timeout in settings.json
    base: str = "HEAD"
    tamper: bool = True
    one_shot: bool = False

    @classmethod
    def from_env(cls) -> "GateConfig":
        e = os.environ
        return cls(
            cmd=e.get("STOP_GATE_CMD", cls.cmd),
            max_blocks=int(e.get("STOP_GATE_MAX_BLOCKS", cls.max_blocks)),
            timeout=int(e.get("STOP_GATE_TIMEOUT", cls.timeout)),
            base=e.get("STOP_GATE_BASE", cls.base),
            tamper=e.get("STOP_GATE_TAMPER", "1") != "0",
            one_shot=e.get("STOP_GATE_ONE_SHOT", "0") == "1",
        )


_SIGNAL = re.compile(r"FAILED|ERROR|Error|error:|assert|^E\s|panic:|--- FAIL|Traceback|\d+ (passed|failed)")


def compact_output(out: str, max_lines: int = 30, max_chars: int = 2500) -> str:
    """Keep the lines a fixer needs (Spotify-style: extract errors, drop build noise)."""
    lines = out.strip().splitlines()
    keep = [ln for ln in lines if _SIGNAL.search(ln)] or lines
    text = "\n".join(keep[-max_lines:])
    return text[-max_chars:]


def run_oracle(cmd: str, cwd: Path, timeout: int) -> OracleResult:
    # PYTHONDONTWRITEBYTECODE: an agent edit that keeps the file size and lands in the same
    # mtime second (e.g. "==" -> ">=") can otherwise be served stale cached bytecode.
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    try:
        r = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        return OracleResult(False, -1, f"oracle timed out after {timeout}s: {cmd}", broken=True)
    out = r.stdout + r.stderr
    broken = r.returncode in (126, 127) or (r.returncode == 5 and "no tests ran" in out)  # pytest 5 = no tests
    return OracleResult(r.returncode == 0, r.returncode, out, broken=broken)


def _fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def evaluate(
    event: dict,
    cfg: GateConfig,
    state: dict,
    oracle: Callable[[], OracleResult],
    diff: Callable[[], str],
    approvals: set[str] | None = None,
) -> tuple[dict | None, dict]:
    """Pure decision function. Returns (hook_output_or_None, new_state)."""
    if cfg.one_shot and event.get("stop_hook_active"):
        return None, {}

    findings = blocking(check_diff(diff(), approvals)) if cfg.tamper else []
    result = oracle()
    if result.ok and not findings:
        return None, {}

    if result.broken:
        return {
            "continue": False,
            "stopReason": f"Stop gate could not run the oracle (exit {result.exit_code}). "
                          f"Treat this task as NOT verified. Details: {compact_output(result.output, 5, 400)}",
        }, {}

    blocks = int(state.get("blocks", 0))
    if blocks >= cfg.max_blocks:
        return {
            "continue": False,
            "stopReason": f"Stop gate gave up after {blocks} blocked attempts. The oracle or the tamper check is "
                          f"still failing; the task is NOT done. Review the transcript before retrying.",
        }, {}

    parts = [f"Stop blocked by the verification gate (attempt {blocks + 1} of {cfg.max_blocks})."]
    if findings:
        parts.append(
            "Test tampering detected. Revert these test changes and fix the code under test instead:\n"
            + format_findings(findings)
            + "\nIf you believe a test is wrong, stop and explain why to the user; only a human can approve test changes."
        )
    if not result.ok:
        parts.append(f"Oracle `{cfg.cmd}` failed (exit {result.exit_code}):\n{compact_output(result.output)}")
    reason = "\n\n".join(parts)

    fp = _fingerprint(format_findings(findings) + compact_output(result.output))
    if fp == state.get("last_fp"):
        reason += ("\n\nThis is the same failure as your previous attempt. Do not repeat the last edit. Re-read the "
                   "failing test and the code path it exercises, state a new hypothesis, then change the code.")
    return {"decision": "block", "reason": reason}, {"blocks": blocks + 1, "last_fp": fp}


def _state_path(root: Path, session_id: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", session_id or "nosession")
    return root / ".claude" / "state" / "stop_gate" / f"{safe}.json"


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"stop_gate: unreadable hook input: {e}", file=sys.stderr)
        return 1  # non-blocking error: don't trap the session on a harness bug
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or event.get("cwd") or ".")
    cfg = GateConfig.from_env()
    sp = _state_path(root, event.get("session_id", ""))
    state = json.loads(sp.read_text()) if sp.exists() else {}

    def diff() -> str:
        try:
            return git_diff(root, cfg.base)
        except RuntimeError:
            return ""

    out, new_state = evaluate(event, cfg, state, lambda: run_oracle(cfg.cmd, root, cfg.timeout), diff, load_approvals(root))
    sp.parent.mkdir(parents=True, exist_ok=True)
    sp.write_text(json.dumps(new_state))
    if out:
        print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
