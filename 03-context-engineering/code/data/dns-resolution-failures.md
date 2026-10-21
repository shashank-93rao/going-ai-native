# DNS resolution failures inside the cluster

Owner: platform. Pager alert: `CoreDNSErrorsHigh` (SERVFAIL or timeout rate > 1%).

## Symptoms
Services log `no such host` or `i/o timeout` when calling internal names such as `ledger-db-primary.billing.svc`. Errors are intermittent and spread across many services at once.

## Diagnosis
Run a lookup from a debug pod: `kubectl run dnsdebug --rm -it --image=busybox -- nslookup ledger-db-primary.billing.svc`.

Check CoreDNS: `kubectl -n kube-system logs deploy/coredns --since=10m | grep -i -E "servfail|timeout"`. High `ndots` causes many search-domain queries per lookup; conntrack table exhaustion on nodes causes UDP drops.

## Mitigation
Scale CoreDNS: `kubectl -n kube-system scale deploy/coredns --replicas=6`. For chatty clients, use fully qualified names with a trailing dot to skip search domains.

## Verification
SERVFAIL and timeout rate under 0.1% and the debug lookup succeeds.
