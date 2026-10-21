"""The eval harness runs offline; LangSmith upload is never attempted in tests."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def no_langsmith_network(monkeypatch):
    for var in ("LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2", "LANGSMITH_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("AINATIVE_FAKE", "1")


def test_both_implementations_score_the_same():
    import langsmith_eval as le

    raw = le.evaluate_locally(le.raw_target)
    graph = le.evaluate_locally(le.langgraph_target)
    assert raw["rows"] == graph["rows"]
    assert raw["summary"] == {"correct_action": 1.0, "no_forbidden_tools": 1.0,
                              "within_turn_budget": 1.0, "restart_precision": 1.0}


def test_evaluators_catch_a_bad_restart():
    import langsmith_eval as le

    bad = {"final_text": "DIAGNOSIS: disk\nACTION: restarted kafka-broker-3", "tools": ["restart_service"],
           "turns": 4, "restarts": ["kafka-broker-3"]}
    ref = {"action": "recommend_owner", "must_not_call": ["restart_service"]}
    assert le.correct_action(bad, ref)["score"] is False
    assert le.no_forbidden_tools(bad, ref)["score"] is False
    assert le.restart_precision([bad], [ref])["score"] == 0.0


def test_dataset_rows_have_langsmith_shape():
    import langsmith_eval as le

    rows = le.load_examples()
    assert len(rows) == 3 and all({"inputs", "outputs"} <= set(r) for r in rows)
