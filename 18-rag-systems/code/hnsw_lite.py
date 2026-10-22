"""A small HNSW index and a brute-force exact index. Stdlib only.

Follows Malkov & Yashunin (arXiv:1603.09320): a multi-layer proximity graph,
greedy descent through sparse upper layers, then a beam search of width `ef`
on layer 0. Simplifications, stated so you don't mistake this for hnswlib:
  - neighbour selection keeps the M closest (no diversity heuristic);
  - deletes are tombstones: the node stays in the graph for routing and is
    filtered from results, like an LSM tombstone until compaction (`rebuild`);
  - pure Python, so it is for learning the trade-offs, not for speed.

Vectors must be unit length; distance is 1 - dot.

    python hnsw_lite.py     # recall@10 and work vs ef_search on random vectors
"""

from __future__ import annotations

import heapq
import math
import random
from typing import Any, Callable

Vector = list[float]
Filter = Callable[[Any], bool]  # receives the item's metadata


def dist(a: Vector, b: Vector) -> float:
    return 1.0 - sum(x * y for x, y in zip(a, b))


class ExactIndex:
    """Brute force. O(n*d) per query, recall 1.0 by definition: the ground truth
    every ANN index is measured against, and the right choice for small n or
    for very selective filters (scan only the rows that pass)."""

    def __init__(self) -> None:
        self.vecs: dict[str, Vector] = {}
        self.meta: dict[str, Any] = {}
        self.distance_calls = 0

    def add(self, key: str, vec: Vector, meta: Any = None) -> None:
        self.vecs[key], self.meta[key] = vec, meta

    def delete(self, key: str) -> None:
        self.vecs.pop(key, None)
        self.meta.pop(key, None)

    def __len__(self) -> int:
        return len(self.vecs)

    def search(self, q: Vector, k: int, filter: Filter | None = None, **_: Any) -> list[tuple[str, float]]:
        scored = []
        for key, v in self.vecs.items():
            if filter and not filter(self.meta[key]):
                continue  # pre-filter: never compute distance for rows that can't be returned
            self.distance_calls += 1
            scored.append((dist(q, v), key))
        scored.sort()
        return [(key, 1.0 - d) for d, key in scored[:k]]


class HNSW:
    def __init__(self, M: int = 8, ef_construction: int = 64, ef_search: int = 32, seed: int = 0):
        self.M, self.M0 = M, 2 * M  # layer 0 gets twice the links, as in the paper
        self.ef_construction, self.ef_search = ef_construction, ef_search
        self.ml = 1.0 / math.log(M)  # level multiplier: P(level >= l) = M^-l
        self.rng = random.Random(seed)
        self.vecs: dict[str, Vector] = {}
        self.meta: dict[str, Any] = {}
        self.links: list[dict[str, list[str]]] = []  # links[layer][node] -> neighbours
        self.entry: str | None = None
        self.deleted: set[str] = set()
        self.distance_calls = 0

    def __len__(self) -> int:
        return len(self.vecs) - len(self.deleted)

    def _d(self, a: Vector, b: Vector) -> float:
        self.distance_calls += 1
        return dist(a, b)

    def _level(self) -> int:
        return int(-math.log(1.0 - self.rng.random()) * self.ml)

    def _search_layer(self, q: Vector, entries: list[str], ef: int, layer: int,
                      ok: Callable[[str], bool] | None = None) -> list[tuple[float, str]]:
        """Beam search. `ok` decides which nodes may enter the result set; all
        nodes are still traversed (filtered nodes still route). Returns
        (distance, key) ascending."""
        visited = set(entries)
        cand = [(self._d(q, self.vecs[e]), e) for e in entries]
        heapq.heapify(cand)
        res = [(-d, e) for d, e in cand if ok is None or ok(e)]  # max-heap via negation
        heapq.heapify(res)
        while cand:
            d, node = heapq.heappop(cand)
            if res and len(res) >= ef and d > -res[0][0]:
                break  # nearest unexplored is worse than our worst kept result
            for nb in self.links[layer].get(node, []):
                if nb in visited:
                    continue
                visited.add(nb)
                dn = self._d(q, self.vecs[nb])
                if len(res) < ef or dn < -res[0][0]:
                    heapq.heappush(cand, (dn, nb))
                    if ok is None or ok(nb):
                        heapq.heappush(res, (-dn, nb))
                        if len(res) > ef:
                            heapq.heappop(res)
        return sorted((-nd, e) for nd, e in res)

    def add(self, key: str, vec: Vector, meta: Any = None) -> None:
        if key in self.vecs:
            raise KeyError(f"{key} exists; delete and re-add (HNSW has no in-place update)")
        self.vecs[key], self.meta[key] = vec, meta
        level = self._level()
        while len(self.links) <= level:
            self.links.append({})
        for layer in range(level + 1):
            self.links[layer][key] = []
        if self.entry is None:
            self.entry = key
            return
        top = self._top_layer()
        ep = [self.entry]
        for layer in range(top, level, -1):  # greedy descent through layers above ours
            ep = [self._search_layer(vec, ep, 1, layer)[0][1]]
        for layer in range(min(level, top), -1, -1):
            found = self._search_layer(vec, ep, self.ef_construction, layer)
            cap = self.M0 if layer == 0 else self.M
            neighbours = [e for _, e in found[: self.M]]
            self.links[layer][key] = neighbours
            for nb in neighbours:  # bidirectional links, pruned to the cap
                lst = self.links[layer][nb]
                lst.append(key)
                if len(lst) > cap:
                    lst.sort(key=lambda x: self._d(self.vecs[nb], self.vecs[x]))
                    del lst[cap:]
            ep = [e for _, e in found]
        if level > top:
            self.entry = key

    def _top_layer(self) -> int:
        return max(i for i, layer in enumerate(self.links) if self.entry in layer)

    def mark_deleted(self, key: str) -> None:
        """Tombstone. The node keeps routing traffic; results skip it."""
        if key in self.vecs:
            self.deleted.add(key)

    def search(self, q: Vector, k: int, ef_search: int | None = None, filter: Filter | None = None,
               filter_mode: str = "inline") -> list[tuple[str, float]]:
        """filter_mode='inline' applies the predicate during the layer-0 beam
        search (results only admit passing nodes, traversal continues).
        'post' searches unfiltered and drops failures afterwards, which is what
        you get when the filter lives outside the index."""
        if self.entry is None:
            return []
        ef = max(ef_search or self.ef_search, k)
        ep = [self.entry]
        for layer in range(self._top_layer(), 0, -1):
            ep = [self._search_layer(q, ep, 1, layer)[0][1]]
        alive = lambda e: e not in self.deleted  # noqa: E731
        if filter and filter_mode == "inline":
            ok = lambda e: alive(e) and filter(self.meta[e])  # noqa: E731
            found = self._search_layer(q, ep, ef, 0, ok)
        else:
            found = [(d, e) for d, e in self._search_layer(q, ep, ef, 0, alive)]
            if filter:
                found = [(d, e) for d, e in found if filter(self.meta[e])]
        return [(e, 1.0 - d) for d, e in found[:k]]

    def rebuild(self) -> "HNSW":
        """Compaction: a fresh graph without tombstones."""
        fresh = HNSW(self.M, self.ef_construction, self.ef_search, seed=0)
        for key, vec in self.vecs.items():
            if key not in self.deleted:
                fresh.add(key, vec, self.meta[key])
        return fresh


