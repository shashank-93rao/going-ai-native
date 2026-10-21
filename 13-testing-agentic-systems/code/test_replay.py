"""Record/replay: what the cassette protects you from, and what it does not."""

import pytest

from replay_demo import cassette_staleness, record, replay
from ops_agent import SYSTEM
from trajectory_checks import trajectory_summary
from world import FaultPlan


@pytest.fixture
def cassette(tmp_path, monkeypatch):
    monkeypatch.setenv("AINATIVE_FAKE", "1")
    cas = tmp_path / "deploy.jsonl"
    rec = record(cas)
    return cas, rec


def test_replay_reproduces_trajectory(cassette):
    cas, rec = cassette
    assert trajectory_summary(replay(cas)) == trajectory_summary(rec)
    assert cassette_staleness(cas) == []


def test_prompt_change_invalidates_cassette(cassette):
    cas, _ = cassette
    with pytest.raises(KeyError, match="re-record"):
        replay(cas, system=SYSTEM + "\n- Prefer canary deploys.")
    assert any(s.startswith("system_sha") for s in cassette_staleness(cas, system=SYSTEM + "x"))


def test_world_change_invalidates_cassette(cassette):
    cas, _ = cassette
    with pytest.raises(KeyError):
        replay(cas, faults=FaultPlan(transient_rate=1.0))


def test_model_upgrade_replays_green_but_meta_catches_it(cassette):
    cas, rec = cassette
    assert trajectory_summary(replay(cas)) == trajectory_summary(rec)  # the lie: still green
    assert cassette_staleness(cas, model="claude-opus-5-5") == [
        "model: recorded 'claude-sonnet-5-5', now 'claude-opus-5-5'"]
