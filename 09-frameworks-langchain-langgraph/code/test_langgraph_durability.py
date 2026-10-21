"""Checkpoints, interrupts, resume, threads, crash recovery, time travel and the Store."""

from __future__ import annotations

import pytest
from ainative_kit import FakeClient

import langgraph_agent as lg
from triage_world import OpsWorld, scripted_policy


def make(world=None, client=None, saver=None, store=None):
    world = world or OpsWorld()
    client = client or FakeClient(scripted_policy)
    saver = saver or lg.MemorySaver()
    return lg.build_graph(client, world, checkpointer=saver, store=store), world, client, saver


def test_interrupt_pauses_before_the_risky_tool():
    graph, world, client, _ = make()
    out = lg.start(graph, "ALERT-4211", "t1")
    payload = lg.pending_interrupt(out)
    assert payload["action_request"] == {
        "action": "restart_service",
        "args": {"service": "checkout-api", "reason": "connection pool exhausted (leak in OrderRepository)"},
    }
    assert world.restarts == []                                  # nothing mutated yet
    assert graph.get_state(lg.thread("t1")).next == ("approve",)
    assert len(client.calls) == 3


def test_read_only_alerts_never_interrupt():
    graph, world, _, _ = make()
    out = lg.start(graph, "ALERT-4212", "t1")
    assert lg.pending_interrupt(out) is None and world.restarts == []


def test_resume_from_a_fresh_graph_uses_the_checkpoint_not_the_model():
    graph, world, _, saver = make()
    lg.start(graph, "ALERT-4211", "t1")
    del graph  # simulate the process going away; only the checkpointer survives

    fresh_client = FakeClient(scripted_policy)
    graph2 = lg.build_graph(fresh_client, world, checkpointer=saver)
    out = lg.resume(graph2, "t1", {"type": "accept"})
    assert world.restarts == ["checkout-api"]
    assert out["final_text"].startswith("DIAGNOSIS: checkout-api connection pool")
    assert len(fresh_client.calls) == 1   # history came from the checkpoint; only the final turn was new
    assert len(fresh_client.calls[0]["messages"]) == 7


def test_reject_and_edit_decisions():
    graph, world, _, _ = make()
    lg.start(graph, "ALERT-4211", "rej")
    out = lg.resume(graph, "rej", {"type": "response", "args": "peak traffic"})
    assert world.restarts == [] and "rejected" in out["final_text"]

    graph, world, _, _ = make()
    lg.start(graph, "ALERT-4211", "edit")
    lg.resume(graph, "edit", {"type": "edit", "args": {"service": "checkout-api-canary", "reason": "canary first"}})
    assert world.restarts == ["checkout-api-canary"]


def test_threads_are_isolated():
    graph, world, _, _ = make()
    lg.start(graph, "ALERT-4211", "a")
    lg.start(graph, "ALERT-4211", "b")
    lg.resume(graph, "a", {"type": "accept"})
    assert graph.get_state(lg.thread("a")).next == ()
    assert graph.get_state(lg.thread("b")).next == ("approve",)   # still parked, untouched
    assert world.restarts == ["checkout-api"]


class FlakyWorld(OpsWorld):
    """query_logs fails once, like a log backend timing out."""

    def __init__(self):
        super().__init__()
        self.failures_left = 1

    def execute(self, name, args, call_id):
        if name == "query_logs" and self.failures_left:
            self.failures_left -= 1
            raise TimeoutError("loki query timed out")
        return super().execute(name, args, call_id)


def test_crash_mid_run_resumes_from_last_checkpoint():
    world, client = FlakyWorld(), FakeClient(scripted_policy)
    graph, *_ = make(world=world, client=client)
    with pytest.raises(TimeoutError):
        lg.start(graph, "ALERT-4211", "t1")
    snap = graph.get_state(lg.thread("t1"))
    assert snap.next == ("tools",)                # the failed node is what runs next
    assert len(client.calls) == 2

    out = graph.invoke(None, lg.thread("t1"))      # retry: no new input, continue the thread
    assert lg.pending_interrupt(out) is not None
    assert len(client.calls) == 3                  # earlier model turns were NOT re-run


def test_time_travel_fork_replays_a_different_decision():
    graph, world, _, _ = make()
    lg.start(graph, "ALERT-4211", "t1")
    first = lg.resume(graph, "t1", {"type": "accept"})
    assert world.restarts == ["checkout-api"]

    fork = lg.fork_before_approval(graph, "t1")
    again = graph.invoke(None, fork)
    assert lg.pending_interrupt(again) is not None  # the approve node re-ran and asked again
    alt = lg.resume(graph, "t1", {"type": "response", "args": "what if we had said no?"})
    assert "rejected" in alt["final_text"] and "restarted" in first["final_text"]
    assert world.restarts == ["checkout-api"]        # the fork did not restart anything


def test_replaying_the_side_effect_node_is_safe_only_because_of_idempotency_keys():
    graph, world, _, _ = make()
    lg.start(graph, "ALERT-4211", "t1")
    original = lg.resume(graph, "t1", {"type": "accept"})
    history = list(graph.get_state_history(lg.thread("t1")))
    before_restart = next(s for s in history if s.next == ("tools",) and s.values.get("approvals"))
    replayed = graph.invoke(None, before_restart.config)   # re-executes the tools node
    assert world.restarts == ["checkout-api"]              # deduped by tool_use_id, not by luck
    assert list(world._results_by_call_id) == ["toolu_03"]
    assert replayed["final_text"] == original["final_text"]  # stored result -> same transcript


def test_store_is_cross_thread_and_not_rolled_back_by_time_travel():
    store = lg.InMemoryStore()
    graph, _, client, _ = make(store=store)
    lg.start(graph, "ALERT-4211", "t1")
    lg.resume(graph, "t1", {"type": "accept"})
    assert "restarted" in store.get(lg.MEMORY_NS, "ALERT-4211").value["action"]

    lg.start(graph, "ALERT-4213", "t2")              # a different thread sees thread t1's memory
    assert "Prior resolutions" in client.calls[-1]["system"]

    fork = lg.fork_before_approval(graph, "t1")
    graph.invoke(None, fork)
    lg.resume(graph, "t1", {"type": "response", "args": "no"})
    # The checkpoint forked; the Store did not. Last writer wins: it now records the fork's outcome.
    assert "rejected" in store.get(lg.MEMORY_NS, "ALERT-4211").value["action"]


def test_stream_updates_shows_nodes_in_order():
    graph, *_ = make()
    nodes = [node for chunk in graph.stream(
        {"alert_id": "ALERT-4213", "messages": [{"role": "user", "content": "Triage ALERT-4213."}]},
        lg.thread("s"), stream_mode="updates") for node in chunk]
    assert nodes == ["model", "tools", "model", "tools", "model"]
