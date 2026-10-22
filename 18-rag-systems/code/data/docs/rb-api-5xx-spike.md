---
id: rb-api-5xx-spike
title: API 5xx spike at the gateway
kind: runbook
team: sre
acl: eng
version: 3
---
# API 5xx spike at the gateway

Owner: sre. Pager alert: `Gateway5xxRateHigh` (5xx ratio > 2% over 5 minutes).

## Symptoms
Clients see HTTP 503 and 504 from the gateway. Retries amplify load, so the error rate can climb even after the trigger is gone.

## Diagnosis
Split by status and route first. 503 with `upstream connect error` points at pod readiness; 504 points at slow dependencies. Check whether a deploy happened in the last hour; most spikes correlate with a rollout.

## Mitigation
If the spike started with a rollout, roll back first and debug later. If a dependency is slow, open its circuit breaker with `flagctl set ledger.fx_rates.breaker=open`.

## Verification
5xx ratio under 0.5% for 15 minutes and error budget burn rate back under 1x.
