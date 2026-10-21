# The triage agent on two vendor SDKs (annotated, not run)

These are sketches. Neither `claude-agent-sdk` nor `openai-agents` is installed in the course venv, and the tests do not run this code. The APIs were checked against the official docs on 2026-10-19:

- Claude Agent SDK Python reference: https://code.claude.com/docs/en/agent-sdk/python
- Claude Agent SDK hooks: https://code.claude.com/docs/en/agent-sdk/hooks
- OpenAI Agents SDK human-in-the-loop: https://openai.github.io/openai-agents-python/human_in_the_loop/
- OpenAI Agents SDK guardrails and handoffs: https://openai.github.io/openai-agents-python/guardrails/ and /handoffs/

Pin a version when you adopt either one. Both SDKs ship often, and several names below (for example `agents.decorators.tool`) are newer than older tutorials.

Same agent as `raw_agent.py` and `langgraph_agent.py`: three tools, the same system prompt, and a human gate before `restart_service`. Read each sketch with one question in mind: **where does the approval gate live, and where does paused state live?**

| | raw_agent.py | langgraph_agent.py | Claude Agent SDK | OpenAI Agents SDK |
|---|---|---|---|---|
| Who owns the loop | you | you (as a graph) | the SDK (the Claude Code harness) | the SDK (`Runner`) |
| Approval gate | `approve()` callback, blocks the process | `interrupt()` in an `approve` node | `PreToolUse` hook (`"ask"`/`"deny"`/`"defer"`) or `can_use_tool` | `needs_approval=True` on the tool |
| Paused state lives in | process memory (lost on crash) | checkpointer, keyed by `thread_id` | session log on disk, resumed with `resume=<session_id>` | `RunState`, serialised by you (`to_string()`) |
| Turn budget | `max_turns` arg | `max_turns` in the router | `max_turns` option | `max_turns` on `Runner.run` |
| Tracing | `ainative_kit.Tracer` | LangSmith via `@traceable` | message stream plus hooks; OpenTelemetry export is not covered here | built in, on by default |

## 1. Claude Agent SDK

The Agent SDK runs the Claude Code harness as a library. You get its loop, context management, compaction, built-in tools and permission system. Custom tools come in as an in-process MCP server.

```python
import asyncio, json
from claude_agent_sdk import (
    ClaudeAgentOptions, ClaudeSDKClient, HookMatcher, ResultMessage,
    create_sdk_mcp_server, tool,
)
from triage_world import ALERTS, LOGS, SYSTEM_PROMPT, OpsWorld

world = OpsWorld()

# (1) Tools are MCP tools. The decorator takes (name, description, input_schema).
#     They return MCP content blocks, not bare strings.
@tool("get_alert", "Fetch an alert by id", {"alert_id": str})
async def get_alert(args):
    return {"content": [{"type": "text", "text": json.dumps(ALERTS[args["alert_id"]])}]}

@tool("query_logs", "Recent ERROR/WARN lines for a service", {"service": str, "minutes": int})
async def query_logs(args):
    return {"content": [{"type": "text", "text": "\n".join(LOGS.get(args["service"], []))}]}

@tool("restart_service", "Rolling restart. MUTATES PRODUCTION.", {"service": str, "reason": str})
async def restart_service(args):
    # There is no tool_use_id here to dedupe on. The idempotency key has to come from
    # somewhere else, e.g. f"{session_id}:{service}" captured in the PreToolUse hook.
    world.restarts.append(args["service"])
    return {"content": [{"type": "text", "text": f"restarted {args['service']}"}]}

ops = create_sdk_mcp_server(name="ops", version="1.0.0",
                            tools=[get_alert, query_logs, restart_service])

# (2) The approval gate is a PreToolUse hook. "ask" hands the call to the permission
#     prompt (your can_use_tool callback in a headless app); "deny" blocks it, and the
#     reason goes back to the model as the tool result. "defer" ends the turn so you can
#     resume the call later, which is the closest analogue to LangGraph's interrupt().
async def gate_restart(input_data, tool_use_id, context):
    if input_data["tool_name"] != "mcp__ops__restart_service":
        return {}
    if is_peak_hours():                       # your policy
        return {"hookSpecificOutput": {
            "hookEventName": input_data["hook_event_name"],
            "permissionDecision": "deny",
            "permissionDecisionReason": "Restarts are frozen during peak; recommend an owner instead.",
        }}
    return {"hookSpecificOutput": {"hookEventName": input_data["hook_event_name"],
                                   "permissionDecision": "ask"}}

options = ClaudeAgentOptions(
    system_prompt=SYSTEM_PROMPT,
    mcp_servers={"ops": ops},                               # tool names become mcp__ops__<tool>
    allowed_tools=["mcp__ops__get_alert", "mcp__ops__query_logs"],  # auto-approve the READ tools only
    disallowed_tools=["Bash", "Write", "Edit"],             # this agent does not need a shell
    hooks={"PreToolUse": [HookMatcher(matcher="mcp__ops__restart_service", hooks=[gate_restart])]},
    max_turns=8,
)

async def main(alert_id: str):
    async with ClaudeSDKClient(options=options) as client:
        await client.query(f"Triage {alert_id}.")
        async for msg in client.receive_response():
            if isinstance(msg, ResultMessage):
                print(msg.result, msg.num_turns, msg.total_cost_usd, msg.session_id)

asyncio.run(main("ALERT-4211"))
```

