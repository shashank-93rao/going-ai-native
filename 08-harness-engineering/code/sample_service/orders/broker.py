"""In-memory fake of a partitioned log (Kafka-shaped) for hermetic tests.

Semantics that matter for the invariants:
- Messages with the same key land on the same partition, in publish order.
- Consumers read from a committed offset per (group, partition), so anything
  not committed is redelivered: at-least-once.
- `fail_next(n)` and `fail_when(pred)` inject publish failures.
"""

from __future__ import annotations

import zlib
from dataclasses import dataclass
from typing import Any, Callable


class BrokerError(Exception):
    pass


@dataclass(frozen=True)
class Message:
    topic: str
    partition: int
    offset: int
    key: str
    value: dict[str, Any]


class FakeBroker:
    def __init__(self, partitions: int = 3):
        self.partitions = partitions
        self.log: dict[tuple[str, int], list[Message]] = {}
        self.committed: dict[tuple[str, str, int], int] = {}
        self._fail_budget = 0
        self._fail_pred: Callable[[str, dict[str, Any]], bool] | None = None

    def partition_for(self, key: str) -> int:
        return zlib.crc32(key.encode()) % self.partitions

    def fail_next(self, n: int = 1) -> None:
        self._fail_budget = n

    def fail_when(self, pred: Callable[[str, dict[str, Any]], bool] | None) -> None:
        self._fail_pred = pred

    def publish(self, topic: str, key: str, value: dict[str, Any]) -> Message:
        if self._fail_budget > 0:
            self._fail_budget -= 1
            raise BrokerError("broker unavailable (injected)")
        if self._fail_pred and self._fail_pred(key, value):
            raise BrokerError("broker rejected message (injected)")
        p = self.partition_for(key)
        msgs = self.log.setdefault((topic, p), [])
        msg = Message(topic, p, len(msgs), key, dict(value))
        msgs.append(msg)
        return msg

    def poll(self, topic: str, group: str, max_messages: int = 100) -> list[Message]:
        out: list[Message] = []
        for p in range(self.partitions):
            start = self.committed.get((group, topic, p), 0)
            out.extend(self.log.get((topic, p), [])[start:])
        return out[:max_messages]

    def commit(self, group: str, msg: Message) -> None:
        self.committed[(group, msg.topic, msg.partition)] = msg.offset + 1

    def messages(self, topic: str) -> list[Message]:
        """All messages on a topic, partition by partition (test helper)."""
        return [m for p in range(self.partitions) for m in self.log.get((topic, p), [])]
