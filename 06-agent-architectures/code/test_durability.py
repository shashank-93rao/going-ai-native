"""Event-sourced run log and double-texting simulator."""

import json

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from ainative_kit import FakeClient, text, tool
from double_texting import POLICIES, simulate, validate_transcript
from run_log import (DurableRun, EventLog, InDoubt, SimulatedCrash, TicketAPI, ToolDef, TICKET_SCHEMA, fold,
                     make_tools, scripted_model)

TASK = "Check notify-svc consumer lag and open a ticket if it is above 100k."


def crash_then_resume(tmp_path, point, honour_keys=True):
    api, log = TicketAPI(honour_keys=honour_keys), EventLog(tmp_path / "run.jsonl")
    client = scripted_model()
    with pytest.raises(SimulatedCrash):
        DurableRun(client, log, make_tools(api), run_id="r1", crash_at=point).start(TASK)
    answer = DurableRun(client, log, make_tools(api), run_id="r1").resume()
    return api, log, client, answer


def test_happy_path(tmp_path):
    api, log = TicketAPI(), EventLog(tmp_path / "run.jsonl")
    client = scripted_model()
    answer = DurableRun(client, log, make_tools(api), run_id="r1").start(TASK)
    assert answer.startswith("Opened OPS ticket") and len(api.tickets) == 1 and len(client.calls) == 3


@pytest.mark.parametrize("point", ["after_llm_response", "after_tool_intent", "after_side_effect"])
def test_crash_anywhere_resumes_with_exactly_one_ticket_and_no_resampling(tmp_path, point):
    api, log, client, answer = crash_then_resume(tmp_path, point)
    assert answer.startswith("Opened OPS ticket")
    assert len(api.tickets) == 1
    assert len(client.calls) == 3, "logged model responses are replayed, never re-requested"


def test_without_idempotency_the_crash_duplicates_the_side_effect(tmp_path):
    api, *_ = crash_then_resume(tmp_path, "after_side_effect", honour_keys=False)
    assert len(api.tickets) == 2                                    # the at-least-once trap


def test_non_idempotent_in_doubt_tool_stops_for_a_human(tmp_path):
    api, log = TicketAPI(), EventLog(tmp_path / "run.jsonl")
    tools = make_tools(api)
    tools["create_ticket"] = ToolDef(TICKET_SCHEMA, api.create, side_effecting=True, idempotent=False)
    with pytest.raises(SimulatedCrash):
        DurableRun(scripted_model(), log, tools, run_id="r1", crash_at="after_side_effect").start(TASK)
    with pytest.raises(InDoubt):
        DurableRun(scripted_model(), log, tools, run_id="r1").resume()


def test_idempotency_key_derives_from_logged_call(tmp_path):
    _, log, *_ = crash_then_resume(tmp_path, "after_side_effect")
    intents = [e for e in log.events() if e["type"] == "tool_intent"]
    assert [e["key"] for e in intents] == ["r1:toolu_02"]           # one intent, not re-logged on resume


def test_resume_of_finished_run_is_a_noop(tmp_path):
    api, log, client, answer = crash_then_resume(tmp_path, "after_tool_intent")
    again = DurableRun(client, log, make_tools(api), run_id="r1").resume()
    assert again == answer and len(api.tickets) == 1


def test_torn_tail_write_is_ignored(tmp_path):
    log = EventLog(tmp_path / "run.jsonl")
    log.append("run_started", run_id="r", task="t")
    with log.path.open("a") as f:
        f.write('{"seq": 1, "type": "llm_resp')                    # crash mid-write
    assert [e["type"] for e in log.events()] == ["run_started"]


def test_step_budget(tmp_path):
    looping = FakeClient(lambda m, kw: tool("get_consumer_lag", {"group": "g"}, id=f"t{len(m)}"))
    out = DurableRun(looping, EventLog(tmp_path / "l.jsonl"), make_tools(TicketAPI()), run_id="r",
                     max_steps=3).start("x")
    assert "budget" in out and len(looping.calls) == 3


