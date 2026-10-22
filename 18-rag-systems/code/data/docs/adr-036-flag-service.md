---
id: adr-036-flag-service
title: ADR-036: Central feature flag service
kind: adr
team: platform
acl: eng
version: 1
---
# ADR-036: Central feature flag service

Status: accepted (2025-10).

## Decision
All runtime flags live in one flag service with an audit log. Services cache flags and refresh every 30 seconds. Kill switches are flags whose default is on.
