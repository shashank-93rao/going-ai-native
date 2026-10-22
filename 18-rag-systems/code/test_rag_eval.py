import pytest

from ainative_kit import FakeClient, text
from chunking import Chunk
from rag_eval import (Answer, abstention_report, evidence_at_k, grounding_check, load_questions, mrr, ndcg_at_k,
                      paired_bootstrap, per_question, recall_at_k, retriever_fn, score_answer)
from rag_pipeline import NOT_COVERED, answer, build_default, fake_generator_responder

C = Chunk("rb-redis-evictions#diagnosis", "rb-redis-evictions", 2, "diagnosis",
          "Run `redis-cli -h idempotency-cache info memory` and check `maxmemory_policy`. "
          "The policy must be `noeviction` or `volatile-ttl`.", frozenset({"eng"}))


def test_rank_metrics():
    ranked = ["x", "a", "y", "b"]
    assert recall_at_k(ranked, {"a", "b"}, 2) == 0.5
    assert mrr(ranked, {"a", "b"}) == 0.5
    assert ndcg_at_k(["a", "b"], {"a", "b"}, 5) == pytest.approx(1.0)
    assert ndcg_at_k(ranked, {"a", "b"}, 5) < 1.0


def test_evidence_at_k_needs_the_span_in_one_shown_chunk():
    assert evidence_at_k([C], ["must be `noeviction` or `volatile-ttl`"], 5) == 1.0
    assert evidence_at_k([C], ["allkeys-lru is fine"], 5) == 0.0


def test_grounding_accepts_a_supported_cited_sentence():
    g = grounding_check("The policy must be `noeviction` or `volatile-ttl`. [rb-redis-evictions#diagnosis]", [C])
    assert g.ok and g.citation_precision == 1.0


@pytest.mark.parametrize("bad, field", [
    ("Use `allkeys-lru` for the cache. [rb-redis-evictions#diagnosis]", "unsupported"),
    ("The policy must be noeviction. [rb-redis-evictions#mitigation]", "unknown"),
    ("The policy must be `noeviction`.", "uncited"),
])
def test_grounding_rejects(bad, field):
    g = grounding_check(bad, [C])
    assert not g.ok and getattr(g, field)


def test_abstention_scoring_counts_answering_the_unanswerable_as_wrong():
    rows = [{"id": "a", "answerable": True, "relevant_docs": ["rb-redis-evictions"]},
            {"id": "u", "answerable": False, "relevant_docs": []}]
    good = Answer("q", "The policy must be `noeviction` or `volatile-ttl`. [rb-redis-evictions#diagnosis]",
                  [type("H", (), {"chunk": C})()], False, ["rb-redis-evictions#diagnosis"])
    assert score_answer(rows[0], good) == "correct"
    assert score_answer(rows[1], good) == "wrong"
    assert score_answer(rows[1], Answer("q", NOT_COVERED, [], True)) == "correct"
    rep = abstention_report({"a": "abstain", "u": "correct"}, rows)
    assert rep["answerable_abstain"] == 1.0 and rep["unanswerable_abstain"] == 1.0


def test_paired_bootstrap_ci_contains_zero_for_identical_systems():
    d, lo, hi = paired_bootstrap([1, 0, 1, 1], [1, 0, 1, 1])
    assert d == lo == hi == 0.0
    d, lo, hi = paired_bootstrap([0] * 20, [1] * 20)
    assert lo > 0.9


def test_whole_doc_parents_find_all_evidence_but_cost_more_words():
    rows = load_questions()
    small = per_question(retriever_fn("heading", "hybrid"), rows)
    big = per_question(retriever_fn("parent-child-doc", "hybrid"), rows)
    ev = lambda pq: sum(v["evidence"] for v in pq.values()) / len(pq)  # noqa: E731
    words = lambda pq: sum(v["words"] for v in pq.values()) / len(pq)  # noqa: E731
    assert ev(big) > ev(small) and words(big) > 2 * words(small)


ROW_Q06 = {"id": "q06", "answerable": True, "relevant_docs": ["rb-redis-evictions"]}
Q06 = "which maxmemory-policy must idempotency-cache use"


def test_pipeline_with_lying_generator_fails_grounding():
    lie = FakeClient([text("Set maxmemory-policy to `allkeys-random`. [rb-redis-evictions#diagnosis]")])
    ans = answer(lie, build_default(), Q06, frozenset({"payments"}))
    assert score_answer(ROW_Q06, ans) == "wrong"


def test_lexical_grounding_is_fooled_by_a_negation_flip():
    """Characterization test: the runbook says `allkeys-lru` is WRONG. An answer
    recommending it reuses the chunk's own words, so term coverage and verbatim
    spans both pass. Catching this needs an entailment check or a calibrated
    judge (Module 11). If you add one, flip this assertion."""
    lie = FakeClient([text("Set maxmemory-policy to `allkeys-lru`. [rb-redis-evictions#diagnosis]")])
    ans = answer(lie, build_default(), Q06, frozenset({"payments"}))
    assert score_answer(ROW_Q06, ans) == "correct"


def test_extractive_fake_answers_and_abstains():
    r = build_default()
    client = FakeClient(fake_generator_responder(3))
    ok = answer(client, r, "which maxmemory-policy must idempotency-cache use", frozenset({"payments"}))
    assert not ok.abstained and grounding_check(ok.text, [h.chunk for h in ok.hits]).ok
    no = answer(client, r, "what is the on-call compensation rate for weekend pages", frozenset({"platform"}))
    assert no.abstained
