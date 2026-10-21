# Code for module 08

Everything runs offline with the course venv. From the course root:
```bash
.venv/bin/python -m pytest -q 08-harness-engineering/code     # about 10 s, 49 tests
```

## Layout
```text
code/
  sample_service/            the "agent-ready" order service (copy this shape for your own repos)
    AGENTS.md                the map (37 lines)
    ARCHITECTURE.md          data flow, ownership, event contracts
    INVARIANTS.md            I1-I5: rule, why, enforced by, typical break
    docs/adr/0001-*.md       why there is an outbox; rejected alternatives
    docs/glossary.md         overloaded words, defined
    .claude/skills/triage-incident/SKILL.md   the runbook, as a skill
    orders/                  db.py (tx), api.py (idempotent commands), outbox.py (relay),
                             consumer.py (idempotent read model), broker.py (fault-injecting fake),
                             obs.py (structured logs), AGENTS.md (local rules)
    tools/check.py           the gate: lint + docs check + tests, prints only failures
    tools/lint_invariants.py AST lint INV001-INV006 with why/fix/see remediation
    tools/check_docs.py      docs freshness: paths, anchors, module coverage, AGENTS.md size
    tools/repro.py           deterministic scenarios, one PASS/FAIL line each
    tools/diagnose.py        structured-log queries: summary, grep, trace, dupes, gaps, conflicts
    tests/                   visible tests (the agent sees these)
  tasks/<id>/                8 seeded tasks: task.toml, hidden_checks.py, incident.jsonl (incidents)
  tasks/gen_incident_logs.py regenerates incident logs by running the buggy code
  task_suite.py              loading tasks, exact-match edits, building workspaces, ablations
  autonomy_eval.py           runs an agent per task in a temp copy, grades, reports a rate with a CI
  fake_agent.py              deterministic stand-in agent (policies: oracle, harness-aware, naive, noop)
  mini_agent.py              a minimal real agent on ainative_kit (4 tools); FakeClient demo offline
  test_*.py                  tests for the lint, docs check, diagnose, eval, task validity, mini agent
```

## The sample service
```bash
cd sample_service
../../../.venv/bin/python tools/check.py              # check: PASS lint=ok docs=ok tests=(11 passed ...)
../../../.venv/bin/python tools/repro.py all
../../../.venv/bin/python tools/diagnose.py --log ../tasks/inc-stats-drift/incident.jsonl dupes
```

## The task suite
| Task | Kind | What the agent must do | Trap |
|---|---|---|---|
| feat-list-orders | feature | read-only listing in creation order | ordering by id instead of creation |
| feat-currency | feature | add a currency field end to end | forgetting it in the idempotency hash (I2) |
| feat-cancel-stats | feature | read model handles cancellations | double-decrement on republish (I4) |
| bug-double-cancel | bug | CI red: restore the transition guard | deleting the failing test |
| bug-relay-skips-failure | bug | consumers see cancel before place | retrying inline instead of stopping (I3) |
| inc-stats-drift | incident | read model too high after relay restart | dedupe on offset; compensating rebuild |
| inc-lost-cancellations | incident | cancels never delivered; lag is 0 | relay marks by aggregate_id (I3) |
| inc-409-spike | incident | 409 storm on retries | tolerating conflicts instead of fixing the hash (I2) |

Bugs are injected as exact search/replace edits (`inject` in task.toml). Reference fixes for bugs are the inverse of the injection. Features carry explicit `solution` edits.

## Running the eval
```bash
cd code
PY=../../.venv/bin/python
$PY autonomy_eval.py --agent "{python} {here}/fake_agent.py --policy harness-aware {workdir} {prompt}"
$PY autonomy_eval.py --agent "{python} {here}/fake_agent.py --policy harness-aware {workdir} {prompt}" --ablate diagnose
$PY autonomy_eval.py --agent "{python} {here}/fake_agent.py --policy oracle --fail feat-currency {workdir} {prompt}" --json out.json
```
Flags: `--tasks a,b`, `--ablate agents_md,invariants,architecture,lint,diagnose,repro,skills|all`, `--trials N`, `--jobs N`, `--timeout S`, `--keep DIR` (keep workspaces and agent.log), `--json PATH`.

The `harness-aware` fake agent succeeds when the files in a task's `needs` exist. Its ablation results are **simulated by construction**: they test the eval machinery, not real agents. For a real measurement:
```bash
# minimal agent on the real API (needs ANTHROPIC_API_KEY; without it, a scripted demo that solves only inc-409-spike)
$PY autonomy_eval.py --agent "{python} {here}/mini_agent.py {workdir} {prompt} --max-turns 40" --trials 3
# Claude Code in print mode, ONLY inside a disposable sandbox that cannot read tasks/
$PY autonomy_eval.py --agent 'sh -c "claude -p \"$(cat {prompt})\" --dangerously-skip-permissions"' --jobs 2
```

## Grading rules (what counts as success)
1. The hidden tests pass. They are copied into `_hidden_tests/` only after the agent exits.
2. The **original** visible tests pass. `tests/test_orders_*.py` and `conftest.py` are restored first, and any change to them is reported as `tamper`.
3. The **original** lint passes. It runs from this checkout against the agent's `orders/`.
4. No timeout.

## Regenerating incident logs
```bash
$PY tasks/gen_incident_logs.py          # runs each incident's buggy code under a fake clock
```
The logs are deterministic. `test_diagnose.py` asserts on their content, so re-run the tests after regenerating.

## Dependencies
None beyond the course venv. `mini_agent.py` uses `ainative_kit` (FakeClient offline, AnthropicClient when a key is set). Nothing else in this folder calls a model.
