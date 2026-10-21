"""Structured JSON logging that an agent can query with tools/diagnose.py.

Every record has: ts, component, event, level, plus correlation fields
(order_id, event_id, idem_key, partition, offset) when they apply.
Set ORDERS_LOG_PATH to also append records to a JSONL file.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

RECORDS: list[dict[str, Any]] = []
_MAX_RECORDS = 10_000


def log(component: str, event: str, level: str = "info", **fields: Any) -> dict[str, Any]:
    rec = {"ts": round(time.time(), 3), "component": component, "event": event, "level": level, **fields}
    RECORDS.append(rec)
    if len(RECORDS) > _MAX_RECORDS:
        del RECORDS[: len(RECORDS) - _MAX_RECORDS]
    path = os.environ.get("ORDERS_LOG_PATH")
    if path:
        with open(path, "a") as f:
            f.write(json.dumps(rec, sort_keys=True) + "\n")
    return rec


def reset() -> None:
    RECORDS.clear()
