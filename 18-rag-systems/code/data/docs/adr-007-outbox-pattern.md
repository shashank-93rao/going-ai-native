---
id: adr-007-outbox-pattern
title: ADR-007: Transactional outbox for payment events
kind: adr
team: payments
acl: eng
version: 1
---
# ADR-007: Transactional outbox for payment events

Status: accepted (2024-03).

## Context
payments-api wrote to Postgres and then published to Kafka. When the publish failed after the commit, downstream services never learned about the payment.

## Decision
Write events to an `outbox` table in the same transaction as the payment row. A relay reads the outbox through logical replication and publishes to Kafka with the payment id as the message key.

## Consequences
Delivery is at-least-once, so every consumer must be idempotent on the event id. Ordering holds per payment id.
