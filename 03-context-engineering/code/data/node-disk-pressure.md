# Kubernetes node DiskPressure

Owner: platform. Pager alert: `NodeDiskPressure` (node condition DiskPressure=True).

## Symptoms
Pods are evicted with reason `Evicted` and message `The node was low on resource: ephemeral-storage`. New pods stay Pending on the affected node.

## Diagnosis
Find the node and the biggest consumers: `kubectl describe node <node> | grep -A5 Conditions` and `kubectl get pods -A --field-selector spec.nodeName=<node>`.

Container logs without rotation and leftover image layers are the usual causes. On the node: `crictl rmi --prune` lists and removes unused images.

## Mitigation
Cordon the node so the scheduler stops placing pods there: `kubectl cordon <node>`. Prune unused images, then uncordon. If one workload writes heavily to emptyDir, set an `ephemeral-storage` limit on it.

## Verification
The DiskPressure condition returns to False and evicted pods are rescheduled.
