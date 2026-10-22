---
id: adr-042-docs-assistant-acl
title: ADR-042: Permission-aware docs assistant
kind: adr
team: platform
acl: eng
version: 1
---
# ADR-042: Permission-aware docs assistant

Status: accepted (2026-06).

## Decision
Every chunk inherits the ACL of its source document. The ACL filter is applied inside the retrieval query using the caller's verified team claims, never a team name supplied by the model or the user. Restricted postmortems stay restricted in the assistant.

## Consequences
A document's ACL change must reach the index within 5 minutes; this is a freshness SLO with a pager alert.
