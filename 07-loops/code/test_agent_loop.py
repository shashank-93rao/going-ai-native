"""Agent loop tests: message accumulation, tool_result plumbing, gates, and runaway governors."""

import json

from ainative_kit import FakeClient, Response, ToolCall, Tracer, load_traces, text
from agent_loop import oracle_gate, run_agent, workspace_tools
from governor import ExitCode, Governor, Limits
from oracle import PytestOracle
from toy_task import (fixing_script, make_workspace, oscillating_responder, premature_script, runaway_responder,
                      wandering_responder)

ORACLE = PytestOracle(["spec_tokenbucket.py"])
TASK = "Make spec_tokenbucket.py pass."


def setup(tmp_path):
    ws = make_workspace(tmp_path)
    tools, state = workspace_tools(ws, ORACLE)
    return ws, tools, state


def test_fixing_script_makes_the_failing_tests_pass(tmp_path):
    ws, tools, state = setup(tmp_path)
    assert not ORACLE.run(ws).ok
    fake = FakeClient(fixing_script())
    res = run_agent(fake, TASK, tools, completion_gate=oracle_gate(ORACLE, ws), metric=lambda: state["last_score"])
    assert res.exit_code is ExitCode.SUCCESS and res.reason == "completion gate passed"
    assert ORACLE.run(ws).ok
    assert res.iterations == 5 and res.governor["best_metric"] == 1.0


def test_messages_accumulate_and_the_full_history_is_resent(tmp_path):
    _, tools, _ = setup(tmp_path)
    fake = FakeClient(fixing_script())
    run_agent(fake, TASK, tools)
    sizes = [len(c["messages"]) for c in fake.calls]
    assert sizes == [1, 3, 5, 7, 9]  # stateless API: user, (assistant, user[tool_results])*
    assert fake.calls[0]["tools"][0]["name"] == "read_file"


def test_parallel_tool_calls_return_in_one_user_turn_with_matching_ids(tmp_path):
    _, tools, _ = setup(tmp_path)
    fake = FakeClient(fixing_script())
    res = run_agent(fake, TASK, tools)
    turn = res.messages[4]  # [task, asst t1, results t1, asst t2+t3, results t2+t3]
    assert turn["role"] == "user"
    assert [b["tool_use_id"] for b in turn["content"]] == ["t2", "t3"]
    assert turn["content"][1]["content"].startswith("FAIL 3/5")


def test_tool_errors_are_fed_back_not_raised(tmp_path):
    _, tools, _ = setup(tmp_path)
    script = [Response(tool_calls=[ToolCall("e1", "read_file", {"path": "../../etc/passwd"}),
                                   ToolCall("e2", "edit_file", {"path": "spec_tokenbucket.py", "old_str": "a", "new_str": "b"}),
                                   ToolCall("e3", "nope", {})], stop_reason="tool_use"),
              text("ok")]
    res = run_agent(FakeClient(script), TASK, tools)
    blocks = res.messages[2]["content"]
    assert all(b["is_error"] for b in blocks)
    assert "escapes workspace" in blocks[0]["content"]
    assert "read-only" in blocks[1]["content"]
    assert "unknown tool" in blocks[2]["content"]


def test_no_gate_means_unverified_success(tmp_path):
    _, tools, _ = setup(tmp_path)
    res = run_agent(FakeClient([text("All done!")]), TASK, tools)
    assert res.exit_code is ExitCode.SUCCESS and "unverified" in res.reason


def test_completion_gate_rejects_premature_done_and_feeds_back_the_failure(tmp_path):
    ws, tools, _ = setup(tmp_path)
    fake = FakeClient(premature_script())
    res = run_agent(fake, TASK, tools, completion_gate=oracle_gate(ORACLE, ws))
    assert res.exit_code is ExitCode.SUCCESS
    pushback = fake.calls[2]["messages"][-1]["content"]
    assert pushback.startswith("Not done.") and "test_refill_never_exceeds_capacity" in pushback


def test_gate_block_cap_stops_a_model_that_keeps_claiming_done(tmp_path):
    ws, tools, _ = setup(tmp_path)
    fake = FakeClient(lambda m, k: text("Done."))
    res = run_agent(fake, TASK, tools, completion_gate=oracle_gate(ORACLE, ws), max_gate_blocks=8)
    assert res.exit_code is ExitCode.FAIL and "blocked 8x" in res.reason
    assert len(fake.calls) == 8


def test_blocked_reply_is_typed(tmp_path):
    _, tools, _ = setup(tmp_path)
    res = run_agent(FakeClient([text("BLOCKED: spec says both > and >=")]), TASK, tools)
    assert res.exit_code is ExitCode.BLOCKED


# ---- runaway FakeClients: the governors must trip ------------------------------------
def test_runaway_same_call_forever_trips_repetition(tmp_path):
    _, tools, _ = setup(tmp_path)
    fake = FakeClient(runaway_responder)
    res = run_agent(fake, TASK, tools, governor=Governor(Limits(max_iterations=1000)))
    assert res.exit_code is ExitCode.STALLED and "repetition" in res.reason
    assert len(fake.calls) == 3  # tripped on the 3rd identical call, not the 1000th


def test_oscillating_reads_trip_the_window_check(tmp_path):
    _, tools, _ = setup(tmp_path)
    fake = FakeClient(oscillating_responder)
    res = run_agent(fake, TASK, tools, governor=Governor(Limits(max_iterations=1000)))
    assert res.exit_code is ExitCode.STALLED and len(fake.calls) <= 6


def test_wandering_agent_is_stopped_by_the_dollar_budget(tmp_path):
    _, tools, _ = setup(tmp_path)
    fake = FakeClient(wandering_responder)  # 50k in / 2k out per call, never repeats
    res = run_agent(fake, TASK, tools, governor=Governor(Limits(max_iterations=1000, max_cost_usd=1.0,
                                                                 max_input_tokens=None, max_output_tokens=None)))
    assert res.exit_code is ExitCode.BUDGET and "cost" in res.reason
    assert len(fake.calls) == 6  # $0.18/call at placeholder prices: trips after crossing $1


def test_consecutive_tool_errors_trip_the_breaker(tmp_path):
    _, tools, _ = setup(tmp_path)
    bad = lambda m, k: Response(tool_calls=[ToolCall(f"x{len(m)}", "read_file", {"path": f"missing_{len(m)}.py"})],
                                stop_reason="tool_use")
    res = run_agent(FakeClient(bad), TASK, tools, governor=Governor(Limits(max_iterations=100)))
    assert res.exit_code is ExitCode.STALLED and "consecutive errors" in res.reason


def test_truncation_counts_toward_the_error_breaker(tmp_path):
    _, tools, _ = setup(tmp_path)
    trunc = lambda m, k: Response(text="Let me expl", stop_reason="max_tokens")
    res = run_agent(FakeClient(trunc), TASK, tools)
    assert res.exit_code is ExitCode.STALLED and res.iterations == 3


def test_trace_has_one_span_per_llm_and_tool_call(tmp_path):
    _, tools, _ = setup(tmp_path)
    path = tmp_path / "trace.jsonl"
    run_agent(FakeClient(fixing_script()), TASK, tools, tracer=Tracer(path))
    (spans,) = load_traces(path).values()
    names = [s["name"] for s in spans]
    assert names.count("llm_call") == 5 and names.count("tool_call") == 6
    root = next(s for s in spans if s["name"] == "agent_run")
    assert root["parent_id"] is None and root["attrs"]["exit_code"] == "SUCCESS"
    assert json.dumps(root["attrs"])  # serialisable
