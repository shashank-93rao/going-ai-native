"""Generate data/incidents.jsonl: the incident-router eval set used in this module.

Each row is one alert to route to an owning team. Alerts are grouped into
incidents (`cluster`): several alerts fired by the same underlying event, so
they share context and their errors correlate. The split is by cluster, so no
incident has alerts on both sides of the dev/test boundary.

`tag` records the difficulty family. It exists for error analysis and for the
simulated model; the router never sees it.

    python make_incidents.py                      # rewrites data/incidents.jsonl (seeded)
    python make_incidents.py --clusters 64 --out data/small.jsonl
"""

from __future__ import annotations

import json
import random
from pathlib import Path

TEAMS = ["payments", "platform", "data-pipeline", "database", "identity", "edge"]

# Internal codenames whose owner is only knowable from the service catalog.
OWNERS = {"orion": "payments", "vega": "data-pipeline", "lyra": "identity",
          "atlas": "platform", "draco": "database", "nova": "edge",
          "castor": "payments", "rigel": "data-pipeline", "deneb": "database"}

EASY = {
    "payments": ["payments-api 5xx rate {x}% on /v1/charges for {m}m",
                 "checkout-svc p99 {ms}ms, card authorizations timing out (region {r})"],
    "platform": ["k8s node pool {pool} NotReady: {n} nodes missing kubelet heartbeats",
                 "cluster-autoscaler failing to provision nodes in {r}"],
    "data-pipeline": ["Kafka consumer group {grp} lag {k} msgs on topic {topic}",
                      "Airflow DAG {dag} failed 3 consecutive runs"],
    "database": ["postgres replica {db}-r{n} replication lag {s}s",
                 "autovacuum stuck on table {tbl} in {db} for {m}m"],
    "identity": ["auth-svc login failures {x}% after signing key rotation",
                 "SAML assertion errors spiking for tenant t-{n}{n}{n}"],
    "edge": ["CDN 5xx at POP {pop} {x}%", "lb {lb} health checks failing on {n} targets"],
}
# (owner, decoy, template). The decoy is the plausible WRONG team a model picks
# when it misses the point: the team whose service shows the symptom.
# Symptom shows in one team's service; the owner is whoever owns the saturated resource.
AMBIGUOUS = [
    ("database", "payments", "connection pool to {db} exhausted from payments-api; checkout errors {x}%"),
    ("platform", "payments", "payments-api pods OOMKilled on node pool {pool}; node memory pressure"),
    ("database", "identity", "auth-svc 500s: postgres {db} rejecting connections (too many clients)"),
    ("platform", "data-pipeline", "consumer {grp} pods evicted for disk pressure on node pool {pool}"),
    ("identity", "edge", "edge 502s on /login; upstream auth-svc failing JWKS fetch"),
]
# Several components alert; the owner is the EARLIEST failing component.
TIEBREAK = [
    ("data-pipeline", "payments", "Alert chain: 09:{b}2 payments-api 5xx; 09:{a}1 kafka broker {n} under-replicated partitions; 09:{b}0 orders-consumer lag"),
    ("platform", "edge", "Alert chain: 14:{b}5 CDN origin timeouts; 14:{b}0 lb {lb} unhealthy targets; 14:{a}3 k8s node {pool}-{n} NotReady"),
    ("database", "identity", "Alert chain: 03:{b}4 identity token refresh errors; 03:{a}2 postgres {db} failover started; 03:{b}1 payments-api retries"),
    ("edge", "payments", "Alert chain: 21:{b}8 checkout conversion drop; 21:{a}0 POP {pop} TLS handshake failures; 21:{b}5 auth-svc timeouts"),
]
LOOKUP = ["svc-{svc} p99 {ms}ms, error budget burn {n}x", "svc-{svc} crash loop after deploy {sha}"]
# Requires connecting several signals to the cause.
REASONING = [
    ("data-pipeline", "database", "{db} WAL volume at 9{n}% and rising; CDC replication slot inactive {n}h; warehouse tables stale"),
    ("platform", "identity", "401s across all services since 1{n}:0{n}; NTP clock-skew alarm on node pool {pool}"),
    ("payments", "edge", "checkout success -{n}%; card network responses normal; flag new-3ds-flow enabled 1{n}:{m}"),
    ("database", "platform", "API latency up everywhere; {db} buffer cache hit rate fell from 99% to 7{n}% after index drop"),
    ("edge", "platform", "spike in 404s on static assets only; CDN cache purge job ran at 0{n}:{m}"),
]


