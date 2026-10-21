"""Router, simulated model and frozen evaluator."""

import json
from pathlib import Path

import pytest
from ainative_kit import FakeClient, Response, text, tool

from incident_router import DEFAULT_CONFIG, build_system, cost_usd, lookup_owner, parse_team, route
from router_eval import by_tag, evaluate, fingerprint, grade, load_split
from sim_model import expected_accuracy, make_sim_client

CLIMBED = json.loads((Path(__file__).parent / "data" / "climbed_config.json").read_text())


@pytest.mark.parametrize("reply,team", [
    ("team: database\nreason: pool", "database"),
    ("Team: Data-Pipeline", "data-pipeline"),
    ("reason first\nteam: edge", "edge"),
    ("team: marketing", None),
    ("I think database", None),
])
def test_parse_team(reply, team):
    assert parse_team(reply) == team


def test_route_runs_tool_loop():
    fake = FakeClient([tool("lookup_owner", {"service": "svc-orion"}, id="t1"), text("team: payments\nreason: x")])
    cfg = dict(DEFAULT_CONFIG, tools=["lookup_owner"])
    r = route(fake, cfg, "svc-orion p99 4000ms")
    assert r.team == "payments" and r.calls == 2 and r.tool_calls == ["lookup_owner"]
    second = fake.calls[1]["messages"]
    assert second[-1]["content"][0] == {"type": "tool_result", "tool_use_id": "t1", "content": "payments"}
    assert fake.calls[0]["tools"][0]["name"] == "lookup_owner"


def test_route_truncation_is_a_miss():
    fake = FakeClient([Response(text="", stop_reason="max_tokens")])
    r = route(fake, DEFAULT_CONFIG, "anything")
    assert r.truncated and r.team is None and grade(r.team, "edge") == 0


def test_route_is_bounded():
    fake = FakeClient(lambda m, k: tool("lookup_owner", {"service": "svc-vega"}))
    r = route(fake, dict(DEFAULT_CONFIG, tools=["lookup_owner"]), "x", max_turns=3)
    assert r.calls == 3 and r.team is None


def test_build_system_and_lookup():
    s = build_system(dict(DEFAULT_CONFIG, sections=["base", "queue_definitions"], extra_prompt="EXTRA"))
    assert "## Queue definitions" in s and s.endswith("EXTRA")
    assert lookup_owner("svc-draco") == "database" and lookup_owner("svc-unknown") == "unknown"


def test_cost():
    assert cost_usd("claude-sonnet-5-5", 1_000_000, 0) == pytest.approx(2.0)


def test_dataset_split_by_cluster():
    rows = load_split("all")
    split_of: dict[str, set] = {}
    for r in rows:
        split_of.setdefault(r["cluster"], set()).add(r["split"])
    assert all(len(s) == 1 for s in split_of.values()), "an incident leaks across dev/test"
    assert len({r["text"] for r in rows}) == len(rows)


def test_sim_is_deterministic_per_seed():
    dev = load_split("dev")[:40]
    a = evaluate(DEFAULT_CONFIG, dev, 2, seed=5)
    b = evaluate(DEFAULT_CONFIG, dev, 2, seed=5)
    c = evaluate(DEFAULT_CONFIG, dev, 2, seed=6)
    assert a.per_repeat == b.per_repeat and a.per_repeat != c.per_repeat


def test_sim_matches_running_example_levels():
    dev = load_split("dev")
    base = expected_accuracy(dev, build_system(DEFAULT_CONFIG), "claude-sonnet-5-5", "medium", False)
    top = expected_accuracy(dev, build_system(CLIMBED), CLIMBED["model"], CLIMBED["effort"], True)
    assert 0.66 <= base <= 0.74 and 0.88 <= top <= 0.95
    r = evaluate(CLIMBED, dev, 3, seed=1)
    assert r.accuracy == pytest.approx(top, abs=0.04)


def test_sim_memorizes_pasted_items():
    item = next(i for i in load_split("dev") if i["tag"] == "tiebreak")
    cfg = dict(DEFAULT_CONFIG, extra_prompt=f"## Examples\n{item['text']}\nteam: {item['label']}")
    r = evaluate(cfg, [item], 5, seed=0, client_factory=lambda c, s: make_sim_client(c["effort"], s))
    assert r.accuracy == 1.0


def test_by_tag_and_fingerprint_stable():
    dev = load_split("dev")[:30]
    r = evaluate(DEFAULT_CONFIG, dev, 1, seed=0)
    assert set(by_tag(r, dev)) <= {"easy", "ambiguous", "tiebreak", "lookup", "reasoning"}
    assert fingerprint() == fingerprint() and len(fingerprint()) == 16
