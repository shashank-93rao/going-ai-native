"""A deterministic toy embedding, and the seam where a real one plugs in.

HONESTY NOTE. `HashedNgramEmbedder` is a stand-in, not a semantic model. It
hashes character 3-5-grams of each word into a fixed number of buckets, weights
them TF-IDF style, and L2-normalizes. That buys three real properties:
  - fixed dimension and cosine similarity, so the index code is the real thing;
  - morphological fuzziness ("rebalancing" ~ "rebalance", "evicted" ~ "evictions");
  - a frozen "model" (the fitted IDF table), so version drift is real.
It does NOT know that "out of space" means "DiskPressure". A trained embedding
model (Voyage, OpenAI, Cohere, an open model) is what gives you that. Swap one
in by implementing the `Embedder` protocol; `VoyageEmbedder` below shows how.

    python embed.py "consumer keeps rebalancing"
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sys
import urllib.request
from collections import Counter
from typing import Protocol, Sequence

Vector = list[float]


class Embedder(Protocol):
    model_id: str  # must change whenever vectors stop being comparable
    dim: int

    def embed(self, texts: Sequence[str], input_type: str = "document") -> list[Vector]: ...


def _bucket(gram: str, dim: int) -> tuple[int, float]:
    """Signed feature hashing with a stable hash (Python's hash() is salted per process)."""
    h = int.from_bytes(hashlib.blake2b(gram.encode(), digest_size=8).digest(), "big")
    return h % dim, (1.0 if (h >> 63) & 1 else -1.0)


def _grams(text: str, lo: int, hi: int) -> list[str]:
    out = []
    for word in re.findall(r"[a-z0-9]+", text.lower()):
        w = f" {word} "
        out.append(w)  # whole word as its own feature
        for n in range(lo, hi + 1):
            out.extend(w[i : i + n] for i in range(max(len(w) - n + 1, 0)))
    return out


def normalize(v: Vector) -> Vector:
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v] if n else v


def cosine(a: Vector, b: Vector) -> float:
    """Dot product. Every embedder here returns unit vectors, so dot == cosine."""
    return sum(x * y for x, y in zip(a, b))


class HashedNgramEmbedder:
    """TF-IDF over hashed character n-grams. Call `fit` once on the corpus; the
    fitted IDF table is the 'model weights'. Refitting changes `model_id`."""

    def __init__(self, dim: int = 512, ngram: tuple[int, int] = (3, 5), name: str = "hashgram"):
        self.dim, self.ngram, self.name = dim, ngram, name
        self.idf: list[float] = [1.0] * dim
        self.model_id = f"{name}-d{dim}-unfitted"
        self.calls = 0  # texts embedded; a stand-in for API cost

    def fit(self, corpus: Sequence[str]) -> "HashedNgramEmbedder":
        df = [0] * self.dim
        for text in corpus:
            for b in {_bucket(g, self.dim)[0] for g in _grams(text, *self.ngram)}:
                df[b] += 1
        n = max(len(corpus), 1)
        self.idf = [math.log((n + 1) / (d + 1)) + 1.0 for d in df]
        digest = hashlib.sha256(json.dumps([round(x, 6) for x in self.idf]).encode()).hexdigest()[:8]
        self.model_id = f"{self.name}-d{self.dim}-{digest}"
        return self

    def embed(self, texts: Sequence[str], input_type: str = "document") -> list[Vector]:
        out = []
        for text in texts:
            self.calls += 1
            v = [0.0] * self.dim
            for gram, tf in Counter(_grams(text, *self.ngram)).items():
                b, sign = _bucket(gram, self.dim)
                v[b] += sign * (1.0 + math.log(tf)) * self.idf[b]
            out.append(normalize(v))
        return out


class CachingEmbedder:
    """Content-addressed cache: (model_id, sha256(text)) -> vector.

    Re-ingesting an unchanged chunk, or changing only its ACL, costs nothing.
    The cache is also a copy of your data: deletion requests must purge it
    (`forget`), or a 'deleted' document lives on as a vector."""

    def __init__(self, inner: Embedder):
        self.inner = inner
        self.cache: dict[tuple[str, str], Vector] = {}
        self.hits = self.misses = 0

    @property
    def model_id(self) -> str:
        return self.inner.model_id

    @property
    def dim(self) -> int:
        return self.inner.dim

    @staticmethod
    def content_hash(text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()

    def embed(self, texts: Sequence[str], input_type: str = "document") -> list[Vector]:
        if input_type == "query":
            return self.inner.embed(texts, input_type)  # queries are not cached here
        keys = [(self.model_id, self.content_hash(t)) for t in texts]
        missing = [t for t, k in zip(texts, keys) if k not in self.cache]
        self.hits += len(texts) - len(missing)
        self.misses += len(missing)
        for t, v in zip(missing, self.inner.embed(missing, input_type) if missing else []):
            self.cache[(self.model_id, self.content_hash(t))] = v
        return [self.cache[k] for k in keys]

    def forget(self, text: str) -> None:
        h = self.content_hash(text)
        for key in [k for k in self.cache if k[1] == h]:
            del self.cache[key]


class VoyageEmbedder:
    """Real embeddings via the Voyage AI API (Anthropic's docs point to Voyage;
    Anthropic has no embedding model of its own). Not used by tests.

    Request shape per https://platform.claude.com/docs/en/build-with-claude/embeddings
    (checked 2026-10-22): POST {"input": [...], "model": ..., "input_type": "query"|"document"}.
    Optional `output_dimension` (Matryoshka: 256/512/1024/2048 on voyage-4 models)."""

    URL = "https://ai.mongodb.com/v1/embeddings"

    def __init__(self, model: str = "voyage-4", dim: int = 1024):
        self.model_id, self.dim = f"{model}-d{dim}", dim
        self._model, self._key = model, os.environ["VOYAGE_API_KEY"]

    def embed(self, texts: Sequence[str], input_type: str = "document") -> list[Vector]:
        body = {"input": list(texts), "model": self._model, "input_type": input_type, "output_dimension": self.dim}
        req = urllib.request.Request(
            self.URL, data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self._key}"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.load(resp)["data"]
        return [normalize(d["embedding"]) for d in sorted(data, key=lambda d: d["index"])]


def truncate(v: Vector, dims: int) -> Vector:
    """Matryoshka-style truncation: keep the leading dims, renormalize. Only
    meaningful for models trained with MRL; on the toy embedder it just loses
    information, which is the honest result."""
    return normalize(v[:dims])


if __name__ == "__main__":
    texts = ["consumer keeps rebalancing", "Rebalance storms usually mean max.poll.interval.ms is too low",
             "the box is out of space", "The node was low on resource: ephemeral-storage"]
    e = HashedNgramEmbedder().fit(texts)
    vs = e.embed(texts)
    print(e.model_id)
    print(f"rebalancing vs rebalance-storm sentence: {cosine(vs[0], vs[1]):.3f}")
    print(f"'out of space' vs ephemeral-storage:     {cosine(vs[2], vs[3]):.3f}  (no semantics: expect low)")
