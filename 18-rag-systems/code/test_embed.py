import math

import pytest

from embed import CachingEmbedder, HashedNgramEmbedder, cosine, truncate


@pytest.fixture
def emb():
    return HashedNgramEmbedder(dim=256).fit(["consumer rebalancing storm", "node out of disk", "tls certificate"])


def test_deterministic_unit_vectors(emb):
    a, b = emb.embed(["consumer rebalancing"]), emb.embed(["consumer rebalancing"])
    assert a == b and math.isclose(sum(x * x for x in a[0]), 1.0, rel_tol=1e-9)


def test_morphology_but_not_semantics(emb):
    q, near, synonym = emb.embed(["rebalancing", "rebalance storms", "partition reassignment"])
    assert cosine(q, near) > cosine(q, synonym)  # shares n-grams; a synonym shares none


def test_refit_changes_model_id(emb):
    other = HashedNgramEmbedder(dim=256).fit(["completely different corpus"])
    assert other.model_id != emb.model_id


def test_cache_hits_unchanged_text_and_forget_purges(emb):
    c = CachingEmbedder(emb)
    c.embed(["a b c", "d e f"])
    c.embed(["a b c"])
    assert (c.misses, c.hits) == (2, 1)
    c.forget("a b c")
    assert all(k[1] != CachingEmbedder.content_hash("a b c") for k in c.cache)


def test_truncate_renormalizes(emb):
    v = truncate(emb.embed(["x y z"])[0], 64)
    assert len(v) == 64 and math.isclose(sum(x * x for x in v), 1.0, rel_tol=1e-9)
