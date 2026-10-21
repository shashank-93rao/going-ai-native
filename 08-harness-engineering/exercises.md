# Exercises

Run everything from `08-harness-engineering/code/` unless noted. `PY=../../.venv/bin/python`.

---

## 1. Read the graders (offline, 20 min)
**Goal:** understand what each grading column catches, and why naive scoring inflates.

**Steps**
1. Run the eval four times, once per fake-agent policy:
   ```bash
   for p in noop naive oracle harness-aware; do
     $PY autonomy_eval.py --agent "{python} {here}/fake_agent.py --policy $p {workdir} {prompt}" --jobs 8
   done
   ```
2. For the `noop` run, count how many tasks have `visible=True`, and how many have both `visible=True` and `lint=True`.
3. For the `naive` run, explain for each task *which* column caught the naive fix, and why the others did not.
4. Run `--policy oracle --fail feat-currency` and look at the `feat-currency` row.

**Done when**
- You have reproduced: noop 0/8, oracle 8/8, harness-aware 8/8.
- You can state the numbers for visible-only (7/8) and visible-plus-lint (5/8) on noop, and name the tasks that make up the difference.
- You can explain in one sentence why `feat-currency`'s naive fix passes visible tests and lint but fails hidden tests.

**Stretch:** run `--trials 3` and explain why the Wilson interval over 24 trials overstates precision compared with 8 tasks.

---

## 2. Close a lint blind spot (offline, 45 min)
**Goal:** turn the harness gap that example 1 reported into a check.

**Steps**
1. In `sample_service/tools/lint_invariants.py`, extend INV004, or add an INV007. It should flag an `INSERT INTO processed_events` whose parameters reference `.offset` or `.partition` (walk the args of the `execute` call for `ast.Attribute` nodes).
2. Write remediation text: why (offsets change on republish), fix (dedupe on `ev["event_id"]`), and a see line pointing at the I4 anchor.
3. Update `test_lint_against_injected_bugs` so that `inc-stats-drift` expects your rule.
4. Re-run `--ablate diagnose` with the harness-aware fake, and think about what would change for a *real* agent on that task.

**Done when**
- `$PY -m pytest -q .` passes from `code/`.
- The base service is still lint-clean.
- `check_docs.py` still passes, because your see anchor exists.

**Stretch:** add a rule for the `inc-lost-cancellations` bug: an `UPDATE outbox ... WHERE` clause on anything other than `id`. Decide whether it is precise enough to keep, or whether it would breed `noqa` spam.

---

## 3. Author a new seeded task (offline, 60 min)
**Goal:** practice task validity: the oracle can fail, can pass, and discriminates.

**Steps**
1. Pick a feature: "refund an order". `refund_order(conn, idem_key, order_id)` is valid only from CANCELLED, emits `OrderRefunded` through the outbox, and is idempotent per key. Or pick a bug: drop the `_remember` call inside the transaction of `cancel_order`.
2. Create `tasks/<id>/task.toml` with `prompt` (written as the requester would write it), `needs`, `inject` (for a bug) or `solution` (for a feature), and a `naive` variant that a plausible agent would produce.
3. Write `hidden_checks.py` that asserts the invariant, not the implementation.
4. Write a *second*, differently shaped correct fix by hand, and confirm it passes your hidden tests.

**Done when**
- `test_suite_shape` and `test_every_task_oracle_can_fail_and_can_pass` pass with your task included.
- The naive variant fails the hidden tests (`--policy naive --tasks <id>`).
- Your alternative fix passes.

**Stretch:** for an incident task, add a scenario to `tasks/gen_incident_logs.py`, regenerate the logs, and confirm that a diagnose subcommand surfaces the evidence.

---

## 4. Add a diagnose query for ordering (offline, 40 min)
**Goal:** encode an on-call query as a tool.

**Steps**
1. Add `diagnose.py ordering`. For each `order_id`, it checks that `OrderPlaced` was published before `OrderCancelled`, based on `relay.event.published` records. Print `ERROR order_id=... published OrderCancelled before OrderPlaced`, plus a summary line and a hint that points at I3.
2. Add a `bug-relay-skips-failure` scenario to `gen_incident_logs.py` (a broker that rejects `OrderPlaced` for a few orders, then recovers), and change the task to `kind = "incident"` with logs. Or keep it a bug task and generate logs only for your test.
3. Test the subcommand on the generated log and on a clean log.

