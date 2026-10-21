"""Retrieval and grounding evals for the runbook assistant. Stdlib only.

Two layers, cheapest first (the order Jason Liu recommends for RAG evals):

1. Retrieval: recall@k, hit@k and MRR against a labelled JSONL of
   {id, question, relevant: [chunk_id, ...]}. Deterministic, no model.
2. Grounding: given an answer and the chunks it was shown, check that every
   citation points at a retrieved chunk and every backticked command in the
   answer appears verbatim in a cited chunk. Also deterministic.

    python retrieval_eval.py            # compare plain vs contextualized BM25
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from runbook_retriever import BM25, Chunk, build_index

EVAL_PATH = Path(__file__).parent / "data" / "retrieval_eval.jsonl"


def load_eval(path: Path = EVAL_PATH) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def recall_at_k(retrieved: list[str], relevant: Iterable[str], k: int) -> float:
    """Fraction of the relevant ids that appear in the top k."""
    rel = set(relevant)
    if not rel:
        raise ValueError("an eval row with no relevant ids cannot be scored")
    return len(rel & set(retrieved[:k])) / len(rel)


def hit_at_k(retrieved: list[str], relevant: Iterable[str], k: int) -> float:
    """1.0 if any relevant id is in the top k. Looser than recall when a row has several."""
    return 1.0 if set(relevant) & set(retrieved[:k]) else 0.0


def reciprocal_rank(retrieved: list[str], relevant: Iterable[str]) -> float:
    rel = set(relevant)
    for i, cid in enumerate(retrieved, start=1):
        if cid in rel:
            return 1.0 / i
    return 0.0


@dataclass
class EvalReport:
    k: int
    recall: float
    hit: float
    mrr: float
    misses: list[dict] = field(default_factory=list)  # rows with recall < 1 at k

    def line(self, label: str) -> str:
        return f"{label:<15} recall@{self.k}={self.recall:.3f}  hit@{self.k}={self.hit:.3f}  MRR={self.mrr:.3f}  misses={len(self.misses)}"


def evaluate(index: BM25, rows: list[dict], k: int = 5, depth: int = 20) -> EvalReport:
    """Score every row. `depth` is how far down we look for MRR."""
    recalls, hits, rrs, misses = [], [], [], []
    for row in rows:
        got = [c.id for c, _ in index.search(row["question"], k=depth)]
        r = recall_at_k(got, row["relevant"], k)
        recalls.append(r)
        hits.append(hit_at_k(got, row["relevant"], k))
        rrs.append(reciprocal_rank(got, row["relevant"]))
        if r < 1.0:
            misses.append({"id": row["id"], "question": row["question"], "relevant": row["relevant"], "top": got[:k]})
    n = len(rows)
    return EvalReport(k=k, recall=sum(recalls) / n, hit=sum(hits) / n, mrr=sum(rrs) / n, misses=misses)


# --- grounding ---------------------------------------------------------------

CITATION_RE = re.compile(r"\[([a-z0-9-]+#[a-z0-9-]+)\]")
COMMAND_RE = re.compile(r"`([^`]+)`")


@dataclass
class GroundingReport:
    unknown_citations: list[str]  # cited ids the model was never shown
    ungrounded_commands: list[str]  # commands not found verbatim in any cited chunk
    uncited_command_lines: list[str]  # lines with a command but no citation
    cited: list[str]

    @property
    def ok(self) -> bool:
        return not (self.unknown_citations or self.ungrounded_commands or self.uncited_command_lines)


def _norm(s: str) -> str:
    return " ".join(s.split())


def grounding_check(answer: str, shown: list[Chunk]) -> GroundingReport:
    """Check an on-call answer against the chunks it was given.

    The rule is strict on purpose: in an incident, a plausible command the
    runbook does not contain is worse than no command. Placeholders like
    `<node>` must match the runbook's placeholders exactly.
    """
    by_id = {c.id: c for c in shown}
    unknown, ungrounded, uncited, cited_all = [], [], [], []
    for line in answer.splitlines():
        cites = CITATION_RE.findall(line)
        cited_all.extend(cites)
        unknown.extend(c for c in cites if c not in by_id)
        commands = COMMAND_RE.findall(line)
        if commands and not cites:
            uncited.append(line.strip())
            continue
        cited_text = " ".join(_norm(by_id[c].text) for c in cites if c in by_id)
        for cmd in commands:
            if _norm(cmd) not in cited_text:
                ungrounded.append(cmd)
    return GroundingReport(
        unknown_citations=sorted(set(unknown)),
        ungrounded_commands=ungrounded,
        uncited_command_lines=uncited,
        cited=sorted(set(cited_all)),
    )


if __name__ == "__main__":
    rows = load_eval()
    for k in (1, 3, 5):
        for label, ctx in (("plain", False), ("contextualized", True)):
            print(evaluate(build_index(contextualize=ctx), rows, k=k).line(label))
    print("\nMisses at k=5 (contextualized):")
    for m in evaluate(build_index(contextualize=True), rows, k=5).misses:
        print(f"  {m['id']} {m['question']!r}\n     wanted {m['relevant']}\n     got    {m['top']}")
