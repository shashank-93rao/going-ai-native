# 01: The augmented LLM, and workflows vs agents

## The idea

Anthropic's "Building effective agents" names the basic unit of every agentic system: "an LLM enhanced with augmentations such as retrieval, tools, and memory" ([Anthropic, "Building effective agents"](https://www.anthropic.com/engineering/building-effective-agents)). Call it the **augmented LLM**. It is one model call that can see retrieved documents and stored memory, and can request tool executions. Everything else in this module is a way of composing that unit.

The same post then splits composed systems into two kinds:

- **Workflows**: "systems where LLMs and tools are orchestrated through predefined code paths."
- **Agents**: "systems where LLMs dynamically direct their own processes and tool usage."

The distinction is about **who owns the control flow**. In a workflow your code decides what happens next, and the model fills in steps. In an agent the model decides what happens next, and your code executes the tools and enforces budgets. A systems analogy: a workflow is an Airflow DAG whose tasks happen to call a model. An agent is a scheduler whose scheduling policy is a model.

## Why it matters

Control flow determines where you can put checks. In a workflow every edge is a place where code runs, so every edge can carry a gate: validate JSON, check a timestamp exists in the source, reject an out-of-range number. In an agent the edges are internal to the model's reasoning. You can check the tools it calls (inputs, permissions, results) and the final answer, and that is all.

