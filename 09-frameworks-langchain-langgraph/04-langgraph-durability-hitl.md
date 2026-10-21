# 04: Durability and human-in-the-loop: checkpointers, threads, interrupts, time travel, memory

## The idea

Compile a graph with a **checkpointer** and every super-step boundary becomes a durable record: the full state, the set of nodes due to run next, any pending writes, and metadata. Records are grouped by **thread** (`config["configurable"]["thread_id"]`) and linked by parent pointers. Everything in this file follows from that one structure:

- **Resume after a crash**: load the latest checkpoint for the thread and run whatever is in `next`.
- **Interrupts**: a node calls `interrupt(payload)`. The run stops, the payload is surfaced to the caller, and the checkpoint records that this node is waiting. Later, `graph.invoke(Command(resume=value), config)` re-enters the node, and `interrupt()` returns `value`.
- **Time travel**: `get_state_history(config)` lists the thread's checkpoints. Invoking from an older checkpoint's config **replays** from there. Calling `update_state(old_config, values)` first **forks** the thread with edited state.
- **Long-term memory** is separate: a **Store** (`InMemoryStore`, or a Postgres-backed store) holds cross-thread key-value documents under namespaces. It is not checkpointed.

> **Distributed-systems anchor:** a thread is an event-sourced aggregate. Checkpoints are snapshots in its log, `interrupt()` is a saga step that waits on an external event, and a fork is point-in-time restore into a branch. The anchor breaks in one place. A checkpoint records **state**, not **effects**. A replay re-executes nodes, and if those nodes called the outside world, the outside world sees the call twice.

This maps to LangChain Academy "Introduction to LangGraph" M3 (Streaming, Breakpoints, Editing State and Human Feedback, Dynamic Breakpoints, Time Travel), M5 (LangGraph Store, Memory Schema), and M6 (Double Texting), plus "LangGraph Essentials" (Memory, Interrupt).

## Why it matters

From 12-Factor Agents (see `research/practitioners.md`): the most-requested framework feature is an interrupt **between tool selection and tool invocation**, for approval. Real ops agents need it for every mutating action. Without durable state, approval means a blocked process, and a blocked process is a run you lose on the next deploy.

The subtle part is resume semantics. LangGraph resumes **by re-running the interrupted node from its first line**. This is real output from a three-line probe in the course venv, where the node appends to a list before and after `interrupt()`:

```text
['entered gate', 'entered gate', 'got yes']
```

The node was entered twice: once to raise the interrupt, and once on resume, when `interrupt()` returned `"yes"`. Anything before the `interrupt()` call runs twice. If that "anything" is `post_to_slack()` or `restart_service()`, you have a duplicate side effect.

## How it works

### Checkpointers and threads

```python
from langgraph.checkpoint.memory import MemorySaver   # alias of InMemorySaver
graph = build_graph(client, world, checkpointer=MemorySaver(), store=InMemoryStore())
cfg = {"configurable": {"thread_id": "incident-4211"}}
```

| Checkpointer | Package | Use |
|---|---|---|
| `InMemorySaver` / `MemorySaver` | `langgraph` (built in) | tests, demos; dies with the process |
| `SqliteSaver` | `langgraph-checkpoint-sqlite` | local dev, single-node tools |
| `PostgresSaver` / `AsyncPostgresSaver` | `langgraph-checkpoint-postgres` | production; call `.setup()` once to create tables |

`durability=` on `invoke`/`stream` controls when checkpoints are written: `"sync"` (before the next step starts), `"async"` (in the background while the next step runs), or `"exit"` (only when the run exits). Those are the values in langgraph 1.2.16. It is the usual fsync trade-off: `"exit"` is fastest and loses everything if the process dies mid-run.

### Inspecting a thread

`graph.get_state(cfg)` returns a `StateSnapshot` with fields `values, next, config, metadata, created_at, parent_config, tasks, interrupts`. Here is the real history of `incident-4211` after an accepted restart (`step, next, len(messages), checkpoint_id prefix`, newest first):

```text
 8 ()             8  1f1cbe29-d76d   <- done
 7 ('model',)     7  1f1cbe29-d76c
 6 ('tools',)     6  1f1cbe29-d76b   <- approvals recorded, restart about to run
 5 ('approve',)   6  1f1cbe29-d769   <- parked here while the human decided
 4 ('model',)     5  1f1cbe29-d769
 3 ('tools',)     4  1f1cbe29-d768
 2 ('model',)     3  1f1cbe29-d768
 1 ('tools',)     2  1f1cbe29-d767
 0 ('model',)     1  1f1cbe29-d767
-1 ('__start__',) 0  1f1cbe29-d765   <- input
```

### Dynamic interrupts vs static breakpoints

- **`interrupt(payload)` inside a node** is the documented human-in-the-loop mechanism. It is conditional (only for risky tools), carries a payload, and returns the human's answer.
- **`compile(interrupt_before=["tools"])`** (or `interrupt_after`) is a static breakpoint, which you resume with `graph.invoke(None, cfg)`. The docs recommend it for debugging, not for HITL. It cannot carry a decision back in, so you would have to `update_state` the approval and then resume.

### Time travel: replay vs fork

```python
history = list(graph.get_state_history(cfg))                 # newest first
before = next(s for s in history if s.next == ("approve",))
graph.invoke(None, before.config)                            # replay: re-runs approve -> interrupts again
fork_cfg = graph.update_state(before.config, {"...": "..."}) # fork: new checkpoint with edited values
graph.invoke(None, fork_cfg)
```

### Store: long-term, cross-thread memory

