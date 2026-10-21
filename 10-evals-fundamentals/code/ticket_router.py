"""Incident ticket router: the single-turn system under test in Module 10.

Given one production alert, the router returns a structured decision:

    {"decision": "route" | "abstain", "team": <team> | null,
     "severity": "SEV1".."SEV4" | null, "rationale": "<one sentence>"}

"abstain" means "send to the human triage queue". A wrong route pages the wrong
team at 3 a.m., so the prompt states the price of a wrong answer explicitly.

The module also ships `fake_router_client`, a deterministic stand-in "model" with
realistic, deliberate flaws (keyword over-matching, severity under-calls, ignored
negations, secret echoing, flaky tie-breaking, broken JSON on one source). The
eval harness is supposed to find every one of them.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
from typing import Any

from ainative_kit import FakeClient, LLMClient, Response, Tracer, Usage

TEAMS = ("streaming", "database", "network", "identity", "payments", "storage")
SEVERITIES = ("SEV1", "SEV2", "SEV3", "SEV4")
PROMPT_VERSION = "router-v3"

ROUTER_SYSTEM_PROMPT = f"""You are the alert router for a production on-call rotation.
Read one alert and decide which team owns it and how severe it is.

Teams and what they own:
- streaming: Kafka/MSK brokers, topics, consumer groups, schema registry
- database: Postgres clusters, replicas, pgbouncer, failover (including the DB's own volumes)
- network: DNS, TLS certificates, load balancers, CDN, edge gateway, rate limiter
- identity: login, OAuth/OIDC token service, SSO/SAML, JWKS
- payments: payments-api, PSP adapters, card authorization, ledger reconciliation
- storage: object storage buckets, block volumes and disks not owned by another team

Severity rubric:
- SEV1: customer-facing outage, or data loss/corruption in progress
- SEV2: customer-facing degradation beyond SLO, or a SEV1 likely within the hour
- SEV3: internal degradation or reduced redundancy, no customer impact yet
- SEV4: informational: scheduled work, resolved alerts, capacity warnings with >24h runway

Abstain (decision "abstain", team and severity null) when the alert does not identify an
owned component, or is a test page. Route only if you are more than 75% confident:
a wrong route costs 3 points, a correct route earns 1, and an abstain costs 0.

Never copy credentials, tokens or keys from the alert into your output.

Output only one JSON object, no markdown fences:
{{"decision": "route"|"abstain", "team": one of {list(TEAMS)} or null,
 "severity": one of {list(SEVERITIES)} or null, "rationale": "<one sentence>"}}"""


def prompt_hash(system: str, tools: list[dict[str, Any]] | None = None) -> str:
    """Stable 12-hex-char hash of everything that defines the prompt. Log it on every trace."""
    blob = json.dumps({"system": system, "tools": tools or []}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:12]


def render_alert(alert: dict[str, Any]) -> str:
    """The user turn. Kept as a function so the fake and the real model see the same bytes."""
    return "Alert:\n" + json.dumps(alert, sort_keys=True)


def parse_router_output(raw: str) -> tuple[dict[str, Any] | None, str | None]:
    """Strict parse: the contract is 'one JSON object'. No fence stripping, no repair."""
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as e:
        return None, f"invalid JSON: {e.msg} at pos {e.pos}"
    if not isinstance(obj, dict):
        return None, "top-level value is not an object"
    return obj, None


def route_alert(
    client: LLMClient,
    alert: dict[str, Any],
    *,
    tracer: Tracer | None = None,
    model: str | None = None,
    case_id: str | None = None,
) -> dict[str, Any]:
    """Run the router once and return raw text, parsed output and trace metadata."""
    tracer = tracer or Tracer()
    p_hash = prompt_hash(ROUTER_SYSTEM_PROMPT)
    with tracer.span("route_alert", case_id=case_id, prompt_version=PROMPT_VERSION,
                     prompt_hash=p_hash, input=alert, state="route") as s:
        with tracer.span("llm_call", model=model or "default", prompt_hash=p_hash) as c:
            resp = client.complete([{"role": "user", "content": render_alert(alert)}],
                                   system=ROUTER_SYSTEM_PROMPT, model=model, max_tokens=300)
            c.attrs.update(model=resp.model, output_text=resp.text, stop_reason=resp.stop_reason,
                           input_tokens=resp.usage.input_tokens, output_tokens=resp.usage.output_tokens)
        parsed, err = parse_router_output(resp.text)
        s.attrs.update(output=parsed, raw_output=resp.text, parse_error=err)
    return {"raw": resp.text, "parsed": parsed, "parse_error": err, "prompt_hash": p_hash,
            "trace_id": s.trace_id, "stop_reason": resp.stop_reason}


# --------------------------------------------------------------------------------------
# A deliberately flawed fake router. Each flaw is a failure mode the evals should catch.
# --------------------------------------------------------------------------------------

_TEAM_PATTERNS = {
    "payments": r"payment|card auth|\bpsp\b|ledger|checkout",
    "streaming": r"kafka|consumer (lag|group)|broker|partition|\bisr\b|schema.?registry",
    "database": r"postgres|replication.?lag|deadlock|connection pool|pgbouncer|patroni",
    "network": r"dns|tls|certificate|load balancer|packet loss|nxdomain|\bcdn\b",
    "identity": r"oauth|\bsso\b|login|jwks|token|saml",  # flaw: bare "token" over-matches
    "storage": r"\bs3\b|disk|volume|\bebs\b|bucket|object store",
}
_SEV1 = r"outage|\bdown\b|unavailable|unreachable|data loss|all writes"  # flaw: "scaled down"
_SEV2_SYMPTOM = r"error rate|5xx|latency|\blag\b|timeouts|degraded"
_SEV4 = r"scheduled|planned|expire|growth .*?/day"  # flaw: "expires in 6 days" -> SEV4


def _fake_decide(alert: dict[str, Any], trial: int, cautious: bool = False) -> dict[str, Any]:
    text = " ".join(str(alert.get(k, "")) for k in ("title", "body", "service")).lower()
    if not alert.get("body") or "[test]" in text:
        return {"decision": "abstain", "team": None, "severity": None, "rationale": "Not enough signal."}
    matches = sorted(t for t, pat in _TEAM_PATTERNS.items() if re.search(pat, text))
    if cautious and len(matches) != 1:  # the "cautious" variant abstains unless exactly one team matches
        return {"decision": "abstain", "team": None, "severity": None, "rationale": "Ambiguous owner."}
    if not matches and len(str(alert.get("body", ""))) < 60:
        return {"decision": "abstain", "team": None, "severity": None, "rationale": "No owned component."}
    if not matches:
        team = "network"  # flaw: overconfident default instead of abstaining
    elif len(matches) == 1:
        team = matches[0]
    else:  # flaw: ties broken at random, so repeated trials disagree
        seed = int(hashlib.sha256(f"{alert.get('title')}|{trial}".encode()).hexdigest(), 16)
        team = random.Random(seed).choice(matches)
    if re.search(_SEV1, text):
        sev = "SEV1"
    elif re.search(_SEV2_SYMPTOM, text):
        sev = "SEV2" if "customer" in text else "SEV3"  # flaw: misses implicit impact and negation
    elif re.search(_SEV4, text):
        sev = "SEV4"
    else:
        sev = "SEV3"
    rationale = f"{team}: {str(alert.get('body', ''))[:60]}"  # flaw: echoes raw body (secrets)
    return {"decision": "route", "team": team, "severity": sev, "rationale": rationale}


def fake_router_client(trial: int = 0, cautious: bool = False) -> FakeClient:
    """A FakeClient whose answers depend only on the alert, the trial number and the variant."""

    def responder(messages: list[dict[str, Any]], kwargs: dict[str, Any]) -> Response:
        content = messages[-1]["content"]
        alert = json.loads(content.split("\n", 1)[1])
        out = json.dumps(_fake_decide(alert, trial, cautious))
        if alert.get("source") == "pagerduty-manual":
            out = f"```json\n{out}\n```"  # flaw: format drift on one input source
        return Response(text=out, usage=Usage(len(content) // 4, len(out) // 4))

    return FakeClient(responder)
