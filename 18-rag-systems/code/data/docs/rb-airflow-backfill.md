---
id: rb-airflow-backfill
title: Backfilling an Airflow DAG safely
kind: runbook
team: data
acl: eng
version: 2
---
# Backfilling an Airflow DAG safely

Owner: data. Use when a DAG missed runs or produced bad partitions.

## Procedure
Clear and rerun with `airflow dags backfill -s <start> -e <end> --reset-dagruns <dag_id>`. Backfills must write with partition overwrite, never append, so that a rerun is idempotent.

## Limits
Run at most 4 backfill tasks in parallel (`max_active_runs=4`); larger fan-out triggers S3 503 SlowDown throttling on the raw bucket.

## Verification
Row counts per partition match the source system's daily totals within 0.1%.
