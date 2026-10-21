"""A tiny BM25 retriever over Markdown runbooks. Stdlib only.

Each runbook is split into chunks at `## ` headings. A chunk's id is
`<file-stem>#<heading-slug>`, e.g. `kafka-consumer-lag#mitigation`.

`contextualize=True` prepends "Runbook: <title>. Section: <heading>." to each
chunk before indexing. That is a deterministic, zero-cost cousin of
Anthropic's Contextual Retrieval, which asks a model to write 50-100 tokens of
situating context per chunk. The point is the same: a chunk titled
"Mitigation" that never says "Kafka" should still match a Kafka question.

    python runbook_retriever.py "consumer group falling behind on invoices"
"""

from __future__ import annotations

import math
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"

# Small on purpose. Removing very common words matters more for BM25 on short
# chunks than any clever stemming does.
STOPWORDS = frozenset(
    """a an and are as at be by do does for from has have how i if in is it its
    of on or our so that the then this to was we what when where which why
    with you your can should my me after before into than not no use""".split()
)


SUFFIXES = ("ation", "ion", "ing", "ate", "ed", "s")


def stem(tok: str) -> str:
    """Crude suffix stripping, applied up to twice: mitigation/mitigate -> mitig,
    evictions/evicted -> evict. Wrong in places, but consistently wrong, which
    is all BM25 needs. A real system would use a proper stemmer."""
    for _ in range(2):
        for suf in SUFFIXES:
            if tok.endswith(suf) and len(tok) - len(suf) >= 3 and not tok.endswith("ss"):
                tok = tok[: -len(suf)]
                break
        else:
            break
    return tok


def tokenize(text: str) -> list[str]:
    """Lowercase, split on non-alphanumerics, drop stopwords, stem.

    Identifiers like `invoices.v2` or `max.poll.interval.ms` become several
    tokens, which is what you want for exact-match lookups of config keys.
    """
    return [stem(t) for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOPWORDS]


def slugify(heading: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", heading.lower()).strip("-")


@dataclass
class Chunk:
    id: str
    doc: str
    title: str
    heading: str
    text: str  # the raw section body, which is what we show the model
    indexed_text: str = ""  # what BM25 sees (may include the context prefix)
    tokens: list[str] = field(default_factory=list)


def chunk_markdown(path: Path, contextualize: bool = True) -> list[Chunk]:
    """Split one runbook at `## ` headings. Text before the first `##` is the preamble."""
    lines = path.read_text().splitlines()
    title = lines[0].lstrip("# ").strip() if lines and lines[0].startswith("# ") else path.stem
    sections: list[tuple[str, list[str]]] = [("overview", [])]
    for line in lines[1:]:
        if line.startswith("## "):
            sections.append((line[3:].strip(), []))
        else:
            sections[-1][1].append(line)
    chunks = []
    for heading, body in sections:
        text = "\n".join(body).strip()
        if not text:
            continue
        prefix = f"Runbook: {title}. Section: {heading}.\n" if contextualize else ""
        indexed = prefix + text
        chunks.append(
            Chunk(
                id=f"{path.stem}#{slugify(heading)}",
                doc=path.stem,
                title=title,
                heading=heading,
                text=text,
                indexed_text=indexed,
                tokens=tokenize(indexed),
            )
        )
    return chunks


def load_corpus(data_dir: Path = DATA_DIR, contextualize: bool = True) -> list[Chunk]:
    chunks: list[Chunk] = []
    for p in sorted(data_dir.glob("*.md")):
        chunks.extend(chunk_markdown(p, contextualize=contextualize))
    return chunks


class BM25:
    """Okapi BM25. k1 controls term-frequency saturation, b controls length normalisation."""

    def __init__(self, chunks: list[Chunk], k1: float = 1.5, b: float = 0.75):
        self.chunks = chunks
        self.k1, self.b = k1, b
        self.tf = [Counter(c.tokens) for c in chunks]
        self.lengths = [len(c.tokens) for c in chunks]
        self.avgdl = sum(self.lengths) / max(len(chunks), 1)
        df: Counter[str] = Counter()
        for tf in self.tf:
            df.update(tf.keys())
        n = len(chunks)
        # The "+1" variant keeps idf positive even for terms in most documents.
        self.idf = {t: math.log(1 + (n - d + 0.5) / (d + 0.5)) for t, d in df.items()}

    def score(self, query_tokens: list[str], i: int) -> float:
        tf, dl = self.tf[i], self.lengths[i]
        s = 0.0
        for t in query_tokens:
            f = tf.get(t, 0)
            if not f:
                continue
            norm = f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
            s += self.idf[t] * norm
        return s

    def search(self, query: str, k: int = 5) -> list[tuple[Chunk, float]]:
        q = tokenize(query)
        scored = [(self.chunks[i], self.score(q, i)) for i in range(len(self.chunks))]
        scored = [x for x in scored if x[1] > 0]
        # Sort by score, then id, so ties are deterministic across runs.
        scored.sort(key=lambda x: (-x[1], x[0].id))
        return scored[:k]


def build_index(data_dir: Path = DATA_DIR, contextualize: bool = True) -> BM25:
    return BM25(load_corpus(data_dir, contextualize=contextualize))


if __name__ == "__main__":
    query = " ".join(sys.argv[1:]) or "consumer group falling behind on invoices"
    for label, ctx in (("plain", False), ("contextualized", True)):
        print(f"--- {label} ---")
        for chunk, score in build_index(contextualize=ctx).search(query, k=3):
            print(f"{score:6.2f}  {chunk.id}")
