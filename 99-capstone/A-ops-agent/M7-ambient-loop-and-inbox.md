# A-M7: Run it as a scheduled, ambient loop with an inbox
**Time:** one weekend. **Offline:** yes, entirely (the incident stream is simulated). **Modules:** [07](../../07-loops/README.md), [06](../../06-agent-architectures/README.md), [14](../../14-steering-and-guardrails/README.md), [15](../../15-observability-and-production/README.md).

## Goal
Stop running the agent by hand. Run it on a schedule against a stream of incidents, have it act within its earned autonomy and put everything else in an inbox for a human, and prove that a crash or a double fire neither loses nor duplicates work.

## Why it matters
Scheduled agents fail quietly. Anthropic's guide to scheduled agent automations lists the usual ways: the agent loses access to a source or drifts from preferences, and nobody notices ([Anthropic, "Building effective agent automations"](https://claude.dev/blog/building-effective-agent-automations/)). A distributed-systems engineer already knows the cures: bookmarks, idempotency keys, ledgers, at-least-once delivery with deduplication. This milestone makes you apply them to an agent.

On the human side, LangChain's ambient-agents post describes three human-in-the-loop patterns, **notify**, **question** and **review**, and an inbox UI built on ticket-queue metaphors because Slack notifications got lost ([Harrison Chase, "Introducing ambient agents"](https://www.langchain.com/blog/introducing-ambient-agents)).

## Steps
1. **An incident stream.** Write `inbox/stream.py`: a deterministic generator of `(event_id, opened_at_tick, scenario_seed)` events, a few per simulated hour. It is the event source the scheduler reads from.
2. **A tick function** that processes all events after the bookmark, then advances it:
   ```text
   tick():
     events = stream.after(bookmark)
     for e in events:
         if ledger.has(e.event_id, status in {done, in_inbox}): continue      # idempotency
         decision = policy(e)                  # what autonomy level applies
         run agent in that mode, write result to ledger and inbox
     bookmark = last processed event_id (only after the ledger write commits)
   ```
   Use bookmarks, not time windows: "a late run leaves a gap and an early run repeats items" (same Anthropic guide).