def test_checkpoint_fold_equals_full_fold(tmp_path):
    api, log = TicketAPI(), EventLog(tmp_path / "run.jsonl")
    DurableRun(scripted_model(), log, make_tools(api), run_id="r1").start(TASK)
    evs = log.events()
    for i in range(1, len(evs) + 1):
        a, b = fold(evs[:i]), fold(evs[:i], use_checkpoint=False)
        assert json.dumps(a.messages) == json.dumps(b.messages) and a.step == b.step and a.finished == b.finished


# --------------------------------------------------------------------------- double texting

REFUND = (0, "please refund order 7731")


def correction(t):
    return (t, "sorry, refund order 7713 instead")


def test_reject_keeps_first_run_and_drops_correction():
    r = simulate("reject", [REFUND, correction(2)])
    assert [x.status for x in r.runs] == ["completed", "rejected"] and r.world == ["refund:7731"]


def test_enqueue_executes_stale_intent_too():
    r = simulate("enqueue", [REFUND, correction(2)])
    assert r.world == ["refund:7731", "refund:7713"] and not r.transcript_errors


def test_interrupt_early_prevents_wrong_refund_and_patches_dangling_tool_use():
    r = simulate("interrupt", [REFUND, correction(2)])
    assert r.world == ["refund:7713"] and not r.transcript_errors
    assert any("synthetic 'cancelled'" in w for w in r.warnings)


def test_interrupt_without_patch_produces_invalid_transcript():
    r = simulate("interrupt", [REFUND, correction(2)], patch_dangling=False)
    assert r.transcript_errors


def test_interrupt_after_side_effect_tells_the_model_it_ran():
    r = simulate("interrupt", [REFUND, correction(4)])
    assert any("executed-result-not-observed" in w for w in r.warnings)


def test_rollback_reverts_thread_but_not_the_world():
    r = simulate("rollback", [REFUND, correction(4)])
    assert "refund:7731" in r.world
    assert any("compensation needed" in w for w in r.warnings)
    assert not any("r1" in m for m in r.messages), "rollback removes the original input as well"


def test_concurrent_runs_corrupt_transcript_and_occ_detects_but_does_not_decide():
    naive = simulate("concurrent", [REFUND, correction(2)])
    assert naive.world == ["refund:7731", "refund:7713"] and len(naive.transcript_errors) >= 2
    r = simulate("concurrent", [REFUND, correction(2)], occ=True)
    assert [x.status for x in r.runs] == ["aborted_conflict", "completed"]
    assert r.world == ["refund:7713"]
    # OCC stopped the stale run, but its partial writes (a dangling tool_use) are still in the
    # thread. Detection is not a policy: you still need interrupt-style cleanup for the loser.
    assert len(r.transcript_errors) == 1


def test_adaptive_rolls_back_only_before_side_effects():
    early = simulate("adaptive", [REFUND, correction(2)])
    late = simulate("adaptive", [REFUND, correction(4)])
    assert early.runs[0].status == "rolled_back" and early.world == ["refund:7713"]
    assert late.runs[0].status == "interrupted" and not any("compensation" in w for w in late.warnings)


def test_validate_transcript():
    assert validate_transcript(["user:r1:x", "tool_use:r1:a", "tool_result:r1:a", "assistant:r1:reply"]) == []
    assert validate_transcript(["tool_use:r1:a", "user:r2:y"])


@settings(max_examples=60, deadline=None)
@given(policy=st.sampled_from([p for p in POLICIES if p != "concurrent"]),
       times=st.lists(st.integers(min_value=0, max_value=12), min_size=1, max_size=4))
def test_serializing_policies_never_corrupt_the_transcript(policy, times):
    """Property: every policy except 'concurrent' keeps the transcript API-valid for any arrival pattern."""
    arrivals = [(t, f"refund order {7000 + i}") for i, t in enumerate(times)]
    r = simulate(policy, arrivals)
    assert r.transcript_errors == []
    assert all(x.status != "running" for x in r.runs)
