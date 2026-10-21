# 04: Mid-run steering: interrupt, redirect, goal, restart

## The idea

Gates catch a bad *result*. Steering changes a bad *trajectory* while it's still cheap to change. You have four moves, ordered by how much state you throw away:

| Move | What survives | Use when |
|---|---|---|
| **Queue a message** | everything; the agent reads your note after its current tool calls finish | small correction, the agent is broadly on track |
| **Interrupt (Esc) and redirect** | the work done so far; the current response or tool call stops | it's heading the wrong way *now* |
| **Rewind (Esc Esc) to a checkpoint** | the conversation and code up to a chosen earlier point | a wrong turn several steps back poisoned what followed |
| **`/clear` and restart** with a better prompt | only what you carry over by hand (and files and git) | corrections aren't sticking; the context is full of a wrong theory |

A fifth primitive turns the loop around: **`/goal`** tells the session to keep taking turns until a separate evaluator judges a condition met. That is steering by *end state* instead of by step.

The skill is choosing the right move and writing a nudge that actually changes behavior. Most bad nudges fail for the same reason bad instructions fail ([01](01-checks-not-instructions.md)): they are vague, they carry no evidence, and they give no check.

Distributed-systems anchor: the agent is a long-running job, and you are the control plane. Queuing a message is a config push the worker picks up at its next safe point. Esc is SIGINT with graceful handling. Rewind is restoring from a snapshot. `/clear` is killing the pod and rescheduling from the spec. As with pods, restarting from a good spec usually beats live-patching a process whose in-memory state is corrupt.

## Why it matters

