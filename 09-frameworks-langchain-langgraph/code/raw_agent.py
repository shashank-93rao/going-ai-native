"""The on-call triage agent as a raw loop over ainative_kit. No framework.

Everything a framework would give you is visible here, which is the point of
building it once by hand: the loop, the turn budget, the approval gate, the
tool_result plumbing, and the tracing spans. Note what is NOT here: durability.
If this process dies while waiting for approval, the run is gone.

    python raw_agent.py ALERT-4211          # fake model unless ANTHROPIC_API_KEY is set
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Any, Callable

from ainative_kit import FakeClient, LLMClient, ToolCall, Tracer, get_client

from triage_world import RISKY_TOOLS, SYSTEM_PROMPT, TOOL_SCHEMAS, OpsWorld, scripted_policy

Approver = Callable[[ToolCall], tuple[bool, str]]  # -> (approved, reason)


def auto_approve(call: ToolCall) -> tuple[bool, str]:
    return True, "auto-approved (demo)"


def cli_approve(call: ToolCall) -> tuple[bool, str]:
    """Blocks the process on stdin. This is the raw version's only form of human-in-the-loop."""
    answer = input(f"Approve {call.name}({call.input})? [y/N] ").strip().lower()
    return answer == "y", "approved at terminal" if answer == "y" else "rejected at terminal"


@dataclass
class RunResult:
    final_text: str
    tool_sequence: list[str]
    messages: list[dict[str, Any]]
    turns: int
    stopped_by: str  # "end_turn" | "max_turns"
    decisions: list[str] = field(default_factory=list)


def run(
    alert_id: str,
    client: LLMClient,
    world: OpsWorld,
    approve: Approver = auto_approve,
    max_turns: int = 8,
    tracer: Tracer | None = None,
) -> RunResult:
    """Run the triage loop to completion (or until the turn budget trips)."""
    tracer = tracer or Tracer()
    messages: list[dict[str, Any]] = [{"role": "user", "content": f"Triage {alert_id}."}]
    tools_used: list[str] = []
    decisions: list[str] = []

    with tracer.span("agent_run", alert_id=alert_id, impl="raw"):
        for turn in range(1, max_turns + 1):
            with tracer.span("llm_call", turn=turn) as s:
                resp = client.complete(messages, system=SYSTEM_PROMPT, tools=TOOL_SCHEMAS)
                s.attrs.update(stop_reason=resp.stop_reason, n_tool_calls=len(resp.tool_calls))
            messages.append(resp.to_assistant_message())

            if not resp.tool_calls:
                return RunResult(resp.text, tools_used, messages, turn, "end_turn", decisions)

            results: list[dict[str, Any]] = []
            for call in resp.tool_calls:
                with tracer.span("tool_call", tool=call.name) as s:
                    if call.name in RISKY_TOOLS:
                        ok, reason = approve(call)
                        decisions.append(f"{call.name}:{'accept' if ok else 'reject'}")
                        s.attrs["approved"] = ok
                        if not ok:
                            results.append(_result(call, f"rejected by human: {reason}", is_error=True))
                            continue
                    out = world.execute(call.name, call.input, call.id)
                    tools_used.append(call.name)
                    results.append(_result(call, out))
            messages.append({"role": "user", "content": results})

    return RunResult("", tools_used, messages, max_turns, "max_turns", decisions)


def _result(call: ToolCall, content: str, is_error: bool = False) -> dict[str, Any]:
    block: dict[str, Any] = {"type": "tool_result", "tool_use_id": call.id, "content": content}
    if is_error:
        block["is_error"] = True
    return block


if __name__ == "__main__":
    alert = sys.argv[1] if len(sys.argv) > 1 else "ALERT-4211"
    world = OpsWorld()
    tracer = Tracer("raw_traces.jsonl")
    result = run(alert, get_client(fake=FakeClient(scripted_policy)), world, approve=cli_approve, tracer=tracer)
    print(result.final_text)
    print(f"\ntools={result.tool_sequence} turns={result.turns} restarts={world.restarts}")
    print(f"spans written to raw_traces.jsonl: {len(tracer.spans)}")
