import pytest

from ainative_kit import FakeClient, Response, ToolCall, Tracer, text
from agentic_rag import Q39, Limits, fake_agent_responder, run, scripted_multi_hop
from rag_pipeline import NOT_COVERED, build_default


@pytest.fixture(scope="module")
def r():
    return build_default()


def search(q, i=0, **extra):
    return Response(tool_calls=[ToolCall(f"t{i}", "search_docs", {"query": q, **extra})], stop_reason="tool_use")


def test_multi_hop_finds_what_single_shot_missed(r):
    single = [h.chunk.id for h in r.search(Q39, frozenset({"payments"}), k=5)]
    assert "adr-012-idempotency-keys#decision" not in single
    tracer = Tracer()
    out = run(FakeClient(scripted_multi_hop()), r, Q39, frozenset({"payments"}), tracer=tracer)
    assert out.exit == "ANSWERED" and "adr-012-idempotency-keys#decision" in out.seen
    assert [s.name for s in tracer.spans].count("llm_call") == 3


def test_repeated_query_trips_stalled(r):
    out = run(FakeClient([search("kafka lag", i) for i in range(5)]), r, "kafka lag?", frozenset({"payments"}))
    assert out.exit == "STALLED" and out.steps == 2


def test_search_cap_trips_budget(r):
    qs = ["kafka", "redis", "postgres", "envoy", "dns", "tls"]
    out = run(FakeClient([search(q, i) for i, q in enumerate(qs)]), r, "x", frozenset({"platform"}),
              Limits(max_steps=10, max_searches=3, no_new_evidence=9))
    assert out.exit == "BUDGET" and len(out.searches) == 3 and out.answer == NOT_COVERED


def test_ungrounded_final_answer_becomes_abstention(r):
    script = [search("redis eviction policy"), text("Use `allkeys-random`. [rb-redis-evictions#diagnosis]")]
    out = run(FakeClient(script), r, "which redis policy", frozenset({"payments"}))
    assert out.exit == "UNGROUNDED" and out.answer == NOT_COVERED


def test_model_cannot_widen_its_own_permissions(r):
    script = [search("signing key material signer.material debug logs", team="identity"), text(NOT_COVERED)]
    out = run(FakeClient(script), r, "how did key material get into logs", frozenset({"platform"}))
    assert not any(c.doc_id == "pm-2026-022-signing-key-in-logs" for c in out.seen.values())
    assert out.ignored_args == ["team"]  # surfaced for alerting


def test_policy_fake_abstains_on_unanswerable(r):
    out = run(FakeClient(fake_agent_responder()), r, "what is the on-call compensation rate for weekend pages",
              frozenset({"platform"}))
    assert out.exit == "ABSTAINED"