Anthropic's best-practices page is blunt about the failure pattern it calls "correcting over and over": after two failed corrections, `/clear` and write a better prompt, because "a clean session with a better prompt almost always outperforms a long session with accumulated corrections" ([Claude Code docs, "Best practices"](https://code.claude.com/docs/en/best-practices)). The mechanism is the one from [Module 03](../03-context-engineering/README.md). Every failed attempt and every rebuttal stays in context, and the model keeps conditioning on its own wrong theory. Dex Horthy's research-plan-implement workflow makes the same move at the planning stage: throw away wrong research and rerun it with more steering, rather than patching it ([HumanLayer, ACE-FCA](https://github.com/humanlayer/advanced-context-engineering-for-coding-agents/blob/main/ace-fca.md)).

## How it works

### Claude Code primitives (verified against the docs 2026-10-19)

From [interactive mode](https://code.claude.com/docs/en/interactive-mode):

- **Type and press Enter while Claude works** to queue a message. If Claude is running tool calls, the message is passed "as soon as those tool calls finish, within the same turn." `Ctrl+Enter` sends queued messages right away. `Up` takes queued messages back for editing.
- **`Esc`** stops "the current response or tool call mid-turn so you can redirect. Claude keeps the work done so far." Queued messages are sent next.
- **`Esc` + `Esc` on an empty prompt** opens the rewind menu "to restore or summarize code and conversation from a previous point" ([checkpointing](https://code.claude.com/docs/en/checkpointing)). File edits are checkpointed, but remote side effects (a push, a deploy, a DB write) are not ([how Claude Code works](https://code.claude.com/docs/en/how-claude-code-works)).
- **`Ctrl+G`** opens your prompt in `$EDITOR`. Use it for any nudge longer than two lines, so you write it rather than blurt it.
- **`/clear`** starts a new conversation. It also removes any active `/goal`.

### `/goal` (verified against [the /goal docs](https://code.claude.com/docs/en/goal) 2026-10-19)

```text
/goal all tests in test/auth pass and the lint step is clean; no file under test/ is modified; or stop after 20 turns
```

- After each turn, the condition and conversation go to the configured small fast model. It returns **not yet met** (the reason becomes guidance for the next turn), **met**, or **impossible**.
- The evaluator "doesn't run commands or read files independently". It judges only what the worker surfaced in the transcript. So write conditions that the worker's own output can demonstrate ("`npm test` exits 0"), and include constraints ("no other test file is modified") and a budget clause.
- If Claude makes no tool calls for several turns in a row, the loop stops and hands control back. Auth failures, an exhausted credit balance, unrecoverable context overflow and an unavailable model all clear the goal.
- `/goal` with no argument shows status, turns and spend. `/goal clear` removes the goal. `claude -p "/goal ..."` runs it non-interactively; add `--output-format stream-json --verbose` to watch progress.

**`/goal` vs a Stop gate.** `/goal` is a wrapper around a session-scoped *prompt-based* Stop hook. Its strength is that "completion is decided by a fresh model rather than the one doing the work". Its weakness is that the evaluator believes the transcript. "No file under test/ is modified" is judged from what the worker *said*, not from `git diff`. The robust combination is to use `/goal` for "keep going", plus `stop_gate.py` for "and here is what actually counts as done".

### OpenAI's steer API (as documented, GPT-6 family)

OpenAI's Responses API has a protocol-level steering primitive ([OpenAI, "Steering"](https://developers.openai.com/api/docs/guides/steering), read 2026-10-19):

- Over a WebSocket, after `response.created`, the client sends `response.steer` with `previous_response_id` and `input`. The server replies `response.steer.accepted` or `response.steer.failed`.
- "Acceptance means the input is queued, not that the model has acted on it." The server creates the continuation itself, so you should not send another `response.create`.
- If steering interrupts the response, it ends `response.incomplete` with `incomplete_details.reason: "steered"`.
- Steering "does not cancel tools that have already started", and earlier actions are not undone.
- Queued steering "exists only on the current connection". Your client must record what it sent and reconcile after a disconnect. The docs say GPT-5.6 and earlier don't support it.

You know these semantics well. **Accepted is not applied** (a produce ack is not consumer processing). **Delivery is at-most-once per connection.** **Actions in flight are not rolled back.** So treat a steer like a message on an unreliable channel. Give it an idempotency key in your own log, reconcile it against the response history after reconnecting, and never assume a steer stopped a side effect. If the side effect matters, the gate belongs in the tool (an approval tier, [06](06-human-in-the-loop.md)), not in the steer.

### Writing a nudge that works

| Works | Doesn't |
|---|---|
| **Evidence**: the exact failing line, log or diff hunk | "That's wrong" |
| **A falsifiable hypothesis or a constraint**: "the rebalance happens because processing exceeds `max.poll.interval.ms`" | "Think harder" |
| **A scope fence**: "don't touch the retry wrapper or any test" | "Be careful" / "IMPORTANT!!!" |
| **A check**: "run `pytest -q tests/test_rebalance.py -x` and show the output" | "Make sure it works" |
| **One change at a time** | a list of seven new requirements |
| **Stop and ask if X**: an explicit exit | a silent expectation |

A nudge like this is a miniature spec: evidence, constraint, check. Emotional emphasis and repetition add no information. Anthropic's own guidance is to use emphasis like IMPORTANT sparingly ([best practices](https://code.claude.com/docs/en/best-practices)), because it skews the weight of one line against everything else.

### When to restart instead of argue

Restart (`/clear`, or a fresh `claude -p` with a rewritten prompt) when:

- you have corrected the same thing twice,
- the agent is defending a theory you've falsified,
- context is above roughly half full of a wrong approach (Horthy's 40–60% utilization guidance is a useful marker),
- or the agent has started editing the checks ([05](05-detecting-drift.md)).

Before you restart, write down what you learned (the falsified hypotheses, the real constraint) and put it in the new prompt or a `NOTES.md`. The restart then carries the knowledge without the poison.

## Worked example: redirecting a Kafka consumer fix

The task: *"Consumer group `orders-billing` keeps rebalancing under load. Fix it."* The service is a Python consumer using `confluent-kafka`. This is an illustrative transcript, condensed from typical sessions and not a recorded run.

```text
> Consumer group orders-billing keeps rebalancing under load. Fix it.

● Read consumer/worker.py, consumer/settings.py
● I'll add a retry wrapper with exponential backoff around process_batch() so transient
  failures don't crash the consumer, and increase session.timeout.ms to 60000.
● Write consumer/retry.py
● Edit consumer/worker.py
● Edit requirements.txt   (+ tenacity==9.0.0)
```

**Bad nudge 1** (queued):

```text
> no that's not right, try again
```

*(illustrative output)* The agent apologizes, bumps `session.timeout.ms` to 120000, and keeps the retry wrapper. You gave it no information, so it changed the thing it was least sure about.

**Bad nudge 2**:

```text
> IMPORTANT: be careful, this is production code. Don't add unnecessary stuff. Make sure it actually works this time!!
```

*(illustrative output)* The agent removes the `tenacity` dependency, writes its own backoff loop instead, and adds a long docstring explaining why. "Unnecessary" was undefined, so it pruned what *it* considered unnecessary.

That's two failed corrections. The guidance says restart, but first you get the evidence yourself. It takes two minutes in the logs:

```text
WARN Rebalance triggered: member orders-consumer-3 left group (max.poll.interval.ms exceeded)
DEBUG batch=500 records, process_batch took 412s
```

**Good nudge** (press Esc, then `/clear`, then write the prompt in `Ctrl+G`):

```text
The orders-billing consumer rebalances because members exceed max.poll.interval.ms (default 300s):
the logs show "left group (max.poll.interval.ms exceeded)" and process_batch taking ~412s for
max.poll.records=500. session.timeout.ms is not the cause (heartbeats run on a background thread).

Constraint: don't add dependencies, don't add retries, don't change session.timeout.ms, don't touch tests
other than adding one.
Do: make one batch finish well within max.poll.interval.ms. Options, pick one and say why:
reduce max.poll.records, or move slow I/O out of the poll loop with pause()/resume().
Check: add a test in tests/test_worker.py that drives a 500-record batch through a fake slow sink and
asserts poll() is called again within the interval; run `pytest -q tests/test_worker.py -x` and show it.
If neither option works without changing the commit semantics, stop and tell me.
```

*(illustrative output)* The agent picks `pause()`/`resume()` with a bounded in-memory queue, explains that this preserves at-least-once delivery because offsets are still committed after the sink acks, adds the test, and shows it passing. The diff touches two files.

The good nudge worked because it moved the *diagnosis* out of the agent's hands. You supplied the falsified theory (session timeout), the evidence (412 s against 300 s), a fence (no retries, no dependencies), and a check. The agent did what it is good at, which is implementing within constraints, instead of what it was doing badly, which was guessing at a root cause.

## Pitfalls

- **Queuing a correction behind a side effect.** A queued message lands *after* the current tool calls, so if the current call is `git push`, the correction is too late. *Detect:* if the next action is irreversible, press Esc instead of queuing. Better still, gate it with `ask` ([07](07-permissions-as-guardrails.md)).
- **Assuming rewind undoes the world.** Checkpoints restore files and conversation, not remote state. *Detect:* before you rewind, check for pushes, deploys, migrations or messages sent since that checkpoint.
- **`/goal` conditions the evaluator can't verify from the transcript.** "The code is clean" isn't checkable. "`make lint` exits 0" is, *if the worker runs it*. *Detect:* read the evaluator's reasons (Ctrl+O). If they say "Claude states that...", the condition is being judged on claims.
- **Steers treated as delivered.** For the OpenAI API, a disconnect drops queued steers. *Detect:* reconcile your steer log against the response events after every reconnect.
- **Arguing past two rounds.** *Detect:* count your corrections. A third means it's time for `/clear` and a rewritten prompt.

## In your day job

- Keep a scratch file open while you supervise. When you notice something, write evidence, constraint and check there, then send it with `Ctrl+G`. Don't type corrections in a hurry.
- Set a personal rule: two failed corrections means `/clear`, and the new prompt includes what you learned.
- Use `/goal` for long mechanical work, such as migrating call sites until the build is green, always with a budget clause, and with a Stop gate as the source of truth.
- If you build on a steer API, write the reconciliation logic first. It is the same at-most-once delivery problem you have solved before.
