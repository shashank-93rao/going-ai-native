from ainative_kit import FakeClient, Tracer, text, tool

import ops_tools
from agent_loop import TASK, actionable_tools, demo, opaque_tools, run_agent, scripted_oncall_model


def test_actionable_errors_let_the_model_self_correct():
    r = run_agent(FakeClient(scripted_oncall_model), TASK, tools=ops_tools.TOOL_SCHEMAS, call_tool=actionable_tools)
    assert r.stop_reason == "answered"
    assert [t["is_error"] for t in r.tool_log] == [True, False, False]
    assert r.tool_log[1]["input"] == {"group": "ledger-writer-v2"}
    assert "partition 3" in r.final_text


def test_opaque_errors_burn_the_error_budget():
    r = run_agent(FakeClient(scripted_oncall_model), TASK, tools=ops_tools.TOOL_SCHEMAS, call_tool=opaque_tools)
    assert r.stop_reason == "too_many_errors" and len(r.tool_log) == 3
    assert all(t["is_error"] for t in r.tool_log)


def test_tool_results_carry_is_error_and_ids():
    fake = FakeClient(scripted_oncall_model)
    run_agent(fake, TASK, tools=ops_tools.TOOL_SCHEMAS, call_tool=actionable_tools)
    second = fake.calls[1]["messages"][-1]["content"][0]
    assert second["type"] == "tool_result" and second["tool_use_id"] == "toolu_1" and second["is_error"] is True
    assert fake.calls[0]["tools"] == ops_tools.TOOL_SCHEMAS


def test_max_turns_governor():
    looping = FakeClient(lambda m, k: tool("deploys_list_services", {}))
    r = run_agent(looping, "x", tools=ops_tools.TOOL_SCHEMAS, call_tool=actionable_tools, max_turns=4)
    assert r.stop_reason == "max_turns" and len(r.tool_log) == 4


def test_tracer_records_tool_spans():
    tr = Tracer()
    run_agent(FakeClient([tool("deploys_list_services", {}), text("ok")]), "x",
              tools=ops_tools.TOOL_SCHEMAS, call_tool=actionable_tools, tracer=tr)
    names = [s.name for s in tr.spans]
    assert names.count("llm_call") == 2 and "tool_call" in names and names[-1] == "agent_run"


def test_demo_both_paths():
    d = demo()
    assert d["actionable"].stop_reason == "answered" and d["opaque"].stop_reason == "too_many_errors"
