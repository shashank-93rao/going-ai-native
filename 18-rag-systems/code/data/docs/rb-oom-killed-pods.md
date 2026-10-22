---
id: rb-oom-killed-pods
title: Pods OOMKilled
kind: runbook
team: platform
acl: eng
version: 1
---
# Pods OOMKilled

Owner: platform.

## Symptoms
Pods restart with reason `OOMKilled` and exit code 137.

## Diagnosis
Compare the container memory limit with the working set in the metrics dashboard. JVM services need `-XX:MaxRAMPercentage=75` so the heap fits under the container limit.

## Mitigation
Raise the limit or fix the leak. Do not remove the limit; an unbounded pod can starve the node.