def random_unit_vectors(n: int, dim: int, seed: int = 0) -> list[Vector]:
    rng = random.Random(seed)
    out = []
    for _ in range(n):
        v = [rng.gauss(0, 1) for _ in range(dim)]
        norm = math.sqrt(sum(x * x for x in v))
        out.append([x / norm for x in v])
    return out


def recall_vs_exact(index: HNSW, exact: ExactIndex, queries: list[Vector], k: int, ef: int,
                    filter: Filter | None = None, filter_mode: str = "inline") -> tuple[float, float]:
    """Mean recall@k against brute force, and mean distance computations per query."""
    hits, before = 0, index.distance_calls
    for q in queries:
        truth = {key for key, _ in exact.search(q, k, filter=filter)}
        got = {key for key, _ in index.search(q, k, ef_search=ef, filter=filter, filter_mode=filter_mode)}
        hits += len(truth & got)
    return hits / (k * len(queries)), (index.distance_calls - before) / len(queries)


if __name__ == "__main__":
    n, dim, k = 2000, 32, 10
    data = random_unit_vectors(n, dim, seed=1)
    queries = random_unit_vectors(50, dim, seed=2)
    exact, h = ExactIndex(), HNSW(M=8, ef_construction=64)
    for i, v in enumerate(data):
        exact.add(str(i), v, {"tenant": i % 20})
        h.add(str(i), v, {"tenant": i % 20})
    print(f"n={n} dim={dim} M=8 efC=64  (brute force = {n} distance computations per query)")
    for ef in (10, 20, 40, 80, 160):
        r, work = recall_vs_exact(h, exact, queries, k, ef)
        print(f"ef_search={ef:<4} recall@{k}={r:.3f}  distance computations/query={work:7.1f}")
    only_t3 = lambda m: m["tenant"] == 3  # noqa: E731  (5% selectivity)
    for mode in ("post", "inline"):
        rr = [len(h.search(q, k, ef_search=40, filter=only_t3, filter_mode=mode)) for q in queries]
        r, _ = recall_vs_exact(h, exact, queries, k, 40, filter=only_t3, filter_mode=mode)
        print(f"filter 5% {mode:<6} ef=40: mean results returned={sum(rr)/len(rr):.1f}/{k}  recall@{k}={r:.3f}")
