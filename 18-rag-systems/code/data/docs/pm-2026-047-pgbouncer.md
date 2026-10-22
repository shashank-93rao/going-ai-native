---
id: pm-2026-047-pgbouncer
title: Postmortem 2026-047: Connection pool exhaustion on ledger-db
kind: postmortem
team: platform
acl: eng
version: 1
---
# Postmortem 2026-047: Connection pool exhaustion on ledger-db

Severity: SEV2.

## Summary
ledger-api requests hung for 25 minutes. PgBouncer showed hundreds of waiting clients.

## Root cause
A code path opened a transaction, then called an external API while holding it. When the API slowed down, every server connection sat idle in transaction.

## Action items
Never call external services inside a database transaction. Set `idle_in_transaction_session_timeout`.
