---
id: rb-dns-resolution
title: DNS resolution failures inside the cluster
kind: runbook
team: platform
acl: eng
version: 2
---
# DNS resolution failures inside the cluster

Owner: platform. Pager alert: `CoreDNSErrorsHigh` (SERVFAIL or timeout rate > 1%).

## Symptoms
Services log `no such host` or `i/o timeout` when calling internal names. Errors are intermittent and spread across many services at once.

## Diagnosis
Run `nslookup` from a debug pod and check CoreDNS logs for SERVFAIL. A high `ndots` setting causes five search-domain queries per lookup; conntrack table exhaustion on nodes causes UDP drops.

## Mitigation
Scale CoreDNS: `kubectl -n kube-system scale deploy/coredns --replicas=6`. For chatty clients, use fully qualified names with a trailing dot to skip search domains, or set `ndots: 2` in the pod dnsConfig.

## Verification
SERVFAIL and timeout rate under 0.1%.