3. **Modes from your M1 ladder.** For each action class, run in `auto`, `review` (agent proposes, inbox item asks for approval, approved actions apply on the next tick) or `shadow` (agent proposes, nothing applies, the grader scores the proposal for your track record).
4. **Inbox items** in a JSONL file, each with a stable id, type (`notify` / `question` / `review`), the evidence, the proposed action and a link to the trace. A tiny CLI lists, approves and rejects them.
5. **Idempotent mutations.** Each proposed action gets an idempotency key `(event_id, tool, service)`. Applying the same key twice is a no-op. Record "maybe applied" when you crashed between sending the action and recording success, and resolve it on the next tick by reading the world (the sim's deploy and replica state).
6. **Staleness re-check.** Before applying an approved `review` action, re-read metrics. If the incident cleared on its own, drop the action and say so.
7. **Budgets.** Per-run token cap, per-day cap across ticks, and a pause state (`budget_reached`) that creates a `notify` item rather than silently stopping. Anthropic's guide suggests starting the budget at 3 to 5x a normal run's cost (same source).
8. **Crash tests.** Inject a crash at each point in the tick (after the agent acts, before the ledger write; after the ledger write, before the bookmark). Re-run. Assert: no duplicate mutation, no lost event.

## Worked example: crash between act and record
Bad version:

```python
for e in stream.after(state.bookmark):
    result = run_agent(e)        # may call rollback(orders)
    state.bookmark = e.event_id  # crash here...
    ledger.append(e.event_id, result)   # ...and this never happens; next tick re-runs e
```

Re-running `e` calls `rollback(orders)` again. In the sim, a second rollback is harmless. In production, the second "rollback" might roll back the *fix*.

Better: write intent first, act, then confirm, and never advance the bookmark ahead of the ledger.

```python
def process(e, ledger, env_for):
    rec = ledger.get(e.event_id)
    if rec and rec["status"] in ("done", "in_inbox"):
        return
    if rec and rec["status"] == "acting":
        # We crashed mid-action last time. Reconcile from the world, not from memory.
        return reconcile(e, rec, env_for(e))
    ledger.put(e.event_id, status="acting", started_tick=now())
    result = run_agent(e)
    ledger.put(e.event_id, status="done" if result.applied_all else "in_inbox", result=result.summary)

def tick(state, ledger, stream, env_for):
    for e in stream.after(state.bookmark):
        process(e, ledger, env_for)
        state.bookmark = e.event_id          # only after the ledger says done or in_inbox
        state.save()
```

And the test:

```python
def test_crash_after_action_before_record_does_not_double_apply(tmp_path):
    led, st = Ledger(tmp_path / "ledger.jsonl"), State(tmp_path / "state.json")
    with pytest.raises(SimulatedCrash):
        tick(st, led, stream, env_for, crash_at="after_agent")
    tick(st, led, stream, env_for)                   # restart
    keys = [(e, r.tool, r.args["service"]) for e, env in envs.items() for r in env.log if r.tool in MUTATIONS]
    assert len(keys) == len(set(keys))              # each idempotency key applied once
    assert led.all_terminal()                        # nothing lost
```

## An inbox item that earns trust
Anthropic's guide has a line worth adopting as a rule: "One stale "still waiting on you" costs more trust than ten missing items, so never hedge an item's status: assert it or drop it" ([Building effective agent automations](https://claude.dev/blog/building-effective-agent-automations/)).

```json
{"id": "inbox-0192", "type": "review", "event_id": "evt-0441", "created_tick": 1288,
 "title": "Roll back payments v2.3.1 (deployed 18 min before alert)",
 "evidence": {"payments.error_rate": 0.25, "orders.error_rate": 0.15, "deploy": "v2.3.1 code, 18 min"},
 "proposed": {"tool": "rollback", "args": {"service": "payments"}, "idempotency_key": "evt-0441:rollback:payments"},
 "mode": "review (rollback is at 'review' on the autonomy ladder)",
 "trace": "runs/ambient/traces.jsonl#trace=7c1e9a"}
```

## Deliverables
- `inbox/` with stream, tick, ledger, state, inbox CLI
- Crash tests at each crash point; double-fire test (two ticks start concurrently, or the same tick twice)
- A 24-simulated-hour run report: events processed, actions auto-applied, inbox items by type, approvals, budget usage, any `maybe applied` reconciliations

## Done when
- [ ] Every crash point test passes: no duplicate mutation, no lost event.
- [ ] Running the same tick twice is a no-op the second time.
- [ ] Every governor trip, budget pause and unreadable source produces an inbox item. A failed read is reported as unreadable, never as a quiet hour.
- [ ] Review-mode actions re-check staleness before applying.
- [ ] Modes per action class match the M1 ladder, updated with evidence from M5/M6.

## Reuse
- `../code/starter_agent.run_episode`, your M6 gate
- Scheduled and ambient loops, bookmarks, ledgers, inbox supervision: [07-loops](../../07-loops/README.md)
- Durable state, checkpoints, resumability, double texting: [06-agent-architectures](../../06-agent-architectures/README.md)
- Stretch: rebuild the tick as a LangGraph graph with a checkpointer and `interrupt` for review items: [09-frameworks-langchain-langgraph](../../09-frameworks-langchain-langgraph/README.md)
- Real schedulers for when you leave the sim: Claude Code `/loop`, desktop tasks and cloud routines ([scheduled tasks docs](https://code.claude.com/docs/en/scheduled-tasks); recurring tasks expire after 7 days, which bounds a forgotten loop)

## Pitfalls
- **Time windows.** "Process incidents from the last 10 minutes" double-processes on an early tick and skips on a late one.
- **Trusting the ledger over the world.** After a crash, reconcile by reading state (`get_deploys`), not by assuming.
- **Inbox spam.** If every event becomes a `notify`, humans stop reading. Count items per day and treat that count as an SLI in M8.
