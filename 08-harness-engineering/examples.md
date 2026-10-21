# Examples

Five scenarios from the world of a distributed-systems engineer. Tool output marked as real was produced by this module's code. Agent transcripts are **(illustrative output)**: they show typical behavior, not a measured run.

---

## 1. Before and after: the same agent, the same incident, with and without the harness
### Situation
The customer-stats read model has drifted. `customer_stats.total_cents` is higher than the sum of orders for two customers, starting a minute after the outbox relay was OOM-killed and restarted. This is the `inc-stats-drift` task. The injected bug is one line in `StatsConsumer.handle`:
```python
                    (self.name, f"{msg.partition}:{msg.offset}"),   # dedupe key
```

### Naive approach: the agent gets the alert and the code, nothing else
Run it with every harness component removed (`--ablate all`): no AGENTS.md, no INVARIANTS.md, no diagnose CLI, no repro scripts, no skill. The logs are still present as a raw JSONL file.

```text
> Read orders/consumer.py, orders/outbox.py, tests/test_orders_pipeline.py
> Ran: python -m pytest -q          11 passed
The consumer dedupes via processed_events, and test_consumer_skips_redelivered_message
covers redelivery, so dedupe works. The drift began after a relay restart. On restart,
the relay may have processed events while the DB was in an inconsistent state. I'll add
a reconciliation step that recomputes customer_stats from the orders table, and run it
on relay startup.
> Edited orders/outbox.py: added rebuild_customer_stats(conn) and a call in relay_once
> Ran: python -m pytest -q          11 passed
Done. Stats are now recomputed from source of truth on every relay start.
```
(illustrative output)

What went wrong, step by step:
1. **No invariant told it that offsets are not stable across republishes.** It saw a dedupe table and a passing redelivery test and concluded dedupe was correct. The visible test only covers same-offset redelivery.
2. **No query tool, so no evidence.** The raw log has the answer, the same `event_id` applied at two different offsets. But nothing prompted the agent to look for that pattern, and 31 lines of JSON do not announce it.
3. **No repro, so no failing test.** It never demonstrated the bug, so it could not demonstrate the fix.
4. **It fixed the symptom.** A compensating rebuild, and from the relay, which violates module ownership. The bug keeps double-counting between restarts. The hidden test `test_relay_republish_does_not_double_count` still fails.

### AI-native approach: the same agent, the full harness
The agent loads AGENTS.md (the map) and sees "for bugs and incidents, follow the triage skill". The skill's symptom table maps "read model too high / double counted" to I4 and `diagnose.py dupes`.

**Step 1, orient.** Real output:
```text
$ python tools/diagnose.py summary
31 records, ts 1791943800.004 .. 1791944005.164
ERROR      1  relay.process.killed
    10  relay.event.published
    10  consumer.event.applied
     8  api.order.placed
     1  relay.process.started
     1  api.idempotency.replay
```
Eight orders placed, ten events published and ten applied. Two extra.

**Step 2, query the invariant.** Real output:
```text
$ python tools/diagnose.py dupes
ERROR event_id=6 order_id=ord_d61f37e394 applied 2x at p0@1, p0@2
ERROR event_id=7 order_id=ord_5492bc16dc applied 2x at p2@3, p2@4
2 event(s) applied more than once; 2 event(s) published more than once
hint: duplicates arrive at different offsets => they come from relay republish, which is legal
(at-least-once). The consumer must dedupe on event_id. See INVARIANTS.md I4.
```

**Step 3, hypothesis tied to a correlation id.** Real output:
```text
$ python tools/diagnose.py trace ord_d61f37e394
1791943960.084 api.order.placed order_id=ord_d61f37e394 idem_key=idem-5
1791943960.100 relay.event.published order_id=ord_d61f37e394 event_id=6 type=OrderPlaced partition=0 offset=1
1791944005.132 relay.event.published order_id=ord_d61f37e394 event_id=6 type=OrderPlaced partition=0 offset=2
1791944005.144 consumer.event.applied order_id=ord_d61f37e394 event_id=6 type=OrderPlaced partition=0 offset=1
1791944005.148 consumer.event.applied order_id=ord_d61f37e394 event_id=6 type=OrderPlaced partition=0 offset=2
```
> "I believe `StatsConsumer.handle` dedupes on (partition, offset) instead of event_id, so a relay republish after the 02:13 crash, which put event 6 at offset 2, was applied a second time. That violates I4."

**Step 4, reproduce.** Real output:
```text
$ python tools/repro.py republish
FAIL republish: stats=2,2000 want 1,1000 after republish
```
Note that `python tools/check.py` is **green** on this bug (`check: PASS lint=ok docs=ok tests=(11 passed ...)`). The lint's INV004 only checks that a dedupe insert exists, and this is one of its documented blind spots. Diagnose and repro carry this task.

