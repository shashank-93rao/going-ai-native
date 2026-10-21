import json

from ainative_kit import FakeClient, Tracer, Usage, text
from otel_like import TracedClient, content_hash, redact, to_otel


def _llm_span(**attrs):
    base = {"model": "claude-sonnet-5-5", "input_tokens": 1500, "cache_read_tokens": 6000,
            "cache_write_tokens": 0, "output_tokens": 210, "stop_reason": "end_turn",
            "prompt_name": "alert-summarizer", "prompt_version": "v14",
            "messages": [{"role": "user", "content": "page from dana@example.com"}], "output": "ok"}
    base.update(attrs)
    return {"name": "llm_call", "trace_id": "t1", "span_id": "s2", "parent_id": "s1",
            "start": 100.0, "end": 101.5, "error": None, "attrs": base}


def test_chat_span_names_and_usage_math():
    o = to_otel(_llm_span())
    a = o["attributes"]
    assert o["name"] == "chat claude-sonnet-5-5" and o["kind"] == "CLIENT"
    assert a["gen_ai.operation.name"] == "chat"
    assert a["gen_ai.provider.name"] == "anthropic"
    # Anthropic input_tokens excludes cache; the convention's input_tokens includes it.
    assert a["gen_ai.usage.input_tokens"] == 7500
    assert a["gen_ai.usage.cache_read.input_tokens"] == 6000
    assert a["gen_ai.prompt.version"] == "v14"
    assert a["gen_ai.response.finish_reasons"] == ["end_turn"]
    assert o["end_time_unix_nano"] - o["start_time_unix_nano"] == 1_500_000_000


def test_content_is_opt_in_and_hashed_by_default():
    a = to_otel(_llm_span())["attributes"]
    assert "gen_ai.input.messages" not in a and "gen_ai.output.messages" not in a
    assert a["app.messages.sha256"] == content_hash([{"role": "user", "content": "page from dana@example.com"}])
    assert "dana@example.com" not in json.dumps(a)


def test_content_capture_is_redacted():
    a = to_otel(_llm_span(output="key sk-ant-api03-SECRETSECRET for ops@corp.io"), capture_content=True)["attributes"]
    assert a["gen_ai.output.messages"] == "key [REDACTED_API_KEY] for [REDACTED_EMAIL]"
    assert "[REDACTED_EMAIL]" in json.dumps(a["gen_ai.input.messages"])


def test_tool_and_agent_spans_and_errors():
    tool = {"name": "tool_call", "trace_id": "t1", "span_id": "s3", "parent_id": "s1", "start": 1, "end": 2,
            "error": "TimeoutError: kafka-admin did not answer in 5s", "attrs": {"tool_name": "describe_consumer_group",
            "tool_call_id": "toolu_1", "tool_input": {"group": "ledger"}}}
    o = to_otel(tool)
    assert o["name"] == "execute_tool describe_consumer_group"
    assert o["attributes"]["gen_ai.tool.name"] == "describe_consumer_group"
    assert o["attributes"]["error.type"] == "TimeoutError"  # low cardinality: no message
    assert o["status"]["code"] == "ERROR"
    agent = {"name": "agent_run", "trace_id": "t1", "span_id": "s1", "parent_id": None, "start": 0, "end": 3,
             "error": None, "attrs": {"agent_name": "triage", "conversation_id": "inc-1", "api_key": "x", "tenant": "acme"}}
    a = to_otel(agent)["attributes"]
    assert a["gen_ai.operation.name"] == "invoke_agent" and a["gen_ai.conversation.id"] == "inc-1"
    assert "app.api_key" not in a and a["app.tenant"] == "acme"


def test_redact_recurses():
    assert redact({"a": ["x@y.com", 3]}) == {"a": ["[REDACTED_EMAIL]", 3]}


def test_traced_client_emits_span_with_cache_fields():
    u = Usage(1200, 80)
    u.cache_read_input_tokens = 6000  # what the real SDK usage object carries
    tracer = Tracer()
    client = TracedClient(FakeClient([text("ok", usage=u)]), tracer, prompt_name="p", prompt_version="v2")
    client.complete([{"role": "user", "content": "hi"}], model="claude-haiku-5-5")
    (sp,) = tracer.spans
    o = to_otel(sp)["attributes"]
    assert o["gen_ai.usage.input_tokens"] == 7200
    assert o["gen_ai.request.model"] == "claude-haiku-5-5"
    assert o["gen_ai.prompt.name"] == "p"
