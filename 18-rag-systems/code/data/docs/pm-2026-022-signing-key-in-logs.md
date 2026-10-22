---
id: pm-2026-022-signing-key-in-logs
title: Postmortem 2026-022: Signing key material in debug logs
kind: postmortem
team: identity
acl: identity,security
version: 1
---
# Postmortem 2026-022: Signing key material in debug logs

Severity: SEV1. Restricted: identity and security only.

## Summary
A debug log line in auth-service printed the private token signing key for 3 hours on two pods.

## Root cause
A temporary debug statement dumped the key config object. The log shipper redaction filter matched field names, and the key was nested under `signer.material`, which the filter did not cover.

## Response
The key was rotated within 40 minutes of detection using the signing key rotation runbook, and the affected log indices were purged.

## Action items
Add `signer.material` to the redaction filter. Block debug logging of config objects in auth-service with a lint rule.
