---
id: rb-envoy-upstream-reset
title: Envoy 503 upstream reset before headers
kind: runbook
team: platform
acl: eng
version: 2
---
# Envoy 503 upstream reset before headers

Owner: platform. Pager alert: `EnvoyUpstreamResetHigh`.

## Symptoms
Access logs show response flag `UC` and the body `upstream connect error or disconnect/reset before headers`. Errors cluster right after pods restart.

## Diagnosis
Compare the upstream idle timeout with the app keep-alive timeout. If the app closes idle connections before Envoy does, Envoy reuses a dead connection and gets a reset.

## Mitigation
Set the app keep-alive timeout above the Envoy `idle_timeout` (ours is 60s, so use 65s). Add a retry policy with `retry_on: reset` capped at 2 attempts.

## Verification
`UC` flags drop to background levels within one deploy.
