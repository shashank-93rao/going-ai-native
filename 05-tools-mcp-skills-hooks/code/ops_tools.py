"""A small on-call toolset: schemas (what the model sees) plus implementations (what runs).

The backend is an in-memory fake of a deploy system, Kafka and a log store, so everything
runs offline. The design choices are the point:
  - namespaced names (`deploys_*`, `kafka_*`, `logs_*`) so the model can tell tools apart
  - human-meaningful identifiers (service and group names, not UUIDs)
  - `response_format` on anything that can return a lot
  - pagination with an opaque cursor, and a hard per-response token budget
  - errors that name the fix ("Did you mean ...?", "valid values are ...")
"""

from __future__ import annotations

import difflib
import inspect
from typing import Any, Callable

from tool_formatter import ToolError, check_response_format, format_records

NOW = 1_760_000_000  # fixed "now" (epoch seconds) so outputs are deterministic

DEPLOYS: list[dict[str, Any]] = [
    {"deploy_id": "dpl_8f2c", "service": "ledger-writer", "env": "prod", "version": "v2.14.0",
     "status": "succeeded", "started_at": NOW - 2400, "deployer": "ci-bot", "commit": "a1b2c3d"},
    {"deploy_id": "dpl_9a71", "service": "ledger-writer", "env": "prod", "version": "v2.14.1",
     "status": "rolling", "started_at": NOW - 900, "deployer": "priya", "commit": "e4f5a6b",
     "pods_ready": "7/12"},
    {"deploy_id": "dpl_77d0", "service": "payments-api", "env": "prod", "version": "v5.3.2",
     "status": "succeeded", "started_at": NOW - 86400, "deployer": "ci-bot", "commit": "0c9d8e7"},
    {"deploy_id": "dpl_1b3e", "service": "payments-api", "env": "staging", "version": "v5.4.0-rc1",
     "status": "failed", "started_at": NOW - 3000, "deployer": "ci-bot", "commit": "ff00aa1",
     "failure": "readiness probe timeout on 3/3 pods"},
]

# group -> topic, per-partition lag
CONSUMER_GROUPS: dict[str, dict[str, Any]] = {
    "ledger-writer-v2": {"topic": "payments.events", "lag": [120, 95, 88, 48211, 101, 77, 64, 130, 90, 85, 99, 110]},
    "fraud-scorer": {"topic": "payments.events", "lag": [3, 0, 5, 2, 1, 0, 4, 2, 0, 1, 3, 2]},
    "search-indexer": {"topic": "catalog.updates", "lag": [900, 1100, 1050, 980, 1010, 990]},
}

LOGS: list[dict[str, Any]] = [
    {"ts": NOW - 60 * i, "service": "ledger-writer", "level": lvl, "msg": msg}
    for i, (lvl, msg) in enumerate(
        [("ERROR", "deserialization failed partition=3 offset=88123401: unknown enum value 'REFUND_PARTIAL'")] * 14
        + [("WARN", "commit offsets slow: 2.1s partition=3")] * 3
        + [("INFO", "processed batch size=500 partition=7")] * 40
    )
]


def _suggest(value: str, choices: list[str], what: str, listing_tool: str) -> ToolError:
    close = difflib.get_close_matches(value, choices, n=1, cutoff=0.4)
    if close:
        return ToolError(f"Unknown {what} {value!r}. Did you mean {close[0]!r}? "
                         f"(Call {listing_tool} to see all {len(choices)} options.)")
    return ToolError(f"Unknown {what} {value!r}. Valid values: {sorted(choices)}.")


# ---------------------------------------------------------------- implementations

