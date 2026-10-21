# AGENTS.md: order service

This file is a map. Follow the links for detail; do not expect the detail here.

## What this is
An order service: an idempotent command API (`orders/api.py`), a transactional
outbox relay (`orders/outbox.py`), and an idempotent consumer that maintains a
read model (`orders/consumer.py`). The broker is a hermetic fake (`orders/broker.py`).

## Before you change anything, read
- `ARCHITECTURE.md`: components, data flow, which module owns which table.
- `INVARIANTS.md`: the five guarantees (atomicity, idempotency, ordering,
  dedupe, transitions). Every change must preserve all of them.
- `docs/glossary.md` if a term is unfamiliar (outbox, relay, aggregate, replay).
- `docs/adr/` for why things are the way they are. Do not reverse an ADR silently.

## Definition of done
`python tools/check.py` exits 0. It runs the invariant lint and the tests in
about a second. Lint errors include a `fix:` line: do what it says.

## Commands
- `python tools/check.py`: lint + tests (the gate).
- `python tools/lint_invariants.py`: lint only. Suppress only with `# noqa: INV00X <reason>`.
- `python -m pytest -q tests/test_orders_api.py -k conflict`: a focused test run.
- `python tools/repro.py all`: deterministic repro scenarios, one line each.
- `python tools/diagnose.py summary`: structured-log queries (`grep`, `trace`, `dupes`, `gaps`, `conflicts`).

## Fixing a bug or an incident
Follow `.claude/skills/triage-incident/SKILL.md`. In short: reproduce, write a
failing test, fix the code, run the gate, keep the test. Never edit or delete
an existing test to make it pass; if you believe a test is wrong, stop and say why.

## Conventions
- All writes go through `with tx(conn):` (orders/db.py). No manual BEGIN/COMMIT.
- Only `orders/outbox.py` publishes to the broker.
- New events: add to the outbox in the same transaction, document the payload in ARCHITECTURE.md.
- Logs: `orders.obs.log(component, event, **fields)`; always include `order_id` and `event_id` when known.
