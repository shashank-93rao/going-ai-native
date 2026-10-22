# 04: Hybrid search, fusion and reranking

## The idea

Production retrieval is a **two-stage funnel**. Stage one generates candidates cheaply and with high recall: run BM25 and dense search in parallel and fuse their rankings. Stage two re-scores a few dozen to a few hundred candidates with an expensive, more precise model (a cross-encoder reranker) and keeps the top handful for the prompt.

- **BM25** wins on rare exact tokens: alert names, config keys, error strings, ticket ids.
- **Dense** wins on paraphrase: "fetching it right after gives not found" vs "follow-up GET returns 404".
- **Fusion** combines them without having to calibrate their scores against each other.
- **Reranking** reads the query and each candidate *together*, which neither first-stage retriever can do.

## Why it matters

Each retriever alone has a failure class the other covers. Anthropic's Contextual Retrieval study measured the stack: top-20 retrieval failure fell from 5.7% (embeddings) to 2.9% (contextual embeddings plus contextual BM25) to 1.9% with reranking. Their pipeline retrieved the top 150 candidates and reranked them down to 20 with Cohere's reranker ([Anthropic, "Introducing Contextual Retrieval"](https://www.anthropic.com/engineering/contextual-retrieval)). The full table is in [Module 03](../03-context-engineering/06-retrieval-agentic-search-vs-rag.md).

BEIR's zero-shot results show the same shape across 18 datasets: BM25 is "a robust baseline", and re-ranking and late-interaction models had the best average zero-shot performance, "at high computational cost" ([Thakur et al., BEIR](https://arxiv.org/abs/2104.08663)).

## How it works

### Reciprocal Rank Fusion

BM25 scores are unbounded and corpus-dependent. Cosines cluster in a narrow band that depends on the model. Adding them needs per-corpus normalization that drifts. RRF throws scores away and uses only ranks:

```text
RRF(d) = Σ over rankings r of  1 / (k + rank_r(d))      rank starts at 1, k = 60
```

It comes from Cormack, Clarke and Büttcher, "Reciprocal Rank Fusion outperforms Condorcet and individual Rank Learning Methods" (SIGIR 2009, pp. 758 to 759). They fixed k=60 in a pilot and reported RRF beating every input system and Condorcet Fuse on TREC data ([Google Research listing](https://research.google/pubs/pub36196/), [PDF](https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf)). Elasticsearch's RRF uses the same formula, with `rank_constant` defaulting to 60 ([Elastic docs](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/reciprocal-rank-fusion)).

What k does: with k=60, rank 1 scores 1/61 ≈ 0.0164 and rank 10 scores 1/70 ≈ 0.0143. The curve is flat, so **agreement beats a single first place**. A doc ranked 2nd by both retrievers (2/62 ≈ 0.0323) beats a doc ranked 1st by one and absent from the other (0.0164). Smaller k makes top ranks dominate.

`hybrid.rrf()` is nine lines, and `test_rrf_formula_and_k60` pins the arithmetic.

### Rerankers

A **bi-encoder** (embedding model) encodes query and document separately, which is why you can precompute document vectors. A **cross-encoder** reranker "jointly process[es] a pair of query and document", which "allows more accurate relevancy prediction than embedding models" ([Voyage reranker docs](https://docs.voyageai.com/docs/reranker)). The price is that nothing can be precomputed, so you can only afford it on candidates.

Operational limits to design around (checked 2026-10-22; check again before you rely on them):

| Provider | Model(s) | Limits that shape your design |
|---|---|---|
| Cohere | `rerank-v5.0-pro`, `rerank-v5.0-fast` | Up to 10,000 docs per request; long docs truncated to `max_tokens_per_doc` (default 4096) ([Cohere best practices](https://docs.cohere.com/docs/reranking-best-practices)) |
| Voyage | `rerank-3`, `rerank-3-lite` | ≤ 1,000 docs; query ≤ 8,000 tokens; query + any one doc ≤ 32,000 tokens; total (query tokens × docs + all doc tokens) ≤ 600K ([Voyage reranker docs](https://docs.voyageai.com/docs/reranker)) |

An LLM can rerank too, by being asked for a JSON ranking. `hybrid.LLMReranker` does this so it runs offline on `FakeClient`. It costs more and is slower than a dedicated cross-encoder. Either way, the wrapper needs the same failure handling:

- **Unknown ids dropped.** The model invents `made-up#id`, and that id never reaches the prompt.
- **Missing ids appended in fused order.** The model returns a partial list, and nothing is lost.
- **Garbage output fails open** to the fused order, and the fallback is counted. Reranking is a precision optimisation, and its outage shouldn't become a retrieval outage.

### How many candidates, and the latency budget

*Course synthesis*, starting points to sweep on your eval:

| Knob | Start | Why |
|---|---|---|
| Candidates per retriever | 50 to 150 | Recall@candidates must be near 1.0, or the reranker can't help |
| Reranked → prompt | 5 to 20 | Anthropic found top-20 beat top-10 and top-5 in their setup; context rot pushes the other way |
| RRF k | 60 | Rarely worth tuning before everything else |

Measure **recall@candidates** separately from **recall@final**. If recall@150 is 0.99 and recall@20 is 0.85, the reranker is the lever. If recall@150 is 0.80, no reranker will save you, so fix chunking, embeddings or the query.

For latency, run BM25 and ANN concurrently (`max`, not sum). Give the reranker a hard deadline with fallback to fused order, and record `rerank_fallback=true` in the trace. That's the same circuit-breaker logic you'd put around any optional dependency on the hot path.

## Worked example: hybrid on the platform-docs corpus

**Bad version: dense only, because "embeddings are semantic".** Here's a question that is an exact error string. Real output from `hybrid.py`:

```text
$ PYTHONPATH=shared .venv/bin/python 18-rag-systems/code/hybrid.py "sorry, too many clients already" --team platform
--- bm25
  0.0164  rb-pgbouncer-exhaustion#symptoms             {'bm25': 1}
  0.0161  pm-2025-044-poison-message#root-cause        {'bm25': 2}
  0.0159  rb-rate-limiter-false-positives#symptoms     {'bm25': 3}
--- dense
  0.0164  rb-pgbouncer-exhaustion#symptoms             {'dense': 1}
  0.0161  rb-api-5xx-spike#symptoms                    {'dense': 2}
  0.0159  adr-012-idempotency-keys#context             {'dense': 3}
--- hybrid
  0.0328  rb-pgbouncer-exhaustion#symptoms             {'bm25': 1, 'dense': 1}
  0.0318  pm-2025-044-poison-message#root-cause        {'bm25': 2, 'dense': 4}
  0.0302  rb-api-5xx-spike#symptoms                    {'bm25': 11, 'dense': 2}
```

Both retrievers get rank 1 right here. Look at the provenance column instead. `Hit.sources` records each retriever's rank, so you can see *why* a chunk is in the top 3. `rb-api-5xx-spike#symptoms` is there on dense's word alone (BM25 ranked it 11th). Log this per request. When a bad chunk shows up, it tells you which retriever to blame.

**The ablation** (real output from `rag_eval.py`, 38 answerable questions, k=5):

```text
config                                     recall@5    MRR  nDCG@5  evid@5  words   evid@5 delta vs row 1 [95% CI]
bm25 heading + header                         0.965  0.974   0.955   0.789    100   +0.000 [-0.079, +0.079]
dense heading + header                        0.943  1.000   0.953   0.816    100   +0.026 [-0.053, +0.132]
hybrid RRF heading + header                   0.965  0.987   0.964   0.816    101   +0.026 [-0.053, +0.105]
hybrid RRF + rerank                           0.965  0.987   0.966   0.816    104   +0.026 [-0.053, +0.105]
```

Honest reading:

- **Dense has the best MRR (1.000) and the worst recall@5 (0.943).** When it finds the doc, it ranks it first. When it doesn't, BM25 does. Hybrid keeps BM25's recall and most of dense's MRR, and it has the best nDCG. That's the expected shape, and the reason hybrid is the default.
- **The differences are inside the error bars.** On 38 questions, none of these four rows is distinguishable from another. That's a real result: on a small, identifier-heavy corpus, BM25 is already strong (as BEIR would predict). It doesn't mean hybrid is useless. It means *this eval can't detect* a difference of this size. [07](07-evaluating-and-hill-climbing-rag.md) covers how many questions you'd need.
- **The reranker stand-in adds nothing,** and that's expected. `fake_rerank_responder` scores by query-term coverage, which is lexical, like BM25. A real cross-encoder learns question-to-answer relevance. It would be the component most likely to promote the *Mitigation* section over the *Symptoms* section for a symptom-phrased question. Swap in a real reranker with `LLMReranker(get_client())`, or wrap Cohere or Voyage in the same `rerank(query, chunks) -> ids` interface, and re-run the table. Don't trust a reranker that hasn't moved your own numbers.

**Good version.** Hybrid by default, with ACL filters applied *inside* both retrievers (`HybridRetriever.search` filters BM25 before scoring and HNSW during traversal, then asserts the invariant on the output). Per-retriever ranks logged, and a reranker with a deadline and a fail-open fallback, kept only if it moves evidence@k on your labeled set beyond the noise.

## Pitfalls

- **Score-level fusion with hand-tuned weights.** Detect it: `0.7 * cosine + 0.3 * bm25_normalized` in the code, and weights that "need retuning" after re-indexing. Use RRF unless you have a learned fusion model and an eval to train it.
- **Filtering after fusion.** Detect it: the ACL check runs on the fused list. Filter in each retriever. A post-fusion filter can return fewer than k and turns a missing line into a leak.
- **Reranking too few candidates.** Detect it: recall@candidates is well below 1.0. Raise the candidate count before you touch the reranker.
- **A reranker on the critical path with no deadline.** Detect it: p99 retrieval latency tracks the reranker vendor's status page. Add a timeout and fail open.
- **Trusting a reranker the leaderboard likes.** Detect it: no before/after evidence@k on your set. Measure.

## In your day job

- Make hybrid (BM25 + dense + RRF k=60) the default in any internal RAG service, and log per-retriever ranks on every hit.
- Report recall@candidates and recall@final separately on your dashboard. The gap between them tells you whether a reranker is worth buying.
- Wrap the reranker call in a deadline with fail-open, and count fallbacks as an SLI.
- When someone proposes a new reranker or embedder, ask for the paired delta with a CI on your labeled set ([Module 12](../12-hill-climbing/README.md)).
