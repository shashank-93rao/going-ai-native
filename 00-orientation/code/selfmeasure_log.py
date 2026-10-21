"""Append-only JSONL event log for a personal AI / no-AI A/B experiment.

The log is event-sourced: every fact is one line, nothing is ever edited in
place, and the per-task state is a fold over the events. That gives you an
audit trail (you cannot quietly re-roll an assignment you did not like) and
makes the analysis reproducible from the raw file.

Event types (all carry "event", "task_id", "ts" as ISO-8601 UTC):

    register   title, kind, size ("S"|"M"|"L"), est_minutes  (estimate made BEFORE assignment)
    assign     arm ("ai"|"no_ai"), block, seed_id             (written by assign_arm, never by hand)
    start      -
    merge      pr (optional), active_minutes (optional)
    rework     rework_kind ("fix"|"revert"|"followup"), minutes
    abandon    reason
    perceive   perceived_other_arm_minutes  (your guess: how long it would have taken in the other arm)
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ARMS = ("ai", "no_ai")
SIZES = ("S", "M", "L")
EVENT_FIELDS: dict[str, set[str]] = {
    "register": {"title", "kind", "size", "est_minutes"},
    "assign": {"arm", "block", "seed_id"},
    "start": set(),
    "merge": set(),
    "rework": {"rework_kind", "minutes"},
    "abandon": {"reason"},
    "perceive": {"perceived_other_arm_minutes"},
}


class LogError(ValueError):
    """Raised for an event that would corrupt the experiment."""


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_ts(ts: str) -> datetime:
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def read_events(path: str | Path) -> list[dict[str, Any]]:
    """Read the log. Blank lines are skipped; a malformed line fails loudly with its line number."""
    p = Path(path)
    if not p.exists():
        return []
    out = []
    for n, line in enumerate(p.read_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError as e:
            raise LogError(f"{p}:{n}: not valid JSON ({e.msg})") from e
    return out


@dataclass
class TaskState:
    """The fold of all events for one task."""

    task_id: str
    title: str = ""
    kind: str = ""
    size: str = ""
    est_minutes: float | None = None
    arm: str | None = None
    block: str | None = None
    started: datetime | None = None
    merged: datetime | None = None
    active_minutes: float | None = None
    abandoned: bool = False
    rework: list[dict[str, Any]] = field(default_factory=list)
    perceived_other_arm_minutes: float | None = None

    @property
    def hours_to_merge(self) -> float | None:
        if self.started and self.merged:
            return (self.merged - self.started).total_seconds() / 3600
        return None


def fold(events: Iterable[dict[str, Any]]) -> dict[str, TaskState]:
    """Replay events into per-task state, enforcing the experiment's invariants."""
    tasks: dict[str, TaskState] = {}
    for ev in events:
        validate_event(ev)
        tid, kind = ev["task_id"], ev["event"]
        if kind == "register":
            if tid in tasks:
                raise LogError(f"{tid}: registered twice")
            tasks[tid] = TaskState(tid, ev["title"], ev["kind"], ev["size"], float(ev["est_minutes"]))
            continue
        if tid not in tasks:
            raise LogError(f"{tid}: '{kind}' before 'register'")
        t = tasks[tid]
        if kind == "assign":
            if t.arm is not None:
                raise LogError(f"{tid}: assigned twice (re-rolling an assignment breaks randomization)")
            t.arm, t.block = ev["arm"], ev["block"]
        elif t.arm is None:
            raise LogError(f"{tid}: '{kind}' before 'assign'")
        elif kind == "start":
            t.started = parse_ts(ev["ts"])
        elif kind == "merge":
            if t.started is None:
                raise LogError(f"{tid}: merge before start")
            t.merged = parse_ts(ev["ts"])
            if ev.get("active_minutes") is not None:
                t.active_minutes = float(ev["active_minutes"])
        elif kind == "rework":
            t.rework.append({"ts": ev["ts"], "kind": ev["rework_kind"], "minutes": float(ev["minutes"])})
        elif kind == "abandon":
            t.abandoned = True
        elif kind == "perceive":
            t.perceived_other_arm_minutes = float(ev["perceived_other_arm_minutes"])
    return tasks


def validate_event(ev: dict[str, Any]) -> None:
    for key in ("event", "task_id", "ts"):
        if key not in ev:
            raise LogError(f"event missing '{key}': {ev}")
    kind = ev["event"]
    if kind not in EVENT_FIELDS:
        raise LogError(f"unknown event type '{kind}'")
    missing = EVENT_FIELDS[kind] - ev.keys()
    if missing:
        raise LogError(f"{ev['task_id']}: '{kind}' missing {sorted(missing)}")
    if kind == "register" and ev["size"] not in SIZES:
        raise LogError(f"{ev['task_id']}: size must be one of {SIZES}")
    if kind == "assign" and ev["arm"] not in ARMS:
        raise LogError(f"{ev['task_id']}: arm must be one of {ARMS}")
    parse_ts(ev["ts"])


def append_event(path: str | Path, event: dict[str, Any]) -> dict[str, Any]:
    """Validate against the existing log (by replaying it), then append one line."""
    event = {"ts": now_iso(), **event}
    events = read_events(path)
    fold(events + [event])  # raises if this event would break an invariant
    with Path(path).open("a") as f:
        f.write(json.dumps(event, sort_keys=True) + "\n")
    return event


def _coin(seed: str, *parts: str) -> int:
    """A deterministic fair coin from a secret seed. Same inputs, same flip."""
    h = hashlib.sha256("|".join((seed, *parts)).encode()).digest()
    return h[0] & 1


def seed_id(seed: str) -> str:
    """A short public fingerprint of the seed, so the log proves which seed was used."""
    return hashlib.sha256(seed.encode()).hexdigest()[:8]


def choose_arm(seed: str, block: str, prior_in_block: list[str]) -> str:
    """Permuted blocks of 2 within each size bucket.

    The first task of each pair gets a coin flip; the second gets the other arm.
    That keeps S/M/L tasks balanced across arms even with a small n, which plain
    coin flips do not (10 tasks can easily land 7/3).
    """
    if len(prior_in_block) % 2 == 1:
        return "no_ai" if prior_in_block[-1] == "ai" else "ai"
    pair_index = str(len(prior_in_block) // 2)
    return ARMS[_coin(seed, block, pair_index)]


def assign_arm(path: str | Path, task_id: str, seed: str, ts: str | None = None) -> str:
    """Assign a registered task to an arm and log it. Refuses to assign twice."""
    events = read_events(path)
    tasks = fold(events)
    if task_id not in tasks:
        raise LogError(f"{task_id}: register the task (with your estimate) before assigning it")
    block = tasks[task_id].size
    # Prior arms in this block, in the order they were assigned (not registered).
    prior = [e["arm"] for e in events if e["event"] == "assign" and e["block"] == block]
    arm = choose_arm(seed, block, prior)
    ev = {"event": "assign", "task_id": task_id, "arm": arm, "block": block, "seed_id": seed_id(seed)}
    append_event(path, {**ev, "ts": ts} if ts else ev)
    return arm


def assign_pending(path: str | Path, seed: str) -> dict[str, str]:
    """Assign every registered-but-unassigned task, in registration order.

    Prefer this over assigning one task at a time. With pairs, the second arm in a
    block is predictable, and if you know it you may (unconsciously) pick which task
    to register next. Registering a batch, then assigning the batch, closes that gap.
    """
    pending = [t.task_id for t in fold(read_events(path)).values() if t.arm is None]
    return {tid: assign_arm(path, tid, seed) for tid in pending}
