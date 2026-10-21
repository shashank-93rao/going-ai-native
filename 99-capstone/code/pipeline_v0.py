"""Pipeline v0 for capstone variant B: map (extract per doc) then reduce (aggregate across docs).

One prompt, one call per document, whole document in context. That is the baseline
you will hill-climb in M4 (decomposition, chunking, gleaning, model/effort, cost).

    python pipeline_v0.py --out runs/preds_v0.jsonl     # then: python score.py runs/preds_v0.jsonl
    AINATIVE_FAKE=1 python pipeline_v0.py ...            # offline: a regex "model" with realistic mistakes
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from ainative_kit import FakeClient, LLMClient, Response, Tracer, Usage, get_client

DATA = Path(__file__).parent / "data"
KNOWN_SERVICES = ["checkout", "payments", "inventory", "search", "auth", "notifications", "ledger", "kafka-ingest"]

EXTRACT_PROMPT = """Extract incident facts from the postmortem below. Return only a JSON object with keys:
incident_id (string), severity ("SEV1"|"SEV2"|"SEV3"), root_cause_category
("deploy"|"config"|"capacity"|"dependency"|"data"|"network"), services_affected (list of strings),
detection_minutes (int), duration_minutes (int), customer_impact (bool),
action_items (list of strings), summary (one sentence).
Use null for anything the document does not state.

<document>
{doc}
</document>"""

REDUCE_PROMPT = """Below are action items from {n} incident postmortems, one per line.
Group them into at most 5 recurring themes. Return only JSON: {{"themes": [{{"theme": str, "count": int}}]}}.

