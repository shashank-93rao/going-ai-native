from ainative_kit import FakeClient, RecordingClient, ReplayClient, Tracer, load_traces, text, tool


def test_fake_client_scripted_and_records_calls():
    c = FakeClient([tool("search", {"q": "x"}), text("done")])
    r1 = c.complete([{"role": "user", "content": "hi"}], system="s")
    assert r1.stop_reason == "tool_use" and r1.tool_calls[0].name == "search"
    assert c.complete([{"role": "user", "content": "hi"}]).text == "done"
    assert c.calls[0]["system"] == "s"


def test_record_then_replay(tmp_path):
    cassette = tmp_path / "c.jsonl"
    rec = RecordingClient(FakeClient([text("A")]), cassette)
    msgs = [{"role": "user", "content": "q"}]
    assert rec.complete(msgs).text == "A"
    assert ReplayClient(cassette).complete(msgs).text == "A"


def test_tracer_nests_spans(tmp_path):
    t = Tracer(tmp_path / "t.jsonl")
    with t.span("run") as outer:
        with t.span("llm", tokens=3):
            pass
    traces = load_traces(tmp_path / "t.jsonl")
    (spans,) = traces.values()
    child = next(s for s in spans if s["name"] == "llm")
    assert child["parent_id"] == outer.span_id


def test_fake_client_records_tool_choice_and_effort_only_when_set():
    c = FakeClient([text("a"), text("b")])
    c.complete([{"role": "user", "content": "x"}])
    c.complete([{"role": "user", "content": "x"}], tool_choice={"type": "tool", "name": "v"}, effort="high")
    assert "effort" not in c.calls[0] and "tool_choice" not in c.calls[0]
    assert c.calls[1]["effort"] == "high" and c.calls[1]["tool_choice"]["name"] == "v"