**Step 5, failing test, fix, verify.** The agent writes a test with the republish scenario, watches it fail with `assert (2, 2000) == (1, 1000)`, and changes the dedupe key back to `ev["event_id"]`. Then `check.py`, the new test and `repro.py republish` all pass.

**Step 6, report.** Root cause, invariant, fix and test, plus a harness gap: "INV004 should also flag dedupe keys built from `msg.offset` or `msg.partition`." That last line is the input to the next harness improvement (Exercise 2).

Graded by the eval, the AI-native run is `PASS` (hidden, visible and lint all True). The naive run fails the hidden test. The pristine lint run by the grader also flags the rebuild function's write to `customer_stats` (INV004). The agent never saw that lint, because it was ablated from its copy. Note that on the *unfixed* code, the visible tests and the lint both pass. That is exactly why they are not the grader.

### What to check
- Did the fix change the code that violates the invariant, or add compensation somewhere else?
- Was there a test that failed before the fix *for the stated reason*?
- Does the diff stay within module ownership (ARCHITECTURE.md)?
- Did the report name a harness gap? If it did, schedule it.

---

## 2. Making a legacy Kafka consumer agent-ready in two weeks
### Situation
You own a Go service that consumes `payments.settled`, writes to Postgres and calls a ledger API. It has unit tests with mocks, no docs beyond a README, and an on-call runbook in Confluence. The team wants agents to take on its backlog.

### Naive approach
Write a 600-line CLAUDE.md from the README, the Confluence runbook and a style guide, then start assigning tickets. Two weeks later:
- the agent has merged a "retry on ledger 5xx" change that double-posts when the ledger times out after committing;
- the reviewers are exhausted;
- nobody can say whether things are better.

### AI-native approach
Order the work by what unlocks measurement first:

1. **Days 1–2: seed the suite.** Pull ten tasks from history: four reverted bug fixes, three recent features, three incidents from postmortems with their log excerpts. Write hidden tests that assert invariants. Run your current agent over them, three trials each, to get a baseline. Illustrative baseline: features 5/9, bugs 4/12, incidents 0/9.
2. **Days 3–4: INVARIANTS.md.** Use the checklist from [02](02-pillar-understand.md). The one that matters most here:
   ```markdown
   ## I2. Ledger posts are idempotent per settlement_id
   **Rule.** Every POST /ledger/entries carries Idempotency-Key = settlement_id. Retries reuse it.
   **Why.** The ledger may commit and then time out; a retry without the key double-posts.
   **Enforced by.** lint LDG001 (ledger client calls must pass idempotency_key); contract test against ledger sandbox.
   **Typical break.** New code path builds a fresh request without the key, or derives the key from time.Now().
   ```
3. **Days 5–6: the gate and one lint.** Write a `make check` under 30 seconds. Add a `go vet` analyzer for LDG001, with a remediation message naming `ledger.PostEntry(ctx, settlementID, ...)`.
4. **Days 7–8: fakes that fail.** Write a ledger fake with `CommitThenTimeout()` and a Kafka fake with redelivery. Run the shared contract suite against the ledger sandbox nightly.
5. **Days 9–10: Diagnose.** Write a `tools/diagnose` CLI over your log store with `dupes --by settlement_id` and `trace <settlement_id>`. Convert the Confluence runbook into a skill with a symptom table.
6. **Re-measure.** Illustrative: features 8/9, bugs 9/12, incidents 5/9. Incidents are still the weak class, so the next harness work is a `lag` query and a repro for rebalance storms.

### What to check
- Each harness change was followed by a re-run, and you can attribute the gain.
- The CLAUDE.md you finally ship is a map under 100 lines, with the runbook moved to a skill and the rules moved to lints.
- The hidden tests for the ledger-retry bug fail on the bad change that actually merged. If they would not have caught it, they are testing the wrong thing.

---

## 3. A schema migration feature on a hot table
### Situation
Ticket: "Add `currency` to `orders`". The table is large, written at a few thousand rows per second, and read by three services.

### Naive approach
The agent writes `ALTER TABLE orders ADD COLUMN currency TEXT NOT NULL DEFAULT 'USD'` and a backfill in the same migration, updates the API, and tests pass on SQLite. In production, depending on engine and version, the migration may rewrite or lock the table. Meanwhile a consumer that deserializes events strictly breaks on the new field.

