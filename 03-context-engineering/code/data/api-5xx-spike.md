# ledger-api 5xx spike

Owner: billing-platform. Pager alert: `LedgerApi5xxRateHigh` (5xx ratio > 2% over 5 minutes).

## Symptoms
Clients see HTTP 503 and 504 from the gateway. Retries amplify load, so the error rate can climb even after the trigger is gone.

## Diagnosis
Split by status and route first. 503 with `upstream connect error` points at pod readiness; 504 points at slow dependencies.

`kubectl -n billing logs deploy/ledger-api --since=10m | grep -c "status=503"`

Check whether a deploy happened in the last hour: `billing-ctl deploys list --service ledger-api --since 1h`. Most spikes correlate with a rollout.

## Mitigation
If the spike started with a rollout, roll back first and debug later (see the deploy rollback runbook). If a dependency is slow, enable the circuit breaker: `billing-ctl flags set ledger.fx_rates.breaker=open`.

## Verification
5xx ratio under 0.5% for 15 minutes; error budget burn rate back under 1x.
