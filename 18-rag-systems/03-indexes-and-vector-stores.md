# 03: Indexes and vector stores

## The idea

A vector index answers "the k nearest vectors to q" without comparing q to everything. **Exact** search (a brute-force scan) is O(n·d) per query, with recall of 1.0 by definition. **Approximate nearest neighbour (ANN)** indexes give up a little recall for a lot of speed. Every ANN index trades three things against each other: **recall, latency and memory**, plus a fourth that gets forgotten until production: **filtered-query behaviour**.

There are three families you'll meet:

- **HNSW** (Hierarchical Navigable Small World). A multi-layer proximity graph. A query descends greedily through sparse upper layers, then runs a beam search of width `ef` on the dense bottom layer. The paper's claim is "logarithmic complexity scaling", from the upper layers plus scale separation ([Malkov & Yashunin, arXiv 1603.09320](https://arxiv.org/abs/1603.09320)).
- **IVF** (inverted file). k-means the vectors into `lists` clusters, and at query time scan only the `probes` nearest clusters.
- **PQ / quantization.** Compress each vector (int8, binary, or product-quantized codes) to cut memory, then re-rank the top candidates with full-precision vectors.

## Why it matters

The ANN defaults that look fine in a benchmark fail in a specific way once you add an ACL filter. pgvector's README says it directly: "With approximate indexes, filtering is applied *after* the index is scanned." Its own example: if a condition matches 10% of rows, HNSW with the default `hnsw.ef_search` of 40 returns about 4 matching rows on average ([pgvector README, v0.8.7](https://github.com/pgvector/pgvector)). Your RAG system asks for the top 10 chunks the caller may read, gets 4, and the answer quality drops only for users on small teams. That's the hardest kind of bug to notice, because it depends on who's asking.

## How it works

### HNSW parameters

| Parameter | Set when | Effect | pgvector default |
|---|---|---|---|
| `M` (links per node; layer 0 gets 2M) | Build | More links: higher recall ceiling, more memory, slower build | `m = 16` |
| `ef_construction` | Build | Wider beam while inserting: better graph, slower build | `64` |
| `ef_search` | Query (any time) | Wider beam at query time: higher recall, more distance computations | `hnsw.ef_search = 40` |