def _fill(tmpl: str, rng: random.Random, svc: str = "") -> str:
    vals = {"x": rng.randint(3, 40), "m": rng.randint(10, 59), "ms": rng.randint(900, 9000),
            "r": rng.choice(["us-east-1", "eu-west-1", "ap-south-1"]), "pool": rng.choice(["gp-a", "gp-b", "mem-c"]),
            "n": rng.randint(2, 9), "grp": rng.choice(["ledger-sink", "orders-enricher", "fraud-scorer"]),
            "k": rng.randint(10_000, 900_000), "topic": rng.choice(["orders.v2", "payments.events", "clicks"]),
            "dag": rng.choice(["daily_revenue", "user_dim", "ledger_rollup"]), "db": rng.choice(["ledger-db", "users-db", "orders-db"]),
            "s": rng.randint(30, 900), "tbl": rng.choice(["events", "ledger_lines", "sessions"]),
            "pop": rng.choice(["FRA", "IAD", "BOM", "SIN"]), "lb": rng.choice(["lb-public-1", "lb-api-2"]),
            "a": rng.randint(0, 2), "b": rng.randint(3, 5), "svc": svc, "sha": f"{rng.getrandbits(28):07x}"}
    return tmpl.format(**vals)


def generate(n_clusters: int = 320, seed: int = 33) -> list[dict]:
    rng = random.Random(seed)
    rows: list[dict] = []
    weights = [("easy", 0.48), ("ambiguous", 0.16), ("tiebreak", 0.13), ("lookup", 0.10), ("reasoning", 0.13)]
    tag_counts: dict[str, int] = {}
    for c in range(n_clusters):
        tag = rng.choices([t for t, _ in weights], [w for _, w in weights])[0]
        decoy = None
        if tag == "easy":
            team = rng.choice(TEAMS)
            tmpl = rng.choice(EASY[team])
        elif tag == "ambiguous":
            team, decoy, tmpl = rng.choice(AMBIGUOUS)
        elif tag == "tiebreak":
            team, decoy, tmpl = rng.choice(TIEBREAK)
        elif tag == "lookup":
            tmpl = rng.choice(LOOKUP)
            decoy = "platform"  # "crash loop / latency" reads like infrastructure
        else:
            team, decoy, tmpl = rng.choice(REASONING)
        svc = rng.choice(list(OWNERS)) if tag == "lookup" else ""
        if tag == "lookup":
            team = OWNERS[svc]
        # Stratified split BY CLUSTER: alternate dev/test within each difficulty tag.
        split = "dev" if tag_counts.get(tag, 0) % 2 == 0 else "test"
        tag_counts[tag] = tag_counts.get(tag, 0) + 1
        for j in range(rng.randint(1, 5)):
            body = _fill(tmpl, rng, svc)  # the [alert c.j] prefix keeps every text unique
            rows.append({"id": f"inc{c:03d}-a{j}", "cluster": f"inc{c:03d}", "split": split,
                         "text": f"[alert {c:03d}.{j}] {body}", "label": team, "tag": tag,
                         "decoy": decoy if decoy != team else None})
    return rows


def load_incidents(path: str | Path | None = None) -> list[dict]:
    p = Path(path) if path else Path(__file__).parent / "data" / "incidents.jsonl"
    return [json.loads(line) for line in p.read_text().splitlines() if line.strip()]


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--clusters", type=int, default=320, help="number of incidents")
    ap.add_argument("--out", default=str(Path(__file__).parent / "data" / "incidents.jsonl"))
    args = ap.parse_args()
    out = Path(args.out)
    out.parent.mkdir(exist_ok=True)
    rows = generate(args.clusters)
    out.write_text("".join(json.dumps(r) + "\n" for r in rows))
    by = {}
    for r in rows:
        by.setdefault((r["split"], r["tag"]), 0)
        by[(r["split"], r["tag"])] += 1
    print(f"wrote {len(rows)} alerts in {len({r['cluster'] for r in rows})} incidents -> {out}")
    for k in sorted(by):
        print(f"  {k[0]:5s} {k[1]:10s} {by[k]}")
