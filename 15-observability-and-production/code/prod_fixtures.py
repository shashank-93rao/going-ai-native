"""Deterministic synthetic production traces for an "alert summarizer" LLM feature.

The feature: an on-call alert (PagerDuty-style payload plus log excerpt) goes in;
a JSON triage note comes out: {"service", "severity", "summary", "runbook"}.

Each trace is two spans in ainative_kit Tracer format:
    agent_run (root): feature, prompt_version, user feedback, guardrail outcome
    llm_call (child): model, token usage incl. cache fields, output text

`python prod_fixtures.py` writes data/prod_traces.jsonl (300 traces).
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

SERVICES = ["orders-api", "payments-worker", "kafka-consumer-ledger", "search-indexer", "auth-gateway"]
SEVERITIES = ["sev1", "sev2", "sev3"]
GOOD = '{{"service": "{svc}", "severity": "{sev}", "summary": "Consumer lag on {svc} rose after deploy; p99 at 4.2s.", "runbook": "RB-{n}"}}'
BAD_OUTPUTS = [
    'Sure! Here is the triage note: {{"service": "{svc}"}}',                     # not JSON / missing keys
    '{{"service": "billing-legacy", "severity": "sev2", "summary": "Disk full.", "runbook": "RB-1"}}',  # ungrounded service
    '{{"service": "{svc}", "severity": "critical", "summary": "Lag.", "runbook": "RB-2"}}',            # bad enum
    '{{"service": "{svc}", "severity": "sev2", "summary": "Token sk-ant-api03-AbCdEf123456 leaked in logs", "runbook": "RB-3"}}',
]
FOLLOWUPS_NEG = ["that's wrong, it's not the ledger", "useless", "no, this is the wrong service again"]


def make_trace(rng: random.Random, i: int, ts: float, *, bad_rate: float, cache_hit: float,
               prompt_version: str, model: str) -> list[dict[str, Any]]:
    """One trace = [agent_run span, llm_call span]."""
    trace_id = f"t{i:05d}"
    svc, sev = rng.choice(SERVICES), rng.choice(SEVERITIES)
    bad = rng.random() < bad_rate
    output = (rng.choice(BAD_OUTPUTS) if bad else GOOD).format(svc=svc, sev=sev, n=rng.randint(10, 99))
    prefix = 6000  # static system prompt + few-shot examples + tool schemas
    tail = rng.randint(800, 2500)  # this alert's payload and logs
    hit = rng.random() < cache_hit
    usage = {
        "input_tokens": tail,
        "cache_read_tokens": prefix if hit else 0,
        "cache_write_tokens": 0 if hit else prefix,
        "output_tokens": rng.randint(120, 260),
    }
    latency = rng.lognormvariate(0.3, 0.35) + (0.0 if hit else 0.6)
    feedback = None
    followup = None
    r = rng.random()
    if bad and r < 0.35:
        feedback, followup = -1, rng.choice(FOLLOWUPS_NEG)
    elif not bad and r < 0.10:
        feedback = 1
    elif r > 0.985:
        feedback = -1
    blocked = "sk-ant-" in output  # the output guardrail caught a secret
    root = {
        "name": "agent_run", "trace_id": trace_id, "span_id": f"{trace_id}r", "parent_id": None,
        "start": ts, "end": ts + latency + 0.05, "error": None,
        "attrs": {"agent_name": "alert-summarizer", "prompt_version": prompt_version,
                  "input_service": svc, "feedback": feedback, "followup": followup,
                  "guardrail_blocked": blocked},
    }
    llm = {
        "name": "llm_call", "trace_id": trace_id, "span_id": f"{trace_id}l", "parent_id": root["span_id"],
        "start": ts + 0.02, "end": ts + 0.02 + latency, "error": None,
        "attrs": {"model": model, "prompt_name": "alert-summarizer", "prompt_version": prompt_version,
                  "stop_reason": "end_turn", "output": output, **usage},
    }
    return [root, llm]


def generate(n: int = 300, *, seed: int = 7, start_ts: float = 1_790_000_000.0, spacing_s: float = 12.0,
             bad_rate: float = 0.06, cache_hit: float = 0.92, prompt_version: str = "v14",
             model: str = "claude-sonnet-5-5", id_offset: int = 0) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    rows: list[dict[str, Any]] = []
    for i in range(n):
        rows.extend(make_trace(rng, id_offset + i, start_ts + i * spacing_s, bad_rate=bad_rate,
                               cache_hit=cache_hit, prompt_version=prompt_version, model=model))
    return rows


def group(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        out.setdefault(r["trace_id"], []).append(r)
    return out


if __name__ == "__main__":
    path = Path(__file__).parent / "data" / "prod_traces.jsonl"
    path.parent.mkdir(exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in generate()))
    print(f"wrote {path}")
