---
id: adr-021-envoy-gateway
title: ADR-021: Move the edge to an Envoy gateway
kind: adr
team: platform
acl: eng
version: 1
---
# ADR-021: Move the edge to an Envoy gateway

Status: accepted (2025-01).

## Decision
Replace the nginx edge with Envoy. Retries are configured centrally with a retry budget of 20% of active requests, so client-side retries must be disabled for internal calls.

## Consequences
Timeouts must be aligned: app keep-alive above Envoy idle timeout.
