# 05: Durable runs: event-sourced logs, checkpoints, resume, idempotent tools

## The idea

An agent run is a long-lived process that makes **nondeterministic decisions** and causes **side effects**. If it can crash and restart, which every process eventually does, you need two guarantees:

1. **Resume continues the same run.** After a crash, the run carries on with the same decisions instead of making new ones.
2. **Each logged side effect happens once.** A retry never opens a second ticket, sends a second email, or issues a second refund.

The standard design is **event sourcing**. Every decision and observation is appended to a log before anything depends on it. Run state is `fold(log)`. Checkpoints are snapshots that make the fold fast, and the log remains the source of truth. Side-effecting tools receive an **idempotency key derived from the logged tool call**.

If you have used Temporal or Azure Durable Functions, this is workflow history plus activities. The one AI-specific twist is in invariant 2 below.

## Why it matters

- Anthropic's research system: errors compound over long runs, so they "built systems that can resume from where the agent was when the errors occurred", combined with retry logic and regular checkpoints. They also use **rainbow deployments** "to avoid disrupting running agents", since agents are always mid-run when you deploy ([Anthropic, multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system)).
- Anthropic's Managed Agents virtualizes the session as an **append-only event log**, separate from the harness (the loop) and the sandbox. A harness crash is recovered by waking the session and replaying the log, and containers become "cattle" ([Anthropic, "Scaling Managed Agents"](https://www.anthropic.com/engineering/managed-agents)).
- Claude Code checkpoints file edits before applying them, but the docs are explicit that remote side effects cannot be checkpointed ([Claude Code docs, how it works](https://code.claude.com/docs/en/how-claude-code-works)). A local undo does not undo a POST.
- Anthropic's scheduled-automation guidance has the same shape: check whether today's post already exists before posting, count a post as sent only on an explicit success, and otherwise record "maybe posted" ([Anthropic, "Building effective agent automations"](https://claude.dev/blog/building-effective-agent-automations/)). "Maybe posted" is an in-doubt state.
- Claude Code's dynamic workflows make `Date.now()` and `Math.random()` throw, so a resumed run replays the same calls ([Claude Code docs, workflows](https://code.claude.com/docs/en/workflows)). That is Temporal's determinism rule, adopted for agent orchestration.

## How it works

### The invariants

1. **Log before you depend.** The model's response is logged before any tool runs. A `tool_intent` is logged before any side effect.
2. **Replay model outputs, never re-sample them.** This is the AI-specific rule. In Temporal, re-executing workflow code is safe because the code is deterministic. A model is not deterministic, even at temperature 0 across infrastructure changes. Re-asking it after a crash can produce a *different* tool call with a *different* id. The idempotency key then changes, and the side effect happens twice. So the log stores model outputs, and resume reads them instead of calling the model.
3. **The key derives from the logged decision:** `f"{run_id}:{tool_call_id}"`. Hashing the tool *input* is not enough. On a re-sample the model writes `"notify-svc lag 512k"` instead of `"notify-svc lag 512k on user-events"`, gets a new hash, and opens a new ticket.
4. **Intent without result means in doubt.** On resume, a `tool_intent` with no `tool_result` means the effect may or may not have happened. If the remote honours idempotency keys, retry with the same key. If it doesn't, stop and escalate. This is the in-doubt transaction of 2PC, and you resolve it the same way: ask the participant, or ask a human.
5. **Checkpoints are an optimization.** `fold(events)` from the start must equal `fold(events)` from the latest checkpoint. The tests check this for every prefix of a real log.

### The log and the fold ([`code/run_log.py`](code/run_log.py))

Events: `run_started`, `llm_response` (the full serialized `Response`), `tool_intent` (call id and key), `tool_result`, `checkpoint` (step and messages), and `run_finished`.

```python
def resume(self) -> str:
    """Idempotent itself: calling resume on a finished run returns the logged answer."""
    while True:
        st = fold(self.log.events())            # all state is derived; nothing lives only in memory
        if st.finished:
            return st.final_text
        if st.pending:                           # logged tool calls without results: execute them
            for call in st.pending:
                self._execute(call, st)
            self.log.append("checkpoint", step=st.step, messages=fold(self.log.events()).messages)
            continue
        if st.step >= self.max_steps:
            self.log.append("run_finished", text="[stopped: step budget exhausted]")
            continue
        resp = self.client.complete(st.messages, system=self.system, tools=[...])
        self.log.append("llm_response", step=st.step + 1, response=resp.to_dict())
        if not resp.tool_calls:
            self.log.append("run_finished", text=resp.text)
```

And the side-effect path:

```python
key = f"{self.run_id}:{call['id']}" if tdef.side_effecting else None
if tdef.side_effecting:
    if call["id"] in st.intents and not tdef.idempotent:
        raise InDoubt(f"{call['name']} {call['id']} may have run; no idempotency guarantee")
    if call["id"] not in st.intents:
        self.log.append("tool_intent", call_id=call["id"], name=call["name"], key=key)
content = tdef.fn(call["input"], key)            # the remote dedups on key
self.log.append("tool_result", call_id=call["id"], content=content, is_error=False)
```

The log reader ignores a torn final line, so a crash in the middle of a write doesn't corrupt the fold. Same rule as a WAL with a checksum per record. A production version would use a real checksum.

### The crash matrix

Each row is a parametrized test in `test_durability.py`:

| Crash point | What's in the log | Resume does | Tickets | Model calls |
|---|---|---|---|---|
| after `llm_response` | decision, no intent | executes the logged call | 1 | 3 (no re-sample) |
| after `tool_intent` | intent, no effect | executes with the same key | 1 | 3 |
| **after the side effect, before `tool_result`** | intent, effect happened | retries with the same key; the remote dedups | 1 | 3 |
| same, but the remote ignores keys | | retries | **2** | 3 |
| same, tool marked `idempotent=False` | | raises `InDoubt` | 1 (human decides) | 2 |

Row 3 is the one that matters. Without the intent record and the key, it is indistinguishable from row 2, and you either skip a real action or repeat one.

## Worked example: an on-call agent that opens tickets

**Task:** "Check notify-svc consumer lag and open a ticket if it is above 100k." Tools: `get_consumer_lag` (read) and `create_ticket` (write).

### Bad: the job runner retries the whole agent

```python
@retry(times=3)                 # the platform's generic retry
def handle_alert(alert):
    return agent_loop(client, f"Check {alert.group} lag and open a ticket if > 100k", tools)
```

The process is OOM-killed after `create_ticket` returns but before the agent finishes. The retry starts from scratch:
- It calls the model again. This time the model writes the title as `"notify-svc consumer lag 512k"`.
- `create_ticket` gets no key, or a key hashed from the new input, so it creates `OPS-1001`.
- On-call now has two tickets, and the dedup bot can't merge them because their titles differ.

This is the at-least-once trap. The retry was correct in itself, but the operation behind it was not idempotent, because its identity was regenerated on every attempt.

### Good: a durable run

`python code/run_log.py` crashes the run right after the side effect, then resumes it from the log. This is real output from the offline script, with a scripted fake model:

```text
crashed at after_side_effect; tickets so far: ['OPS-1000']
resumed -> Opened OPS ticket for notify-svc lag (512k).
tickets: ['OPS-1000']
0 run_started {}
1 llm_response {'step': 1}
2 tool_result {'call_id': 'toolu_01'}
3 checkpoint {'step': 1}
4 llm_response {'step': 2}
5 tool_intent {'call_id': 'toolu_02', 'key': 'run-42:toolu_02'}
6 tool_result {'call_id': 'toolu_02'}
7 checkpoint {'step': 2}
8 llm_response {'step': 3}
9 run_finished {}
```

Read the log as a senior engineer would:
- Event 4 recorded the decision to create a ticket, including the exact input.
- Event 5 recorded the intent with key `run-42:toolu_02`, and then the process died.
- On resume, the fold found intent 5 with no result, called `create_ticket` again with the same key, and the API returned the existing `OPS-1000`. Event 6 is that result.
- The model was called three times in total across both processes. The test asserts `len(client.calls) == 3`, which proves that resume did not re-sample.

## Pitfalls

- **Keys from input hashes.** Detect it by looking for `hash(json.dumps(input))` in tool wrappers. Derive keys from the logged call id instead.
- **Logging after acting.** If the `llm_response` event is written after the tools run, a crash in between loses the decision. Detect it by reading the order of appends in the loop.
- **Treating checkpoints as truth.** If you snapshot only messages and drop the log, you can't answer what happened, can't audit, and can't time-travel. Detect it by asking whether you can rebuild the state at step 3 from storage.
- **Remotes that ignore keys.** Many internal APIs don't support idempotency keys. Detect it by reading the API's contract. Then wrap the remote with a dedup table on your side (a `(key → result)` store written in the same transaction as the effect), or mark the tool `idempotent=False` so it fails into `InDoubt`.
- **Deploying mid-run.** A new harness version folding an old log can misread events. Version the event schema, and use rainbow deploys or drain-and-resume ([15-observability-and-production](../15-observability-and-production/README.md)).
- **Logging secrets and huge payloads.** Tool results land in the log verbatim. Store references to blobs, and redact credentials at the tool boundary ([16-security-and-containment](../16-security-and-containment/README.md)).

## In your day job

- List every side-effecting tool your agent can call, and record next to each whether the remote honours an idempotency key. Anything marked "no" needs a dedup wrapper or an `InDoubt` path.
- Don't let a generic job-level retry wrap an agent. Retry the *step* from the log.
- When adopting a framework, check its checkpointer semantics against these invariants: LangGraph persists a checkpoint per super-step on a thread, and supports time travel from any checkpoint ([09-frameworks-langchain-langgraph](../09-frameworks-langchain-langgraph/README.md)). Ask whether it logs model outputs and whether tools get a stable key.
- Use the run log for record/replay testing as well ([13-testing-agentic-systems](../13-testing-agentic-systems/README.md)). A logged run is a fixture.
