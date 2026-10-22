---
id: adr-012-idempotency-keys
title: ADR-012: Idempotency keys on payments-api
kind: adr
team: payments
acl: eng
version: 2
---
# ADR-012: Idempotency keys on payments-api

Status: accepted (2024-06).

## Context
Mobile clients retry POST /payments on timeouts. Without dedupe, a retry after a slow success creates a second charge.

## Decision
Every mutating request carries an `Idempotency-Key` header. The server stores the key and the response in the idempotency-cache with a 24h TTL and returns the stored response for a repeat key. Keys are scoped per merchant.

## Consequences
The idempotency-cache becomes correctness-critical, so its eviction policy must never evict live keys.
