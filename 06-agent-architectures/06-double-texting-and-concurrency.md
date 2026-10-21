# 06: Double texting: concurrent user input during a run

## The idea

**Double texting** is LangChain's name for a user sending a new message on a thread while a run on that thread is still in flight ([LangSmith docs, double texting](https://docs.langchain.com/langsmith/double-texting)). It is a concurrency-control problem on a per-thread aggregate. The thread is the aggregate, a run is a transaction that writes to it (one checkpoint per step), and the new message is a concurrent writer.

LangSmith Deployment (the Agent Server) offers four strategies. These definitions are paraphrased from the docs as of October 2026:

| Strategy | Behaviour | DS equivalent |
|---|---|---|
| **enqueue** (the default) | The current run finishes, then the new input runs. | Per-key FIFO, one consumer per partition: serializable by construction |
| **reject** | New runs are refused while one is in progress. | Try-lock that fails fast (HTTP 409) |
| **interrupt** | Halt the current run, *keep* progress up to that point, insert the new input, and continue from that state. | Preemption at a safe point, with partial results kept |
| **rollback** | Halt the current run, revert *all* its progress *including its original input*, and run the new input fresh. | Transaction abort and restart |

The docs describe double texting as a feature of the deployment server, not of the open-source LangGraph library, and the SDK exposes the choice as a per-run multitask strategy. Check the current API reference for the exact parameter before you rely on it. Claude Code has its own version: a message queued mid-turn is read after the current tool calls finish ([Claude Code docs](https://code.claude.com/docs/en/how-claude-code-works)), which is enqueue at tool-call granularity, used for steering.

## Why it matters

Users double-text all the time: "wait, I meant order 7713", "also check staging", "stop". An agent product without a deliberate policy gets one by accident, usually *concurrent*: both runs write to the thread at once. Two things then break:

1. **The transcript becomes invalid.** In the Anthropic Messages API, every `tool_use` block must be answered by a `tool_result` in the next user turn. Interleave two runs and run 1's `tool_use` is followed by run 2's user message, so the next model call on that thread fails. Worse, the model gets confused about which reply belongs to which question.
2. **Side effects from stale intent.** The first run carries on acting on the request the user just corrected.

Interrupt and rollback each have a subtler failure, and they are the reason a distributed-systems engineer should own this decision rather than leave it to a UX default.

## How it works

[`code/double_texting.py`](code/double_texting.py) is a deterministic discrete-time simulator. A run is a list of steps (`think`, `tool_use`, `tool_result`, `reply`). Each step commits a checkpoint to the thread and bumps its version. A step can carry an external side effect, such as `refund:7731`. The simulator runs each policy over the same arrivals and reports the final thread, the world's side effects, warnings, and `validate_transcript()` errors, which applies the tool_use/tool_result pairing rule.

### Failure mode by policy

**reject.** Simple and safe for the thread, but the correction is lost and the stale intent completes. Acceptable for API clients that can retry on a 409. Hostile in a chat UI.

**enqueue.** The thread stays valid, but the stale run finishes first, including its side effects. Safe for the *thread*, not for the *world*. Run 2 does at least see what run 1 did, so the model can compensate ("refund 7731 was issued; reversing it").

**interrupt.** Responsive, and progress is kept. The danger is preempting between `tool_use` and `tool_result`. You must insert a synthetic `tool_result` to keep the transcript valid, and it must tell the truth:
- If the tool hadn't run: `"cancelled"`.
- If the tool *had* run: say so (`"executed; result not observed"`). Telling the model "cancelled" when the refund went through creates a model whose beliefs diverge from the world.

**rollback.** The thread is clean, because it reverts to before the run's input. But rollback reverts *your* state, not the world's. If the run already issued the refund, the refund still happened, and now the thread has no record of it. The new run cannot compensate for something it can't see. This is the saga problem: an abort needs explicit **compensating actions** for every external effect, and those can't be recovered from a rolled-back history.

**concurrent + OCC.** If every step commits with compare-and-set on the thread version, the user's new message bumps the version, and the in-flight run's next commit fails, so the stale run is stopped. But OCC *detects* the conflict without *deciding* what happens next. The loser's partial writes (a dangling `tool_use`) remain, and you still need interrupt-style cleanup. OCC is a mechanism, and you still have to choose a policy.

### Choosing

| Surface | Recommended | Why |
|---|---|---|
| Chat agent with read-only tools | interrupt | Responsiveness matters, and nothing to compensate |
| Agent with side-effecting tools | **enqueue** by default, or **adaptive** (below) | Never lose track of an effect |
| Programmatic API or batch | reject (409 + Retry-After) | Callers can serialize, and you shouldn't guess |
| "Correction" UX on a run with no effects yet | rollback | Cleanest state, since there's nothing to compensate |

> **Synthesis:** a policy that is safe in every case picks per run, based on whether the run has crossed a side-effect boundary. The simulator's `adaptive` policy rolls back if the in-flight run has produced no external effects, and otherwise interrupts with a truthful synthetic result. It is the same reasoning as "abort is free until you've sent a message outside the transaction". A property-based test checks that every non-concurrent policy, including `adaptive`, keeps the transcript API-valid for any arrival pattern.

## Worked example: the refund correction

**Situation.** A support agent with an `issue_refund` tool. The user writes "please refund order 7731" and, a moment later, "sorry, refund order 7713 instead". In the simulation the refund tool fires at tick 3.

### Bad: no policy (concurrent)

Real output from `python code/double_texting.py`. The model is a scripted step planner, but the policies and validator are real code:

```text
#### early correction (tick 2, before the refund fires)
== concurrent runs=[(1, 'completed'), (2, 'completed')] world=['refund:7731', 'refund:7713']
   ! message 1: tool_use:r1:lookup_order not followed by its tool_result (got 'user:r2:sorry, refund order 7713 instead')
   ! message 4: tool_use:r1:issue_refund not followed by its tool_result (got 'tool_use:r2:lookup_order')
   ! message 5: tool_use:r2:lookup_order not followed by its tool_result (got 'tool_result:r1:issue_refund')
```

The correction arrived *before* the refund fired, yet both refunds happen, and the thread is now one the API will reject on the next call.

### Good: pick the policy deliberately, and know its failure mode

Same arrivals:

```text
== reject     runs=[(1, 'completed'), (2, 'rejected')] world=['refund:7731']
== enqueue    runs=[(1, 'completed'), (2, 'completed')] world=['refund:7731', 'refund:7713']
== interrupt  runs=[(1, 'interrupted'), (2, 'completed')] world=['refund:7713']
   ! r1: interrupted between tool_use and tool_result; inserted a synthetic 'cancelled' tool_result
== rollback   runs=[(1, 'rolled_back'), (2, 'completed')] world=['refund:7713']
== adaptive   runs=[(1, 'rolled_back'), (2, 'completed')] world=['refund:7713']
```

Now the *late* correction, arriving after the refund fired:

```text
== interrupt  runs=[(1, 'interrupted'), (2, 'completed')] world=['refund:7731', 'refund:7713']
   ! r1: interrupted between tool_use and tool_result; inserted a synthetic 'executed-result-not-observed' tool_result
== rollback   runs=[(1, 'rolled_back'), (2, 'completed')] world=['refund:7731', 'refund:7713']
   ! r1: rolled back thread state, but side effect 'refund:7731' already happened in the world; compensation needed
== adaptive   runs=[(1, 'interrupted'), (2, 'completed')] world=['refund:7731', 'refund:7713']
```

Read the late case carefully. Every policy leaves both refunds in the world, because the first refund really happened. The policies differ in **what the next run knows**:
- With interrupt or adaptive, run 2's transcript says refund 7731 executed. A real model can now reverse it, or ask the user before doing so.
- With rollback, run 2's transcript has *no trace* of 7731. Only the warning, which goes to your ops channel and not to the model, knows a compensation is owed.

The simulator's planner doesn't compensate, because it isn't a model. In production, making that compensation possible is the job of the interrupt path, and the job of the run log from [05](05-durable-runs-event-sourcing-idempotency.md): the effect is in the log even if it is no longer in the thread.

## Pitfalls

- **Lying synthetic tool results.** Detect it by grepping your interrupt handler for a hard-coded "cancelled" string, and checking whether it consults the run log for completed side effects.
- **Rollback with side-effecting tools.** Detect it with a static check: if any tool is marked side-effecting and the thread's strategy is rollback, fail the config lint, unless effects trigger compensation.
- **Assuming enqueue is safe for the world.** It is safe for the thread. Detect it by asking whether a queued correction can arrive after an irreversible step. If it can, add a confirmation step before irreversible tools ([14-steering-and-guardrails](../14-steering-and-guardrails/README.md)).
- **No policy at all.** Two browser tabs on one thread is enough to trigger it. Detect it by running two concurrent requests against a staging thread and calling `validate_transcript`.
- **Preempting mid-tool.** Interrupt should take effect at step boundaries, not inside a tool's execution. Detect it by checking whether your cancel path can kill a tool process halfway through a write.

## In your day job

- Write down the double-texting policy per agent surface, in the same doc as your API's concurrency semantics.
- Make the interrupt handler consult the run log, so the synthetic result reflects what actually happened.
- Add `validate_transcript` as an assertion in your agent's integration tests, along with a test that sends two messages 200 ms apart.
- For side-effecting agents, treat "a correction arrived after an irreversible step" as a first-class product flow: confirm, compensate, or escalate.