<action_items>
{items}
</action_items>"""


def parse_json_object(s: str) -> dict[str, Any] | None:
    """Pull the first JSON object out of a model reply (tolerates code fences and prose)."""
    m = re.search(r"\{.*\}", s, re.S)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def map_extract(client: LLMClient, doc_id: str, doc: str, model: str | None = None,
                tracer: Tracer | None = None) -> dict[str, Any]:
    """MAP: one document in, one prediction row out. Parse failures are recorded, not raised."""
    tracer = tracer or Tracer()
    with tracer.span("map_extract", doc_id=doc_id, doc_chars=len(doc)) as sp:
        resp = client.complete([{"role": "user", "content": EXTRACT_PROMPT.format(doc=doc)}],
                               model=model, max_tokens=1024, temperature=0)
        obj = parse_json_object(resp.text)
        sp.attrs.update(input_tokens=resp.usage.input_tokens, output_tokens=resp.usage.output_tokens,
                        parse_ok=obj is not None, raw=resp.text[:800])
    row = {"doc_id": doc_id, **(obj or {}), "_parse_ok": obj is not None,
           "_tokens_in": resp.usage.input_tokens, "_tokens_out": resp.usage.output_tokens}
    return row


def reduce_stats(preds: list[dict[str, Any]]) -> dict[str, Any]:
    """REDUCE (code): fleet-level aggregates a reliability review would ask for."""
    by_cat = Counter(p.get("root_cause_category") for p in preds)
    minutes: dict[str, int] = defaultdict(int)
    for p in preds:
        for s in p.get("services_affected") or []:
            minutes[s] += int(p.get("duration_minutes") or 0)
    det = [p["detection_minutes"] for p in preds if isinstance(p.get("detection_minutes"), int)]
    return {"incidents": len(preds), "by_root_cause": dict(by_cat),
            "impact_minutes_by_service": dict(sorted(minutes.items(), key=lambda kv: -kv[1])),
            "mean_detection_minutes": round(sum(det) / len(det), 1) if det else None}


def reduce_themes(client: LLMClient, preds: list[dict[str, Any]], model: str | None = None) -> dict[str, Any]:
    """REDUCE (LLM): cluster action items into themes. Free text, so M5 judges it."""
    items = [a for p in preds for a in (p.get("action_items") or [])]
    resp = client.complete([{"role": "user", "content": REDUCE_PROMPT.format(n=len(preds), items="\n".join(items))}],
                           model=model, max_tokens=1024, temperature=0)
    return parse_json_object(resp.text) or {"themes": [], "_parse_ok": False}


def run_pipeline(client: LLMClient, docs_dir: Path = DATA / "postmortems", model: str | None = None,
                 tracer: Tracer | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    docs = sorted(docs_dir.glob("*.md"))
    preds = [map_extract(client, p.stem, p.read_text(), model, tracer) for p in docs]
    agg = {**reduce_stats(preds), **reduce_themes(client, preds, model)}
    agg["tokens_in"] = sum(p["_tokens_in"] for p in preds)
    agg["tokens_out"] = sum(p["_tokens_out"] for p in preds)
    return preds, agg


# ---------- offline stand-in for the model: a regex extractor with realistic blind spots ----------

def naive_extractor_responder(messages: list[dict[str, Any]], kwargs: dict[str, Any]) -> Response:
    prompt = messages[-1]["content"]
    usage = Usage(input_tokens=len(prompt) // 4, output_tokens=120)
    if "<action_items>" in prompt:
        items = prompt.split("<action_items>")[1].split("</action_items>")[0].strip().splitlines()
        themes = Counter(("canary" if "canary" in i.lower() else "resilience" if "circuit" in i.lower() or
                          "retry" in i.lower() or "bulkhead" in i.lower() else "other") for i in items)
        return Response(text=json.dumps({"themes": [{"theme": t, "count": c} for t, c in themes.items()]}),
                        usage=usage)
    doc = prompt.split("<document>")[1].split("</document>")[0]
    low = doc.lower()
    sev = re.search(r"\*\*Severity:\*\* (SEV\d)", doc) or re.search(r"(SEV\d)", doc)  # first mention wins
    dur = re.search(r"\*\*Duration:\*\* (?:(\d+)h )?(\d+)m", doc)
    times = re.findall(r"^- (\d\d):(\d\d) (.*)$", doc, re.M)
    to_min = lambda h, m: int(h) * 60 + int(m)  # noqa: E731
    alert = next((to_min(h, m) for h, m, t in times if "First alert" in t), None)
    detection = alert - to_min(*times[0][:2]) if alert is not None and times else None
    cats = [("release", "deploy"), ("configuration", "config"), ("lag", "capacity"),
            ("provider", "dependency"), ("schema migration", "data"), ("security group", "network")]
    summary = re.search(r"## Summary\s+(.+?\.)", doc, re.S)
    out = {
        "incident_id": (re.search(r"(INC-\d+)", doc) or [None, None])[1],
        "severity": sev.group(1) if sev else None,
        "root_cause_category": next((c for k, c in cats if k in low), None),
        "services_affected": [s for s in KNOWN_SERVICES if s in low],  # every mention counts: decoys leak in
        "detection_minutes": detection,
        "duration_minutes": (int(dur.group(1) or 0) * 60 + int(dur.group(2))) if dur else None,
        "customer_impact": "customer" in low,  # misses "No customer-facing impact"
        "action_items": re.findall(r"^- \[ \] (.+)$", doc, re.M),
        "summary": summary.group(1).strip() if summary else None,
    }
    return Response(text="```json\n" + json.dumps(out) + "\n```", usage=usage)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--docs", default=str(DATA / "postmortems"))
    ap.add_argument("--out", default="runs/preds_v0.jsonl")
    ap.add_argument("--traces", default=None)
    ap.add_argument("--model", default=None)
    args = ap.parse_args()
    client = get_client(fake=FakeClient(naive_extractor_responder))
    tracer = Tracer(args.traces) if args.traces else Tracer()
    preds, agg = run_pipeline(client, Path(args.docs), args.model, tracer)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as f:
        for p in preds:
            f.write(json.dumps(p) + "\n")
    print(json.dumps(agg, indent=2))


if __name__ == "__main__":
    main()
