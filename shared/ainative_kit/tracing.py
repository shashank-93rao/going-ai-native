"""Minimal span tracer writing JSONL. Enough to do error analysis without a vendor.

    tracer = Tracer("traces.jsonl")
    with tracer.span("agent_run", task_id="t1") as s:
        with tracer.span("llm_call") as c:
            c.attrs["tokens"] = 1234

Each line is one finished span: {trace_id, span_id, parent_id, name, start, end, attrs, error}.
"""

from __future__ import annotations

import contextvars
import json
import time
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterator

_current: contextvars.ContextVar["Span | None"] = contextvars.ContextVar("current_span", default=None)


@dataclass
class Span:
    name: str
    trace_id: str
    span_id: str
    parent_id: str | None
    start: float
    end: float | None = None
    attrs: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


class Tracer:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else None
        self.spans: list[Span] = []

    @contextmanager
    def span(self, name: str, **attrs: Any) -> Iterator[Span]:
        parent = _current.get()
        s = Span(
            name=name,
            trace_id=parent.trace_id if parent else uuid.uuid4().hex[:12],
            span_id=uuid.uuid4().hex[:8],
            parent_id=parent.span_id if parent else None,
            start=time.time(),
            attrs=dict(attrs),
        )
        token = _current.set(s)
        try:
            yield s
        except Exception as e:
            s.error = f"{type(e).__name__}: {e}"
            raise
        finally:
            s.end = time.time()
            _current.reset(token)
            self.spans.append(s)
            if self.path:
                with self.path.open("a") as f:
                    f.write(json.dumps(asdict(s), default=str) + "\n")


def load_traces(path: str | Path) -> dict[str, list[dict[str, Any]]]:
    """Group a JSONL trace file by trace_id, spans sorted by start time."""
    out: dict[str, list[dict[str, Any]]] = {}
    for line in Path(path).read_text().splitlines():
        row = json.loads(line)
        out.setdefault(row["trace_id"], []).append(row)
    for spans in out.values():
        spans.sort(key=lambda r: r["start"])
    return out
