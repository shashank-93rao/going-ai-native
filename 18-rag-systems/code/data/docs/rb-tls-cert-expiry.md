---
id: rb-tls-cert-expiry
title: TLS certificate expiry
kind: runbook
team: platform
acl: eng
version: 3
---
# TLS certificate expiry

Owner: platform. Pager alert: `CertExpiringSoon` (less than 14 days to expiry) or `CertExpired`.

## Symptoms
Clients fail with `x509: certificate has expired or is not yet valid`. Partner webhooks start failing handshakes.

## Diagnosis
Check what the endpoint serves with `openssl s_client` and `openssl x509 -noout -enddate`. Check cert-manager with `kubectl -n billing get certificate`. A stuck ACME challenge is the most common cause of a missed renewal.

## Mitigation
Force renewal: `cmctl renew -n billing ledger-api-tls`. If ACME is broken, install the break-glass certificate and open a platform ticket.

## Verification
The served notAfter date moves forward and `CertExpiringSoon` clears.
