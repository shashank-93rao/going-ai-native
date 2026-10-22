"""Hybrid retrieval: BM25 + dense, fused with RRF, then an optional reranker.

The ACL filter is applied inside both retrievers (pre-filter for BM25, inline
filter for HNSW), never after fusion. A post-fusion filter can return fewer
than k results and, worse, makes "forgot to filter" a one-line bug.

    python hybrid.py "invoice consumer keeps rebalancing" --team payments
"""

from __future__ import annotations

import json
import math
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable, Protocol

from ainative_kit import DEFAULT_MODEL, LLMClient, Response

from chunking import PUBLIC, Chunk
from embed import Embedder
from hnsw_lite import HNSW, ExactIndex

STOPWORDS = frozenset(
    """a an and are as at be by do does for from has have how i if in is it its of on or our so
    that the then this to was we what when where which why with you your can should my me after
    before into than not no use just right""".split()
)


def stem(tok: str) -> str:
    """Crude suffix stripping, as in Module 03's runbook retriever."""
    for suf in ("ation", "ing", "ion", "ed", "es", "s"):
        if tok.endswith(suf) and len(tok) - len(suf) >= 3 and not tok.endswith("ss"):
            return tok[: -len(suf)]
    return tok


def tokenize(text: str) -> list[str]:
    return [stem(t) for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOPWORDS]


def can_read(teams: frozenset[str]) -> Callable[[Chunk], bool]:
    """ACL predicate from the caller's *verified* team claims."""
    allowed = teams | {PUBLIC}
    return lambda c: bool(c.acl & allowed)


class BM25Index:
    def __init__(self, chunks: list[Chunk], k1: float = 1.2, b: float = 0.75):
        self.chunks = {c.id: c for c in chunks}
        self.k1, self.b = k1, b
        self.tf = {c.id: Counter(tokenize(c.indexed_text)) for c in chunks}
        self.len = {cid: sum(tf.values()) for cid, tf in self.tf.items()}
        self.avgdl = sum(self.len.values()) / max(len(self.len), 1)
        df: Counter[str] = Counter()
        for tf in self.tf.values():
            df.update(tf.keys())
        n = len(chunks)
        self.idf = {t: math.log(1 + (n - d + 0.5) / (d + 0.5)) for t, d in df.items()}

    def search(self, query: str, k: int, allow: Callable[[Chunk], bool] | None = None) -> list[tuple[str, float]]:
        q = tokenize(query)
        out = []
        for cid, tf in self.tf.items():
            if allow and not allow(self.chunks[cid]):
                continue
            s = 0.0
            for t in q:
                f = tf.get(t, 0)
                if f:
                    s += self.idf[t] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * self.len[cid] / self.avgdl))
            if s > 0:
                out.append((cid, s))
        out.sort(key=lambda x: (-x[1], x[0]))
        return out[:k]


def rrf(rankings: list[list[str]], k: int = 60) -> list[tuple[str, float]]:
    """Reciprocal Rank Fusion (Cormack, Clarke & Buettcher, SIGIR 2009):
    score(d) = sum over rankings r of 1 / (k + rank_r(d)), rank starting at 1.
    Uses only ranks, so BM25 scores and cosines never need calibrating."""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, doc in enumerate(ranking, start=1):
            scores[doc] = scores.get(doc, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda x: (-x[1], x[0]))


class Reranker(Protocol):
    def rerank(self, query: str, chunks: list[Chunk]) -> list[str]: ...


RERANK_SYSTEM = (
    "You rank documentation chunks by how directly they answer an on-call engineer's question. "
    'Reply with JSON only: {"ranking": ["<chunk id>", ...]}, most relevant first. '
    "Include only ids you were given."
)


class LLMReranker:
    """Listwise LLM reranker. A dedicated cross-encoder (Cohere Rerank, Voyage
    rerank) is cheaper and faster for this job; the LLM version is here because
    it runs offline on FakeClient and shows the failure handling you need
    either way: unknown ids dropped, missing ids appended in input order."""

    def __init__(self, client: LLMClient, model: str = DEFAULT_MODEL):
        self.client, self.model = client, model

    def rerank(self, query: str, chunks: list[Chunk]) -> list[str]:
        docs = "\n".join(f'<chunk id="{c.id}">{c.indexed_text}</chunk>' for c in chunks)
        msg = f"<chunks>\n{docs}\n</chunks>\n<question>{query}</question>"
        resp = self.client.complete([{"role": "user", "content": msg}], system=RERANK_SYSTEM, model=self.model, max_tokens=512)
        given = [c.id for c in chunks]
        try:
            ranked = [i for i in json.loads(resp.text)["ranking"] if i in given]
        except (ValueError, KeyError, TypeError):
            return given  # fail open to the fused order, and count it in your metrics
        seen = set(ranked)
        return list(dict.fromkeys(ranked)) + [i for i in given if i not in seen]


