# Glossary

| Term | Meaning here |
|---|---|
| aggregate | One order. Its id is the broker key, so all its events share a partition. |
| outbox | Table of events written in the same tx as the state change; drained by the relay. |
| relay | `relay_once()`: publishes unpublished outbox rows in id order, then marks them. |
| event_id | The outbox row id (string). Globally unique, stable across republishes. The dedupe key. |
| offset | Position of a message in a partition. Not stable across republishes; never a dedupe key. |
| replay | Returning the stored response for a repeated Idempotency-Key with an identical body. |
| conflict | A repeated Idempotency-Key with a different body. HTTP 409, `IdempotencyConflict`. |
| request hash | `request_hash(op, body)` over client-supplied fields only. |
| read model | `customer_stats`: derived from events, rebuildable, owned by `StatsConsumer`. |
| lag | Count (or age) of unpublished outbox rows. The relay's SLI. |
| drift | Read model disagrees with the source of truth (`orders`). Usually a dedupe bug. |
