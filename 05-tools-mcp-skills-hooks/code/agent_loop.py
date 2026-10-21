"""A minimal tool-calling loop, and a demo of why actionable error messages matter.

    python agent_loop.py            # real model if ANTHROPIC_API_KEY is set, else the scripted fake

The loop is the standard one: call the model with tool schemas; if it asks for tools, run
them and append `tool_result` blocks (with `is_error` set on failures); repeat until it
answers in text, hits `max_turns`, or makes `max_consecutive_errors` failed calls in a row
(12-factor-agents factor 9: compact errors into context, but break after ~3).

The demo runs the same task against two versions of the same toolset:
  - actionable: errors say "Did you mean 'ledger-writer-v2'?"
  - opaque:     errors say "KeyError: 'ledger-writer'"
The fake model's policy is scripted: it retries only when the error contains a concrete fix.
That mirrors the mechanism (the model can only act on information it is given); it is
not a measurement of how often a real model recovers. Run with a key to see a real model.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

from ainative_kit import FakeClient, LLMClient, Response, Tracer, get_client, text, tool

import ops_tools

ToolFn = Callable[[str, dict[str, Any]], tuple[str, bool]]

SYSTEM = ("You are an on-call assistant. Use the tools to investigate; do not guess names. "
          "When a tool returns an error, read it and fix the call. Answer in 3 sentences or fewer.")


@dataclass
class AgentResult:
    final_text: str
    stop_reason: str  # "answered" | "max_turns" | "too_many_errors"
    turns: int
    tool_log: list[dict[str, Any]] = field(default_factory=list)
    messages: list[dict[str, Any]] = field(default_factory=list)


def run_agent(client: LLMClient, task: str, *, tools: list[dict[str, Any]], call_tool: ToolFn,
              system: str = SYSTEM, max_turns: int = 8, max_consecutive_errors: int = 3,
              tracer: Tracer | None = None) -> AgentResult:
    tracer = tracer or Tracer()
    messages: list[dict[str, Any]] = [{"role": "user", "content": task}]
    log: list[dict[str, Any]] = []
    consecutive_errors = 0
    with tracer.span("agent_run", task=task[:80]) as run:
        for turn in range(1, max_turns + 1):
            with tracer.span("llm_call", turn=turn) as s:
                resp: Response = client.complete(messages, system=system, tools=tools)
                s.attrs.update(stop_reason=resp.stop_reason, n_tool_calls=len(resp.tool_calls))
            messages.append(resp.to_assistant_message())
            if not resp.tool_calls:
                run.attrs["stop"] = "answered"
                return AgentResult(resp.text, "answered", turn, log, messages)
            results = []
            for tc in resp.tool_calls:
                with tracer.span("tool_call", tool=tc.name) as s:
                    content, is_error = call_tool(tc.name, tc.input)
                    s.attrs.update(is_error=is_error, result_chars=len(content))
                log.append({"turn": turn, "name": tc.name, "input": tc.input, "is_error": is_error, "content": content})
                results.append({"type": "tool_result", "tool_use_id": tc.id, "content": content, "is_error": is_error})
                consecutive_errors = consecutive_errors + 1 if is_error else 0
            messages.append({"role": "user", "content": results})
            if consecutive_errors >= max_consecutive_errors:
                run.attrs["stop"] = "too_many_errors"
                return AgentResult("Stopped: repeated tool errors; escalating to a human.", "too_many_errors", turn, log, messages)
        run.attrs["stop"] = "max_turns"
        return AgentResult("Stopped: turn budget exhausted.", "max_turns", max_turns, log, messages)


# ---------------------------------------------------------------- the two toolsets

def actionable_tools(name: str, args: dict[str, Any]) -> tuple[str, bool]:
    return ops_tools.call_tool(name, args)


def opaque_tools(name: str, args: dict[str, Any]) -> tuple[str, bool]:
    """Same tools, but errors look like what a thin wrapper over a Python dict lookup returns."""
    if name == "kafka_consumer_lag" and args.get("group") not in ops_tools.CONSUMER_GROUPS:
        return f"KeyError: {args.get('group')!r}", True
    return ops_tools.call_tool(name, args)


# ---------------------------------------------------------------- scripted stand-in for the model

def _last_tool_result(messages: list[dict[str, Any]]) -> dict[str, Any] | None:
    last = messages[-1]
    if last["role"] == "user" and isinstance(last["content"], list):
        return last["content"][-1]
    return None


def scripted_oncall_model(messages: list[dict[str, Any]], kwargs: dict[str, Any]) -> Response:
    """Deterministic policy: start with a plausible-but-wrong group name, then act on errors."""
    res = _last_tool_result(messages)
    n_calls = sum(1 for m in messages if m["role"] == "assistant")
    if res is None:
        return tool("kafka_consumer_lag", {"group": "ledger-writer"}, id="toolu_1",
                    text_="Checking lag for the ledger writer's consumer group.")
    body = res["content"]
    if res.get("is_error"):
        m = re.search(r"Did you mean '([^']+)'", body)
        if m:
            return tool("kafka_consumer_lag", {"group": m.group(1)}, id=f"toolu_{n_calls + 1}")
        if n_calls < 3:  # retry blindly with another guess, as models do when given nothing to go on
            guess = ["ledger_writer", "ledger-writer-consumer"][n_calls - 1]
            return tool("kafka_consumer_lag", {"group": guess}, id=f"toolu_{n_calls + 1}")
        return text("I could not find the consumer group; the lag tool only returned KeyError.")
    if body.startswith("group="):
        stats = dict(kv.split("=", 1) for kv in body.splitlines()[0].split() if "=" in kv)
        if "One partition dominates" in body:
            return tool("logs_search", {"service": "ledger-writer", "query": "partition=3", "level": "ERROR",
                                        "limit": 3}, id=f"toolu_{n_calls + 1}")
        return text(f"Lag on {stats['group']} is {stats['total_lag']} and evenly spread.")
    if "log lines" in body:
        return text("ledger-writer-v2 lag (~49k) is concentrated on partition 3: the consumer is failing to "
                    "deserialize offset 88123401 (unknown enum 'REFUND_PARTIAL'). Likely a producer schema change; "
                    "check the most recent payments.events producer deploy before restarting consumers.")
    return text("Done.")


TASK = "Alert: ConsumerLagHigh for ledger-writer. What is going on?"


def demo(client: LLMClient | None = None) -> dict[str, AgentResult]:
    out = {}
    for label, fn in (("actionable", actionable_tools), ("opaque", opaque_tools)):
        c = client or FakeClient(scripted_oncall_model)
        out[label] = run_agent(c, TASK, tools=ops_tools.TOOL_SCHEMAS, call_tool=fn)
    return out


if __name__ == "__main__":
    real = get_client(fake=FakeClient(scripted_oncall_model))
    for label, r in demo(None if isinstance(real, FakeClient) else real).items():
        print(f"=== {label}: stop={r.stop_reason} turns={r.turns}")
        for t in r.tool_log:
            print(f"  -> {t['name']}({t['input']})  error={t['is_error']}\n     {t['content'].splitlines()[0][:110]}")
        print(f"  final: {r.final_text}\n")
