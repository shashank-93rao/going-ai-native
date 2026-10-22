"""Ingestion as a CDC consumer: idempotent upserts, tombstones, compaction, and
a re-embedding migration with dual-write, backfill, shadow reads and cutover.

The rules, each enforced in `DocIndex.apply` and pinned by tests:
  1. Every event carries (doc_id, version). Apply only if version > the doc's
     high-water mark. Replays, duplicates and out-of-order delivery are no-ops.
  2. A delete is a tombstone with a version. An older upsert arriving after it
     is stale, so a deleted doc can never resurface.
  3. Upserts are make-before-break: new chunk vectors are added before the
     old ones are tombstoned, so a reader never sees the doc vanish.
  4. Vectors are content-addressed: an ACL-only change re-uses cached vectors.
  5. Deletion is not done until compaction: a tombstoned HNSW node still holds
     the vector bytes, and the embedding cache holds another copy.
  6. Every vector is tagged with its embedding model id; querying with another
     model's vectors is refused (embedding drift is a type error, not a vibe).

    PYTHONPATH=shared .venv/bin/python 18-rag-systems/code/ingest.py
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from typing import Callable

from chunking import Chunk, Doc, heading_chunks, load_docs
from embed import CachingEmbedder, Embedder, HashedNgramEmbedder
from hnsw_lite import HNSW
from hybrid import can_read


@dataclass(frozen=True)
class Event:
    seq: int  # CDC log offset; ordering is per partition, not global
    op: str  # "upsert" | "delete"
    doc_id: str
    version: int
    doc: Doc | None = None
    ts: float = 0.0  # source commit time, for staleness


class StaleModel(Exception):
    """Query embedder does not match the index's embedding model."""


