---
id: pm-2026-027-warehouse-duplicates
title: Postmortem 2026-027: Duplicate rows in fct_payments
kind: postmortem
team: data
acl: eng
version: 1
---
# Postmortem 2026-027: Duplicate rows in fct_payments

Severity: SEV3.

## Summary
Revenue dashboards overstated one day by 3%.

## Root cause
A retried load task used blind `INSERT` into `fct_payments`, so the retry appended the same rows twice.

## Action items
Move loads to `MERGE` on payment id (ADR-039). Add a uniqueness test on the fact table.
