---
name: investigate-kafka-consumer-lag
description: Triage a Kafka consumer lag alert (ConsumerLagHigh, ConsumerGroupLagGrowing, Burrow WARN/ERR) down to a cause and a safe next action. Use when an alert, page or user mentions consumer lag, a consumer group falling behind, offsets not advancing, or a stuck partition. Read-only investigation; it never resets offsets or restarts consumers itself.
metadata:
  owner: platform-streaming
  version: "1.2"
---

# Investigate a Kafka consumer lag alert

Goal: within ~10 minutes, classify the lag into one of the causes in
[references/causes.md](references/causes.md), with evidence, and propose the least risky next action.
You are read-only. Never run `kafka-consumer-groups.sh --reset-offsets`, `--delete`, or restart
pods. Those go in your recommendation for a human.

## Step 1: Get the lag shape (always)

Run describe for the group, then pipe it through the bundled summarizer. Execute the script; do not
read it into context.

```bash
kafka-consumer-groups.sh --bootstrap-server "$KAFKA_BOOTSTRAP" --describe --group "<group>" \
  | python3 scripts/lag_summary.py
```

If you don't know the group name, list them: `kafka-consumer-groups.sh --bootstrap-server "$KAFKA_BOOTSTRAP" --list | grep <service>`.
If you have no shell access to Kafka, use the `kafka_consumer_lag` tool instead; it returns the same summary fields.

The summary prints `shape=` as one of `single_partition`, `uniform`, `unassigned`, `none`. Use it to
choose the branch in Step 3.

## Step 2: Is it still growing? (always)

One snapshot can't tell a backlog that is draining from one that is growing. Take a second sample
60 seconds later, or query the metric over 30 minutes (queries in [references/commands.md](references/commands.md)).
Record: lag now, lag 30m ago, and the direction.

## Step 3: Branch on shape

- **single_partition**: one partition holds most of the lag. Search the consumer's logs for that
  partition number and errors (`partition=<n>`, `deserializ`, `poison`, `retry`). Check the
  producer side for a recent schema or deploy change. Likely causes: poison message, hot key.
- **uniform**: lag spread across partitions. Check, in order: a recent deploy of the consumer
  (throughput regression), downstream latency (DB or HTTP p99 from the consumer's dashboards),
  consumers vs partitions (more consumers than partitions adds nothing), producer rate spike.
- **unassigned**: partitions have no consumer (`CONSUMER-ID` is `-`). Check for crash-looping
  pods and rebalance storms (`Revoking previously assigned partitions` / `Attempt to heartbeat failed`
  repeating in logs; `max.poll.interval.ms` exceeded).
- **none**: lag is below threshold now. Check whether the alert has already recovered; report that and stop.

## Step 4: Report

Fill in [assets/incident-note-template.md](assets/incident-note-template.md). Every claim cites the
command or query that produced it. If evidence is missing, write "unknown" rather than guessing.

## Gotchas

- `LAG` is computed from *committed* offsets. A consumer that processes but commits rarely shows
  sawtooth lag that is not an incident.
- Lag in messages is not lag in time. A partition with 50k small messages may be 4 seconds behind.
  Prefer time-lag metrics when they exist.
- During a rebalance, `--describe` can briefly show every partition as unassigned. Re-sample before
  concluding `unassigned`.
