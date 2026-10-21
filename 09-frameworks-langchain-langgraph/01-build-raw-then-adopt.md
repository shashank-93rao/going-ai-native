# 01: Build it raw once, then adopt a framework for durability and tracing

## The idea

An agent is a loop: call the model, run whatever tools it asked for, append the results, and repeat until it stops asking or a budget trips. You can write that loop in about 60 lines (see [`code/raw_agent.py`](code/raw_agent.py) and [Module 07](../07-loops/README.md)). A framework does not change the loop. It changes **what surrounds it**: where state lives between steps, how a run pauses for a human and resumes in a different process, how every step gets traced, and how you replay a run from the middle.

So the course stance, from [`research/01-gap-analysis.md`](../research/01-gap-analysis.md), is:

> **Build it raw once to understand it, then adopt a framework for durability and tracing.**

"Raw once" means you can say, for any framework you later use, exactly which request it sent to the model, and why. "Adopt" means you stop hand-rolling checkpointing, interrupt and resume, and trace plumbing. Those are infrastructure problems with subtle failure modes, and you would not hand-roll a consensus library either.

## Why it matters

There are two well-sourced positions, and they are both right about different things.

- **Anthropic, "Building effective agents"** ([link](https://www.anthropic.com/engineering/building-effective-agents)): successful teams use "simple, composable patterns", and frameworks "add abstraction layers that hide prompts and responses and make debugging harder." The post recommends starting with LLM APIs directly.
- **Anthropic, "Demystifying evals"** (see `research/anthropic.md` #23) lists LangSmith, Braintrust, Langfuse and others as fine choices, with the advice to pick one quickly and spend the effort on tasks and graders. Anthropic now ships its own orchestration layers too: the Agent SDK, Managed Agents and workflows.

The failure story on the "framework first" side is familiar. A team adopts a high-level agent constructor, the agent starts calling `restart_service` on capacity alerts, and nobody can answer "what exactly did the model see?" The system prompt was assembled from three layers of defaults, tool descriptions came from docstrings someone forgot to update, and the message history had been trimmed by a middleware nobody configured on purpose.

The failure story on the "raw forever" side is just as familiar, and more expensive. The agent waits 40 minutes for an on-call engineer to approve a restart, the pod is rescheduled, and the run is gone. So you add a JSON file for state, then a lock around the JSON file, then a resume path that accidentally re-executes the last tool call. Six weeks later you have written a worse checkpointer, with no time travel and no trace UI.

## How it works: what a framework actually buys you

Map each feature to the distributed-systems primitive it implements. That tells you whether you need it.

| Framework feature | Systems primitive | You need it when |
|---|---|---|
| Checkpointer, per-step state persistence | Write-ahead log or event sourcing | Runs outlive a process: human approval, long tools, deploys mid-run |
| Threads (`thread_id`) | Partition key or session id | More than one concurrent conversation or incident |
| `interrupt()` and `Command(resume=...)` | Durable promise or saga step awaiting an external event | A human or another system must decide mid-run |
| Time travel (fork from a checkpoint) | Point-in-time restore plus branch | Debugging and "what if" replay, and eval of alternative decisions |
| Long-term store | External KV store, cross-partition | Memory across threads (user preferences, past resolutions) |
| Tracing (LangSmith, Agents SDK traces) | Distributed tracing (spans, trace ids) | Always, from day one ([Module 10](../10-evals-fundamentals/README.md)) |
| Streaming | Server-sent events, progress reporting | A UI, or long runs someone watches |
| Prebuilt agent and middleware | A framework's opinionated defaults | You want a standard loop and accept its prompt choices |

> **Synthesis:** The bottom row is the one that hides prompts. The top six rows are infrastructure, and they mostly do not touch what the model sees. A good adoption keeps the bottom row thin and leans on the top six.

### Decision rule

1. **Prototype raw** until the loop, the tools and one eval exist. That is usually a day.
2. **Adopt an orchestration runtime** (LangGraph, or a vendor SDK) the moment any of these is true: a run must survive a process restart, a human must approve something asynchronously, more than one run happens at once, or you need to replay a run from the middle.
3. **Adopt a tracing and eval platform** (LangSmith or an alternative) when you have more than one person looking at failures, or more than about 50 traces a day to read.
4. **Adopt prebuilt agents and middleware** (`create_agent`, Deep Agents) only after you can diff the prompt they produce against your raw version.

## Worked example: the triage agent, raw vs LangGraph

The module's code builds one on-call triage agent with three tools: `get_alert`, `query_logs` and `restart_service` (risky). `test_parity.py` runs it both ways against the same scripted model and asserts that the **model saw byte-identical requests**:

```python
assert raw.final_text == graph["final_text"]
assert raw.tool_sequence == graph["tool_sequence"]
assert [c["messages"] for c in raw_client.calls] == [c["messages"] for c in graph_client.calls]
assert [c["system"] for c in raw_client.calls] == [c["system"] for c in graph_client.calls]
```

That last assertion is the whole argument in four lines. If you adopt LangGraph at the orchestration layer and keep your own model calls, **the framework changes nothing the model sees**. You can prove it with a test.

### The bad version: human-in-the-loop in the raw loop

```python
def cli_approve(call: ToolCall) -> tuple[bool, str]:
    answer = input(f"Approve {call.name}({call.input})? [y/N] ")   # blocks the process
    return answer == "y", ...
```

This works on your laptop. In production the agent runs in a worker that receives an alert webhook, and the on-call engineer answers 20 minutes later from a phone. The worker cannot block for 20 minutes holding the conversation in memory. If it is restarted in that window, the run is gone. Then the alert fires again, a second run starts, and now two agents may both decide to restart.

### The good version: the same gate as a durable interrupt

```python
def approve(state: TriageState) -> dict:
    for call in _pending_calls(state):
        if call["name"] in RISKY_TOOLS:
            decision = interrupt({"action_request": {"action": call["name"], "args": call["input"]}, ...})
            decisions[call["id"]] = decision
    return {"approvals": decisions}
```

Running `python langgraph_agent.py` (real output from the course venv, fake model):

```text
== 1. run until the human gate ==
paused with: Agent wants to run restart_service on checkout-api: connection pool exhausted (leak in OrderRepository)
next node: ('approve',) | restarts so far: []

== 2. 'new process': fresh graph object, same checkpointer, resume with accept ==
DIAGNOSIS: checkout-api connection pool exhausted by a leak in OrderRepository.findOpen.
ACTION: restarted checkout-api; file a bug to fix the leak before it recurs.
restarts: ['checkout-api']
```

The run paused, its state was persisted, a **fresh** graph object picked it up by `thread_id`, and the test `test_resume_from_a_fresh_graph_uses_the_checkpoint_not_the_model` checks that the fresh client was called exactly once. History came from the checkpoint, not from re-running the model.

What you wrote: one node and one `interrupt()` call. What you did not write: the state store, the resume protocol, the "which node runs next" bookkeeping, or the history API used for time travel.

## Pitfalls

- **Adopting the prebuilt agent before you can read its prompt.** Detection: you cannot produce the exact system prompt and tool list your agent sends without running it under a tracer. Fix: trace one run and diff it against your raw version.
- **Treating the framework as the model wrapper.** If every model call goes through a framework chat-model class, the framework now owns retries, message conversion and token accounting. That is fine, but decide it on purpose. Detection: the framework's message type appears in your domain code.
- **Assuming the checkpointer makes side effects safe.** It makes *state* durable. It does not make `restart_service` idempotent. Resume and replay can re-run a node (see [04](04-langgraph-durability-hitl.md)). Detection: a test that replays from the checkpoint before the side-effecting node and counts the side effects, as `test_replaying_the_side_effect_node_is_safe_only_because_of_idempotency_keys` does.
- **Choosing by feature list.** Every framework lists "memory", "multi-agent" and "HITL". Choose by where the gate lives, where paused state lives, and who can see the requests ([07](07-framework-landscape.md)).
- **Never re-testing the raw baseline.** Frameworks and models both change. Keep the raw implementation and the parity test as a canary when you upgrade either one.

## In your day job

- Keep a 60-line raw loop for every agent you ship, with a parity test against the framework version. It is your reference implementation and your upgrade canary.
- Before adopting a framework, write down which of the six infrastructure rows you need. If the answer is "none", do not adopt one yet.
- In design review, ask "where does paused state live, and what happens if the worker dies while we wait for approval?" before asking which framework.
- Put tracing in on day one, framework or not. `ainative_kit.Tracer` is enough to start. LangSmith is where it goes when more than one person reads traces.
