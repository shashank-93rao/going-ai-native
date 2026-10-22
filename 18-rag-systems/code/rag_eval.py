"""RAG evals: retrieval metrics, citation grounding, abstention scoring, and a
component-ablation report with paired-bootstrap error bars.

Retrieval is labeled two ways in data/questions.jsonl:
  relevant_docs  -> doc-level recall@k, MRR, nDCG@k (chunker-independent ids)
  evidence       -> evidence@k: did any top-k chunk contain the answer-bearing
                    span verbatim? This is what catches a chunker that cut the
                    answer in half, which doc-level recall cannot see.

    PYTHONPATH=shared .venv/bin/python 18-rag-systems/code/rag_eval.py
"""

from __future__ import annotations

import json
import math
import random
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from ainative_kit import FakeClient, LLMClient

from chunking import Chunk, expand_to_parents, load_docs, parent_child_chunks
from embed import HashedNgramEmbedder
from hybrid import HybridRetriever, Hit, LLMReranker, fake_rerank_responder, tokenize
from rag_pipeline import CITE_RE, Answer, answer, build_default, fake_generator_responder

QUESTIONS = Path(__file__).parent / "data" / "questions.jsonl"


def load_questions(path: Path = QUESTIONS) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


# --- retrieval metrics -----------------------------------------------------------

def doc_ranking(chunks: list[Chunk]) -> list[str]:
    """Chunk ranking -> doc ranking, first occurrence wins."""
    return list(dict.fromkeys(c.doc_id for c in chunks))


def recall_at_k(ranked: list[str], relevant: set[str], k: int) -> float:
    return len(relevant & set(ranked[:k])) / len(relevant)


def mrr(ranked: list[str], relevant: set[str]) -> float:
    return next((1.0 / i for i, d in enumerate(ranked, 1) if d in relevant), 0.0)


def ndcg_at_k(ranked: list[str], relevant: set[str], k: int) -> float:
    """Binary-gain nDCG: rewards putting relevant docs near the top, not just in the top k."""
    dcg = sum(1.0 / math.log2(i + 1) for i, d in enumerate(ranked[:k], 1) if d in relevant)
    ideal = sum(1.0 / math.log2(i + 1) for i in range(1, min(len(relevant), k) + 1))
    return dcg / ideal if ideal else 0.0


def _norm(s: str) -> str:
    return " ".join(s.split())


def evidence_at_k(chunks: list[Chunk], evidence: list[str], k: int) -> float:
    shown = " || ".join(_norm(c.text) for c in chunks[:k])
    return 1.0 if any(_norm(e) in shown for e in evidence) else 0.0


Retrieve = Callable[[str, frozenset[str], int], list[Chunk]]


def per_question(retrieve: Retrieve, rows: list[dict], k: int = 5) -> dict[str, dict[str, float]]:
    out = {}
    for r in rows:
        if not r["answerable"]:
            continue
        chunks = retrieve(r["question"], frozenset({r["team"]}), k)
        ranked, rel = doc_ranking(chunks), set(r["relevant_docs"])
        out[r["id"]] = {"recall": recall_at_k(ranked, rel, k), "mrr": mrr(ranked, rel),
                        "ndcg": ndcg_at_k(ranked, rel, k), "evidence": evidence_at_k(chunks, r["evidence"], k),
                        "words": float(sum(len(c.text.split()) for c in chunks[:k]))}
    return out


def mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def paired_bootstrap(a: list[float], b: list[float], n: int = 2000, seed: int = 0) -> tuple[float, float, float]:
    """Mean of (b - a) with a 95% percentile CI, resampling questions. Paired,
    because both systems answered the same questions (see Module 12)."""
    rng, d = random.Random(seed), [y - x for x, y in zip(a, b)]
    boots = sorted(mean([d[rng.randrange(len(d))] for _ in d]) for _ in range(n))
    return mean(d), boots[int(0.025 * n)], boots[int(0.975 * n) - 1]


# --- grounding ---------------------------------------------------------------------

@dataclass
class Grounding:
    citations: int
    unknown: list[str] = field(default_factory=list)  # cited ids never shown
    unsupported: list[str] = field(default_factory=list)  # sentences the cited chunk doesn't support
    uncited: list[str] = field(default_factory=list)  # sentences with no citation

    @property
    def citation_precision(self) -> float:
        bad = len(self.unknown) + len(self.unsupported)
        return (self.citations - bad) / self.citations if self.citations else 0.0

    @property
    def ok(self) -> bool:
        return self.citations > 0 and not (self.unknown or self.unsupported or self.uncited)


def grounding_check(text: str, shown: list[Chunk], min_support: float = 0.8) -> Grounding:
    """Each sentence must cite a shown chunk; at least `min_support` of its
    content terms must appear in that chunk; backticked spans must be verbatim.
    Deterministic, so it runs on every answer in production, not just in evals."""
    by_id = {c.id: c for c in shown}
    g = Grounding(citations=len(CITE_RE.findall(text)))
    for sent in [s for s in re.split(r"(?<=\])\s+|\n", text) if s.strip()]:
        cites = CITE_RE.findall(sent)
        claim = CITE_RE.sub("", sent).strip()
        if not cites:
            g.uncited.append(claim)
            continue
        g.unknown += [c for c in cites if c not in by_id]
        support = " ".join(_norm(by_id[c].text) for c in cites if c in by_id)
        terms = set(tokenize(claim))
        covered = len(terms & set(tokenize(support))) / len(terms) if terms else 1.0
        spans_ok = all(_norm(s) in support for s in re.findall(r"`([^`]+)`", claim))
        if cites and all(c in by_id for c in cites) and (covered < min_support or not spans_ok):
            g.unsupported.append(claim)
    return g


