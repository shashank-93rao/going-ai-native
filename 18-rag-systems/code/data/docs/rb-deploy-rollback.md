---
id: rb-deploy-rollback
title: Rolling back a bad deploy
kind: runbook
team: platform
acl: eng
version: 5
---
# Rolling back a bad deploy

Owner: platform. Use this when a release causes errors, latency regressions, or data issues.

## When to roll back
Roll back when a release correlates with an SLO burn and the fix is not a one-line config change. Do not wait for root cause.

## Procedure
Find the last good revision with `deployctl list --service <svc> --since 24h`, then run `deployctl rollback --service <svc> --to <revision>`.

The rollback is safe only if the release did not run a schema migration. Expand-contract migrations allow rolling back code without reverting schema.

## Verification
Confirm the running image tag matches the target revision, then watch the service SLO dashboard for 15 minutes.
