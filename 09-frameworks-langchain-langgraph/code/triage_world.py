"""The shared world for the on-call triage agent: tools, a fake ops backend, and a scripted model.

Every implementation in this module (raw loop, LangGraph, the SDK sketches) uses the
SAME three tools, the SAME system prompt and, in tests, the SAME scripted "model".
That is what makes "same outcome" a meaningful assertion: only the orchestration differs.

Tools:
    get_alert(alert_id)          read-only
    query_logs(service, minutes) read-only
    restart_service(service)     RISKY: mutates production, needs human approval
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from ainative_kit import Response, ToolCall, text

SYSTEM_PROMPT = """You are the on-call triage agent for the payments platform.
For each alert: (1) fetch it with get_alert, (2) read recent logs with query_logs,
(3) decide. Only call restart_service when logs show a fault a restart clears
(connection-pool exhaustion, leaked threads, a wedged process). Never restart for
upstream dependency failures or capacity problems; recommend an owner instead.
Finish with one line starting 'DIAGNOSIS:' then one line starting 'ACTION:'."""

RISKY_TOOLS = frozenset({"restart_service"})

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "get_alert",
        "description": "Fetch a PagerDuty-style alert by id. Returns service, symptom and start time.",
        "input_schema": {
            "type": "object",
            "properties": {"alert_id": {"type": "string", "description": "e.g. ALERT-4211"}},
            "required": ["alert_id"],
        },
    },
    {
        "name": "query_logs",
        "description": "Return the most recent ERROR/WARN log lines for a service. Read-only.",
        "input_schema": {
            "type": "object",
            "properties": {
                "service": {"type": "string"},
                "minutes": {"type": "integer", "description": "Look-back window, 1-60", "default": 15},
            },
            "required": ["service"],
        },
    },
    {
        "name": "restart_service",
        "description": (
            "Rolling-restart every pod of a service. MUTATES PRODUCTION. Use only when logs show "
            "a fault that a restart clears. Requires human approval."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"service": {"type": "string"}, "reason": {"type": "string"}},
            "required": ["service", "reason"],
        },
    },
]

ALERTS: dict[str, dict[str, Any]] = {
    "ALERT-4211": {"service": "checkout-api", "symptom": "p99 latency 2.4s (SLO 800ms), 5xx 8%",
                   "started": "2026-10-19T03:12Z"},
    "ALERT-4212": {"service": "kafka-broker-3", "symptom": "disk usage 97% on /var/lib/kafka",
                   "started": "2026-10-19T04:40Z"},
    "ALERT-4213": {"service": "payments-router", "symptom": "5xx 22% on POST /charge",
                   "started": "2026-10-19T05:02Z"},
}

LOGS: dict[str, list[str]] = {
    "checkout-api": [
        "ERROR HikariPool-1 - Connection is not available, request timed out after 30000ms",
        "WARN  HikariPool-1 - pool stats (total=50, active=50, idle=0, waiting=212)",
        "ERROR leak detection: connection held > 60s by OrderRepository.findOpen",
    ],
    "kafka-broker-3": [
        "WARN  log.retention.bytes not set for topic clickstream.raw",
        "ERROR Disk usage 97% on /var/lib/kafka; segments not eligible for deletion",
    ],
    "payments-router": [
        "ERROR upstream card-gateway.example returned 503 Service Unavailable (x1840)",
        "WARN  circuit breaker card-gateway OPEN",
    ],
}


@dataclass
class OpsWorld:
    """Fake ops backend. `restarts` is the side-effect log the tests inspect.

    restart_service is idempotent per tool_use_id: replaying the same call (after a crash
    and resume, or a time-travel replay) does not restart twice, and it returns the
    ORIGINAL result, so the model sees the same transcript on replay. Same contract as an
    idempotency key on a payments API (replay returns the stored response).
    """

    restarts: list[str] = field(default_factory=list)
    _results_by_call_id: dict[str, str] = field(default_factory=dict)

    def execute(self, name: str, args: dict[str, Any], call_id: str) -> str:
        if name == "get_alert":
            alert = ALERTS.get(args["alert_id"])
            return json.dumps(alert) if alert else f"error: unknown alert {args['alert_id']}"
        if name == "query_logs":
            lines = LOGS.get(args["service"], [])
            return "\n".join(lines) if lines else f"no recent errors for {args['service']}"
        if name == "restart_service":
            if call_id in self._results_by_call_id:  # replay: no new side effect, same answer
                return self._results_by_call_id[call_id]
            self.restarts.append(args["service"])
            result = f"rolling restart of {args['service']} complete; 6/6 pods ready"
            self._results_by_call_id[call_id] = result
            return result
        return f"error: unknown tool {name}"


# ---------------------------------------------------------------------------
# Scripted "model": a deterministic policy over the transcript, for offline runs.
# It reads tool_results out of the messages exactly as a real model would see them.
# ---------------------------------------------------------------------------

def _tool_results(messages: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for m in messages:
        if m["role"] == "user" and isinstance(m["content"], list):
            out += [b["content"] for b in m["content"] if b.get("type") == "tool_result"]
    return out


def _first_user_text(messages: list[dict[str, Any]]) -> str:
    c = messages[0]["content"]
    return c if isinstance(c, str) else " ".join(b.get("text", "") for b in c)


def scripted_policy(messages: list[dict[str, Any]], kwargs: dict[str, Any]) -> Response:
    """Plays the model: get_alert -> query_logs -> (restart | recommend) -> final answer."""
    results = _tool_results(messages)
    alert_id = next(w for w in _first_user_text(messages).replace(".", " ").split() if w.startswith("ALERT-"))
    if len(results) == 0:
        return Response(tool_calls=[ToolCall("toolu_01", "get_alert", {"alert_id": alert_id})], stop_reason="tool_use")
    service = json.loads(results[0])["service"]
    if len(results) == 1:
        return Response(text="Checking logs.", tool_calls=[ToolCall("toolu_02", "query_logs",
                        {"service": service, "minutes": 15})], stop_reason="tool_use")
    logs = results[1]
    if len(results) == 2 and "Connection is not available" in logs:
        return Response(tool_calls=[ToolCall("toolu_03", "restart_service",
                        {"service": service, "reason": "connection pool exhausted (leak in OrderRepository)"})],
                        stop_reason="tool_use")
    if "rolling restart" in results[-1]:
        return text(f"DIAGNOSIS: {service} connection pool exhausted by a leak in OrderRepository.findOpen.\n"
                    f"ACTION: restarted {service}; file a bug to fix the leak before it recurs.")
    if "rejected" in results[-1]:
        return text(f"DIAGNOSIS: {service} connection pool exhausted by a leak in OrderRepository.findOpen.\n"
                    "ACTION: restart was rejected by the on-call human; paging checkout-api owners.")
    if "Disk usage" in logs:
        return text(f"DIAGNOSIS: {service} disk at 97%; clickstream.raw has no retention.bytes limit.\n"
                    "ACTION: no restart; page the streaming-platform owner to set retention.")
    return text(f"DIAGNOSIS: {service} errors come from upstream card-gateway 503s; breaker is open.\n"
                "ACTION: no restart; open an incident with the card-gateway vendor.")


def outcome_of(final_text: str) -> str:
    """Classify the agent's final answer into a coarse action label (used by evals)."""
    action = next((ln for ln in final_text.splitlines() if ln.startswith("ACTION:")), "")
    if "restarted" in action:
        return "restart"
    if "rejected" in action:
        return "escalate_after_reject"
    return "recommend_owner" if action else "no_action_line"
