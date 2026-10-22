---
id: rb-redis-evictions
title: Redis evictions on idempotency-cache
kind: runbook
team: payments
acl: eng
version: 2
---
# Redis evictions on idempotency-cache

Owner: payments. Pager alert: `IdempotencyCacheEvictions` (evicted_keys rate > 0).

## Symptoms
Duplicate charges or duplicate ledger entries. ledger-api stores idempotency keys in Redis with a 24h TTL; if keys are evicted early, a client retry is treated as a new request.

## Diagnosis
Run `redis-cli -h idempotency-cache info memory` and check `maxmemory_policy`. The policy must be `noeviction` or `volatile-ttl`. `allkeys-lru` is wrong for this cache because it evicts live idempotency keys.

## Mitigation
Set the policy back if it drifted: `redis-cli -h idempotency-cache config set maxmemory-policy volatile-ttl`. Then reconcile duplicates with `billing-ctl ledger dedupe --since <ts>`.

## Verification
`evicted_keys` stops increasing and the dedupe job reports zero new duplicates.
