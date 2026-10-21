"""Same agent, two orchestrations: the raw loop and the LangGraph graph must agree exactly."""

from __future__ import annotations

import pytest
from ainative_kit import FakeClient, Response, ToolCall, Tracer

import langgraph_agent as lg
import raw_agent
from triage_world import OpsWorld, outcome_of, scripted_policy

ALERTS = ["ALERT-4211", "ALERT-4212", "ALERT-4213"]


def run_graph_auto_accept(alert_id: str, client, world, **kw):
    graph = lg.build_graph(client, world, checkpointer=lg.MemorySaver(), **kw)
    out = lg.start(graph, alert_id, f"t-{alert_id}")
    while lg.pending_interrupt(out):
        out = lg.resume(graph, f"t-{alert_id}", {"type": "accept"})
    return out


@pytest.mark.parametrize("alert_id", ALERTS)
def test_same_outcome_and_same_transcript(alert_id):
    raw_client, graph_client = FakeClient(scripted_policy), FakeClient(scripted_policy)
    raw_world, graph_world = OpsWorld(), OpsWorld()

    raw = raw_agent.run(alert_id, raw_client, raw_world)
    graph = run_graph_auto_accept(alert_id, graph_client, graph_world)

    assert raw.final_text == graph["final_text"]
    assert raw.tool_sequence == graph["tool_sequence"]
    assert raw_world.restarts == graph_world.restarts
    # Stronger: the model saw byte-identical requests in both implementations.
    assert [c["messages"] for c in raw_client.calls] == [c["messages"] for c in graph_client.calls]
    assert [c["system"] for c in raw_client.calls] == [c["system"] for c in graph_client.calls]


def test_expected_decisions_per_alert():
    outcomes = {}
    for a in ALERTS:
        world = OpsWorld()
        outcomes[a] = (outcome_of(raw_agent.run(a, FakeClient(scripted_policy), world).final_text), world.restarts)
    assert outcomes == {
        "ALERT-4211": ("restart", ["checkout-api"]),
        "ALERT-4212": ("recommend_owner", []),
        "ALERT-4213": ("recommend_owner", []),
    }


def test_raw_rejection_path_matches_graph_rejection_path():
    raw_world = OpsWorld()
    raw = raw_agent.run("ALERT-4211", FakeClient(scripted_policy), raw_world, approve=lambda c: (False, "peak hours"))
    g_world = OpsWorld()
    graph = lg.build_graph(FakeClient(scripted_policy), g_world, checkpointer=lg.MemorySaver())
    lg.start(graph, "ALERT-4211", "t")
    out = lg.resume(graph, "t", {"type": "response", "args": "peak hours"})
    assert raw.final_text == out["final_text"]
    assert outcome_of(raw.final_text) == "escalate_after_reject"
    assert raw_world.restarts == g_world.restarts == []


def test_turn_budget_trips_in_both():
    def stuck(messages, kwargs):  # a model that never stops calling tools
        return Response(tool_calls=[ToolCall(f"toolu_{len(messages)}", "get_alert", {"alert_id": "ALERT-4211"})],
                        stop_reason="tool_use")

    raw = raw_agent.run("ALERT-4211", FakeClient(stuck), OpsWorld(), max_turns=3)
    assert raw.stopped_by == "max_turns" and raw.turns == 3
    out = run_graph_auto_accept("ALERT-4211", FakeClient(stuck), OpsWorld(), max_turns=3)
    assert out["turns"] == 3 and "final_text" not in out


def test_raw_agent_emits_spans():
    tracer = Tracer()
    raw_agent.run("ALERT-4211", FakeClient(scripted_policy), OpsWorld(), tracer=tracer)
    names = [s.name for s in tracer.spans]
    assert names.count("llm_call") == 4 and names.count("tool_call") == 3
    root = next(s for s in tracer.spans if s.name == "agent_run")
    assert all(s.trace_id == root.trace_id for s in tracer.spans)
    approved = [s for s in tracer.spans if s.attrs.get("tool") == "restart_service"]
    assert approved[0].attrs["approved"] is True
