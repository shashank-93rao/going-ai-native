# 02: LangChain essentials: models, messages, tools, `create_agent`, middleware

## The idea

LangChain v1 is a thin agent layer on top of LangGraph. It gives you five things:

1. **Models** behind one interface (`init_chat_model("provider:model")`), so swapping providers is a string change.
2. **Messages** as typed objects (`SystemMessage`, `HumanMessage`, `AIMessage`, `ToolMessage`) that normalise each provider's wire format into one shape, including `AIMessage.tool_calls` and provider-neutral `content_blocks`.
3. **Tools** declared as decorated Python functions (`@tool`). The docstring becomes the description and the type hints become the JSON schema.
4. **`create_agent`**, a prebuilt tool-calling loop. The reveal, as Ed Donner's course puts it (see `research/curricula.md` 2b), is that **it is a LangGraph graph**: a model node, a tools node, and a conditional edge, the same shape as [`code/langgraph_agent.py`](code/langgraph_agent.py).
5. **Middleware**: hooks around that loop (`before_model`, `wrap_model_call`, `wrap_tool_call`, `after_model`, and others) where retries, PII redaction, summarization, human approval and loop detection live.

This maps onto LangChain Academy's "Quickstart: LangChain Essentials" (Create Agent, Models and Messages, Streaming, Tools, Tools with MCP, Memory, Structured Output, Dynamic Prompt, Human in the Loop) and "Introduction to LangChain" (its Module 3 is all middleware). See [references.md](references.md).

> **Note on versions.** Snippets in this file are checked against docs.langchain.com as of 2026-10-19. `langchain` is not installed in the course venv (only `langchain-core` 1.6.12, which LangGraph pulls in), so these snippets are not run by the tests. Pin `langchain>=1` when you try them.

## Why it matters

Middleware is where the harness lives. LangChain's own harness-engineering post reports that the deepagents CLI went from 52.8% to 66.5% on Terminal Bench 2.0 **with the model held fixed** (gpt-5.2-codex), through harness changes. Two of those changes were middleware: a `PreCompletionChecklistMiddleware` that blocks exit until a verification pass runs, and a `LoopDetectionMiddleware` that counts edits per file and injects a "reconsider your approach" prompt after N of them ([LangChain, "Improving Deep Agents with harness engineering"](https://www.langchain.com/blog/improving-deep-agents-with-harness-engineering)). Those are the governors from [Module 07](../07-loops/README.md), packaged as composable hooks.

The cost is the one from [01](01-build-raw-then-adopt.md): every middleware can change what the model sees. Summarization rewrites history. A dynamic prompt rewrites the system prompt. PII redaction rewrites tool output. If you stack five middlewares, you need a trace to know what was sent.

## How it works

### Models and messages

```python
from langchain.chat_models import init_chat_model
from langchain.messages import SystemMessage, HumanMessage

model = init_chat_model("anthropic:claude-sonnet-5-5")        # "provider:model" string
resp = model.invoke([SystemMessage("You are terse."), HumanMessage("Why is p99 > p50?")])
resp.content_blocks          # provider-neutral blocks: text, reasoning, tool_call, ...
```

Compare with `ainative_kit`: `Response(text, tool_calls, stop_reason, usage)`. The idea is the same. LangChain's version covers more providers and modalities, and it is one more translation layer between you and the wire format.

### Tools

```python
from langchain.tools import tool

@tool
def query_logs(service: str, minutes: int = 15) -> str:
    """Return recent ERROR/WARN log lines for a service. Read-only."""
    ...
```

The docstring *is* the tool description the model reads. Treat it like an API contract ([Module 05](../05-tools-mcp-skills-hooks/README.md)): say what it does, what it does not do, and what the arguments mean. A stale docstring is a prompt bug.

### `create_agent`

```python
from langchain.agents import create_agent
from langgraph.checkpoint.memory import InMemorySaver

agent = create_agent(
    model="anthropic:claude-sonnet-5-5",
    tools=[get_alert, query_logs, restart_service],
    system_prompt=SYSTEM_PROMPT,
    response_format=TriageVerdict,        # optional structured output -> result["structured_response"]
    checkpointer=InMemorySaver(),          # it is a LangGraph graph, so it takes a checkpointer
)
result = agent.invoke({"messages": [{"role": "user", "content": "Triage ALERT-4211."}]},
                      {"configurable": {"thread_id": "incident-4211"}})
```

Other documented parameters include `state_schema` (extend `AgentState` with your own fields), `context_schema` (per-run, read-only context such as a user id), and `middleware=[...]`.

### Middleware hooks

| Hook | When it runs | Typical use |
|---|---|---|
| `before_agent` / `after_agent` | once per invocation | load memory, write a summary |
| `before_model` / `after_model` | around each model call (node style: return a state update) | trim messages, count turns, `jump_to: "end"` |
| `wrap_model_call` | wraps the call (decide whether and how often to call the handler) | retry, fallback model, dynamic model or prompt |
| `wrap_tool_call` | wraps each tool execution | tool retry, sandboxing, output redaction |