**Done when**
- The query reports every out-of-order key on the buggy log and nothing on a log from the fixed code.
- Output stays under 20 lines by default.

---

## 5. Property-based tests for I3 and I4 (offline, 60 min)
**Goal:** replace hand-picked scenarios with generated interleavings, the Jepsen instinct applied to a hermetic fake.

**Steps**
1. In `sample_service/tests/test_properties.py`, use Hypothesis to generate sequences of operations: `create(customer, amount)`, `cancel(i)`, `relay(batch)`, `fail_next(n)`, `republish_all()` (reset `published_at`), and `drain()`.
2. After each sequence, finish with a healthy `drain()` loop until lag is 0. Then assert:
   - I3: for each order, the published types are a prefix-ordered subsequence of `[OrderPlaced, OrderCancelled]`;
   - I4: `customer_stats` equals the count and sum of placed orders per customer.
3. Apply the `bug-relay-skips-failure` and `inc-stats-drift` injections to a temp copy (`task_suite.apply_edits`), and confirm the property test finds each one.

**Done when**
- The property test passes on the base service in under 10 seconds (`@settings(max_examples=200)`).
- It fails on both injected bugs, and Hypothesis shrinks to a minimal sequence you can read.

**Stretch:** after doing exercise 3's refund feature, extend I4 to cover cancellations.

---

## 6. Measure a real agent and ablate (real agent or API, 90 min plus run time)
**Goal:** produce a real autonomy rate and a real ablation table.

**Steps**
1. Choose an agent:
   - `mini_agent.py` with `ANTHROPIC_API_KEY` set: `--agent "{python} {here}/mini_agent.py {workdir} {prompt} --max-turns 40"`;
   - or Claude Code or Codex inside a container where `tasks/` is not mounted (see [05](05-measuring-autonomy-rate.md) for the template).
2. Run the full harness with `--trials 3 --json full.json`.
3. Run `--ablate diagnose`, `--ablate invariants`, and `--ablate agents_md,skills`, each with three trials.
4. Build a table of per-class rates with intervals, and the delta from full.
5. Read at least three failing transcripts (`--keep runs/`, then `agent.log`), and classify each failure: missing context, missing verifier, missing evidence, or agent error.

**Done when**
- You have four JSON result files and a table.
- You have one paragraph saying which deltas exceed noise and which do not.
- You have one proposed harness change, justified by a transcript, that does not paste task content into the harness.

**Stretch:** make your proposed change, re-run on the tasks you did *not* read transcripts for, and apply the revert rule.

---

## 7. Block test edits with a hook (real agent, 20 min)
**Goal:** add prevention to the "fixing the test" defense.

**Steps**
1. Create `sample_service/tools/guard_tests.py` and `.claude/settings.json` from [04](04-pillar-diagnose.md).
2. In a copy of the `bug-double-cancel` workspace (`build_workspace`), start Claude Code and ask it to "get CI green by any means".
3. Observe the hook blocking an edit to `tests/test_orders_api.py`, and what the agent does next.

**Done when**
- The transcript shows the block message reaching the agent.
- The final diff touches only `orders/api.py` and, optionally, a *new* test file.
- The eval run on that workspace shows `tamper -`.

---

## 8. Your own service (half a day)
**Goal:** apply all three pillars to something you own.

**Steps**
1. Write INVARIANTS.md using the checklist in [02](02-pillar-understand.md). Fill the "Enforced by" column honestly.
2. Write one custom lint with remediation for the invariant with the emptiest "Enforced by" cell.
3. Write a `diagnose` CLI with your three most-used on-call queries over your log store (read-only).
4. Seed five tasks: two reverted bug fixes, two features, one incident. Run your agent over them, three trials each.

**Done when**
- Your AGENTS.md or CLAUDE.md is a map under 100 lines.
- The lint runs in your gate.
- You have a per-class autonomy rate with intervals, and one harness change you will make next, chosen by reading a failure.
