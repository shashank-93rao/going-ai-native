---
id: rb-ledger-reconciliation
title: Ledger reconciliation mismatch
kind: runbook
team: payments
acl: payments,sre
version: 2
---
# Ledger reconciliation mismatch

Owner: payments. Restricted: payments and sre only.

## Symptoms
The nightly reconciliation job reports a mismatch between ledger totals and processor settlement files.

## Diagnosis
Run `billing-ctl recon diff --date <d>` and group mismatches by processor. Mismatches under 0.01% are usually timezone cutoffs at midnight UTC.

## Mitigation
For cutoff mismatches, rerun with `--cutoff-tz UTC`. For real gaps, open a finance-ops ticket; never edit ledger rows by hand.
