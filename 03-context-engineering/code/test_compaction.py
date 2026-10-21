from ainative_kit import FakeClient, text
from compaction import (
    PLACEHOLDER, EventLog, clear_tool_results, compact, demo_history, lossy_fake_summarizer, safe_split,
)

CRITICAL = ["INC-7731", "CONSTRAINT: do not reset offsets.", "CONSTRAINT: no deploys before 09:00 UTC.",
            "DECISION: raise max.poll.interval.ms to 300000, keep batch size. Commit it.", "commit 3f9c2ab"]


def compacted_text(result) -> str:
    c = result.messages[0]["content"]
    return c if isinstance(c, str) else c[0]["text"]


def test_critical_facts_survive_a_lossy_summarizer():
    # The fake drops every CONSTRAINT line, as a careless model would.
    result = compact(demo_history(), lossy_fake_summarizer(lambda ln: "CONSTRAINT" in ln), keep_last=3)
    body = compacted_text(result)
    for fact in CRITICAL:
        assert fact in body, fact
    assert "CONSTRAINT: do not reset offsets." in result.missing_from_summary


def test_good_summarizer_needs_no_restoration():
    perfect = FakeClient(lambda msgs, kw: text("\n".join(f"- {f}" for f in CRITICAL + ["deploy/invoice-consumer/values.yaml"])))
    result = compact(demo_history(), perfect, keep_last=3)
    assert result.missing_from_summary == []
    assert "restored by harness" not in compacted_text(result)


def test_summarizer_gets_instructions_and_history():
    fake = lossy_fake_summarizer(lambda ln: False)
    compact(demo_history(), fake, keep_last=3)
    call = fake.calls[0]
    assert "decisions made" in call["system"]
    assert "INC-7731" in call["messages"][0]["content"]


def test_tail_is_verbatim_and_starts_with_plain_user_turn():
    hist = demo_history()
    result = compact(hist, lossy_fake_summarizer(lambda ln: False), keep_last=3)
    assert result.messages[1:] == hist[-2:]
    assert result.messages[0]["role"] == "user"
    assert result.messages[0]["content"].endswith(hist[-3]["content"])


def test_split_never_orphans_a_tool_result():
    hist = demo_history()
    # keep_last=7 would start the tail at index 2, a tool_result; must move back.
    i = safe_split(hist, keep_last=7)
    assert hist[i]["role"] == "user" and isinstance(hist[i]["content"], str)
    assert i <= 2


def test_evicted_turns_land_in_queryable_log():
    log = EventLog()
    result = compact(demo_history(), lossy_fake_summarizer(lambda ln: True), keep_last=3, log=log)
    assert result.log_range == (0, result.evicted)
    assert log.grep(r"Revoking previously assigned")  # raw tool output still recoverable
    assert "event log entries 0.." in compacted_text(result)


def test_clear_tool_results_keeps_newest():
    msgs = []
    for n in range(5):
        msgs.append({"role": "assistant", "content": [{"type": "tool_use", "id": f"t{n}", "name": "get_logs", "input": {}}]})
        msgs.append({"role": "user", "content": [{"type": "tool_result", "tool_use_id": f"t{n}", "content": f"big output {n}"}]})
    out, n_cleared = clear_tool_results(msgs, keep_last=2)
    results = [m["content"][0]["content"] for m in out if m["role"] == "user"]
    assert n_cleared == 3
    assert results[:3] == [PLACEHOLDER] * 3 and results[3:] == ["big output 3", "big output 4"]
    assert msgs[1]["content"][0]["content"] == "big output 0"  # input not mutated
