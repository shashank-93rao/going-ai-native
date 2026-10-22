---
id: adr-039-iceberg-warehouse
title: ADR-039: Iceberg tables for the warehouse
kind: adr
team: data
acl: eng
version: 1
---
# ADR-039: Iceberg tables for the warehouse

Status: accepted (2026-03).

## Decision
Fact tables move to Apache Iceberg so loads can use atomic partition overwrite and time travel. Every load writes with `MERGE` on a natural key, never blind `INSERT`.

## Consequences
Retried loads become idempotent. Deletes for data-subject requests become row-level deletes followed by snapshot expiry.
