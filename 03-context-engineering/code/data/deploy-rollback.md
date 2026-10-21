# Rolling back a bad deploy

Owner: platform. Use this when a release causes errors, latency regressions, or data issues.

## When to roll back
Roll back when a release correlates with an SLO burn and the fix is not a one-line config change. Do not wait for root cause.

## Procedure
Find the last good revision: `billing-ctl deploys list --service <svc> --since 24h`. Then roll back: `billing-ctl deploys rollback --service <svc> --to <revision>`.

The rollback is safe only if the release did not run a schema migration. If it did, check the migration's down script in `migrations/` first; expand-contract migrations allow rollback of code without reverting schema.

## Verification
Confirm the running image tag matches the target revision with `kubectl -n billing get deploy/<svc> -o jsonpath='{.spec.template.spec.containers[0].image}'`, then watch the service's SLO dashboard for 15 minutes.
