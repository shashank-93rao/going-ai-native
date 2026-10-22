# 18: RAG systems
> After this module you can design, build, operate and hill-climb a production retrieval-augmented generation system. You'll be able to pick chunking, embeddings, index and fusion with measurements, keep the index correct under replays, deletes, ACL changes and model migrations, and prove with error bars that a change helped.

## Why this matters

Most RAG systems are built in a weekend and debugged for a year. The weekend version embeds the question, takes the five nearest chunks and asks a model to answer. It demos well. Then it meets real users. Their questions are phrased as symptoms, so they match the *Symptoms* section instead of the fix. Restricted postmortems show up for people who can't open them. A doc deleted for legal reasons is still quoted. The runbook was fixed on Tuesday and the old command is served on Thursday. A new embedding model rolls out and recall quietly drops for half the corpus.

None of those are model problems. They're retrieval-quality problems you can only see with the right labels, and data-pipeline problems you already know how to solve: idempotent consumers, tombstones, compaction, online migrations, consistency SLOs, authorization at the data layer. This module goes deeper than [Module 03](../03-context-engineering/06-retrieval-agentic-search-vs-rag.md), which covered *whether* to use RAG versus agentic search and how to start evaluating it. Here you build and run the whole thing.

The course thesis applies stage by stage. Retrieval is checkable without a model (recall@k, evidence@k). Grounding is checkable deterministically (citations to shown chunks, verbatim commands). The ACL invariant is checkable as a property over arbitrary queries. Index correctness is checkable as convergence under any event order. Where a check exists, you can let the system act on its own. Where it doesn't (answer relevance, negation flips), you need a calibrated judge or a human, and the system should abstain rather than guess.

## The distributed-systems anchor

**A RAG index is a materialized view with a lossy, statistical query engine.**

| RAG concept | What you already know |
|---|---|
| Ingestion pipeline | CDC consumer maintaining a derived store |
| `(doc_id, version)` upsert with a high-water mark | Idempotent consumer; last-writer-wins register |
| Delete event with a version | Tombstone (Kafka compacted topics, Cassandra) |
| HNSW delete, then rebuild | LSM tombstone, then compaction |
| Re-embedding with a new model | Online schema migration: dual-write, backfill, shadow-read, cutover |
| Index lag SLO, reconciler | Replication lag SLO, anti-entropy repair |
| ACL filter inside retrieval | Row-level security, enforced in the query, not the app |
| Per-tenant namespace | Physical sharding by tenant |
| HNSW `ef_search` | A per-query latency/completeness knob |
| Post-filtered ANN starving results | A query planner choosing the wrong index and filtering after |
| BM25 + dense + RRF | Scatter-gather over two indexes, merged by rank |

**Where the analogy breaks.** A database index returns *exactly* the matching rows. A vector index returns *approximately* the nearest neighbours, and "nearest" is itself a learned, imperfect proxy for "answers the question". So you have two layers of statistical error stacked on top of ordinary pipeline correctness: ANN recall vs exact search, and embedding similarity vs relevance. Neither can be certified once. Both have to be measured continuously on sampled real queries, the way you'd monitor a cache hit rate, not the way you'd unit-test a B-tree.

## Learning goals
- [ ] Draw the eight-stage pipeline (ingest, chunk, embed, index, retrieve, rerank, generate, cite) and name each stage's failure mode, Q/C/A symptom and trace attribute.
- [ ] Decide when *not* to build RAG: long context with caching, agentic search, or a structured query.
- [ ] Compare chunkers with evidence@k at equal token budget, and choose an embedding model on your own labeled set rather than a leaderboard.
- [ ] Explain HNSW's M / ef_construction / ef_search trade-offs, estimate index memory, and measure recall@10 against exact search.
- [ ] Diagnose filtered-ANN starvation and choose between post-filter, in-traversal filter, partial indexes and partitions.
- [ ] Implement hybrid retrieval with RRF (k=60) and a reranker that fails open behind a deadline.
- [ ] Build an agentic retrieval loop with governors, identity bound outside the model, and a grounding gate on the final answer.
- [ ] Build an indexer whose state converges under replays, reordering and duplicates; whose deletes survive late events and are physically complete after compaction; and whose ACL changes need no re-embedding.
- [ ] Run a re-embedding migration with dual-write, backfill, a shadow-read gate and a reversible cutover.
- [ ] Build a labeled set with evidence spans, unanswerable rows and permission-dependent pairs. Report per-stage metrics and climb with paired-bootstrap CIs.

