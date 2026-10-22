---
id: adr-033-cell-architecture
title: ADR-033: Cell-based architecture for checkout
kind: adr
team: platform
acl: eng
version: 1
---
# ADR-033: Cell-based architecture for checkout

Status: proposed (2026-05).

## Decision
Split checkout into independent cells of about 5,000 merchants each, with a thin routing layer. A bad deploy or a noisy merchant then affects one cell.

## Consequences
Cross-cell queries such as global reporting move to the warehouse.
