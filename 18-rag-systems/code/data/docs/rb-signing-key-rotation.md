---
id: rb-signing-key-rotation
title: Rotating the auth token signing key
kind: runbook
team: identity
acl: identity,sre
version: 4
---
# Rotating the auth token signing key

Owner: identity. Restricted: identity and sre only.

## When to rotate
Rotate on schedule every 90 days, or immediately if the private key may have been exposed.

## Procedure
Generate the new key in the KMS with `keyctl create --purpose token-signing`. Publish it to the JWKS endpoint as a secondary key and wait 15 minutes for caches to refresh. Then promote it with `keyctl promote <kid>`. Keep the old key in JWKS for 24 hours so in-flight tokens still validate.

## Verification
New tokens carry the new `kid` and the auth error rate is flat.
