---
id: pm-2026-019-session-loss
title: Postmortem 2026-019: Users logged out by Redis evictions
kind: postmortem
team: identity
acl: eng
version: 1
---
# Postmortem 2026-019: Users logged out by Redis evictions

Severity: SEV2.

## Summary
Users were logged out randomly for two hours. The session store Redis ran out of memory and evicted session keys.

## Root cause
A config change set `maxmemory-policy allkeys-lru` on the shared Redis cluster that holds both sessions and a cache.

## Action items
Split sessions onto their own cluster with `noeviction` and alert on `evicted_keys`.
