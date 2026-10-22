---
id: pm-2026-003-cert-expiry
title: Postmortem 2026-003: ledger-api certificate expired
kind: postmortem
team: platform
acl: eng
version: 1
---
# Postmortem 2026-003: ledger-api certificate expired

Severity: SEV2. Duration: 52 minutes.

## Summary
The public certificate for ledger-api expired and partner webhooks failed.

## Root cause
cert-manager could not complete the ACME HTTP-01 challenge after an ingress change, and the `CertExpiringSoon` alert was routed to a channel nobody watched.

## Action items
Route certificate alerts to the pager. Add a synthetic check that reads the served notAfter date daily.
