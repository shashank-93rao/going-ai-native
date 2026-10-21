"""Synthetic alerts from dimension tuples: the cold-start dataset for the router.

    python synth_data.py --n 24 --out data/synth_cases.jsonl

Method (from Hamel Husain and Shreya Shankar's evals FAQ and course):
1. Name the *dimensions* along which real alerts vary.
2. Enumerate tuples (cross product), then filter out impossible combinations.
3. Sample tuples so every value of the dimensions you care about appears.
4. In a *separate* step, ask a model to turn each tuple into one realistic alert.
   Splitting "what to cover" from "how to phrase it" avoids the repetitive phrasing
   you get when you ask for 50 alerts in one prompt.
5. Draft labels by rule and mark every row `needs_review`. The model writes the
   inputs only; a human owns the expected outputs.
"""

from __future__ import annotations

import argparse
import itertools
import json
import random
import re
import sys
from pathlib import Path
from typing import Any, Callable

from ainative_kit import FakeClient, LLMClient, get_client, text

DIMENSIONS: dict[str, list[str]] = {
    "subsystem": ["kafka", "postgres", "dns", "oauth", "payments-api", "object-store"],
    "symptom": ["error_rate", "latency", "saturation", "outage", "cert_expiry"],
    "impact": ["none_yet", "internal", "customer_facing"],
    "signal_quality": ["clear", "misleading_keyword", "missing_service", "negated_impact"],
    "source": ["prometheus", "datadog", "cloudwatch", "pagerduty-manual"],
}
SUBSYSTEM_TEAM = {"kafka": "streaming", "postgres": "database", "dns": "network",
                  "oauth": "identity", "payments-api": "payments", "object-store": "storage"}

Rule = Callable[[dict[str, str]], bool]
RULES: list[tuple[str, Rule]] = [
    ("an outage always has impact", lambda t: not (t["symptom"] == "outage" and t["impact"] == "none_yet")),
    ("cert expiry is a dns/edge or oauth concern here",
     lambda t: t["symptom"] != "cert_expiry" or t["subsystem"] in ("dns", "oauth")),
    ("negated impact only makes sense when there is none",
     lambda t: t["signal_quality"] != "negated_impact" or t["impact"] == "none_yet"),
]


def cross_product(dims: dict[str, list[str]]) -> list[dict[str, str]]:
    keys = list(dims)
    return [dict(zip(keys, combo)) for combo in itertools.product(*(dims[k] for k in keys))]


def filter_tuples(tuples: list[dict[str, str]], rules: list[tuple[str, Rule]] = RULES) -> list[dict[str, str]]:
    return [t for t in tuples if all(rule(t) for _, rule in rules)]


def stratified_sample(tuples: list[dict[str, str]], n: int, seed: int = 0,
                      cover: tuple[str, ...] = ("subsystem", "signal_quality")) -> list[dict[str, str]]:
    """Pick n tuples so that every value of every `cover` dimension appears at least once (if n allows)."""
    rng = random.Random(seed)
    pool = tuples[:]
    rng.shuffle(pool)
    picked: list[dict[str, str]] = []
    for dim in cover:
        for value in DIMENSIONS[dim]:
            if len(picked) >= n:
                break
            if not any(p[dim] == value for p in picked):
                hit = next((t for t in pool if t[dim] == value and t not in picked), None)
                if hit:
                    picked.append(hit)
    for t in pool:
        if len(picked) >= n:
            break
        if t not in picked:
            picked.append(t)
    return picked


def draft_label(t: dict[str, str]) -> dict[str, Any]:
    """Rule-based *draft* expected output. A human reviews every one before it enters the golden set."""
    if t["signal_quality"] == "missing_service":
        return {"decision": "abstain", "team": None, "severity": None}
    if t["symptom"] == "outage":
        sev = "SEV1" if t["impact"] == "customer_facing" else "SEV2"
    elif t["impact"] == "customer_facing":
        sev = "SEV2"
    elif t["symptom"] == "cert_expiry":
        sev = "SEV3"
    else:
        sev = "SEV3" if t["impact"] == "internal" else "SEV4"
    return {"decision": "route", "team": SUBSYSTEM_TEAM[t["subsystem"]], "severity": sev}


