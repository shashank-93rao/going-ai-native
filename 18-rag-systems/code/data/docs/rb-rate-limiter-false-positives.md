---
id: rb-rate-limiter-false-positives
title: Rate limiter blocking legitimate traffic
kind: runbook
team: identity
acl: eng
version: 2
---
# Rate limiter blocking legitimate traffic

Owner: identity.

## Symptoms
Customers behind a corporate NAT get HTTP 429 on login. Many users share one egress IP.

## Diagnosis
Check whether the limit key is the client IP. The login limiter uses a token bucket of 20 requests per minute per key.

## Mitigation
Key the login limiter on account id plus IP instead of IP alone. Add the customer's egress range to the allowlist only with a ticket from identity.
