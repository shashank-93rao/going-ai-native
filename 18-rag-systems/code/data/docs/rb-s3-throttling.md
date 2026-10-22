---
id: rb-s3-throttling
title: S3 503 SlowDown throttling
kind: runbook
team: data
acl: eng
version: 1
---
# S3 503 SlowDown throttling

Owner: data.

## Symptoms
Jobs fail with `503 SlowDown` from S3, usually during backfills.

## Diagnosis
S3 scales request rate per prefix. A backfill that writes every task to one prefix concentrates load.

## Mitigation
Spread writes across date-partitioned prefixes and retry with exponential backoff and jitter. Lower backfill parallelism.