```python
def model(state, runtime: Runtime):
    prior = runtime.store.search(("triage_memory",), limit=5)    # read across threads
    ...
    runtime.store.put(("triage_memory",), state["alert_id"], {"action": action})
```

Checkpointer state is per thread (short-term, conversation-scoped). The Store is global and namespaced (long-term: user profiles, past resolutions, learned runbooks). The Academy's Memory Schema lessons cover the two common store shapes: a **profile** (one document you keep updating) and a **collection** (many small documents you search).

### Double texting

What happens when a second message arrives for a thread while a run is in flight? LangSmith Deployment (the Agent Server) offers four strategies: **reject**, **enqueue** (the default), **interrupt** (stop the current run, keep its progress, continue with the new input), and **rollback** (undo the current run, including its input, and start fresh). The docs state that this feature is **not** in open-source LangGraph. On OSS you implement it yourself, usually as a per-thread lock or queue in front of `invoke`. That is a concurrency-control choice, the same one you make for any single-writer aggregate ([Module 06](../06-agent-architectures/README.md)).

## Worked example: crash, resume, fork, and the replay trap

All of this is in [`code/test_langgraph_durability.py`](code/test_langgraph_durability.py) and passes offline.

**1. Crash mid-run.** `FlakyWorld.query_logs` raises `TimeoutError` once, like a Loki query timing out.

```python
with pytest.raises(TimeoutError):
    lg.start(graph, "ALERT-4211", "t1")
assert graph.get_state(lg.thread("t1")).next == ("tools",)   # the failed node runs next
assert len(client.calls) == 2
out = graph.invoke(None, lg.thread("t1"))                     # retry: no new input
assert len(client.calls) == 3                                 # earlier model turns NOT re-run
```

The raw loop has no equivalent. The exception unwinds the stack and the transcript goes with it.

**2. Fork: "what if the human had said no?"** After an accepted restart, find the checkpoint before `approve`, replay from it, and answer differently:

```text
== 3. time travel: fork before approval, replay with a rejection ==
re-paused: True
DIAGNOSIS: checkout-api connection pool exhausted by a leak in OrderRepository.findOpen.
ACTION: restart was rejected by the on-call human; paging checkout-api owners.
restarts (unchanged, fork never restarted): ['checkout-api']
```

This is a cheap way to build eval cases for decision points: fork every historical incident at its approval checkpoint and replay with each decision.

**3. The replay trap (bad version).** Suppose `restart_service` had no idempotency key. Replaying from step 6 (`next == ('tools',)`, approvals already recorded) re-executes the `tools` node, and the service restarts again. Nothing in LangGraph prevents that: the checkpoint says "tools is next", and it runs.

**Good version.** `OpsWorld.execute` dedupes on `tool_use_id`, which is stable because it is part of the checkpointed assistant message. On a duplicate it returns the **stored original result**:

```python
before_restart = next(s for s in history if s.next == ("tools",) and s.values.get("approvals"))
replayed = graph.invoke(None, before_restart.config)   # re-executes the tools node
assert world.restarts == ["checkout-api"]              # deduped by tool_use_id, not by luck
assert replayed["final_text"] == original["final_text"]
```

The last assertion matters, and the first draft of this module got it wrong. The dedupe originally returned `"already restarted ... (idempotent no-op)"`. That was safe for the service, but the model then saw a *different* tool result on replay, and the scripted policy produced a different final diagnosis. An idempotent tool for agents has to keep the Stripe contract: a replayed key returns the original response, not a description of the replay. In production, pass that id to the ops API as an idempotency key, exactly as you would for a payment.

**4. The Store is not rolled back.** After the fork, the long-term memory for `ALERT-4211` says "rejected". The fork's outcome overwrote the real one, because the Store sits outside the checkpoint log:

```python
assert "rejected" in store.get(lg.MEMORY_NS, "ALERT-4211").value["action"]
```

If you use time travel for "what if" analysis, point the forked run at a scratch Store namespace.

## Pitfalls

- **Side effects before `interrupt()` in the same node.** They run twice. Detection: a test that counts calls across interrupt and resume. Fix: put the side effect in its own node after the gate.
- **Non-idempotent side-effect nodes.** Replay, retry after crash, and fork all re-run them. Detection: the replay test above. Fix: idempotency keys derived from checkpointed data (`tool_use_id`), never from `uuid4()` called inside the node.
- **Non-determinism inside nodes on replay.** `datetime.now()` or a random choice inside a node gives a different branch on replay. Put such values in state at the step that first needs them.
- **`MemorySaver` in production.** Parked approvals vanish on deploy. Detection: kill the worker while a run is parked, then try to resume.
- **Resuming with the wrong `thread_id`.** A new id starts an empty thread. There is no error, just a fresh run. Detection: assert that `get_state(cfg).next` is non-empty before you resume.
- **Treating the Store as transactional with the checkpoint.** It isn't. Writes to the Store survive forks and failed runs.
- **Assuming double-texting protection on OSS.** It is a Deployment feature. Add your own per-thread lock.

## In your day job

- Model each incident, PR or ticket as one `thread_id`. You then get resumability, auditing and "what did the agent know at 03:14" for free.
- Put every mutating tool behind a gate node and an idempotency key. Write the replay test before you ship.
- Use Postgres checkpointers with `durability="sync"` for anything that touches production. Use `"exit"` only for batch jobs you can re-run from the start.
- Mine `get_state_history` for eval data: every approval checkpoint is a labelled decision point ([Module 13](../13-testing-agentic-systems/README.md)).
