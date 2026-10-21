# Consumer lag: cause catalog

Read this when Step 3 of SKILL.md needs a decision. Each entry: signature, how to confirm, safe next action.

| Cause | Signature | Confirm with | Next action (for a human) |
|---|---|---|---|
| Poison message | `single_partition`; that partition's offset not moving; repeated deserialize/validation errors naming one offset | Logs filtered by `partition=<n>`; offset unchanged across two samples | Fix forward (deploy a consumer that tolerates the value) or route the record to a DLQ. Skipping the offset loses data: needs owner sign-off |
| Hot key | `single_partition`; offset *is* moving, just slower; producer key distribution skewed | Per-partition produce rate; top keys on that partition | Short term: scale the consumer's per-record work. Long term: re-key or split the key |
| Throughput regression | `uniform`; started at a consumer deploy | Deploy history vs lag start time; processing-time metric step change | Roll back the consumer deploy |
| Slow downstream | `uniform`; consumer CPU low; downstream p99 up | Consumer's DB/HTTP client latency metrics | Engage downstream owner; consider lowering `max.poll.records` to avoid poll-interval timeouts |
| Under-provisioned | `uniform`; grows with traffic; consumers at CPU limit | Consumer CPU/throttling; consumers < partitions | Scale consumers up to the partition count; beyond it adds nothing |
| Producer burst | `uniform`; produce rate spike; lag draining once the spike ends | Produce rate on the topic | Usually wait; confirm drain ETA from the second sample |
| Rebalance storm | `unassigned` or flapping; repeated revoke/assign logs | Logs for `Revoking previously assigned partitions`, heartbeat failures; pod restarts | Find the crash or slow poll; raise `max.poll.interval.ms` only with a reason |
| Consumer down | `unassigned` for all partitions; no members | `--describe --members` shows none; pods not Running | Restore the deployment |

Drain ETA: `lag / (consume_rate - produce_rate)`. If the denominator is <= 0 the backlog never drains on its own.
