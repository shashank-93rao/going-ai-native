---
id: rb-warehouse-load-late
title: Warehouse load is late
kind: runbook
team: data
acl: eng
version: 3
---
# Warehouse load is late

Owner: data. Pager alert: `WarehouseFreshnessBreach` (fact tables older than 2h).

## Symptoms
Dashboards show yesterday's numbers. The freshness check on `fct_payments` fails.

## Diagnosis
Check the CDC connector status with `connectctl status pg-ledger-cdc`. A paused connector or a full replication slot on the source are the usual causes.

## Mitigation
Restart the connector with `connectctl restart pg-ledger-cdc`. If the replication slot is near `max_slot_wal_keep_size`, page platform before the slot is invalidated.

## Verification
`fct_payments` freshness under 30 minutes.
