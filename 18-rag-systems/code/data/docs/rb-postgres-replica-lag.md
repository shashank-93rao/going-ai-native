---
id: rb-postgres-replica-lag
title: Postgres replica lag on ledger-db
kind: runbook
team: platform
acl: eng
version: 3
---
# Postgres replica lag on ledger-db

Owner: platform. Pager alert: `LedgerReplicaLagSeconds` (replay lag > 30s).

## Symptoms
Read-your-writes failures in ledger-api: a client creates a payment and the follow-up GET returns 404 because reads go to the replica.

## Diagnosis
On the primary run `psql -h ledger-db-primary -c "select client_addr, state, replay_lag from pg_stat_replication;"`.

Long-running analytics queries on the replica block WAL replay when `hot_standby_feedback` is on. Find them in `pg_stat_activity` ordered by transaction age.

## Mitigation
Cancel the blocking query with `select pg_cancel_backend(<pid>);`. As a stopgap, pin ledger-api reads to the primary: `billing-ctl flags set ledger.read_from_primary=true`. Revert the flag once lag is under 5s, because the primary has limited headroom.

## Verification
`replay_lag` under 5 seconds for 10 minutes, and the read-your-writes synthetic check is green.