Built-ins include `HumanInTheLoopMiddleware`, `ModelRetryMiddleware`, `ToolRetryMiddleware`, `PIIMiddleware` and `TodoListMiddleware` (all from `langchain.agents.middleware`). The docs import `SummarizationMiddleware` and `FilesystemMiddleware` from `deepagents.middleware`. A hook that exits early returns `{"jump_to": "end"}` and must declare `@hook_config(can_jump_to=["end"])`.

## Worked example: the triage agent with middleware

### Bad version: approval by prompt

```python
agent = create_agent(
    model="anthropic:claude-sonnet-5-5",
    tools=[get_alert, query_logs, restart_service],
    system_prompt=SYSTEM_PROMPT + "\nALWAYS ask the human before calling restart_service.",
)
```

This fails in two ways. The model cannot *ask* anyone: it can only emit text or tool calls, so "asking" means ending the turn with a question, and an ambient agent with no chat UI has nobody to answer it. And the instruction is a request, not a check ([Module 14](../14-steering-and-guardrails/README.md)). Under a long context or a confident diagnosis, the model will sometimes call the tool anyway, and nothing stops it.

### Good version: approval as middleware, budget as middleware

```python
from typing import Any
from langchain.agents import create_agent
from langchain.agents.middleware import (
    AgentMiddleware, AgentState, HumanInTheLoopMiddleware, ToolRetryMiddleware, hook_config,
)
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.runtime import Runtime
from langgraph.types import Command

class TurnBudget(AgentMiddleware):
    """Circuit breaker: stop after N model calls (the raw loop's max_turns)."""
    def __init__(self, max_model_calls: int = 8):
        super().__init__()
        self.max = max_model_calls

    @hook_config(can_jump_to=["end"])
    def before_model(self, state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
        ai_turns = sum(1 for m in state["messages"] if m.type == "ai")
        return {"jump_to": "end"} if ai_turns >= self.max else None

agent = create_agent(
    model="anthropic:claude-sonnet-5-5",
    tools=[get_alert, query_logs, restart_service],
    system_prompt=SYSTEM_PROMPT,
    middleware=[
        TurnBudget(8),
        ToolRetryMiddleware(max_retries=2),               # flaky log backend
        HumanInTheLoopMiddleware(interrupt_on={
            "restart_service": {"allowed_decisions": ["approve", "edit", "reject"]},
            "get_alert": False, "query_logs": False,
        }),
    ],
    checkpointer=InMemorySaver(),                         # required: the interrupt must persist
)

cfg = {"configurable": {"thread_id": "incident-4211"}}
out = agent.invoke({"messages": [{"role": "user", "content": "Triage ALERT-4211."}]}, cfg)
# out["__interrupt__"] holds the pending restart_service call
agent.invoke(Command(resume={"decisions": [{"type": "approve"}]}), cfg)
```

Why this is better: the gate is **structural**. The tools node cannot run `restart_service` without a decision, the decision persists in the checkpointer, and resuming uses the same `Command(resume=...)` protocol as the hand-written graph in `langgraph_agent.py`. The budget is a check in code, not a sentence in the prompt.

What to verify before you trust it: trace one run (see [05](05-langsmith-tracing-and-evals.md)) and diff the system prompt and tool list against `triage_world.SYSTEM_PROMPT` and `TOOL_SCHEMAS`. If they match, you have the raw agent plus three governors. If they don't, find out which layer changed them.

## Pitfalls

- **Middleware order is semantics.** A retry middleware outside a summarization middleware retries the summarised request. Detection: write the order down, and test the one combination you care about (for example, "a retried model call sees the same messages").
- **A docstring edit is a prompt deploy.** Detection: diff tool schemas in CI. `[t.tool_call_schema for t in tools]` or the trace's tool list is enough.
- **HITL decisions are positional.** The resume payload is one decision per pending action, in the order the actions appeared. Detection: a test with two risky calls in one turn.
- **`create_agent` without a checkpointer.** Interrupts need one. The docs are explicit, and an in-memory saver in production silently loses parked approvals on restart.
- **Mixing message types.** Your domain code ends up passing `AIMessage` around. Detection: `grep -r "langchain" src/domain`. Keep framework types at the edge.

## In your day job

- If you adopt `create_agent`, write the three governors you need (turn budget, tool retry, human gate) as middleware on day one, and put a test on each.
- Treat tool docstrings as reviewed API contracts. They are prompt text.
- Use `response_format` with a Pydantic model for verdicts that downstream code consumes (for example `TriageVerdict(action, owner, confidence)`), and validate it like any other input ([Module 14](../14-steering-and-guardrails/README.md)).
- Keep the raw loop and a parity test, so that a LangChain upgrade that changes default prompts shows up as a failing diff rather than a behaviour change in production.