class DocIndex:
    """One index generation: one embedding model, one vector index."""

    def __init__(self, embedder: Embedder, chunker: Callable[[Doc], list[Chunk]] = heading_chunks,
                 compact_ratio: float = 0.3):
        self.emb = embedder if isinstance(embedder, CachingEmbedder) else CachingEmbedder(embedder)
        self.model_id = self.emb.model_id
        self.chunker, self.compact_ratio = chunker, compact_ratio
        self.hwm: dict[str, int] = {}  # doc_id -> highest version seen (upsert or delete)
        self.tombstones: dict[str, int] = {}
        self.chunks: dict[str, Chunk] = {}  # live chunk id -> chunk
        self.doc_chunks: dict[str, list[str]] = {}
        self.vkey: dict[str, str] = {}  # live chunk id -> vector key in the ANN index
        self.vindex = HNSW(M=8, ef_construction=48)
        self.lag: list[float] = []  # indexed_at - source ts, per applied event
        self.stats = {"applied": 0, "stale": 0, "compactions": 0}

    # --- writes ------------------------------------------------------------------
    def apply(self, e: Event, now: float | None = None) -> str:
        if e.version <= self.hwm.get(e.doc_id, 0):
            self.stats["stale"] += 1
            return "stale"
        self.hwm[e.doc_id] = e.version
        if e.op == "upsert":
            assert e.doc is not None and e.doc.version == e.version
            self.tombstones.pop(e.doc_id, None)
            self._upsert(e.doc)
        elif e.op == "delete":
            self.tombstones[e.doc_id] = e.version
            self._remove(e.doc_id, forget=True)
        else:
            raise ValueError(e.op)
        self.stats["applied"] += 1
        self.lag.append((now if now is not None else e.ts) - e.ts)
        self._maybe_compact()
        return "applied"

    def _upsert(self, doc: Doc) -> None:
        new = self.chunker(doc)
        vecs = self.emb.embed([c.indexed_text for c in new], "document")
        old = self.doc_chunks.get(doc.id, [])
        old_keys = [self.vkey[cid] for cid in old]
        for c, v in zip(new, vecs):  # make ...
            key = f"{c.id}@v{doc.version}"
            self.vindex.add(key, v, c)
            self.chunks[c.id], self.vkey[c.id] = c, key
        for key in old_keys:  # ... before break
            self.vindex.mark_deleted(key)
        for cid in set(old) - {c.id for c in new}:  # sections that disappeared
            self.chunks.pop(cid, None)
            self.vkey.pop(cid, None)
        self.doc_chunks[doc.id] = [c.id for c in new]

    def _remove(self, doc_id: str, forget: bool) -> None:
        for cid in self.doc_chunks.pop(doc_id, []):
            self.vindex.mark_deleted(self.vkey.pop(cid))
            chunk = self.chunks.pop(cid)
            if forget:
                self.emb.forget(chunk.indexed_text)  # the cache is a copy of the data too

    def _maybe_compact(self) -> None:
        total = len(self.vindex.vecs)
        if total and len(self.vindex.deleted) / total > self.compact_ratio:
            self.compact()

    def compact(self) -> None:
        """Rebuild without tombstones. Until this runs, deleted text is still on disk."""
        self.vindex = self.vindex.rebuild()
        self.stats["compactions"] += 1

    # --- reads -------------------------------------------------------------------
    def search(self, query: str, teams: frozenset[str], k: int = 5, embedder: Embedder | None = None) -> list[Chunk]:
        emb = embedder or self.emb
        if emb.model_id != self.model_id:
            raise StaleModel(f"query model {emb.model_id} != index model {self.model_id}")
        allow = can_read(teams)
        qv = emb.embed([query], "query")[0]
        return [self.vindex.meta[key] for key, _ in self.vindex.search(qv, k, ef_search=64, filter=allow)]

    # --- consistency ---------------------------------------------------------------
    def fingerprint(self) -> str:
        """Order-independent digest of live state: equal digests, equal indexes."""
        rows = sorted((cid, c.version, sorted(c.acl), hashlib.sha256(c.indexed_text.encode()).hexdigest()[:12])
                      for cid, c in self.chunks.items())
        return hashlib.sha256(json.dumps([rows, sorted(self.tombstones.items())]).encode()).hexdigest()[:16]

    def physically_present(self, doc_id: str) -> list[str]:
        """Vector keys for a doc still in storage (tombstoned or not)."""
        return [k for k in self.vindex.vecs if k.startswith(f"{doc_id}#")]

    def reconcile(self, source_versions: dict[str, int]) -> dict[str, list[str]]:
        """Anti-entropy against the source of truth: what is missing, stale, or extra."""
        live = {d: v for d, v in self.hwm.items() if d not in self.tombstones}
        return {
            "missing": sorted(d for d in source_versions if d not in live),
            "stale": sorted(d for d, v in source_versions.items() if d in live and live[d] < v),
            "extra": sorted(d for d in live if d not in source_versions),
        }


# --- re-embedding migration --------------------------------------------------------

@dataclass
class ShadowReport:
    queries: int
    mean_overlap: float  # Jaccard of top-k doc ids, old vs new
    old_recall: float
    new_recall: float
    passed: bool
    notes: list[str] = field(default_factory=list)


