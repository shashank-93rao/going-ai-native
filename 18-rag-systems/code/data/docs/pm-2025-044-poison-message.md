---
id: pm-2025-044-poison-message
title: Postmortem 2025-044: Invoice lag from a poison message
kind: postmortem
team: payments
acl: eng
version: 1
---
# Postmortem 2025-044: Invoice lag from a poison message

Severity: SEV2. Duration: 3 hours 10 minutes.

## Summary
One malformed invoice on partition 7 of `invoices.v2` made invoice-consumer crash and restart in a loop. Lag on that partition reached 400k messages.

## Root cause
The consumer had no dead-letter path, so it retried the same offset forever. Scaling out did not help because the partition count was already the limit.

## Action items
Add the dead-letter skip tool. Alert on lag per partition, not only total lag.
