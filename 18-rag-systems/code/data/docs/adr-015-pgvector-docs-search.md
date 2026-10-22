---
id: adr-015-pgvector-docs-search
title: ADR-015: pgvector for internal docs search
kind: adr
team: platform
acl: eng
version: 1
---
# ADR-015: pgvector for internal docs search

Status: accepted (2026-02).

## Context
We want semantic search over runbooks, ADRs and postmortems, about 40k chunks. Running a separate vector database means another stateful system for platform to operate.

## Decision
Use the pgvector extension on the existing docs Postgres cluster with an HNSW index (m=16, ef_construction=64). ACL filters are SQL predicates in the same query. Revisit if the corpus passes 5 million chunks or p95 query latency passes 150 ms.

## Consequences
Backups, failover and access control reuse the Postgres runbooks. Filtered queries need iterative index scans so restrictive ACL filters still return enough rows.