Annotations:

- **Do not put `restart_service` in `allowed_tools`.** Allow rules approve a call before `can_use_tool` runs. The docs warn about exactly this, and it is the classic way to bypass your own gate.
- **`allowed_tools` is not an allowlist of what exists.** The docs say it "does not restrict Claude to only these tools". Use `disallowed_tools` (or the `tools` option) to remove tools.
- **Resumption is session-based.** Pass `resume=<session_id>`, or `fork_session=True` to branch. That is coarser than LangGraph's per-super-step checkpoints, but you get it for free.
- **What you give up:** you do not own the loop. You cannot insert a node between "model chose a tool" and "tool ran" except through hooks, and you cannot assert that two implementations sent byte-identical requests, as `test_parity.py` does.

## 2. OpenAI Agents SDK

`Runner` owns the loop: call the model, then classify the result as a final output, a handoff, or tool calls ([docs](https://openai.github.io/openai-agents-python/running_agents/)). Approval is a tool property, and paused state is a `RunState` you serialise.

```python
import asyncio, json
from pathlib import Path
from agents import Agent, GuardrailFunctionOutput, RunState, Runner, function_tool, handoff
from agents.decorators import input_guardrail
from triage_world import ALERTS, LOGS, SYSTEM_PROMPT, OpsWorld

world = OpsWorld()

@function_tool
def get_alert(alert_id: str) -> str:
    """Fetch an alert by id."""                    # the docstring becomes the tool description
    return json.dumps(ALERTS[alert_id])

@function_tool
def query_logs(service: str, minutes: int = 15) -> str:
    """Recent ERROR/WARN lines for a service. Read-only."""
    return "\n".join(LOGS.get(service, []))

@function_tool(needs_approval=True)                # (1) the gate is declared on the tool
def restart_service(service: str, reason: str) -> str:
    """Rolling restart. MUTATES PRODUCTION."""
    world.restarts.append(service)
    return f"restarted {service}"

# (2) Input guardrail: runs on the FIRST agent only, in parallel with it by default.
#     A parallel guardrail can trip after the model has already spent tokens or called
#     tools. For anything with side effects, use blocking mode (run_in_parallel=False).
@input_guardrail
async def only_known_alerts(ctx, agent, input):
    text = input if isinstance(input, str) else str(input)
    return GuardrailFunctionOutput(output_info=None, tripwire_triggered="ALERT-" not in text)

db_oncall = Agent(name="DB on-call", instructions="You own Postgres and connection pools.")

triage = Agent(
    name="Triage",
    instructions=SYSTEM_PROMPT,
    tools=[get_alert, query_logs, restart_service],
    input_guardrails=[only_known_alerts],
    handoffs=[handoff(db_oncall)],                 # (3) exposed to the model as transfer_to_db_oncall
)

async def main(alert_id: str):
    result = await Runner.run(triage, f"Triage {alert_id}.", max_turns=8)
    while result.interruptions:                    # paused on restart_service
        state = result.to_state()
        Path("pending.json").write_text(state.to_string())   # park it; a human decides later
        # ... later, possibly in another process:
        state = await RunState.from_json(triage, json.loads(Path("pending.json").read_text()))
        for item in result.interruptions:
            state.approve(item)                    # or state.reject(item)
        result = await Runner.run(triage, state)
    print(result.final_output)

asyncio.run(main("ALERT-4211"))
```

Annotations:

- **Handoff vs agent-as-tool.** A handoff transfers the conversation to the other agent, and `input_filter` controls how much history it sees. `Agent.as_tool()` calls the other agent and keeps control. Use the tool form when the triage agent must stay accountable for the final answer, which is the single-writer rule from [Module 06](../../06-agent-architectures/README.md).
- **Tracing is on by default and captures sensitive data by default.** Tool inputs and outputs, including log lines, go to the trace backend. Redact in a custom trace processor, or turn off sensitive-data capture, before you point this at production logs.
- **`RunState.from_json` does not authenticate the snapshot.** The docs say so. Treat the parked state like a session cookie: store it server-side and sign it or keep it where only your service can write.
- **Model choice.** The SDK targets OpenAI models first. Other providers go through its model-provider adapters. Check the current docs before assuming Claude support for a given feature.

## What the four versions teach together

> **Synthesis:** All four have the same loop: model call, classify, execute tools, append results, repeat until there are no tool calls or the budget trips. They differ in three places: **where the gate sits, where paused state lives, and who can see the requests**. Pick a framework by which of those three you need to control, not by its feature list.
