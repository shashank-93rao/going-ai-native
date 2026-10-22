---
id: rb-kafka-consumer-lag
title: Kafka consumer lag on invoice-consumer
kind: runbook
team: payments
acl: eng
version: 4
---
# Kafka consumer lag on invoice-consumer

Owner: payments. Pager alert: `InvoiceConsumerLagHigh` (lag > 50k messages for 10 minutes on topic `invoices.v2`).

## Symptoms
Invoices appear in the ledger late. The committed offset of group `invoice-consumer` falls behind the log end offset. Messages-in is steady while records-consumed drops.

## Diagnosis
Check lag per partition with `kafka-consumer-groups --bootstrap-server $KAFKA --describe --group invoice-consumer`. If one partition dominates, suspect a hot key or a poison message rather than under-provisioning.

Rebalance storms usually mean `max.poll.interval.ms` is too low for the batch size, so the broker evicts the consumer mid-batch. Look for `Revoking previously assigned partitions` in the consumer logs.

## Mitigation
Scale out only up to the partition count; extra replicas sit idle. `kubectl -n billing scale deploy/invoice-consumer --replicas=12`

If a single offset fails repeatedly, route it to the dead-letter topic: `billing-ctl dlq skip --topic invoices.v2 --partition <p> --offset <o>`. Never reset the group offset to latest; that silently drops invoices.

## Verification
Lag falls monotonically within 15 minutes and `invoice_ledger_write_total` is rising.
