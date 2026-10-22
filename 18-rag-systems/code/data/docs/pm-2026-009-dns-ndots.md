---
id: pm-2026-009-dns-ndots
title: Postmortem 2026-009: DNS latency from ndots
kind: postmortem
team: platform
acl: eng
version: 1
---
# Postmortem 2026-009: DNS latency from ndots

Severity: SEV3.

## Summary
p99 latency on internal calls rose by 40 ms after a base image change reset `ndots` to 5.

## Root cause
Each lookup of an external name tried five search domains first, and CoreDNS hit its CPU limit.

## Action items
Pin `ndots: 2` in the shared pod template.
