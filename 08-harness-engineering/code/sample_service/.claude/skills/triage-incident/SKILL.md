---
name: triage-incident
description: Use when given an alert, an incident report, a production symptom, or a bug report for the order service (409 spikes, outbox lag, read-model drift, missing or duplicated events). Walks from symptom to a verified fix with a regression test.
---

# Triage an order-service incident

You are fixing a correctness problem in a system with at-least-once delivery.
The symptom is rarely where the bug is. Work the loop below in order and write
down each step's result in your final message.

## 1. Orient (2 minutes)
- `python tools/diagnose.py summary`: what happened, how often, any ERROR/WARN rows.
- Map the symptom to an invariant in `INVARIANTS.md`:

| Symptom | Start with |
|---|---|
| 409 spike, retries failing | I2: `diagnose.py conflicts` |
| downstream missing events, outbox lag | I1/I3: `diagnose.py gaps`, `grep --event publish.failed` |
| events out of order downstream | I3: `repro.py broker-blip` |
| read model too high / double counted | I4: `diagnose.py dupes` |
| duplicate transition events | I5: `repro.py double-cancel` |

## 2. Hypothesize
Write one sentence: "I believe <component> does <wrong thing> when <condition>,
which violates <invariant>." Pick a correlation id from the logs
(`diagnose.py trace <order_id>`) that the hypothesis must explain.

## 3. Reproduce
Run the matching `tools/repro.py` scenario. If none matches, write the smallest
script against `FakeBroker` that shows the symptom. A hypothesis you cannot
reproduce is not confirmed; go back to step 2.

## 4. Failing test first
Add a test under `tests/` that fails for the reason in your hypothesis. Run it
and confirm it fails *for that reason* (read the assertion message).

## 5. Fix the cause, not the symptom
Change the code that violates the invariant. Disallowed "fixes":
- editing, skipping or deleting an existing test;
- catching the exception the alert counts (for example swallowing `IdempotencyConflict`);
- adding a compensating job that repairs the read model while the bug keeps happening;
- `# noqa` without a reason.

## 6. Verify
`python tools/check.py` exits 0, the new test passes, and the repro scenario
prints PASS. Re-run the diagnose query from step 1 against a fresh run if you
can produce one.

## 7. Report
Root cause (one paragraph), the invariant, the fix, the new test, and anything
the harness was missing that would have made this faster (a lint rule, a
diagnose query, a doc line). That last item is how the harness improves.
