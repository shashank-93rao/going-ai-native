"""Worked example: incident summary = routing + prompt chaining, with code gates.

    raw incident log
      -> route (cheap model): database | deploy | capacity | other
      -> chain step 1 "timeline": extract JSON timeline with a route-specific prompt
           gate: valid JSON, every timestamp occurs in the raw log, sorted, services grounded
      -> code: compute duration (never ask a model for arithmetic code can do)
      -> chain step 2 "summary": write the summary from the timeline only
           gate: <= 120 words, names every impacted service, no timestamps absent from timeline

Run:  python incident_summary.py            (fake model unless ANTHROPIC_API_KEY is set)
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from ainative_kit import FakeClient, LLMClient, Response, get_client
from patterns import Step, chain, parse_json, route

CHEAP_MODEL = "claude-haiku-5-5"
TS = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")

CLASSIFIER_SYSTEM = (
    "Classify the incident log into exactly one label: database, deploy, capacity, other.\n"
    "database = locks, replication, migrations, query plans. deploy = a rollout or config push "
    "preceded the symptoms. capacity = load, lag or saturation fixed by scaling.\n"
    "Answer with the label only."
)

FOCUS = {
    "database": "Note lock types, migration IDs, replication lag values and which replica.",
    "deploy": "Note the version that rolled out, the version rolled back to, and canary percentage.",
    "capacity": "Note the saturated resource, the before/after replica or partition counts, and lag values.",
    "other": "Note the first symptom, the mitigation and the recovery signal.",
}

TIMELINE_SYSTEM = (
    "You extract incident timelines. Output only JSON of the form "
    '{"services": [..], "timeline": [{"ts": "<ISO timestamp copied from the log>", "event": "<short>"}], '
    '"mitigation": "<short>"}. Copy timestamps exactly; never invent one. {focus}'
)

SUMMARY_SYSTEM = (
    "You write incident summaries for an on-call channel. Use only the facts in the timeline JSON. "
    "At most 120 words. Start with 'Impact:', then 'Duration:', 'Cause:', 'Mitigation:', 'Follow-up:'."
)


# --------------------------------------------------------------------------- gates (the checkable part)

def timeline_gate(out: str, ctx: dict[str, str]) -> str | None:
    try:
        data = parse_json(out)
    except (ValueError, json.JSONDecodeError) as e:
        return f"not valid JSON ({e})"
    raw = ctx["log"]
    stamps = [e.get("ts", "") for e in data.get("timeline", [])]
    if not stamps:
        return "timeline is empty"
    missing = [s for s in stamps if s not in raw]
    if missing:
        return f"timestamps not present in the log: {missing}"
    if stamps != sorted(stamps):
        return "timeline is not in chronological order"
    services = data.get("services", [])
    ungrounded = [s for s in services if s not in raw]
    if not services or ungrounded:
        return f"services missing or not in the log: {ungrounded or 'none listed'}"
    return None


def summary_gate(out: str, ctx: dict[str, str]) -> str | None:
    data = parse_json(ctx["timeline"])
    words = len(out.split())
    if words > 120:
        return f"{words} words; the limit is 120"
    absent = [s for s in data["services"] if s not in out]
    if absent:
        return f"summary does not name impacted services: {absent}"
    allowed = {e["ts"] for e in data["timeline"]}
    invented = [t for t in TS.findall(out) if t not in allowed]
    if invented:
        return f"summary cites timestamps not in the timeline: {invented}"
    if "Duration:" not in out:
        return "missing 'Duration:' line"
    return None


def duration_minutes(log: str) -> int | None:
    """Computed in code: TRIGGERED to RESOLVED."""
    start = re.search(rf"({TS.pattern}) pagerduty TRIGGERED", log)
    end = re.search(rf"({TS.pattern}) pagerduty RESOLVED", log)
    if not (start and end):
        return None
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    delta = datetime.strptime(end.group(1), fmt) - datetime.strptime(start.group(1), fmt)
    return int(delta.total_seconds() // 60)


# --------------------------------------------------------------------------- the workflow

def summarize_incident(client: LLMClient, log: str) -> dict[str, Any]:
    def handler_for(label: str):
        def handle(item: str) -> str:
            steps = [
                Step("timeline", lambda c: f"<log>\n{c['log']}\n</log>",
                     gate=timeline_gate, system=TIMELINE_SYSTEM.replace("{focus}", FOCUS[label])),
                Step("summary",
                     lambda c: (f"<timeline>\n{c['timeline']}\n</timeline>\n"
                                f"Duration computed from paging data: {c['duration']} minutes."),
                     gate=summary_gate, system=SUMMARY_SYSTEM),
            ]
            ctx = chain(client, steps, {"log": item, "duration": str(duration_minutes(item))})
            return json.dumps({"timeline": parse_json(ctx["timeline"]), "summary": ctx["summary"]})
        return handle

    routed = route(client, log, {k: handler_for(k) for k in FOCUS}, classifier_system=CLASSIFIER_SYSTEM,
                   default="other", model=CHEAP_MODEL)
    out = json.loads(routed.output)
    return {"route": routed.label, "fell_back": routed.fell_back, **out}


# --------------------------------------------------------------------------- offline stand-in

def fake_incident_model(messages: list[dict[str, Any]], kw: dict[str, Any]) -> Response:
    """A deterministic stand-in so the script runs offline. It is not a model."""
    system = kw.get("system") or ""
    user = messages[-1]["content"]
    if system.startswith("Classify"):
        for label, keys in [("database", ["replication", "migration", "lock"]),
                            ("deploy", ["rollout", "rolled back"]), ("capacity", ["consumer lag", "scaled"])]:
            if any(k in user for k in keys):
                return Response(text=label)
        return Response(text="other")
    if system.startswith("You extract"):
        lines = [l for l in user.splitlines() if TS.match(l)]
        services = sorted({m for l in lines for m in re.findall(r"\b[a-z]+-(?:svc|api)\b", l)})
        timeline = [{"ts": l[:20], "event": l[21:][:80]} for l in lines]
        return Response(text=json.dumps({"services": services, "timeline": timeline,
                                         "mitigation": timeline[-2]["event"]}))
    data = parse_json(user.split("</timeline>")[0].split("<timeline>")[1])
    minutes = re.search(r"(\d+|None) minutes", user).group(1)
    svc = ", ".join(data["services"])
    return Response(text=(f"Impact: {svc} degraded.\nDuration: {minutes} minutes "
                          f"({data['timeline'][0]['ts']} to {data['timeline'][-1]['ts']}).\n"
                          f"Cause: see timeline.\nMitigation: {data['mitigation']}.\nFollow-up: write RCA."))


def main() -> None:
    client = get_client(fake=FakeClient(fake_incident_model))
    for line in (Path(__file__).parent / "data" / "incidents.jsonl").read_text().splitlines():
        inc = json.loads(line)
        result = summarize_incident(client, inc["log"])
        print(f"== {inc['id']}  route={result['route']}")
        print(result["summary"], "\n")


if __name__ == "__main__":
    main()
