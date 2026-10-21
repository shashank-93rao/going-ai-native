# orders/: local notes (loaded when you work in this directory)

- `api.py` owns the `orders` and `idempotency_keys` tables. Every command is
  `validate -> request_hash(body) -> with tx: replay-or-execute -> _enqueue -> _remember`.
  Keep that order; `_remember` must be inside the same transaction as the write.
- `request_hash` covers client-supplied body fields only. Adding a request field?
  Add it to `body`, or retries with a different value will silently replay (I2).
- `outbox.py` is the only publisher. Its failure handler must `break` (I3).
- `consumer.py` dedupes on `event_id` via `processed_events` before any write (I4).
- `broker.py` is a test fake. Do not add production behaviour to it; add knobs for fault injection instead.
