---
id: adr-030-log-retention
title: ADR-030: Log retention and redaction
kind: adr
team: sre
acl: eng
version: 2
---
# ADR-030: Log retention and redaction

Status: accepted (2025-07).

## Decision
Application logs are kept for 30 days, audit logs for 1 year. A redaction filter in the log shipper drops fields named `authorization`, `card_number` and `password` before indexing.

## Consequences
Anything the filter misses is retained for 30 days and must be purged by hand if it is sensitive.
