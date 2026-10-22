---
id: pm-2026-044-card-data-logs
title: Postmortem 2026-044: Card numbers in request logs
kind: postmortem
team: payments
acl: payments,security
version: 1
---
# Postmortem 2026-044: Card numbers in request logs

Severity: SEV1. Restricted: payments and security only.

## Summary
For 6 hours, a new endpoint logged full request bodies including primary account numbers, which put the log cluster in PCI scope.

## Root cause
The endpoint used a field named `pan` instead of `card_number`, so the redaction filter from ADR-030 did not match it.

## Action items
Redact by value pattern (Luhn-valid digit runs), not only by field name. Purge the affected indices and document the purge for the QSA.
