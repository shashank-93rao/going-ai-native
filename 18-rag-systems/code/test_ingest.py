"""Ingestion invariants as properties: replays, reordering, deletes, ACLs, migration."""
from dataclasses import replace

import pytest
from hypothesis import given, settings, strategies as st

from chunking import load_docs
from hybrid import can_read
from ingest import DocIndex, Event, Migration, StaleModel, fitted_embedder, initial_events
from rag_eval import load_questions

DOCS = load_docs()[:12]  # small slice keeps property tests fast
EMB = fitted_embedder(load_docs())


def fresh() -> DocIndex:
    return DocIndex(EMB)


def history():
    """v1..v2 upserts for some docs, a delete, and an ACL change."""
    ev = initial_events(DOCS)
    d0, d1, d2 = DOCS[0], DOCS[1], DOCS[2]
    ev.append(Event(100, "upsert", d0.id, d0.version + 1, replace(d0, version=d0.version + 1, body=d0.body + "\n\nEdited.")))
    ev.append(Event(101, "delete", d1.id, d1.version + 1))
    ev.append(Event(102, "upsert", d2.id, d2.version + 1, replace(d2, version=d2.version + 1, acl=frozenset({"data"}))))
    return ev


def apply_all(events) -> DocIndex:
    idx = fresh()
    for e in events:
        idx.apply(e)
    return idx


EXPECTED = apply_all(history()).fingerprint()


@settings(max_examples=25, deadline=None)
@given(st.permutations(history()), st.lists(st.integers(0, len(history()) - 1), max_size=10))
def test_any_order_with_duplicates_converges_to_the_same_state(order, dup_idx):
    events = list(order) + [history()[i] for i in dup_idx]
    assert apply_all(events).fingerprint() == EXPECTED


def test_replay_is_a_noop():
    idx = apply_all(history())
    outcomes = [idx.apply(e) for e in history()]
    assert set(outcomes) == {"stale"} and idx.fingerprint() == EXPECTED


def test_deleted_doc_never_resurfaces_even_after_late_old_upserts():
    d = DOCS[1]
    idx = apply_all(history())
    for e in initial_events(DOCS):  # a lagging consumer replays v1 after the delete
        idx.apply(e)
    hits = idx.search(d.title, frozenset({"platform", "payments", "data", "identity", "sre", "security"}), k=20)
    assert d.id not in {c.doc_id for c in hits} and d.id not in idx.doc_chunks


def test_delete_is_complete_only_after_compaction_and_cache_purge():
    d = DOCS[1]
    idx = apply_all(initial_events(DOCS))
    texts = [idx.chunks[c].indexed_text for c in idx.doc_chunks[d.id]]
    idx.apply(Event(200, "delete", d.id, d.version + 1))
    assert idx.physically_present(d.id)  # tombstoned, bytes still on disk
    idx.compact()
    assert not idx.physically_present(d.id)
    hashes = {idx.emb.content_hash(t) for t in texts}
    assert not any(k[1] in hashes for k in idx.emb.cache)


def test_acl_only_change_reuses_vectors_and_takes_effect():
    d = DOCS[2]
    idx = apply_all(initial_events(DOCS))
    misses = idx.emb.misses
    idx.apply(Event(300, "upsert", d.id, d.version + 1, replace(d, version=d.version + 1, acl=frozenset({"data"}))))
    assert idx.emb.misses == misses
    hits = idx.search(d.title, frozenset({"payments"}), k=20)
    assert d.id not in {c.doc_id for c in hits}


@pytest.fixture(scope="module")
def full_index():
    idx = DocIndex(EMB)
    for e in initial_events(load_docs()):
        idx.apply(e)
    return idx


@pytest.mark.parametrize("team", ["payments", "platform", "data", "identity", "sre"])
def test_acl_filter_never_leaks_on_the_labeled_questions(full_index, team):
    allow = can_read(frozenset({team}))
    for r in load_questions():
        assert all(allow(c) for c in full_index.search(r["question"], frozenset({team}), k=10))


def test_querying_with_a_different_model_is_refused(full_index):
    with pytest.raises(StaleModel):
        full_index.search("kafka", frozenset({"payments"}), embedder=fitted_embedder(load_docs(), 128, "other"))


def test_backfill_does_not_overwrite_newer_dual_written_version():
    live = apply_all(initial_events(DOCS))
    m = Migration(live, fitted_embedder(load_docs(), 256, "v2"))
    d = DOCS[0]
    newer = replace(d, version=d.version + 1, body=d.body + "\n\nNew step.")
    m.on_event(Event(400, "upsert", d.id, newer.version, newer))  # dual-write lands first
    m.backfill(DOCS, {})  # snapshot taken before the edit
    assert m.shadow.hwm[d.id] == newer.version
    assert {c.version for c in m.shadow.chunks.values() if c.doc_id == d.id} == {newer.version}


def test_shadow_gate_cuts_over_good_model_and_aborts_bad_one(full_index):
    rows = [r for r in load_questions() if r["answerable"]][:15]
    docs = load_docs()
    good = Migration(full_index, fitted_embedder(docs, 256, "v2"))
    good.backfill(docs, {})
    rep = good.shadow_compare(rows)
    assert rep.passed and good.cutover(rep) is good.shadow
    bad = Migration(full_index, fitted_embedder(docs, 8, "tiny"))
    bad.backfill(docs, {})
    rep = bad.shadow_compare(rows)
    assert not rep.passed and bad.cutover(rep) is full_index and bad.phase == "aborted"
