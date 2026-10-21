# Read-only commands and queries

All of these are safe to run. Nothing here changes offsets or group membership.

## Kafka CLI

```bash
# Lag per partition (the input for scripts/lag_summary.py)
kafka-consumer-groups.sh --bootstrap-server "$KAFKA_BOOTSTRAP" --describe --group "$GROUP"

# Group members and their assignments (who owns which partition)
kafka-consumer-groups.sh --bootstrap-server "$KAFKA_BOOTSTRAP" --describe --group "$GROUP" --members --verbose

# Group state (Stable, PreparingRebalance, CompletingRebalance, Empty, Dead)
kafka-consumer-groups.sh --bootstrap-server "$KAFKA_BOOTSTRAP" --describe --group "$GROUP" --state
```

## Prometheus (kafka_exporter metric names; adjust if you use a different exporter)

```promql
# Total lag for the group, 30m trend
sum(kafka_consumergroup_lag{consumergroup="$GROUP"})

# Lag per partition, to see skew
max by (partition) (kafka_consumergroup_lag{consumergroup="$GROUP", topic="$TOPIC"})

# Produce rate on the topic (messages/s)
sum(rate(kafka_topic_partition_current_offset{topic="$TOPIC"}[5m]))
```

## Logs

Search the consumer service's logs for the hot partition and for rebalance messages:
`partition=<n>`, `deserializ`, `Revoking previously assigned partitions`, `Attempt to heartbeat failed`,
`max.poll.interval.ms`.