WRITER_PROMPT = """Write ONE realistic production alert as a JSON object with keys
"source", "title", "body", "service", "env". Do not say which team owns it or how severe it is.

Make it match this scenario exactly:
<scenario>{tuple_json}</scenario>

Meaning of signal_quality:
- clear: the owning component is named plainly
- misleading_keyword: mention a word that belongs to another team (e.g. "payments" in a Kafka topic name)
- missing_service: do not name the component or service; keep the body vague
- negated_impact: explicitly say there is no customer impact
Use concrete numbers (rates, durations, hostnames) like a real monitor would. Output only the JSON."""


def tuple_to_prompt(t: dict[str, str]) -> str:
    return WRITER_PROMPT.format(tuple_json=json.dumps(t, sort_keys=True))


def generate_cases(client: LLMClient, tuples: list[dict[str, str]], start_id: int = 1) -> tuple[list[dict], list[dict]]:
    """One model call per tuple. Returns (cases, rejects); rejects keep the reason for inspection."""
    cases, rejects = [], []
    for i, t in enumerate(tuples, start_id):
        resp = client.complete([{"role": "user", "content": tuple_to_prompt(t)}], max_tokens=400, temperature=1.0)
        try:
            alert = json.loads(resp.text)
            assert {"title", "body"} <= alert.keys(), "missing title/body"
        except (json.JSONDecodeError, AssertionError) as e:
            rejects.append({"tuple": t, "raw": resp.text, "reason": str(e)})
            continue
        alert.setdefault("source", t["source"])
        cases.append({"id": f"s{i:03d}", "input": alert, "expected": draft_label(t),
                      "slice": t["signal_quality"] if t["signal_quality"] != "clear" else SUBSYSTEM_TEAM[t["subsystem"]],
                      "tags": ["synthetic"], "split": "dev", "origin": "synthetic", "tuple": t, "needs_review": True})
    return cases, rejects


_PHRASES = {
    "error_rate": "5xx rate 7.4% for 11 min (SLO 0.5%)", "latency": "p99 latency 3.1s vs SLO 900ms",
    "saturation": "utilization 91% and climbing 3%/hour", "outage": "all requests failing since 10:42 UTC",
    "cert_expiry": "TLS certificate expires in 5 days; renewal job failing",
}
_IMPACT = {"none_yet": "", "internal": " Internal batch jobs retrying.", "customer_facing": " Customers report failures."}
_SERVICE = {"kafka": "kafka-prod", "postgres": "orders-db", "dns": "coredns", "oauth": "auth-service",
            "payments-api": "payments-api", "object-store": "media-store"}
_NAME = {"kafka": "kafka-prod broker 4", "postgres": "postgres orders-db primary", "dns": "CoreDNS resolver",
         "oauth": "oauth token service", "payments-api": "payments-api", "object-store": "object store bucket media"}


def fake_alert_writer() -> FakeClient:
    """Offline stand-in for the writer model: templates an alert from the tuple in the prompt."""
    def responder(messages, kwargs):
        t = json.loads(re.search(r"<scenario>(.*?)</scenario>", messages[-1]["content"], re.S).group(1))
        name = "" if t["signal_quality"] == "missing_service" else _NAME[t["subsystem"]]
        body = f"{name} {_PHRASES[t['symptom']]}.{_IMPACT[t['impact']]}".strip()
        if t["signal_quality"] == "misleading_keyword":
            body += " Affects topic payments-ledger." if t["subsystem"] != "payments-api" else " Kafka client logs noisy."
        if t["signal_quality"] == "negated_impact":
            body += " No customer impact."
        title = f"{t['symptom'].replace('_', ' ')} on {name or 'unknown component'}"
        return text(json.dumps({"source": t["source"], "title": title, "body": body,
                                "service": _SERVICE[t["subsystem"]] if name else "", "env": "prod"}))
    return FakeClient(responder)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=24)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default="synth_cases.jsonl")
    a = ap.parse_args(argv)
    valid = filter_tuples(cross_product(DIMENSIONS))
    print(f"{len(cross_product(DIMENSIONS))} tuples in the cross product, {len(valid)} after filtering")
    picked = stratified_sample(valid, a.n, a.seed)
    cases, rejects = generate_cases(get_client(fake=fake_alert_writer()), picked)
    with Path(a.out).open("w") as f:
        for c in cases:
            f.write(json.dumps(c) + "\n")
    print(f"wrote {len(cases)} draft cases to {a.out} ({len(rejects)} rejected). Review every label before use.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
