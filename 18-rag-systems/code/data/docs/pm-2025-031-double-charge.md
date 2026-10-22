---
id: pm-2025-031-double-charge
title: Postmortem 2025-031: Double charges on payment retry
kind: postmortem
team: payments
acl: eng
version: 2
---
# Postmortem 2025-031: Double charges on payment retry

Severity: SEV1. Duration: 47 minutes.

## Summary
About 1,900 customers were charged twice. A new checkout path retried POST /payments without sending the `Idempotency-Key` header, so payments-api treated each retry as a new payment.

## Root cause
The retry wrapper in the new checkout path built a fresh request object and dropped headers. The idempotency design from ADR-012 was correct; the client did not use it.

## Action items
Reject mutating requests without an `Idempotency-Key` with HTTP 400. Add a contract test that replays a request and asserts one charge.