## Reading order
1. [01-the-rag-pipeline-as-a-system.md](01-the-rag-pipeline-as-a-system.md): stages, failure modes per stage, latency budget, and when not to build RAG.
2. [02-chunking-and-embeddings.md](02-chunking-and-embeddings.md): five chunking strategies measured with evidence@k, choosing an embedding model, and embedding drift as a type error.
3. [03-indexes-and-vector-stores.md](03-indexes-and-vector-stores.md): exact vs HNSW vs IVF/PQ, memory math, why filtered ANN is hard, and pgvector vs a dedicated store.
4. [04-hybrid-search-fusion-and-reranking.md](04-hybrid-search-fusion-and-reranking.md): BM25 + dense, RRF, cross-encoder rerankers, candidate counts and latency.
5. [05-query-side-techniques-and-agentic-rag.md](05-query-side-techniques-and-agentic-rag.md): rewriting, HyDE, decomposition, routing, governed agentic retrieval, Self-RAG/CRAG/GraphRAG.
6. [06-ingestion-freshness-and-correctness.md](06-ingestion-freshness-and-correctness.md): CDC indexing, idempotent upserts, tombstones, deletion requests, re-embedding migrations, staleness SLOs, permission-aware retrieval.
7. [07-evaluating-and-hill-climbing-rag.md](07-evaluating-and-hill-climbing-rag.md): labeled sets, retrieval and generation metrics, RAGAS vs calibrated judges, abstention, ablations, production monitoring.
- [examples.md](examples.md), [exercises.md](exercises.md), [references.md](references.md), [code/](code/README.md)

## The running example

An internal **"ask the platform docs + postmortems" assistant** for an engineering org. The corpus in `code/data/docs/` is 48 synthetic documents written for this module: 18 runbooks, 12 ADRs, 14 postmortems and 4 guides, owned by five teams (payments, platform, data, identity, sre). Four documents are restricted to specific teams, for example an identity-only postmortem about signing-key material in logs. `code/data/questions.jsonl` has 44 labeled questions: 38 answerable, 6 unanswerable for the asking team, including permission-dependent pairs where the same question has a different correct answer depending on who asks.

**Honesty note.** The code is stdlib-only and runs offline. The embedding is a deterministic hashed character n-gram TF-IDF (`embed.py`). It captures morphology, not meaning, and it stands in for a real embedding model, which plugs in through the same interface. The generator, reranker and agent in the measured runs are deterministic `FakeClient` stand-ins whose behaviour is documented in the code. Every number in this module is real output from that code on that corpus. Treat the numbers as a demonstration of method, not as benchmarks of any product. With `ANTHROPIC_API_KEY` set, the scripts call Claude through `ainative_kit` instead.

## Prerequisites
- [Module 03: Context engineering](../03-context-engineering/README.md), especially [06-retrieval-agentic-search-vs-rag](../03-context-engineering/06-retrieval-agentic-search-vs-rag.md) (BM25 baseline, Contextual Retrieval numbers, the first eval tiers).
- [Module 07: Loops](../07-loops/README.md) for governors, used in agentic RAG.
- [Module 10](../10-evals-fundamentals/README.md), [11](../11-llm-as-judge/README.md) and [12](../12-hill-climbing/README.md) for datasets, judges and paired statistics.
- Helpful: [Module 16: Security and containment](../16-security-and-containment/README.md) for prompt injection via retrieved content and the confused deputy.

## Key takeaways
- **Measure evidence@k, not just recall@k.** Doc-level labels hide the most common failure: right document, wrong section. Label a verbatim answer span for every question.
- **Compare components at equal token budget, with paired CIs.** On 40 questions, ±8 points is noise. Most "improvements" are inside it.
- **Hybrid (BM25 + dense, fused with RRF k=60) is the default.** Keep a reranker only if it moves *your* evidence@k, and put a deadline with fail-open on it.
- **Filter inside retrieval, never after.** Post-filtered ANN returns fewer than k for small groups, and post-fusion filtering turns a missing line of code into a leak. Count `results_returned < k`.
- **The index is a materialized view.** Use versioned idempotent upserts, versioned tombstones, make-before-break replacement, and content-addressed embeddings so ACL changes are free. Test convergence under any event order.
- **A delete isn't done until compaction and cache purge.** Tombstoned vectors and cached embeddings are copies of the data.
- **An embedding model change is a migration.** Dual-write, backfill with version checks, gate on shadow-read quality, cut over behind a pointer, keep rollback.
- **Identity comes from verified claims, never from the model.** A leaked chunk can't be un-leaked, so it's a security incident, not a relevance bug.
