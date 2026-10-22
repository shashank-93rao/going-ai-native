---
id: rb-feature-flag-kill-switch
title: Using a feature flag kill switch
kind: runbook
team: platform
acl: eng
version: 2
---
# Using a feature flag kill switch

Owner: platform.

## When to use
Use a kill switch when a feature misbehaves in production and a rollback would also revert unrelated fixes.

## Procedure
Set the flag off with `flagctl set <flag>=off --reason "<incident id>"`. Flag changes propagate to all services within 30 seconds. Every change is audited and needs an incident id.

## Verification
The flag evaluation dashboard shows the new value served by all pods.
