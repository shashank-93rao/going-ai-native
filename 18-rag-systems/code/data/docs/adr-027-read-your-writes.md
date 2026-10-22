---
id: adr-027-read-your-writes
title: ADR-027: Read-your-writes via primary pinning
kind: adr
team: platform
acl: eng
version: 1
---
# ADR-027: Read-your-writes via primary pinning

Status: accepted (2026-02), written after the replica-lag 404 incident.

## Decision
After a write, ledger-api pins that client's reads to the primary for 5 seconds using a session cookie carrying the commit LSN. Reads go to a replica only once its replay LSN is at or past the cookie's LSN.

## Consequences
Primary read load rises about 8%. Replica lag no longer causes 404s after writes.
