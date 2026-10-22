---
id: pm-2026-051-s3-backfill
title: Postmortem 2026-051: Backfill throttled by S3
kind: postmortem
team: data
acl: eng
version: 1
---
# Postmortem 2026-051: Backfill throttled by S3

Severity: SEV3.

## Summary
A 90-day backfill ran 64 parallel tasks against one S3 prefix and was throttled for 5 hours.

## Action items
Cap backfill parallelism at 4 and write to date-partitioned prefixes.
