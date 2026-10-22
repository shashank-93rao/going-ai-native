"""HNSW against brute force. The numbers in the assertions are loose floors on
a seeded run; the point is the shape: more ef, more recall, more work."""
import pytest

from hnsw_lite import HNSW, ExactIndex, random_unit_vectors, recall_vs_exact

N, DIM, K = 1200, 24, 10


@pytest.fixture(scope="module")
def built():
    data = random_unit_vectors(N, DIM, seed=1)
    exact, h = ExactIndex(), HNSW(M=8, ef_construction=48, seed=0)
    for i, v in enumerate(data):
        exact.add(str(i), v, {"tenant": i % 20})
        h.add(str(i), v, {"tenant": i % 20})
    return h, exact, random_unit_vectors(30, DIM, seed=2)


def test_recall_at_10_vs_exact_and_ef_search_tradeoff(built):
    h, exact, queries = built
    curve = [(ef, *recall_vs_exact(h, exact, queries, K, ef)) for ef in (10, 40, 160)]
    recalls = [r for _, r, _ in curve]
    work = [w for _, _, w in curve]
    assert recalls == sorted(recalls) and work == sorted(work)  # monotone trade-off
    assert recalls[0] < 0.8 and recalls[-1] > 0.95
    assert work[-1] < N  # still cheaper than brute force


def test_post_filter_starves_results_inline_filter_does_not(built):
    h, exact, queries = built
    only = lambda m: m["tenant"] == 3  # noqa: E731  5% selectivity
    post = [len(h.search(q, K, ef_search=40, filter=only, filter_mode="post")) for q in queries]
    inline = [len(h.search(q, K, ef_search=40, filter=only, filter_mode="inline")) for q in queries]
    assert sum(post) / len(post) < 5 and min(inline) == K
    r_inline, _ = recall_vs_exact(h, exact, queries, K, 40, filter=only)
    assert r_inline > 0.9


def test_tombstones_hide_results_until_rebuild_removes_them(built):
    h, _, queries = built
    h2 = HNSW(M=8, ef_construction=32)
    for i, v in enumerate(random_unit_vectors(200, DIM, seed=5)):
        h2.add(str(i), v)
    top = h2.search(queries[0], 1)[0][0]
    h2.mark_deleted(top)
    assert top not in [k for k, _ in h2.search(queries[0], 10)]
    assert top in h2.vecs  # bytes still there
    assert top not in h2.rebuild().vecs


def test_exact_prefilter_only_scores_rows_that_pass():
    e = ExactIndex()
    for i, v in enumerate(random_unit_vectors(100, 8)):
        e.add(str(i), v, i % 10)
    e.search(random_unit_vectors(1, 8, seed=9)[0], 5, filter=lambda m: m == 0)
    assert e.distance_calls == 10