def fake_rerank_responder(messages, kwargs) -> Response:
    """Deterministic stand-in for a cross-encoder: scores each chunk by the share
    of distinct query terms it covers (coverage, not tf-idf), ties broken by input order."""
    content = messages[-1]["content"]
    q = set(tokenize(re.search(r"<question>(.*?)</question>", content, re.S).group(1)))
    chunks = re.findall(r'<chunk id="([^"]+)">(.*?)</chunk>', content, re.S)
    scored = [(-len(q & set(tokenize(body))), i, cid) for i, (cid, body) in enumerate(chunks)]
    return Response(text=json.dumps({"ranking": [cid for *_, cid in sorted(scored)]}))


@dataclass
class Hit:
    chunk: Chunk
    score: float
    sources: dict[str, int] = field(default_factory=dict)  # retriever -> rank (1-based)


class HybridRetriever:
    """Holds both indexes for one chunk set. `mode` is 'bm25', 'dense' or 'hybrid'."""

    def __init__(self, chunks: list[Chunk], embedder: Embedder, index: str = "hnsw", M: int = 8, ef_construction: int = 64):
        self.chunks = {c.id: c for c in chunks}
        self.embedder = embedder
        self.bm25 = BM25Index(chunks)
        self.vindex = HNSW(M=M, ef_construction=ef_construction) if index == "hnsw" else ExactIndex()
        vecs = embedder.embed([c.indexed_text for c in chunks], "document")
        for c, v in zip(chunks, vecs):
            self.vindex.add(c.id, v, c)

    def search(self, query: str, teams: frozenset[str], k: int = 5, mode: str = "hybrid", candidates: int = 30,
               reranker: Reranker | None = None, ef_search: int = 64) -> list[Hit]:
        allow = can_read(teams)
        ranks: dict[str, dict[str, int]] = {}
        lists: list[list[str]] = []
        if mode in ("bm25", "hybrid"):
            lex = [cid for cid, _ in self.bm25.search(query, candidates, allow)]
            lists.append(lex)
            for r, cid in enumerate(lex, 1):
                ranks.setdefault(cid, {})["bm25"] = r
        if mode in ("dense", "hybrid"):
            qv = self.embedder.embed([query], "query")[0]
            dense = [cid for cid, _ in self.vindex.search(qv, candidates, ef_search=max(ef_search, candidates), filter=allow)]
            lists.append(dense)
            for r, cid in enumerate(dense, 1):
                ranks.setdefault(cid, {})["dense"] = r
        fused = rrf(lists)
        if reranker:
            order = reranker.rerank(query, [self.chunks[cid] for cid, _ in fused])
            fused = [(cid, 1.0 / (i + 1)) for i, cid in enumerate(order)]
        hits = [Hit(self.chunks[cid], s, ranks.get(cid, {})) for cid, s in fused[:k]]
        assert all(allow(h.chunk) for h in hits), "ACL invariant violated"  # defence in depth
        return hits


if __name__ == "__main__":
    from chunking import chunk_corpus, load_docs
    from embed import HashedNgramEmbedder

    args = sys.argv[1:]
    team = args[args.index("--team") + 1] if "--team" in args else "platform"
    query = " ".join(a for i, a in enumerate(args) if a != "--team" and (i == 0 or args[i - 1] != "--team")) \
        or "invoice consumer keeps rebalancing"
    chunks = chunk_corpus(load_docs(), "heading")
    emb = HashedNgramEmbedder().fit([c.indexed_text for c in chunks])
    r = HybridRetriever(chunks, emb)
    for mode in ("bm25", "dense", "hybrid"):
        print(f"--- {mode}")
        for h in r.search(query, frozenset({team}), k=3, mode=mode):
            print(f"  {h.score:.4f}  {h.chunk.id:<44} {h.sources}")
