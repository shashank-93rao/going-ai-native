---
id: pm-2026-014-replica-lag-404
title: Postmortem 2026-014: 404s after create from replica lag
kind: postmortem
team: platform
acl: eng
version: 2
---
# Postmortem 2026-014: 404s after create from replica lag

Severity: SEV2. Duration: 1 hour 25 minutes.

## Summary
Clients got 404 on GET right after creating a payment. Replica lag reached 90 seconds.

## Root cause
A finance analytics query ran for 40 minutes on the replica with `hot_standby_feedback` on and blocked WAL replay. ledger-api read from the replica with no read-your-writes guarantee.

## Action items
Move analytics to the warehouse. Adopt primary pinning after writes (ADR-027).