class Migration:
    """dual_write -> backfill -> shadow compare -> cutover (or abort).

    Like an online schema migration: new writes go to both generations from the
    start, the backfill copies history, and version checks make the two safe to
    interleave in any order."""

    def __init__(self, live: DocIndex, new_embedder: Embedder):
        self.live, self.shadow = live, DocIndex(new_embedder, live.chunker)
        self.phase = "dual_write"

    def on_event(self, e: Event) -> None:
        self.live.apply(e)
        self.shadow.apply(e)

    def backfill(self, snapshot: list[Doc], deleted: dict[str, int]) -> int:
        """Copy a snapshot. Rows the dual-write already advanced come back 'stale'."""
        applied = 0
        for d in snapshot:
            applied += self.shadow.apply(Event(-1, "upsert", d.id, d.version, d)) == "applied"
        for doc_id, v in deleted.items():
            applied += self.shadow.apply(Event(-1, "delete", doc_id, v)) == "applied"
        self.phase = "shadow"
        return applied

    def shadow_compare(self, rows: list[dict], k: int = 5, max_recall_drop: float = 0.02) -> ShadowReport:
        overlaps, old_hits, new_hits, n_lab = [], 0, 0, 0
        for r in rows:
            teams = frozenset({r["team"]})
            old = {c.doc_id for c in self.live.search(r["question"], teams, k)}
            new = {c.doc_id for c in self.shadow.search(r["question"], teams, k)}
            overlaps.append(len(old & new) / len(old | new) if old | new else 1.0)
            if r.get("relevant_docs"):
                n_lab += 1
                old_hits += bool(old & set(r["relevant_docs"]))
                new_hits += bool(new & set(r["relevant_docs"]))
        o, n = old_hits / max(n_lab, 1), new_hits / max(n_lab, 1)
        live_versions = {d: v for d, v in self.live.hwm.items() if d not in self.live.tombstones}
        diff = self.shadow.reconcile(live_versions)
        notes = [f"{k}: {v}" for k, v in diff.items() if v]
        if self.shadow.tombstones != self.live.tombstones:
            notes.append("tombstones differ")
        passed = n >= o - max_recall_drop and not notes
        return ShadowReport(len(rows), sum(overlaps) / len(overlaps), o, n, passed, notes)

    def cutover(self, report: ShadowReport) -> DocIndex:
        if not report.passed:
            self.phase = "aborted"
            return self.live  # keep serving the old generation; shadow can be dropped
        self.phase = "cut_over"
        self.live, old = self.shadow, self.live
        self.previous = old  # keep for fast rollback until the new one has soaked
        return self.live


def initial_events(docs: list[Doc], t0: float = 0.0) -> list[Event]:
    return [Event(i, "upsert", d.id, d.version, d, t0 + i) for i, d in enumerate(docs)]


def fitted_embedder(docs: list[Doc], dim: int = 512, name: str = "hashgram") -> HashedNgramEmbedder:
    return HashedNgramEmbedder(dim=dim, name=name).fit([c.indexed_text for d in docs for c in heading_chunks(d)])


if __name__ == "__main__":
    from rag_eval import load_questions

    docs = load_docs()
    source = {d.id: d for d in docs}  # the source of truth the CDC stream describes
    idx = DocIndex(fitted_embedder(docs))
    log = initial_events(docs)
    for e in log:
        idx.apply(e, now=e.ts + 2.0)
    print(f"ingested {idx.stats['applied']} docs, {len(idx.chunks)} chunks, fingerprint {idx.fingerprint()}")
    before = idx.fingerprint()
    replay = [idx.apply(e) for e in log]
    print(f"replay whole log: applied={replay.count('applied')} stale={replay.count('stale')} "
          f"fingerprint unchanged={idx.fingerprint() == before}")

    d = source["pm-2026-031-flag-misconfig"]
    source[d.id] = replace(d, acl=frozenset({"platform"}), version=d.version + 1)
    misses = idx.emb.misses
    idx.apply(Event(100, "upsert", d.id, d.version + 1, source[d.id]))
    print("ACL-only change: chunks re-embedded =", idx.emb.misses - misses)

    gone = "pm-2026-040-log-flood-disk"
    del source[gone]
    idx.apply(Event(101, "delete", gone, 2))
    hits = idx.search("log flood filled node disks", frozenset({"platform"}), 10)
    print(f"after delete: searchable={any(c.doc_id == gone for c in hits)} "
          f"vectors still on disk={len(idx.physically_present(gone))}")
    idx.compact()
    print("after compaction: vectors on disk =", len(idx.physically_present(gone)))
    print("late replay of the v1 upsert ->", idx.apply(next(e for e in log if e.doc_id == gone)))
    print("reconcile vs source:", idx.reconcile({k: v.version for k, v in source.items()}))

    rows = load_questions()
    for label, emb in (("hashgram d=256", fitted_embedder(docs, 256, "hashgram-v2")),
                       ("hashgram d=16", fitted_embedder(docs, 16, "tiny"))):
        m = Migration(idx, emb)
        m.backfill(list(source.values()), dict(idx.tombstones))
        rep = m.shadow_compare(rows)
        print(f"migrate to {label}: overlap@5={rep.mean_overlap:.2f} hit@5 old={rep.old_recall:.3f} "
              f"new={rep.new_recall:.3f} -> {'CUT OVER' if rep.passed else 'ABORT'}")
