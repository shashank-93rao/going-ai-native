import json
from pathlib import Path

from trifecta_audit import audit, main

DATA = Path(__file__).parent / "data" / "manifests"


def load(name: str) -> dict:
    return json.loads((DATA / name).read_text())


def manifest(*servers: tuple[str, list[dict]]) -> dict:
    return {"agent": "t", "servers": [{"name": n, "tools": tools} for n, tools in servers]}


def test_naive_coding_agent_has_trifecta_and_bash_is_all_three():
    r = audit(load("coding_agent.json"))
    assert r.has_trifecta
    assert r.single_tool_trifectas == ["local.bash"]
    assert not r.cross_server  # the local server alone already has all three


def test_contained_coding_agent_breaks_exfil_leg():
    r = audit(load("coding_agent_contained.json"))
    assert not r.has_trifecta
    assert r.providers["exfil"] == []
    assert "sandbox.bash" in r.mitigated["exfil"]
    assert r.problems == []


def test_oncall_agent_trifecta_from_mixing_servers_and_nonstructural_mitigation_ignored():
    r = audit(load("oncall_agent.json"))
    assert r.has_trifecta and r.cross_server
    assert "web.fetch_url" in r.providers["exfil"]
    assert any("not structural" in p for p in r.problems)
    assert r.cheapest_leg() == "exfil"


def test_two_legs_is_not_a_trifecta():
    r = audit(manifest(("a", [{"name": "read_db", "legs": ["private"]}, {"name": "web", "legs": ["untrusted"]}])))
    assert not r.has_trifecta and r.cheapest_leg() is None


def test_unlabeled_tool_fails_closed():
    r = audit(manifest(("mystery-mcp", [{"name": "do_stuff"}])))
    assert r.has_trifecta
    assert any("unlabeled" in p for p in r.problems)


def test_unknown_leg_reported():
    r = audit(manifest(("a", [{"name": "x", "legs": ["private", "spicy"]}])))
    assert any("unknown legs" in p for p in r.problems)
    assert r.providers["private"] == ["a.x"]


def test_render_mentions_verdict():
    assert "LETHAL TRIFECTA PRESENT" in audit(load("coding_agent.json")).render()
    assert "no trifecta" in audit(load("coding_agent_contained.json")).render()


def test_cli_exit_codes(capsys):
    assert main(["prog", str(DATA / "coding_agent.json")]) == 1
    assert main(["prog", str(DATA / "coding_agent_contained.json")]) == 0
    assert "agent:" in capsys.readouterr().out
