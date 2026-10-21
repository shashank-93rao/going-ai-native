# Redis memory pressure and evictions on idempotency-cache

Owner: billing-platform. Pager alert: `IdempotencyCacheEvictions` (evicted_keys rate > 0).

## Symptoms
Duplicate charges or duplicate ledger entries. ledger-api stores idempotency keys in Redis with a 24h TTL; if keys are evicted early, a client retry is treated as a new request.

## Diagnosis
`redis-cli -h idempotency-cache info memory | grep -E "used_memory_human|maxmemory_policy"` and `redis-cli -h idempotency-cache info stats | grep evicted_keys`.

The policy must be `noeviction` or `volatile-ttl`. `allkeys-lru` is wrong for this cache because it evicts live idempotency keys.

## Mitigation
Increase memory or shard. Set the policy back if it drifted: `redis-cli -h idempotency-cache config set maxmemory-policy volatile-ttl`. Then reconcile duplicates for the window with `billing-ctl ledger dedupe --since <ts>`.

## Verification
`evicted_keys` stops increasing, and the dedupe job reports zero new duplicates.
