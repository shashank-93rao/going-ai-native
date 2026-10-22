---
id: adr-018-invoice-partitions
title: ADR-018: Partition count for invoices.v2
kind: adr
team: payments
acl: eng
version: 1
---
# ADR-018: Partition count for invoices.v2

Status: accepted (2024-09).

## Decision
`invoices.v2` has 12 partitions keyed by merchant id. This caps invoice-consumer parallelism at 12 replicas.

## Consequences
Increasing partitions later reshuffles keys and breaks per-merchant ordering during the transition, so it needs a planned migration.
