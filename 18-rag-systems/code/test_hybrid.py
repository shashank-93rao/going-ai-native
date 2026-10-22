import json

import pytest
from hypothesis import given, settings, strategies as st

from ainative_kit import FakeClient, text
from chunking import chunk_corpus, load_docs
from embed import HashedNgramEmbedder
from hybrid import HybridRetriever, LLMReranker, can_read, fake_rerank_responder, rrf

TEAMS = ["payments", "platform", "data", "identity", "sre", "security"]


@pytest.fixture(scope="module")
def retriever():
    chunks = chunk_corpus(load_docs(), "heading")
    return HybridRetriever(chunks, HashedNgramEmbedder().fit([c.indexed_text for c in chunks]))


def test_rrf_formula_and_k60():
    fused = dict(rrf([["a", "b"], ["b", "c"]], k=60))
    assert fused["b"] == pytest.approx(1 / 62 + 1 / 61)
    assert fused["a"] == pytest.approx(1 / 61)
    assert list(dict(rrf([["a", "b"], ["b", "c"]]))) [0] == "b"  # agreement beats one first place


def test_hybrid_records_which_retriever_found_each_hit(retriever):
    hits = retriever.search("invoice consumer keeps rebalancing", frozenset({"payments"}), k=3)
    assert hits[0].chunk.doc_id == "rb-kafka-consumer-lag"
    assert all(h.sources for h in hits)


def test_restricted_doc_visible_only_to_its_teams(retriever):
    q = "signing key material nested under signer.material in debug logs"
    for team in TEAMS:
        docs = {h.chunk.doc_id for h in retriever.search(q, frozenset({team}), k=10)}
        assert ("pm-2026-022-signing-key-in-logs" in docs) == (team in ("identity", "security")), team


@settings(max_examples=40, deadline=None)
@given(query=st.text(alphabet="abcdefghijklmnopqrstuvwxyz -.", min_size=1, max_size=40),
       team=st.sampled_from(TEAMS), mode=st.sampled_from(["bm25", "dense", "hybrid"]))
def test_acl_never_leaks_for_any_query(retriever, query, team, mode):
    allow = can_read(frozenset({team}))
    assert all(allow(h.chunk) for h in retriever.search(query, frozenset({team}), k=10, mode=mode))


def test_llm_reranker_drops_unknown_ids_and_appends_missing(retriever):
    chunks = [h.chunk for h in retriever.search("kafka lag", frozenset({"payments"}), k=4)]
    ids = [c.id for c in chunks]
    fake = FakeClient([text(json.dumps({"ranking": [ids[2], "made-up#id", ids[0]]}))])
    assert LLMReranker(fake).rerank("kafka lag", chunks) == [ids[2], ids[0], ids[1], ids[3]]


def test_llm_reranker_fails_open_on_garbage(retriever):
    chunks = [h.chunk for h in retriever.search("kafka lag", frozenset({"payments"}), k=3)]
    assert LLMReranker(FakeClient([text("sure! here you go")])).rerank("q", chunks) == [c.id for c in chunks]


def test_fake_reranker_runs_through_the_pipeline(retriever):
    hits = retriever.search("which maxmemory-policy must idempotency-cache use", frozenset({"payments"}), k=3,
                            reranker=LLMReranker(FakeClient(fake_rerank_responder)))
    assert hits[0].chunk.doc_id == "rb-redis-evictions"
