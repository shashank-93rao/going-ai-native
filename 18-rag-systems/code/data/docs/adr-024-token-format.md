---
id: adr-024-token-format
title: ADR-024: Short-lived access tokens
kind: adr
team: identity
acl: eng
version: 1
---
# ADR-024: Short-lived access tokens

Status: accepted (2025-04).

## Decision
Access tokens are JWTs signed with an asymmetric key and expire after 15 minutes. Refresh tokens are opaque, stored server-side, and revocable.

## Consequences
Signing key rotation must keep the old public key in JWKS until all tokens signed with it expire.
