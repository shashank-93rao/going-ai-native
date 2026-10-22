"""Documents and three chunkers: fixed-size, heading-aware, and parent-child.

Every chunk keeps the metadata retrieval needs later: the source doc id and
version (for idempotent upserts and deletes), the ACL (for permission-aware
retrieval), and a stable id (for citations). A chunk without those is a
string, not a retrievable unit.

    python chunking.py                 # show how each chunker splits one doc
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from pathlib import Path

DOCS_DIR = Path(__file__).parent / "data" / "docs"
PUBLIC = "eng"  # ACL group that every engineer belongs to


@dataclass(frozen=True)
class Doc:
    id: str
    title: str
    kind: str  # runbook | adr | postmortem | guide
    team: str
    acl: frozenset[str]
    version: int
    body: str  # markdown, starting with "# Title"


@dataclass(frozen=True)
class Chunk:
    id: str
    doc_id: str
    version: int
    section: str  # heading slug, or "" when the chunker does not know
    text: str  # what the model is shown
    acl: frozenset[str]
    context: str = ""  # contextual header, indexed but not shown
    parent_id: str | None = None  # parent-child: the section this child came from

    @property
    def indexed_text(self) -> str:
        """What BM25 and the embedder see. The header travels with the chunk."""
        return f"{self.context}\n{self.text}" if self.context else self.text


def parse_doc(raw: str) -> Doc:
    """Parse the `---` front matter used in data/docs/*.md."""
    m = re.match(r"---\n(.*?)\n---\n(.*)", raw, re.S)
    if not m:
        raise ValueError("missing front matter")
    meta = dict(line.split(": ", 1) for line in m.group(1).splitlines())
    return Doc(
        id=meta["id"],
        title=meta["title"],
        kind=meta["kind"],
        team=meta["team"],
        acl=frozenset(a.strip() for a in meta["acl"].split(",")),
        version=int(meta["version"]),
        body=m.group(2).strip(),
    )


def load_docs(path: Path = DOCS_DIR) -> list[Doc]:
    return [parse_doc(p.read_text()) for p in sorted(path.glob("*.md"))]


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def sections(doc: Doc) -> list[tuple[str, str]]:
    """Split at `## ` headings. Text before the first heading is 'overview'."""
    out: list[tuple[str, list[str]]] = [("overview", [])]
    for line in doc.body.splitlines():
        if line.startswith("# "):
            continue
        if line.startswith("## "):
            out.append((line[3:].strip(), []))
        else:
            out[-1][1].append(line)
    return [(h, "\n".join(b).strip()) for h, b in out if "\n".join(b).strip()]


def header_for(doc: Doc, heading: str) -> str:
    """A deterministic contextual header: the zero-cost cousin of Anthropic's
    model-written Contextual Retrieval prefix (see Module 03, file 06)."""
    return f"{doc.title} ({doc.kind}, owner {doc.team}) > {heading}"


# --- 1. fixed-size --------------------------------------------------------------

def fixed_chunks(doc: Doc, size: int = 40, overlap: int = 10, contextual: bool = False) -> list[Chunk]:
    """Sliding window of `size` words with `overlap`. Ignores structure entirely,
    so a command or a sentence can be cut in half at a window edge."""
    if overlap >= size:
        raise ValueError("overlap must be smaller than size")
    words = " ".join(text for _, text in sections(doc)).split()
    chunks, start, n = [], 0, 0
    while start < len(words):
        window = " ".join(words[start : start + size])
        ctx = f"{doc.title} ({doc.kind}, owner {doc.team})" if contextual else ""
        chunks.append(Chunk(f"{doc.id}#w{n}", doc.id, doc.version, "", window, doc.acl, ctx))
        if start + size >= len(words):
            break
        start += size - overlap
        n += 1
    return chunks


# --- 2. heading-aware -----------------------------------------------------------

def heading_chunks(doc: Doc, contextual: bool = True, max_words: int = 120) -> list[Chunk]:
    """One chunk per `##` section; sections longer than `max_words` split at
    paragraph boundaries. Ids are `<doc>#<section-slug>[-n]`, stable across
    re-ingestion as long as headings don't change."""
    out: list[Chunk] = []
    for heading, text in sections(doc):
        slug = slugify(heading)
        parts = _split_paragraphs(text, max_words)
        for i, part in enumerate(parts):
            cid = f"{doc.id}#{slug}" + (f"-{i}" if len(parts) > 1 else "")
            ctx = header_for(doc, heading) if contextual else ""
            out.append(Chunk(cid, doc.id, doc.version, slug, part, doc.acl, ctx))
    return out


def _split_paragraphs(text: str, max_words: int) -> list[str]:
    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    parts, cur = [], []
    for p in paras:
        if cur and len(" ".join(cur + [p]).split()) > max_words:
            parts.append("\n\n".join(cur))
            cur = []
        cur.append(p)
    if cur:
        parts.append("\n\n".join(cur))
    return parts


# --- 3. parent-child (small-to-big) ---------------------------------------------

def sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z`])", text) if s.strip()]


@dataclass
class ParentChild:
    children: list[Chunk]  # small, precise units: what you index
    parents: dict[str, Chunk] = field(default_factory=dict)  # sections: what you show


def parent_child_chunks(doc: Doc, child_sentences: int = 1, contextual: bool = True, parent: str = "section") -> ParentChild:
    """Index small children (n sentences) for precise matching; return their
    parent for generation, so the model sees the surrounding steps.
    parent='section' returns the `##` section; parent='doc' returns the whole
    document (fine for short runbooks, wasteful for long design docs)."""
    pc = ParentChild(children=[])
    sects = heading_chunks(doc, contextual=contextual, max_words=10_000)
    whole = None
    if parent == "doc":
        body = "\n\n".join(f"## {h}\n{t}" for h, t in sections(doc))
        whole = Chunk(f"{doc.id}#doc", doc.id, doc.version, "doc", body, doc.acl, f"{doc.title} ({doc.kind}, owner {doc.team})")
        pc.parents[whole.id] = whole
    for sec in sects:
        if whole is None:
            pc.parents[sec.id] = sec
        sents = sentences(sec.text)
        for i in range(0, len(sents), child_sentences):
            text = " ".join(sents[i : i + child_sentences])
            pc.children.append(replace(sec, id=f"{sec.id}~{i}", text=text, parent_id=(whole or sec).id))
    return pc


def expand_to_parents(child_ids: list[str], parents: dict[str, Chunk], children: dict[str, Chunk]) -> list[Chunk]:
    """Map ranked child hits to their parents, keeping the first-seen order and
    de-duplicating: three hits in one section become one shown chunk."""
    seen, out = set(), []
    for cid in child_ids:
        pid = children[cid].parent_id or cid
        if pid not in seen:
            seen.add(pid)
            out.append(parents[pid])
    return out


def chunk_corpus(docs: list[Doc], strategy: str = "heading", **kw) -> list[Chunk]:
    """Convenience for evals: 'fixed', 'fixed+ctx', 'heading', 'heading-noctx'."""
    out: list[Chunk] = []
    for d in docs:
        if strategy == "fixed":
            out += fixed_chunks(d, **kw)
        elif strategy == "fixed+ctx":
            out += fixed_chunks(d, contextual=True, **kw)
        elif strategy == "heading":
            out += heading_chunks(d, **kw)
        elif strategy == "heading-noctx":
            out += heading_chunks(d, contextual=False, **kw)
        else:
            raise ValueError(strategy)
    return out


if __name__ == "__main__":
    doc = next(d for d in load_docs() if d.id == "rb-kafka-consumer-lag")
    for name, chunks in (("fixed(40/10)", fixed_chunks(doc)), ("heading", heading_chunks(doc))):
        print(f"--- {name}: {len(chunks)} chunks")
        for c in chunks:
            print(f"  {c.id:<36} {c.text[:70]!r}")
    pc = parent_child_chunks(doc)
    print(f"--- parent-child: {len(pc.children)} children -> {len(pc.parents)} parents")
    for c in pc.children[:4]:
        print(f"  {c.id:<36} parent={c.parent_id}")