Pinecone's Faiss walkthrough adds two useful facts. `ef_construction` and `ef_search` don't affect memory, only `M` does. And on SIFT1M, their sweep spans "from 80%-1ms to 100%-50ms" for recall vs search time ([Pinecone, "HNSW"](https://www.pinecone.io/learn/series/faiss/hnsw/)). The level for each node is drawn with multiplier `mL = 1/ln(M)`, so P(level ≥ l) = M^-l. `hnsw_lite.py` uses exactly that.

**Memory, back of envelope.** OpenSearch's k-NN docs estimate HNSW at `1.1 * (4 * dimension + 8 * M)` bytes per vector for float32 ([OpenSearch k-NN index docs](https://docs.opensearch.org/2.9/search-plugins/knn/knn-index/)). For 10M chunks at 1024 dims with M=16, that's 1.1 × (4096 + 128) × 10M ≈ **46 GB**, before replicas. The vectors are about 97% of that, which is why quantization and Matryoshka truncation ([02](02-chunking-and-embeddings.md)) matter more than graph tuning.

### IVF and PQ

pgvector's starting points for IVFFlat: `lists = rows / 1000` up to 1M rows and `sqrt(rows)` above that; `probes = sqrt(lists)`. Build the index *after* the table has data, because the clusters are trained on what's there. HNSW "has better query performance than IVFFlat (in terms of speed-recall tradeoff), but has slower build times and uses more memory" ([pgvector README](https://github.com/pgvector/pgvector)).

Product quantization splits each vector into `m` subvectors and replaces each with the id of its nearest centroid (256 centroids = 8 bits). In Pinecone's Faiss example, a 128-dim float vector goes from 4096 bits to 64 bits. On SIFT1M, IndexPQ used 98.4% less memory than the flat index, but recall was only about 50%. IVFPQ reached 52% at `nprobe=48` ([Pinecone, "Product Quantization"](https://www.pinecone.io/learn/series/faiss/product-quantization/)). So **quantize for candidate generation, then re-rank with full vectors.** pgvector documents exactly that pattern for binary quantization: index `binary_quantize(embedding)`, fetch 20 candidates by Hamming distance, re-sort by the original vectors.

### Filtering: why filtered ANN is hard

| Strategy | How | Failure mode |
|---|---|---|
| Post-filter | ANN top-ef, then drop rows that fail | Returns fewer than k when the filter is selective; can return zero |
| Pre-filter + exact | Find allowed ids, brute-force only those | Fine when the allowed set is small; slow when it's large |
| In-traversal filter | Traverse the graph, admit only passing nodes to the result set | Must walk further for selective filters; graph can disconnect |
| Partition | Separate index (or partition / namespace) per tenant or filter value | Index count; cross-partition queries |

Vendors converge on hybrids of these. Weaviate switches to a flat (brute-force) search "when a filter becomes too restrictive", with the cutoff "configured at ~15% of the dataset". Its default filter strategy since v1.34 is ACORN, in which "objects that do not meet the filters are ignored in distance calculations" ([Weaviate filtering docs](https://docs.weaviate.io/weaviate/concepts/filtering)). The ACORN paper reports 2 to 1,000x higher throughput than prior methods at fixed recall ([Patel et al., arXiv 2403.04871](https://arxiv.org/abs/2403.04871)). pgvector added iterative index scans in 0.8.0 (`hnsw.iterative_scan = strict_order | relaxed_order`, bounded by `hnsw.max_scan_tuples`, default 20,000). Its README recommends partial indexes for filters with few distinct values and partitioning for filters with many.

### The distributed-systems anchor

| Vector index concept | What you already know |
|---|---|
| Exact scan | Full table scan: always correct, O(n) |
| HNSW | A skip list generalized to a graph: express lanes on top, local walk at the bottom |
| `ef_search` | A per-query knob trading latency for completeness, like `LIMIT` with a read-repair budget |
| IVF | Hash/range partitioning plus scatter-gather to the `probes` nearest partitions |
| PQ | Lossy compression of the column, then a second pass on the real rows |
| Post-filter starvation | A secondary-index miss: the planner used the wrong index and then filtered |
| HNSW delete = tombstone | LSM tombstones: hidden from reads, physically present until compaction ([06](06-ingestion-freshness-and-correctness.md)) |
| HNSW build cost | B-tree bulk load vs incremental inserts: bulk is faster and makes a better structure |

**Where the analogy breaks.** A B-tree lookup is exact and deterministic. An ANN lookup's correctness is statistical, and it depends on the data distribution and the query. Two queries against the same index can have very different recall. So you can't certify an index once. You measure recall@k against exact search on a sample of real queries, continuously.

### pgvector or a dedicated store

| Question | Lean pgvector | Lean dedicated (Pinecone, Weaviate, Qdrant, OpenSearch...) |
|---|---|---|
| Corpus size | Up to low tens of millions of vectors on one node | Hundreds of millions+, or needs sharding today |
| ACL/metadata filters | Rich SQL predicates, joins to your ACL tables, same transaction | Simple metadata filters; per-tenant namespaces |
| Ops | You already run Postgres: backups, failover, IAM | You'd rather buy than operate; serverless pricing |
| Consistency | Transactional with the source rows | Eventually consistent; async upserts |
| Hybrid search | `tsvector` + vector in one query, fused yourself | Often built in (BM25 + vector + fusion) |
| Tenant isolation | Row-level security, partitions | Namespaces: Pinecone recommends "one namespace per tenant", which gives "physical isolation" and almost-instant tenant deletion ([Pinecone multitenancy](https://docs.pinecone.io/guides/index-data/implement-multitenancy)) |
| Index rebuild cost | Competes with OLTP for memory and IO | Isolated |

The running example's [ADR-015](code/data/docs/adr-015-pgvector-docs-search.md) chooses pgvector for about 40k chunks, with explicit revisit triggers (5M chunks or p95 > 150 ms). That's the shape a good decision takes: a default, plus the numbers that would change it.

## Worked example: measuring the trade-off yourself

`hnsw_lite.py` builds a small HNSW and a brute-force `ExactIndex` over 2,000 random unit vectors (32 dims), then measures recall@10 against exact search. Real output:

```text
$ PYTHONPATH=shared .venv/bin/python 18-rag-systems/code/hnsw_lite.py
n=2000 dim=32 M=8 efC=64  (brute force = 2000 distance computations per query)
ef_search=10   recall@10=0.530  distance computations/query=  177.9
ef_search=20   recall@10=0.700  distance computations/query=  271.7
ef_search=40   recall@10=0.876  distance computations/query=  427.7
ef_search=80   recall@10=0.958  distance computations/query=  686.9
ef_search=160  recall@10=0.990  distance computations/query= 1062.6
filter 5% post   ef=40: mean results returned=1.7/10  recall@10=0.174
filter 5% inline ef=40: mean results returned=10.0/10  recall@10=1.000
```

What to take from it:

- **The curve is the product.** Going from recall 0.876 to 0.990 costs 2.5x the work. Where you sit on it is a business decision, and it should be written down with the number.
- **Random vectors are the worst case.** Real embeddings are clustered and low intrinsic dimension, so HNSW does much better on them. Don't reuse these numbers for capacity planning. Reuse the *method*: sample production queries, run exact and ANN, compare.
- **Post-filtering starves.** With a 5% filter (one tenant in twenty), the post-filtered search returned 1.7 of 10 requested results. That's the pgvector README's warning reproduced. In-traversal filtering returned all 10 at recall 1.0, at the cost of walking more of the graph.

**Bad version.** `SELECT ... WHERE team = ANY($teams) ORDER BY embedding <=> $q LIMIT 10` on pgvector with default settings, and nobody counts the returned rows. The identity team (a small share of docs) quietly gets 2 to 4 results per query.

**Good version.** Count results per query and alert when it's below k. Turn on iterative scans (`SET hnsw.iterative_scan = relaxed_order`), or for very selective ACLs use a partial index or partition per restricted group. Record "returned < k" as a metric next to latency. `test_hnsw_lite.py::test_post_filter_starves_results_inline_filter_does_not` pins this behaviour.

## Pitfalls

- **Benchmarking ANN without a filter.** Detect it: your load test queries have no `WHERE`. Replay real queries with real caller ACLs.
- **Never measuring recall in production.** Detect it: no job compares ANN to exact on sampled queries. Run one nightly on a few hundred queries; alert on drift.
- **Treating deletes as free.** Detect it: index memory grows while row count is flat. HNSW deletes are tombstones; schedule rebuilds or vacuums.
- **Building IVF on an empty or tiny table.** Detect it: recall collapses after the table grows. Rebuild IVF when the data distribution changes.
- **Quantizing without a re-rank step.** Detect it: recall drops after a "memory optimisation". Quantize for candidates and re-score with full vectors.
- **Sizing on vector count alone.** Detect it: you forgot replicas and the 8·M bytes of graph per vector. Use the formula above and add headroom.

## In your day job

- Add `results_returned < k` as a counter on your retrieval endpoint, tagged by caller team.
- Write the ef_search (or probes) value and its measured recall@10 into your service's runbook, next to the latency SLO it buys.
- Before choosing a vector store, fill in the pgvector-vs-dedicated table for your corpus, with numbers.
- Schedule a recall-vs-exact job: 500 sampled production queries, nightly, alert below your floor.
