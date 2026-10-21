# ADR-0001: Transactional outbox instead of publish-on-commit

- Status: accepted
- Date: 2026-03-02

## Context
Order commands must change state and notify downstream services. Publishing to
the broker from the request path is a dual write: there is no transaction that
spans SQLite and the broker, so a crash or timeout between the two leaves them
disagreeing. We saw this as "ghost cancels" (event published, tx rolled back)
and "silent orders" (tx committed, publish timed out).

## Decision
Commands write an `outbox` row in the same transaction as the state change. A
relay publishes unpublished rows in id order and marks each one after the broker
acknowledges it. Delivery is therefore at-least-once; every consumer dedupes on
`event_id`.

## Consequences
- Request latency no longer depends on broker availability.
- Duplicates are normal and must be handled by consumers (INVARIANTS.md I4).
- Ordering is per aggregate and depends on the relay stopping at the first
  failure (I3). A relay that skips ahead is a correctness bug, not a liveness fix.
- Outbox lag (`outbox.lag()`) is an SLI; alert at > 5 minutes.

## Rejected alternatives
- Publish then commit: invents events for rolled-back changes.
- Two-phase commit across DB and broker: not supported by the broker; too much
  operational cost for this service.
- CDC from the DB log: a good fit later; it does not change the consumer contract.
