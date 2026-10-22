---
id: pm-2026-040-log-flood-disk
title: Postmortem 2026-040: Log flood filled node disks
kind: postmortem
team: platform
acl: eng
version: 1
---
# Postmortem 2026-040: Log flood filled node disks

Severity: SEV3.

## Summary
A service logged a stack trace per request and filled ephemeral storage on six nodes. Pods were evicted for DiskPressure.

## Action items
Enforce log rotation at the container runtime. Rate-limit identical error logs.
