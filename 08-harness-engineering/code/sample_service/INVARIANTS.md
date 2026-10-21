# INVARIANTS.md

The guarantees this service makes. Each has: the rule, why it exists, what
enforces it, and how it typically gets broken. If a change cannot preserve one,
stop and write an ADR instead of working around it.

| ID | Guarantee | Enforced by |
|---|---|---|
| I1 | State change and its event commit atomically | lint INV001, INV002, INV006; `test_create_writes_order_and_event_atomically` |
| I2 | Commands are idempotent per key; a reused key with a different body is a 409 | lint INV005; `test_identical_retry_*`, `test_same_key_different_body_conflicts`; `repro.py retry` |
| I3 | Events for one aggregate are published in commit order | lint INV003; `repro.py broker-blip` |
| I4 | Consumers apply each event at most once, even though delivery is at-least-once | lint INV004; `test_consumer_skips_redelivered_message`; `repro.py republish` |
| I5 | Order status only moves PLACED -> CANCELLED | `test_cancel_twice_with_new_key_is_invalid_transition`; `repro.py double-cancel` |

## I1. Atomic state and event
**Rule.** Any write to `orders` inserts its event into `outbox` inside the same
`with tx(conn):` block. Nothing outside `orders/outbox.py` publishes to the broker.

**Why.** The alternative is a dual write: commit, then publish. A crash between
the two loses the event; publish-then-commit invents an event for a rolled-back
change. The outbox turns "write DB and broker" into "write DB" plus an
at-least-once relay. See `docs/adr/0001-transactional-outbox.md`.

**Typical break.** A new command updates `orders` and calls `broker.publish`
directly, or forgets `_enqueue` entirely.

## I2. Idempotent commands
**Rule.** `request_hash(op, body)` is computed from client-supplied fields only.
Same key and same hash: return the stored response and do nothing else. Same key
and a different hash: raise `IdempotencyConflict` (HTTP 409). The key, the state
change, the outbox row and the stored response commit in one transaction.

**Why.** Clients and proxies retry on timeouts. Without replay, a retry creates a
second order. Without the conflict check, a client bug that reuses keys silently
returns the wrong order.

**Typical breaks.** (a) A server-generated value (timestamp, uuid) gets into the
hash, so every retry conflicts: a 409 storm. (b) A new request field is left out
of `body`, so a retry with a different value replays the old response.

## I3. Per-key ordering
**Rule.** The relay publishes unpublished rows in `outbox.id` order and stops at
the first failure. It marks exactly the row it published (`WHERE id = ?`).

**Why.** The broker preserves order per key (partition), but only for what we
send it. If the relay skips a failed `OrderPlaced` and publishes the
`OrderCancelled` behind it, consumers see a cancel for an order that does not
exist yet. If it marks rows by `aggregate_id`, one success marks later,
never-published events as done: they are lost.

**Typical breaks.** `continue` in the failure handler; `UPDATE ... WHERE aggregate_id = ?`.

## I4. Idempotent consumers
**Rule.** A consumer inserts `(consumer, event_id)` into `processed_events` in
the same transaction as its read-model write, and skips the event on conflict.
Dedupe on `event_id`, which is the outbox row id.

**Why.** Delivery is at-least-once in two ways. The broker redelivers
uncommitted offsets after a rebalance (same partition and offset). The relay
republishes a row if it crashes between publish and mark, and that copy has a
**new offset**. Dedupe on `(partition, offset)` handles only the first.

**Typical break.** Dedupe key built from `msg.partition`/`msg.offset`. The
symptom is read-model drift (for example `customer_stats.total_cents` above the
sum of orders) after a relay restart.

## I5. Status transitions
**Rule.** `PLACED -> CANCELLED` is the only transition. A cancel of a cancelled
order with a new idempotency key raises `InvalidTransition`. (A retry with the
same key replays, per I2.)

**Why.** Each transition emits an event. A second `OrderCancelled` would make
downstream consumers refund or decrement twice.
