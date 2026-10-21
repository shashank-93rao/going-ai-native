"""Toy task for the loop code: make a buggy token-bucket rate limiter pass its spec.

The workspace has two seeded bugs (FP-1: `>` instead of `>=`; FP-2: refill not capped).
`spec_tokenbucket.py` is the oracle; `spec_smoke.py` is a deliberately weak oracle.

Helpers here are shared by the scripts, the tests and the FakeClient scripts:
- make_workspace(dest, fixed=False): copy the workspace somewhere disposable
- FIXES: the two real fixes, keyed by fix_plan item id
- MUTANTS: known-bad changes to the *fixed* code, for prove_it_can_fail
- fixing_script(): a FakeClient script that solves the task like a competent agent
- runaway_responder / oscillating_responder: FakeClient responders that never finish
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from ainative_kit import Response, ToolCall, Usage, text

WORKSPACE = Path(__file__).parent / "workspace"

FIXES: dict[str, tuple[str, str]] = {
    "FP-1": ("if self._tokens > n:", "if self._tokens >= n:"),
    "FP-2": (
        "self._tokens = self._tokens + elapsed * self.refill_per_sec",
        "self._tokens = min(self.capacity, self._tokens + elapsed * self.refill_per_sec)",
    ),
}


def apply_fix(root: Path, item: str) -> None:
    f = root / "tokenbucket.py"
    old, new = FIXES[item]
    f.write_text(f.read_text().replace(old, new, 1))


def make_workspace(dest: Path, fixed: bool = False) -> Path:
    """Copy the toy workspace to dest/ws. With fixed=True, apply both fixes (known-good)."""
    ws = Path(dest) / "ws"
    shutil.copytree(WORKSPACE, ws)
    if fixed:
        for item in FIXES:
            apply_fix(ws, item)
    return ws


def _mut(old: str, new: str):
    from oracle import replace_in

    return replace_in("tokenbucket.py", old, new)


# Known-bad changes. A good oracle rejects all of them.
MUTANTS = {
    "off_by_one_acquire": _mut("if self._tokens >= n:", "if self._tokens > n:"),
    "uncapped_refill": _mut("min(self.capacity, self._tokens + elapsed * self.refill_per_sec)",
                            "self._tokens + elapsed * self.refill_per_sec"),
    "always_allow": _mut("if self._tokens >= n:", "if True:"),
    "no_refill": _mut("elapsed = now - self._last", "elapsed = 0.0"),
    "double_spend": _mut("self._tokens -= n", "self._tokens -= n - 1"),
}


def _u(i: int = 1200, o: int = 150) -> Usage:
    return Usage(input_tokens=i, output_tokens=o)


def _call(id_: str, name: str, args: dict[str, Any]) -> ToolCall:
    return ToolCall(id_, name, args)


def fixing_script() -> list[Response]:
    """What a competent agent does: look, measure, fix both bugs, re-measure, report."""
    fp1_old, fp1_new = FIXES["FP-1"]
    fp2_old, fp2_new = FIXES["FP-2"]
    return [
        Response(text="Let me look at the workspace.", tool_calls=[_call("t1", "list_files", {"path": "."})],
                 stop_reason="tool_use", usage=_u(900)),
        Response(tool_calls=[_call("t2", "read_file", {"path": "tokenbucket.py"}),
                             _call("t3", "run_tests", {})], stop_reason="tool_use", usage=_u(1400)),
        Response(text="Two bugs: strict > on acquire, and refill is not capped at capacity.",
                 tool_calls=[_call("t4", "edit_file", {"path": "tokenbucket.py", "old_str": fp1_old, "new_str": fp1_new}),
                             _call("t5", "edit_file", {"path": "tokenbucket.py", "old_str": fp2_old, "new_str": fp2_new})],
                 stop_reason="tool_use", usage=_u(2600, 300)),
        Response(tool_calls=[_call("t6", "run_tests", {})], stop_reason="tool_use", usage=_u(3000)),
        text("Fixed both bugs; spec_tokenbucket.py passes 5/5.", usage=_u(3300, 40)),
    ]


def premature_script() -> list[Response]:
    """Claims success after fixing only one bug. A completion gate should catch this."""
    fp1_old, fp1_new = FIXES["FP-1"]
    fp2_old, fp2_new = FIXES["FP-2"]
    return [
        Response(tool_calls=[_call("p1", "edit_file", {"path": "tokenbucket.py", "old_str": fp1_old, "new_str": fp1_new})],
                 stop_reason="tool_use", usage=_u()),
        text("Done, the limiter is fixed.", usage=_u()),
        # after the gate pushes back with the failing test:
        Response(tool_calls=[_call("p2", "edit_file", {"path": "tokenbucket.py", "old_str": fp2_old, "new_str": fp2_new})],
                 stop_reason="tool_use", usage=_u()),
        text("Refill is now capped too.", usage=_u()),
    ]


def runaway_responder(messages: list[dict], kwargs: dict) -> Response:
    """Never finishes: reads the same file forever. Governors must trip on this."""
    n = len(messages)
    return Response(tool_calls=[ToolCall(f"r{n}", "read_file", {"path": "tokenbucket.py"})],
                    stop_reason="tool_use", usage=_u())


def oscillating_responder(messages: list[dict], kwargs: dict) -> Response:
    """A-B-A-B: alternates two reads, so a consecutive-only repeat check would miss it."""
    n = len(messages)
    path = "tokenbucket.py" if (n // 2) % 2 == 0 else "fix_plan.md"
    return Response(tool_calls=[ToolCall(f"o{n}", "read_file", {"path": path})], stop_reason="tool_use", usage=_u())


def wandering_responder(messages: list[dict], kwargs: dict) -> Response:
    """Different args every call (no repeats), lots of tokens: only budgets stop it."""
    n = len(messages)
    return Response(tool_calls=[ToolCall(f"w{n}", "list_files", {"path": ".", "pattern": f"*{n}*"})],
                    stop_reason="tool_use", usage=_u(50_000, 2_000))