def deploys_get_status(service: str, env: str = "prod", response_format: str = "concise") -> str:
    """Latest deploy for one service in one env, plus the previous one for comparison."""
    check_response_format(response_format)
    envs = sorted({d["env"] for d in DEPLOYS})
    if env not in envs:
        raise ToolError(f"env must be one of {envs}, got {env!r}.")
    services = sorted({d["service"] for d in DEPLOYS})
    if service not in services:
        raise _suggest(service, services, "service", "deploys_list_services")
    rows = sorted((d for d in DEPLOYS if d["service"] == service and d["env"] == env),
                  key=lambda d: -d["started_at"])
    if not rows:
        return f"No deploys of {service} in {env}. It has deploys in: {sorted({d['env'] for d in DEPLOYS if d['service'] == service})}."
    view = [{**r, "age_min": (NOW - r["started_at"]) // 60} for r in rows[:2]]
    return format_records(view, response_format=response_format, noun="deploys", total=len(rows),
                          concise_fields=["service", "env", "version", "status", "age_min", "pods_ready", "failure"])


def deploys_list_services() -> str:
    return "services: " + ", ".join(sorted({d["service"] for d in DEPLOYS}))


def kafka_list_consumer_groups(name_contains: str = "") -> str:
    names = [g for g in sorted(CONSUMER_GROUPS) if name_contains in g]
    return "consumer groups: " + (", ".join(names) if names else f"(none contain {name_contains!r})")


def kafka_consumer_lag(group: str, response_format: str = "concise", top_partitions: int = 3) -> str:
    """Lag summary for one group. Concise: total, max, skew, top partitions. Detailed: every partition."""
    check_response_format(response_format)
    if group not in CONSUMER_GROUPS:
        raise _suggest(group, list(CONSUMER_GROUPS), "consumer group", "kafka_list_consumer_groups")
    if not 1 <= top_partitions <= 50:
        raise ToolError(f"top_partitions must be between 1 and 50, got {top_partitions}.")
    g = CONSUMER_GROUPS[group]
    lag: list[int] = g["lag"]
    total, mx = sum(lag), max(lag)
    median = sorted(lag)[len(lag) // 2]
    skew = round(mx / max(median, 1), 1)
    head = (f"group={group} topic={g['topic']} partitions={len(lag)} total_lag={total} "
            f"max_lag={mx} median_lag={median} skew(max/median)={skew}")
    if response_format == "detailed":
        return head + "\n" + "\n".join(f"partition={p} lag={v}" for p, v in enumerate(lag))
    top = sorted(enumerate(lag), key=lambda pv: -pv[1])[:top_partitions]
    tops = ", ".join(f"p{p}={v}" for p, v in top)
    note = " One partition dominates: suspect a poison message or hot key on it." if skew >= 20 else ""
    return f"{head}\ntop partitions: {tops}.{note}"


def logs_search(service: str, query: str = "", level: str = "", since_minutes: int = 60,
                limit: int = 10, cursor: str = "", response_format: str = "concise") -> str:
    """Search one service's logs. Returns matching lines newest-first, paginated."""
    check_response_format(response_format)
    services = sorted({r["service"] for r in LOGS} | {d["service"] for d in DEPLOYS})
    if service not in services:
        raise _suggest(service, services, "service", "deploys_list_services")
    levels = ["DEBUG", "INFO", "WARN", "ERROR"]
    if level and level.upper() not in levels:
        raise ToolError(f"level must be one of {levels} or empty, got {level!r}.")
    if not 1 <= limit <= 50:
        raise ToolError(f"limit must be 1..50, got {limit}. For more, page with the returned cursor.")
    if not 1 <= since_minutes <= 1440:
        raise ToolError(f"since_minutes must be 1..1440 (24h), got {since_minutes}.")
    try:
        offset = int(cursor) if cursor else 0
    except ValueError:
        raise ToolError(f"cursor {cursor!r} is not valid. Pass back the exact cursor string from the previous page, or omit it.")
    hits = [r for r in LOGS if r["service"] == service and r["ts"] >= NOW - since_minutes * 60
            and (not level or r["level"] == level.upper()) and query.lower() in r["msg"].lower()]
    page = hits[offset: offset + limit]
    nxt = str(offset + limit) if offset + limit < len(hits) else None
    view = [{**r, "age_min": (NOW - r["ts"]) // 60} for r in page]
    return format_records(view, response_format=response_format, noun="log lines", total=len(hits), next_cursor=nxt,
                          concise_fields=["age_min", "level", "msg"],
                          refine_hint="Add `query` or `level` to narrow")


# ---------------------------------------------------------------- schemas (what the model reads)

_FMT = {"type": "string", "enum": ["concise", "detailed"], "default": "concise",
        "description": "'concise' for reading; 'detailed' adds IDs/raw fields you need for follow-up calls."}

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {"name": "deploys_get_status",
     "description": ("Latest and previous deploy of ONE service in ONE environment: version, status, age, rollout "
                     "progress, failure reason. Use this first when an alert may be caused by a recent change."),
     "input_schema": {"type": "object", "properties": {
         "service": {"type": "string", "description": "Service name, e.g. 'ledger-writer' (not an ID)."},
         "env": {"type": "string", "enum": ["prod", "staging"], "default": "prod"},
         "response_format": _FMT}, "required": ["service"]}},
    {"name": "deploys_list_services",
     "description": "List service names known to the deploy system. Use when unsure of a service's exact name.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "kafka_list_consumer_groups",
     "description": "List Kafka consumer group names, optionally filtered by substring.",
     "input_schema": {"type": "object", "properties": {"name_contains": {"type": "string"}}}},
    {"name": "kafka_consumer_lag",
     "description": ("Lag summary for ONE consumer group: total, max, median, skew and the most-lagged partitions. "
                     "High skew means one partition is stuck (poison message, hot key); low skew with high total "
                     "means the group is under-provisioned or downstream is slow."),
     "input_schema": {"type": "object", "properties": {
         "group": {"type": "string", "description": "Exact consumer group name, e.g. 'ledger-writer-v2'."},
         "response_format": _FMT,
         "top_partitions": {"type": "integer", "minimum": 1, "maximum": 50, "default": 3}},
         "required": ["group"]}},
    {"name": "logs_search",
     "description": ("Search ONE service's logs (newest first, max 24h back). Always pass `query` or `level`; "
                     "unfiltered searches return mostly INFO noise. Returns a cursor when more lines match."),
     "input_schema": {"type": "object", "properties": {
         "service": {"type": "string"},
         "query": {"type": "string", "description": "Case-insensitive substring, e.g. 'partition=3' or 'timeout'."},
         "level": {"type": "string", "enum": ["DEBUG", "INFO", "WARN", "ERROR"]},
         "since_minutes": {"type": "integer", "minimum": 1, "maximum": 1440, "default": 60},
         "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
         "cursor": {"type": "string", "description": "Opaque cursor from a previous page."},
         "response_format": _FMT}, "required": ["service"]}},
]

REGISTRY: dict[str, Callable[..., str]] = {
    "deploys_get_status": deploys_get_status,
    "deploys_list_services": deploys_list_services,
    "kafka_list_consumer_groups": kafka_list_consumer_groups,
    "kafka_consumer_lag": kafka_consumer_lag,
    "logs_search": logs_search,
}


def call_tool(name: str, args: dict[str, Any], registry: dict[str, Callable[..., str]] | None = None) -> tuple[str, bool]:
    """Dispatch one tool call. Returns (content, is_error). Never raises for model mistakes."""
    registry = REGISTRY if registry is None else registry
    fn = registry.get(name)
    if fn is None:
        return f"No tool named {name!r}. Available tools: {sorted(registry)}.", True
    sig = inspect.signature(fn)
    try:
        sig.bind(**args)  # validate names before running, so TypeErrors inside the tool stay bugs
    except TypeError as e:
        return f"Bad arguments for {name}: {e}. Accepted parameters: {list(sig.parameters)}.", True
    try:
        return fn(**args), False
    except ToolError as e:
        return str(e), True
