# Kafka consumer lag on invoice-consumer

Owner: billing-platform. Pager alert: `InvoiceConsumerLagHigh` (lag > 50k messages for 10 minutes on topic `invoices.v2`).

## Symptoms
Invoices appear in the ledger late. The alert fires when the committed offset of group `invoice-consumer` falls behind the log end offset. Dashboards show messages-in steady while records-consumed drops.

## Diagnosis
Check lag per partition. If one partition dominates, suspect a hot key or a poison message rather than under-provisioning.

`kafka-consumer-groups --bootstrap-server $KAFKA --describe --group invoice-consumer`

Look for repeated rebalances in the consumer logs: `grep "Revoking previously assigned partitions" /var/log/invoice-consumer/*.log | tail`. Rebalance storms usually mean `max.poll.interval.ms` is too low for the batch size, so the broker evicts the consumer mid-batch.

## Mitigation
Scale out only up to the partition count; extra replicas sit idle. `kubectl -n billing scale deploy/invoice-consumer --replicas=12`

If a single offset fails repeatedly, route it to the dead-letter topic with the skip tool: `billing-ctl dlq skip --topic invoices.v2 --partition <p> --offset <o>`. Never reset the group offset to latest; that silently drops invoices.

## Verification
Lag should fall monotonically within 15 minutes. Confirm with the describe command above and check that `invoice_ledger_write_total` is rising.
