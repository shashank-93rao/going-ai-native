---
id: rb-node-disk-pressure
title: Kubernetes node DiskPressure
kind: runbook
team: platform
acl: eng
version: 2
---
# Kubernetes node DiskPressure

Owner: platform. Pager alert: `NodeDiskPressure` (node condition DiskPressure=True).

## Symptoms
Pods are evicted with message `The node was low on resource: ephemeral-storage`. New pods stay Pending on the affected node. Engineers usually report this as the box being out of space.

## Diagnosis
Find the node and its biggest consumers with `kubectl describe node <node>`. Container logs without rotation and leftover image layers are the usual causes.

## Mitigation
Cordon the node: `kubectl cordon <node>`. Prune unused images with `crictl rmi --prune`, then uncordon. If one workload writes heavily to emptyDir, set an `ephemeral-storage` limit on it.

## Verification
The DiskPressure condition returns to False and evicted pods are rescheduled.