### AI-native approach
- **INVARIANTS.md** gains a migration section: expand/contract only; no `NOT NULL` without a default on a large table; backfills in batches outside the DDL transaction; event fields additive-only.
- **A migration lint** with remediation:
  ```text
  migrations/0042_currency.sql:3: MIG002 NOT NULL column added with backfill in one migration
    why: on large tables this can hold a long lock or rewrite the table; writers stall.
    fix: split into 0042 (ADD COLUMN currency TEXT NULL), a batched backfill job, and
         0043 (SET NOT NULL) after the backfill completes. See docs/adr/0007-online-migrations.md
  ```
  (illustrative output)
- **An ephemeral per-worktree Postgres**, from `tools/env_up.sh` in [03](03-pillar-verify.md), seeded with a production-sized synthetic table. The agent's verification step times the migration against it and fails above a budget.
- **A contract test** checks that the new event schema is backward compatible, and the visible tests use subset assertions, so additive fields do not break them.
- **The idempotency hash.** `orders/AGENTS.md` reminds the agent that request fields go into `body`. This is the `feat-currency` trap, and the hidden test `test_same_key_different_currency_conflicts` is the check.

### What to check
- Is the migration split expand/contract, with a measured duration on realistic data?
- Is the new field in the request hash?
- Did any existing test get edited? For an additive feature, none should need to be.

---

## 4. The flaky integration test that the agent "fixed"
### Situation
`test_consumer_rebalance` fails about 1 run in 20. You ask an agent to fix the flake.

### Naive approach
```text
The test is timing-sensitive. I've increased the poll timeout from 2s to 10s and added
@retry(times=3). It passed 50/50 locally.
```
(illustrative output)

It passed because the race is now rarer. The underlying bug is that offsets are committed before the DB transaction commits, so a crash in that window loses an event. That bug is still there.

### AI-native approach
- **AGENTS.md:** "A flaky test is a bug report. Never add retries, sleeps or longer timeouts to make a test pass; find the race." Back it with a lint that flags new `time.sleep` and `@retry` in `tests/`, with a remediation message pointing at the fake clock and the broker fake's deterministic scheduling.
- **Diagnose for tests:** run the test 200 times with structured logs and a seed, then use `diagnose.py grep --event` to compare event order in passing and failing runs. The failing runs show `consumer.offset.committed` before `consumer.event.applied`.
- **Repro:** a deterministic scenario with the fake broker's fault injection: crash between commit-offset and commit-tx. It fails every time. Now the agent has a real failing test.
- **Fix:** commit the DB transaction first, then the offset. The duplicate that this creates on a crash is already handled by the I4 dedupe. That is the at-least-once-plus-idempotent-consumer pattern.

### What to check
- The diff contains no new sleeps, retries or timeout increases.
- The new deterministic test fails on the old code 100% of the time.
- The flaky test now passes 1,000 out of 1,000 runs, and it was not edited.

---

## 5. An alert-triggered agent at 03:00
### Situation
`outbox-lag > 5m` fires at night. You want an agent to do first-line triage, so that the human on call wakes up to findings, or does not need to wake up at all.

### Naive approach
Give the agent production database credentials "so it can fix things". At 03:10 it runs `UPDATE outbox SET published_at = now()` to clear the lag. The alert resolves, and every unpublished event is now lost.

### AI-native approach
The event-driven loop from [04](04-pillar-diagnose.md), with containment:
- **Trigger:** the alert webhook starts a headless agent in a fresh worktree with a read-only log and metrics token and **no** production write access ([16-security-and-containment](../16-security-and-containment/README.md)).
- **Brief:**
  ```text
  An alert fired: {alert_text}. Follow .claude/skills/triage-incident/SKILL.md.
  You may query logs/metrics (read-only) and change code in this worktree. You may
  not change production data or config. End with EITHER a PR containing a failing-
  then-passing test and a root-cause report, OR an escalation note with your
  evidence and top two hypotheses. Budget: 40 turns, $5.
  ```
- **Evidence:** `diagnose.py gaps` shows four `OrderCancelled` events committed but never published, and `publish.failed` errors from 09:05. That is the `inc-lost-cancellations` pattern.
- **Output (illustrative):** an escalation note, because the root cause is a code bug, and also because recovering the lost events needs a human-approved data operation:
  ```text
  Root cause: relay marks rows published by aggregate_id, not id (outbox.py:33), so one
  success marks later unpublished events for that order as published (I3). 4 cancels lost.
  PR #431: fix + regression test (failing before, passing after). check.py green.
  Needs human: re-enqueue outbox rows 9-12 (query attached). I did not run it.
  ```

### What to check
- The agent had no credentials capable of the 03:10 mistake.
- Every run ends in a PR with evidence or an escalation with evidence, never "done" with nothing attached.
- Data repair is proposed, not executed.
- Over a month, track how many alerts ended in a merged agent PR versus an escalation. That is the autonomy rate for the incident class, measured in production.