The post's own advice follows: "add multi-step agentic systems only when simpler solutions fall short", and agentic systems "trade latency and cost for task performance" ([Anthropic](https://www.anthropic.com/engineering/building-effective-agents)). OpenAI's guide makes the same call from the other side. Build an agent when you face complex decision-making, rules that are hard to maintain, or heavy reliance on unstructured data. Otherwise a deterministic workflow is enough ([OpenAI, "A practical guide to building agents"](https://cdn.openai.com/business-guides-and-resources/a-practical-guide-to-building-agents.pdf)).

The failure you will actually see is the inverse: a fixed process wrapped in an agent loop. It works in the demo. In production the step count varies from run to run, cost has a long tail, and when it goes wrong the trace shows a sequence of reasonable-looking tool calls with no place where a check could have stopped it.

## How it works

### The augmented LLM in code

```python
# code/patterns.py
@dataclass
class Augmented:
    client: LLMClient
    system: str = ""
    retrieve: Callable[[str], list[str]] | None = None
    memory: list[str] = field(default_factory=list)

    def ask(self, question: str) -> str:
        parts = []
        if self.memory:
            parts.append("<memory>\n" + "\n".join(self.memory) + "\n</memory>")
        if self.retrieve:
            parts.append("<documents>\n" + "\n---\n".join(self.retrieve(question)) + "\n</documents>")
        parts.append(question)
        return ask(self.client, "\n\n".join(parts), system=self.system or None)
```

Retrieval and memory are *context assembly*: code decides what the model sees. Tools are different, because the model decides to call them. That is the first step toward agency.

### The agent: the model owns the loop

```python
def agent_loop(client, task, tools, *, system=None, max_turns=10) -> AgentResult:
    messages = [{"role": "user", "content": task}]
    for turn in range(1, max_turns + 1):
        resp = client.complete(messages, system=system, tools=[t.schema for t in tools.values()])
        messages.append(resp.to_assistant_message())
        if not resp.tool_calls:
            return AgentResult(resp.text, turn, "end_turn", messages)
        results = []
        for call in resp.tool_calls:
            try:
                out, is_error = tools[call.name].fn(call.input), False
            except Exception as e:      # tool errors go back to the model, not up the stack
                out, is_error = f"{type(e).__name__}: {e}", True
            results.append({"type": "tool_result", "tool_use_id": call.id, "content": out, "is_error": is_error})
        messages.append({"role": "user", "content": results})
    return AgentResult("", max_turns, "max_turns", messages)
```

Notice what code still owns: the turn budget (`max_turns`), what each tool is allowed to do, and turning exceptions into observations. [07-loops](../07-loops/README.md) builds this loop properly, with governors, stall detection and oracles.

### The decision rule

Use the cheapest row that works:

| Task property | Architecture | Where the checks live |
|---|---|---|
| One transformation, inputs in hand | **Single augmented call** | Output validator |
| Fixed, known steps | **Workflow** (chain, route, parallel) | Every edge |
| Steps unknown in advance, but bounded and decomposable | **Orchestrator-workers** | Plan validation, each worker's output, the merge |
| Clear acceptance criteria, iteration helps | **Evaluator-optimizer** | The evaluator, which must be a real check |
| Open-ended: "difficult or impossible to predict the required number of steps" ([Anthropic](https://www.anthropic.com/engineering/building-effective-agents)) | **Agent** | Tool boundaries, budget, final-output oracle |

Two questions settle most cases:

1. **Can you write the step list down before you see the input?** If yes, use a workflow. If you can write it down only after looking at the input, use orchestrator-workers. If you can't write it down even then, use an agent.
2. **What can you check automatically?** If the only check is the final answer, an agent costs you little checkability, because you had none in the middle anyway. If you can check intermediate artifacts, a workflow lets you use those checks.

> **Synthesis:** This is the course thesis at architecture scale. An agent gives up intermediate checks in exchange for flexibility. Do that only when the task really needs the flexibility, or when there were no intermediate checks to lose.

## Worked example: Kafka dead-letter-queue triage

**Situation.** The `payments-ledger` consumer sends failed messages to `payments-ledger.DLQ`. Every morning someone triages the DLQ. Each message is replayed (transient failure), discarded (a known-bad producer bug, already fixed), or escalated (unknown). There are about 200 messages a day.

### Bad: an agent

```text
SYSTEM: You are a DLQ triage agent. Tools: read_dlq(n), search_logs(query),
replay(offset), discard(offset), page_human(summary).
USER: Triage the payments-ledger DLQ.
```

What happens (illustrative output, a composite of what such loops do):

```text
turn 1  read_dlq(50)
turn 2  search_logs("offset 88123 error")
turn 3  replay(88123)
turn 4  search_logs("ConstraintViolation ledger_entries_pkey")
turn 5  replay(88124)            <- a duplicate-key failure, replayed anyway
...
turn 31 read_dlq(50)             <- re-reads the same batch, context is now 140k tokens
turn 32 discard(88123)           <- discards a message it replayed at turn 3
```

Why it fails:
- The process is **fixed**: for each message, classify and then act. The model is spending tokens rediscovering the control flow on every run.
- `replay` is side-effecting, and nothing checks the decision before it runs.
- Step count and cost vary run to run, so there is no SLO you can set.
- When it goes wrong, no edge exists where a check could have fired.

### Good: a workflow with one model call per message

```python
REPLAYABLE = {"TimeoutException", "LeaderNotAvailable", "SerializationRetryable"}
KNOWN_BAD = {"ADV-PRODUCER-311"}   # fixed producer bug, safe to discard

def triage(msg) -> str:
    # 1. deterministic first: most messages never need a model
    if msg.error_class in REPLAYABLE and msg.attempts < 3:
        return "replay"
    # 2. one augmented call, structured output, retrieved runbook as context
    raw = classifier.ask(f"<error>{msg.error}</error>\n<payload_schema>{msg.schema}</payload_schema>\n"
                         'Answer JSON: {"category": "transient|producer_bug|data|unknown", "evidence": "..."}')
    verdict = parse_json(raw)
    # 3. gate: the evidence must be a substring of the error text, or we don't trust the label
    if verdict["evidence"] not in msg.error:
        return "escalate"
    return {"transient": "replay", "producer_bug": "discard" if msg.bug_id in KNOWN_BAD else "escalate"}.get(
        verdict["category"], "escalate")
```

What changed:
- The control flow is in code, so every message takes exactly one path. Cost is roughly one call per message for the messages that reach step 2.
- The model does the one thing code can't: read an unstructured error and name its category.
- The gate (`evidence in msg.error`) is cheap and catches the classic failure, a confident label with made-up reasoning.
- Side effects (`replay`, `discard`) are decided by a table in code. A model output alone never triggers them.

### When the agent *is* right

The next morning, the DLQ rate jumped from 200 a day to 40,000 an hour. "Find out why" has no step list. It might be a schema change, a broker problem, or a bad deploy. That is an agent task: read-only tools (`search_logs`, `describe_topic`, `git_log`), a budget, and a human who reads the conclusion. Note that the agent gets **read** tools only. If remediation is needed, it goes back through a workflow with gates.

## Pitfalls

- **Agent-washing a fixed process.** Detect it in traces: if 90% of runs have the same tool-call sequence, you have a workflow wearing an agent costume. Extract it.
- **Workflow with no gates.** A chain of model calls with no code between them has the cost of a workflow and the checkability of an agent. Detect it by grepping for consecutive `complete()` calls with no validation in between.
- **Side effects inside the agent with no decision record.** If an agent can call `replay`, `deploy` or `refund`, you need the durable-run machinery from [05](05-durable-runs-event-sourcing-idempotency.md). Detect it by listing every tool and marking read or write. Any write tool in an agent needs a policy.
- **Choosing by framework.** "We use LangGraph, so it's an agent." The framework is orthogonal. LangGraph expresses both, and so does a for-loop. See [09-frameworks-langchain-langgraph](../09-frameworks-langchain-langgraph/README.md).
- **No budget.** An agent loop without `max_turns` and a token budget is an unbounded retry loop. Detect it by asking what the p99 cost per run is. If nobody knows, there is no budget.

## In your day job

- For any proposed agent, ask for the tool-call sequence from 20 real runs. If they're mostly identical, write the workflow.
- Classify every tool as read or write before design review. Write tools get a deterministic policy or a human checkpoint.
- Put the first deterministic filter in front of the model (the `REPLAYABLE` set above). The cheapest model call is the one you don't make.
- Keep agents for diagnosis and exploration, and workflows for remediation.
