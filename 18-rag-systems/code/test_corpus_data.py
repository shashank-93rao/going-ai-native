"""The labels are data; test them like data. A bad label silently corrupts every metric."""
from chunking import Chunk, load_docs
from hybrid import can_read
from rag_eval import _norm, load_questions

DOCS = {d.id: d for d in load_docs()}
ROWS = load_questions()


def test_corpus_size_and_ids_unique():
    assert 40 <= len(DOCS) <= 60
    assert len({r["id"] for r in ROWS}) == len(ROWS)


def test_every_evidence_span_exists_verbatim_in_a_relevant_doc():
    for r in ROWS:
        for ev in r["evidence"]:
            assert any(_norm(ev) in _norm(DOCS[d].body) for d in r["relevant_docs"]), (r["id"], ev)


def test_answerable_rows_point_at_docs_the_asker_can_read():
    for r in ROWS:
        assert r["answerable"] == bool(r["relevant_docs"]), r["id"]
        for d in r["relevant_docs"]:
            probe = Chunk("x", d, 1, "", "", DOCS[d].acl)
            assert can_read(frozenset({r["team"]}))(probe), (r["id"], d)


def test_set_has_unanswerable_and_permission_dependent_rows():
    assert sum(not r["answerable"] for r in ROWS) >= 5
    by_q = {}
    for r in ROWS:
        by_q.setdefault(r["question"], []).append(r)
    # the same question asked by two teams with different correct outcomes
    assert any(len({x["answerable"] for x in rs}) == 2 or len({tuple(x["relevant_docs"]) for x in rs}) == 2
               for rs in by_q.values() if len(rs) > 1)
