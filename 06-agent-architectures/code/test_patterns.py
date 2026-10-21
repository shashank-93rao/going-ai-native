import threading

import pytest

from ainative_kit import FakeClient, Response, text, tool
from patterns import (Augmented, GateFailed, Step, Tool, Verdict, agent_loop, chain, evaluator_optimizer,
                      orchestrator_workers, parallel_sections, parse_json, route, vote)


def test_parse_json_tolerates_fences_and_prose():
    assert parse_json('Here you go:\n```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json('noise [1, 2]') == [1, 2]
    with pytest.raises(ValueError):
        parse_json("no json here")


def test_augmented_puts_memory_and_retrieval_in_context():
    fake = FakeClient([text("ok")])
    llm = Augmented(fake, system="sys", retrieve=lambda q: ["doc about " + q], memory=["user prefers terse"])
    llm.ask("kafka lag")
    sent = fake.calls[0]["messages"][0]["content"]
    assert "<memory>" in sent and "user prefers terse" in sent and "doc about kafka lag" in sent
    assert fake.calls[0]["system"] == "sys"


def test_agent_loop_runs_tools_and_returns_errors_to_model():
    calls = []
    tools = {"lag": Tool({"name": "lag"}, lambda inp: calls.append(inp) or "512330"),
             "boom": Tool({"name": "boom"}, lambda inp: 1 / 0)}
    fake = FakeClient([tool("lag", {"g": "notify"}, id="t1"), tool("boom", {}, id="t2"), text("done")])
    res = agent_loop(fake, "check lag", tools)
    assert res.stopped_by == "end_turn" and res.turns == 3 and calls == [{"g": "notify"}]
    err = fake.calls[2]["messages"][-1]["content"][0]
    assert err["is_error"] and "ZeroDivisionError" in err["content"]


def test_agent_loop_respects_turn_budget():
    fake = FakeClient(lambda m, kw: tool("lag", {}, id=f"t{len(m)}"))
    res = agent_loop(fake, "x", {"lag": Tool({"name": "lag"}, lambda i: "1")}, max_turns=3)
    assert res.stopped_by == "max_turns" and len(fake.calls) == 3


def test_chain_gate_retries_with_reason_then_passes():
    fake = FakeClient([text("TOO LONG " * 50), text("short"), text("final: short")])
    steps = [Step("draft", lambda c: f"draft {c['topic']}",
                  gate=lambda out, c: None if len(out) < 20 else "over 20 chars"),
             Step("final", lambda c: f"polish {c['draft']}")]
    ctx = chain(fake, steps, {"topic": "lag"})
    assert ctx["draft"] == "short" and ctx["final"] == "final: short"
    assert "rejected: over 20 chars" in fake.calls[1]["messages"][0]["content"]


def test_chain_raises_when_gate_keeps_failing():
    fake = FakeClient([text("bad"), text("bad")])
    with pytest.raises(GateFailed) as e:
        chain(fake, [Step("s", lambda c: "p", gate=lambda o, c: "always")], {})
    assert e.value.step == "s"


def test_route_validates_label_and_falls_back():
    handlers = {"database": lambda x: "db", "other": lambda x: "generic"}
    assert route(FakeClient([text("Database.")]), "x", handlers, classifier_system="c", default="other").output == "db"
    r = route(FakeClient([text("I think it's networking")]), "x", handlers, classifier_system="c", default="other")
    assert r.fell_back and r.label == "other"


def test_parallel_sections_really_run_concurrently():
    barrier = threading.Barrier(2, timeout=2)   # deadlocks (BrokenBarrierError) if run serially
    def section(name):
        def run():
            barrier.wait()
            return name
        return run
    out = parallel_sections({"a": section("A"), "b": section("B")})
    assert out == {"a": "A", "b": "B"}


def test_vote_majority_and_abstain():
    answers = iter(["yes", "yes", "no"])
    v = vote(FakeClient(lambda m, kw: text(next(answers))), "safe?", n=3, parse=str.strip)
    assert v.winner == "yes" and v.tally == {"yes": 2, "no": 1}
    answers2 = iter(["a", "b", "c", "a"])
    v2 = vote(FakeClient(lambda m, kw: text(next(answers2))), "q", n=4, parse=str.strip)
    assert v2.winner is None                    # 2/4 does not clear a >50% quorum


def test_orchestrator_caps_and_validates_plan():
    plan = '{"subtasks": [{"x": 1}, {"x": 2}, {"x": -1}, {"x": 3}]}'
    res = orchestrator_workers(FakeClient([text(plan)]), "t", plan_system="p", validate=lambda s: s["x"] > 0,
                               worker=lambda s: s["x"] * 10, synthesize=sum, max_subtasks=2)
    assert res.worker_outputs == [10, 20] and res.final == 30
    assert {"x": -1} in res.dropped and {"x": 3} in res.dropped


def test_evaluator_optimizer_stop_rules():
    passes = evaluator_optimizer(lambda h: str(len(h)), lambda c: Verdict(c == "2", int(c) / 2, "more"))
    assert passes.stopped_by == "passed" and len(passes.attempts) == 3
    stalls = evaluator_optimizer(lambda h: "x", lambda c: Verdict(False, 0.5, "no"), max_rounds=10, stall_rounds=2)
    assert stalls.stopped_by == "stalled" and len(stalls.attempts) == 3
    budget = evaluator_optimizer(lambda h: str(len(h)), lambda c: Verdict(False, int(c), "no"), max_rounds=3)
    assert budget.stopped_by == "max_rounds" and budget.best.candidate == "2"
