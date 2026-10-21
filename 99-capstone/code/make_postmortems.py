"""Generate synthetic incident postmortems and their gold labels (capstone variant B).

Deterministic by seed. Each document is assembled from a hidden ground-truth record,
then written the way real postmortems are written: facts spread across sections,
durations in prose, severities that change mid-incident, decoy services that were
investigated but not affected. The `hard_features` tags let you slice errors in M3.

    python make_postmortems.py --n 20 --out data     # rewrites data/postmortems/*.md and data/labels.jsonl
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any

SERVICES = ["checkout", "payments", "inventory", "search", "auth", "notifications", "ledger", "kafka-ingest"]
CATEGORIES = ["deploy", "config", "capacity", "dependency", "data", "network"]
HARD = ["sev_upgrade", "decoy_service", "duration_prose", "detection_in_prose", "no_customer_impact", "long_appendix"]

CAUSE_TEXT = {
    "deploy": "A release of {svc} ({ver}) changed the retry policy on the outbound client from 3 attempts with "
              "backoff to unbounded immediate retries. Under normal error rates this amplified load on {dep}.",
    "config": "A configuration push set the {svc} connection timeout to 50ms instead of 500ms. The change was "
              "applied fleet-wide without a canary because the config pipeline treated it as low risk.",
    "capacity": "Consumer lag on {svc} grew after a traffic shift doubled event volume. The consumer group was "
                "pinned at 12 partitions, so adding consumers did not increase throughput.",
    "dependency": "Our upstream card-network provider returned intermittent 503s. {svc} had no circuit breaker "
                  "on that call path, so request threads blocked on the provider until pools were exhausted.",
    "data": "A schema migration on {svc} backfilled NULL into a column the read path assumed was non-null. "
            "Rows written during the backfill window failed deserialization.",
    "network": "A security group change removed the rule allowing traffic from {svc} to {dep} on port 5432. "
               "Connections hung until TCP timeout rather than failing fast.",
}
ACTIONS = {
    "deploy": ["Add a retry budget to the shared HTTP client", "Require canary analysis for client library changes"],
    "config": ["Route timeout changes through the canary stage", "Add a lint rejecting timeouts under 100ms"],
    "capacity": ["Raise partition count to 48 and document the procedure", "Alert on consumer lag growth rate"],
    "dependency": ["Add a circuit breaker on the provider call path", "Bulkhead provider calls into their own pool"],
    "data": ["Make the backfill write a sentinel instead of NULL", "Add a contract test for nullable columns"],
    "network": ["Manage security groups through reviewed IaC only", "Add a synthetic probe for this path"],
}


def _hhmm(minutes: int) -> str:
    return f"{(minutes // 60) % 24:02d}:{minutes % 60:02d}"


def _dur(minutes: int) -> str:
    h, m = divmod(minutes, 60)
    return f"{h}h {m}m" if h else f"{m}m"


def make_record(i: int, rng: random.Random) -> dict[str, Any]:
    cat = CATEGORIES[i % len(CATEGORIES)]
    affected = rng.sample(SERVICES, rng.choice([1, 2, 2, 3]))
    hard = sorted(rng.sample(HARD, rng.choice([1, 2, 2, 3])))
    start = rng.randint(6 * 60, 20 * 60)
    detect = rng.randint(3, 40)
    duration = rng.randint(detect + 10, 300)
    sev = rng.choice(["SEV1", "SEV2", "SEV2", "SEV3"])
    if "sev_upgrade" in hard and sev == "SEV3":
        sev = "SEV2"
    decoy = rng.choice([s for s in SERVICES if s not in affected])
    return {
        "doc_id": f"pm-{i:03d}",
        "incident_id": f"INC-{2000 + rng.randint(0, 999)}",
        "severity": sev,
        "root_cause_category": cat,
        "services_affected": sorted(affected),
        "impact_start": _hhmm(start),
        "detection_minutes": detect,
        "duration_minutes": duration,
        "customer_impact": "no_customer_impact" not in hard,
        "action_items": ACTIONS[cat],
        "summary": "",  # filled after rendering
        "hard_features": hard,
        "_decoy": decoy,
        "_start": start,
    }


def render(r: dict[str, Any], rng: random.Random) -> str:
    hard, svcs = r["hard_features"], r["services_affected"]
    primary, start = svcs[0], r["_start"]
    alert, end = start + r["detection_minutes"], start + r["duration_minutes"]
    mitigate = start + max(r["detection_minutes"] + 5, r["duration_minutes"] - rng.randint(5, 30))
    sev = r["severity"]
    declared = {"SEV1": "SEV2", "SEV2": "SEV3"}.get(sev, sev) if "sev_upgrade" in hard else sev
    dep = rng.choice([s for s in SERVICES if s != primary])
    lines = [f"# Postmortem: {primary} degradation ({r['incident_id']})", ""]
    header = []
    if "sev_upgrade" not in hard:
        header.append(f"**Severity:** {sev}")
    if "duration_prose" not in hard:
        header.append(f"**Duration:** {_dur(r['duration_minutes'])}")
    header.append(f"**Author:** on-call, {rng.choice(['platform', 'payments', 'core'])} team")
    lines += [" | ".join(header), "", "## Summary", ""]
    impact = ("No customer-facing impact; internal batch jobs and dashboards were delayed."
              if not r["customer_impact"] else
              f"Customers saw elevated errors on {', '.join(svcs)}.")
    summary = f"{CAUSE_TEXT[r['root_cause_category']].split('.')[0].format(svc=primary, ver='v4.12.0', dep=dep)}."
    r["summary"] = summary
    lines += [summary + " " + impact, ""]
    if "decoy_service" in hard:
        lines += [f"We initially suspected {r['_decoy']} because its dashboards were noisy, but its error rate "
                  "and latency were within normal bounds throughout and it was not affected.", ""]
    lines += ["## Timeline (UTC)", ""]
    if "detection_in_prose" in hard:
        lines.append(f"- {_hhmm(alert)} First alert fired: error ratio above SLO on {primary}.")
    else:
        lines += [f"- {_hhmm(start)} Impact begins: error ratio on {primary} starts rising.",
                  f"- {_hhmm(alert)} First alert fired: error ratio above SLO on {primary}."]
    lines.append(f"- {_hhmm(alert + 3)} Incident declared {declared}; incident commander assigned.")
    if "sev_upgrade" in hard:
        lines.append(f"- {_hhmm(alert + 12)} Upgraded to {sev} after impact spread to {svcs[-1]}.")
    lines += [f"- {_hhmm(mitigate)} Mitigation applied.", f"- {_hhmm(end)} Error rates back to baseline; "
              "incident resolved.", ""]
    if "detection_in_prose" in hard:
        lines += [f"Later log analysis showed impact actually began at {_hhmm(start)}, before any alert.", ""]
    if "duration_prose" in hard:
        lines += [f"Customer-visible impact lasted from {_hhmm(start)} until resolution at {_hhmm(end)}.", ""]
    lines += ["## Root cause", "", CAUSE_TEXT[r["root_cause_category"]].format(svc=primary, ver="v4.12.0", dep=dep), ""]
    lines += ["## Impact", "", impact + (f" Affected services: {', '.join(svcs)}." if len(svcs) > 1 else ""), ""]
    lines += ["## Action items", ""] + [f"- [ ] {a}" for a in r["action_items"]] + [""]
    if "long_appendix" in hard:
        lines += ["## Appendix: runbook excerpt", "",
                  "This runbook applies to SEV1 incidents on any tier-0 service. For SEV1, page the "
                  f"{rng.choice(SERVICES)} and {rng.choice(SERVICES)} owners immediately. Typical SEV1 "
                  "duration targets are under 1h 0m.", ""]
        lines += [f"    {_hhmm(start + k)} {rng.choice(SERVICES)} INFO healthcheck ok" for k in range(0, 40, 4)] + [""]
    return "\n".join(lines)


def generate(n: int = 20, seed: int = 99) -> list[tuple[dict[str, Any], str]]:
    rng = random.Random(seed)
    out = []
    for i in range(n):
        rec = make_record(i, rng)
        doc = render(rec, rng)
        out.append(({k: v for k, v in rec.items() if not k.startswith("_")}, doc))
    return out


def write(out_dir: str | Path, n: int = 20, seed: int = 99) -> None:
    out = Path(out_dir)
    (out / "postmortems").mkdir(parents=True, exist_ok=True)
    with open(out / "labels.jsonl", "w") as f:
        for rec, doc in generate(n, seed):
            (out / "postmortems" / f"{rec['doc_id']}.md").write_text(doc)
            f.write(json.dumps(rec) + "\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--seed", type=int, default=99)
    ap.add_argument("--out", default=str(Path(__file__).parent / "data"))
    a = ap.parse_args()
    write(a.out, a.n, a.seed)
    print(f"wrote {a.n} postmortems to {a.out}")
