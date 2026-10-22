---
id: rb-pgbouncer-exhaustion
title: PgBouncer connection pool exhaustion
kind: runbook
team: platform
acl: eng
version: 2
---
# PgBouncer connection pool exhaustion

Owner: platform. Pager alert: `PgBouncerWaitingClients`.

## Symptoms
Requests hang then fail with `sorry, too many clients already` or `query_wait_timeout`.

## Diagnosis
Run `SHOW POOLS;` on the PgBouncer admin console. Many `cl_waiting` with few `sv_active` means a few long transactions are holding server connections.

## Mitigation
Find idle-in-transaction sessions and kill them. Set `idle_in_transaction_session_timeout = 30s` on the database. Raise `default_pool_size` only after fixing the leak.