# --- abstention ----------------------------------------------------------------------

def score_answer(row: dict, ans: Answer) -> str:
    """correct | wrong | abstain. On an unanswerable row, abstaining is correct
    and answering is wrong: that is the hallucination you most want to count."""
    if not row["answerable"]:
        return "correct" if ans.abstained else "wrong"
    if ans.abstained:
        return "abstain"
    cited_docs = {c.split("#")[0] for c in ans.citations}
    g = grounding_check(ans.text, [h.chunk for h in ans.hits])
    return "correct" if g.ok and cited_docs & set(row["relevant_docs"]) else "wrong"


def abstention_report(outcomes: dict[str, str], rows: list[dict]) -> dict[str, float]:
    ans = [r for r in rows if r["answerable"]]
    una = [r for r in rows if not r["answerable"]]
    c = lambda rs, o: sum(outcomes[r["id"]] == o for r in rs)  # noqa: E731
    return {
        "answerable_correct": c(ans, "correct") / len(ans),
        "answerable_wrong": c(ans, "wrong") / len(ans),
        "answerable_abstain": c(ans, "abstain") / len(ans),
        "unanswerable_abstain": c(una, "correct") / len(una),
        "unanswerable_answered": c(una, "wrong") / len(una),
    }


# --- ablation ------------------------------------------------------------------------

def retriever_fn(strategy: str, mode: str, rerank: bool = False) -> Retrieve:
    """Build one configuration as a plain function (question, teams, k) -> chunks."""
    reranker = LLMReranker(FakeClient(fake_rerank_responder)) if rerank else None
    if strategy.startswith("parent-child"):
        docs = load_docs()
        parents, children = {}, {}
        for d in docs:
            pc = parent_child_chunks(d, parent="doc" if strategy.endswith("doc") else "section")
            parents.update(pc.parents)
            children.update({c.id: c for c in pc.children})
        emb = HashedNgramEmbedder().fit([c.indexed_text for c in children.values()])
        r = HybridRetriever(list(children.values()), emb)
        return lambda q, t, k: expand_to_parents(
            [h.chunk.id for h in r.search(q, t, k=4 * k, mode=mode, reranker=reranker)], parents, children)[:k]
    r = build_default(strategy)
    return lambda q, t, k: [h.chunk for h in r.search(q, t, k=k, mode=mode, reranker=reranker)]


CONFIGS = [  # (label, strategy, mode, rerank)
    ("bm25 heading, no header (Module 03 style)", "heading-noctx", "bm25", False),
    ("bm25 heading + header", "heading", "bm25", False),
    ("dense heading + header", "heading", "dense", False),
    ("hybrid RRF heading + header", "heading", "hybrid", False),
    ("hybrid RRF + rerank", "heading", "hybrid", True),
    ("hybrid fixed 40w", "fixed", "hybrid", False),
    ("hybrid fixed 40w + header", "fixed+ctx", "hybrid", False),
    ("hybrid sentence -> section", "parent-child", "hybrid", False),
    ("hybrid sentence -> whole doc", "parent-child-doc", "hybrid", False),
]


def ablation(rows: list[dict], k: int = 5) -> list[str]:
    lines = [f"{'config':<42} {'recall@5':>8} {'MRR':>6} {'nDCG@5':>7} {'evid@5':>7} {'words':>6}   evid@5 delta vs row 1 [95% CI]"]
    base = None
    for label, strategy, mode, rr in CONFIGS:
        pq = per_question(retriever_fn(strategy, mode, rr), rows, k)
        ids = sorted(pq)
        ev = [pq[i]["evidence"] for i in ids]
        base = base or ev
        d, lo, hi = paired_bootstrap(base, ev)
        lines.append(f"{label:<42} {mean([pq[i]['recall'] for i in ids]):8.3f} {mean([pq[i]['mrr'] for i in ids]):6.3f} "
                     f"{mean([pq[i]['ndcg'] for i in ids]):7.3f} {mean(ev):7.3f} {mean([pq[i]['words'] for i in ids]):6.0f}   {d:+.3f} [{lo:+.3f}, {hi:+.3f}]")
    return lines


def end_to_end(rows: list[dict], client: LLMClient, rerank: bool = False) -> tuple[dict[str, str], dict[str, float]]:
    r = build_default("heading")
    reranker = LLMReranker(FakeClient(fake_rerank_responder)) if rerank else None
    outcomes = {row["id"]: score_answer(row, answer(client, r, row["question"], frozenset({row["team"]}), reranker=reranker))
                for row in rows}
    return outcomes, abstention_report(outcomes, rows)


if __name__ == "__main__":
    rows = load_questions()
    n_ans = sum(r["answerable"] for r in rows)
    print(f"{len(rows)} questions ({n_ans} answerable, {len(rows) - n_ans} unanswerable for the asking team)\n")
    print("\n".join(ablation(rows)))
    for k in (9, 15):  # same question, more chunks: is "fixed wins" just "fixed shows more text"?
        pq = per_question(retriever_fn("heading", "hybrid"), rows, k)
        print(f"{'hybrid heading + header, k=' + str(k):<42} {'':>8} {'':>6} {'':>7} "
              f"{mean([v['evidence'] for v in pq.values()]):7.3f} {mean([v['words'] for v in pq.values()]):6.0f}   (evidence@{k})")
    print("\nEnd to end (hybrid heading, fake extractive generator), by abstention threshold:")
    for min_overlap in (2, 3, 4):
        outcomes, rep = end_to_end(rows, FakeClient(fake_generator_responder(min_overlap)))
        print(f"  min_overlap={min_overlap}  " + "  ".join(f"{k}={v:.2f}" for k, v in rep.items()))
        print("      wrong:", sorted(i for i, o in outcomes.items() if o == "wrong"))
