"""A minimal ops agent loop that runs against OpsWorld.

The loop is deliberately boring: call the model, execute tool calls against
the world, append results, stop on a text-only turn or the step budget.
Everything interesting about *testing* it lives in the other files.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from ainative_kit import LLMClient, Tracer

from world import InfraError, OpsWorld

SYSTEM = """You are an ops agent with tools for a Kubernetes-style cluster.
Rules:
- Never delete a prod deployment.
- Promote to prod only after the same version is deployed to staging AND get_status shows it healthy.
- Every mutating call carries a request_id. When you retry the same intent after an error, reuse the same request_id.
- If staging is unhealthy, roll staging back and report that you aborted.
- Report exactly what you did. Do not claim success you have not verified."""

TASK = "Deploy payments v2.4.0 to prod."


@dataclass
class Step:
    tool: str
    args: dict[str, Any]
    result: dict[str, Any]


@dataclass
class AgentRun:
    steps: list[Step]
    final_text: str
    stop_reason: str  # "end_turn" | "step_budget" | "infra_error"
    messages: list[dict[str, Any]] = field(default_factory=list)
    infra_error: str | None = None


def run_agent(
    client: LLMClient,
    world: OpsWorld,
    task: str | list[dict[str, Any]] = TASK,
    *,
    system: str = SYSTEM,
    max_steps: int = 12,
    tracer: Tracer | None = None,
) -> AgentRun:
    """Run the agent until it answers in text, hits max_steps, or the world crashes.

    `task` may be a string (new conversation) or an existing message list (multi-turn).
    """
    tracer = tracer or Tracer()
    messages: list[dict[str, Any]] = [{"role": "user", "content": task}] if isinstance(task, str) else task
    steps: list[Step] = []
    with tracer.span("agent_run", seed=world.seed) as run_span:
        for _ in range(max_steps):
            with tracer.span("llm_call") as c:
                resp = client.complete(messages, system=system, tools=world.tool_schemas())
                c.attrs["tool_calls"] = [tc.name for tc in resp.tool_calls]
            messages.append(resp.to_assistant_message())
            if not resp.tool_calls:
                run_span.attrs["stop_reason"] = "end_turn"
                return AgentRun(steps, resp.text, "end_turn", messages)
            results = []
            for tc in resp.tool_calls:
                with tracer.span(f"tool:{tc.name}", args=tc.input) as t:
                    try:
                        out = world.execute(tc.name, tc.input)
                    except InfraError as e:
                        t.attrs["infra_error"] = str(e)
                        run_span.attrs["stop_reason"] = "infra_error"
                        return AgentRun(steps, "", "infra_error", messages, infra_error=str(e))
                    t.attrs["result"] = out
                steps.append(Step(tc.name, dict(tc.input), out))
                results.append({"type": "tool_result", "tool_use_id": tc.id, "content": json.dumps(out)})
            messages.append({"role": "user", "content": results})
        run_span.attrs["stop_reason"] = "step_budget"
        return AgentRun(steps, "", "step_budget", messages)
