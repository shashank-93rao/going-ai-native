# TLS certificate expiry

Owner: security-eng. Pager alert: `CertExpiringSoon` (less than 14 days to expiry) or `CertExpired`.

## Symptoms
Clients fail with `x509: certificate has expired or is not yet valid` or `certificate verify failed`. Partner webhooks to billing start failing handshakes.

## Diagnosis
Check what the endpoint actually serves: `openssl s_client -connect api.billing.example.com:443 -servername api.billing.example.com </dev/null | openssl x509 -noout -enddate`.

Check cert-manager's view: `kubectl -n billing get certificate` and `kubectl -n billing describe certificaterequest`. A stuck ACME challenge is the most common cause of a missed renewal.

## Mitigation
Force renewal: `cmctl renew -n billing ledger-api-tls`. If ACME is broken, install the break-glass certificate from the vault path `secret/billing/tls/breakglass` and open a security-eng ticket.

## Verification
The `openssl` command above shows a new notAfter date, and the `CertExpiringSoon` alert clears.
