---
id: pm-2026-036-retry-storm
title: Postmortem 2026-036: Retry storm through the gateway
kind: postmortem
team: sre
acl: eng
version: 1
---
# Postmortem 2026-036: Retry storm through the gateway

Severity: SEV1. Duration: 38 minutes.

## Summary
A 2-minute slowdown in fx-rates turned into a 38-minute outage of ledger-api.

## Root cause
Clients retried 3 times, the SDK retried 3 times, and Envoy retried 2 times: up to 18x amplification on a degraded dependency. The Envoy retry budget from ADR-021 had not been rolled out to this route.

## Action items
Apply the retry budget to all routes. Remove SDK-level retries for internal calls.
