# 18-rag-systems code

Stdlib plus `ainative_kit`. Everything runs offline. Model calls go through `ainative_kit`. With no `ANTHROPIC_API_KEY` (or with `AINATIVE_FAKE=1`), scripts fall back to deterministic `FakeClient` stand-ins. Run from the course root.

```bash
.venv/bin/python -m pytest -q 18-rag-systems/code      # 57 tests, offline, ~7 s
```

| File | What it is | Run it |
|---|---|---|
| `chunking.py` | `Doc`/`Chunk` with ACL, version and stable ids; fixed-window, heading-aware (with contextual headers) and parent-child (section or whole-doc parents) chunkers | `PYTHONPATH=shared .venv/bin/python 18-rag-systems/code/chunking.py` |
| `embed.py` | `Embedder` protocol; `HashedNgramEmbedder` (deterministic toy: hashed char 3-to-5-gram TF-IDF, a stand-in with no semantics); `CachingEmbedder` (content-addressed, with `forget` for deletions); `VoyageEmbedder` (real API, not used by tests); Matryoshka `truncate` | `... embed.py "consumer keeps rebalancing"` |
| `hnsw_lite.py` | A small HNSW (M, ef_construction, ef_search, tombstones, rebuild, inline vs post filtering) and a brute-force `ExactIndex`; recall@10 vs exact and the ef_search curve | `... hnsw_lite.py` |
| `hybrid.py` | BM25, RRF (k=60), `HybridRetriever` with ACL filtering inside both retrievers, `LLMReranker` with fail-open handling, and a fake reranker | `... hybrid.py "sorry, too many clients already" --team platform` |
| `rag_pipeline.py` | Retrieve, prompt (documents first, question last), generate, cite; an extractive fake generator with an abstention threshold | `... rag_pipeline.py "how long are idempotency keys stored" --team payments` |
| `ingest.py` | `DocIndex`: versioned idempotent upserts, tombstones, make-before-break, compaction, ACL-only updates with no re-embedding, model-id guard, reconcile; `Migration`: dual-write, backfill, shadow compare, cutover/abort | `... ingest.py` |
| `rag_eval.py` | recall@k, MRR, nDCG@k, evidence@k, citation grounding, abstention scoring, paired bootstrap, and the component-ablation report | `... rag_eval.py` |
| `agentic_rag.py` | Retrieval-tool loop with governors (steps, searches, context, duplicate query, no new evidence), identity bound outside the model, and a grounding gate on the final answer | `... agentic_rag.py` |
| `data/docs/*.md` | 48 synthetic docs (runbooks, ADRs, postmortems, guides) with front matter: `id`, `kind`, `team`, `acl`, `version` | |
| `data/questions.jsonl` | 44 labeled questions: `team`, `category`, `answerable`, `relevant_docs`, verbatim `evidence` spans | |

(`...` = `PYTHONPATH=shared .venv/bin/python 18-rag-systems/code/`)

## Tests

| Test file | Pins |
|---|---|
| `test_corpus_data.py` | Labels are valid: evidence spans exist verbatim, relevant docs are readable by the asking team, unanswerable and permission-dependent rows exist |
| `test_chunking.py` | Stable ids, ACL/version propagation, header indexed but not shown, fixed windows can split a command, parent expansion de-duplicates |
| `test_embed.py` | Determinism, unit norm, morphology without semantics, model id changes on refit, cache hits and `forget` |
| `test_hnsw_lite.py` | recall@10 vs exact rises with ef_search, as does work (still below brute force); post-filter starves while inline filter returns k; tombstones hide until rebuild |
| `test_hybrid.py` | RRF arithmetic; provenance; restricted docs visible only to their teams; **property test: ACL never leaks for any query, team or mode**; reranker drops unknown ids, appends missing, fails open |
| `test_ingest.py` | **Property test: any permutation with duplicates converges to the same fingerprint**; replay is a no-op; deletes never resurface; deletion is complete only after compaction and cache purge; ACL-only change re-embeds nothing; ACL filter never leaks on labeled questions; model mismatch refused; backfill never overwrites a newer dual-write; the migration gate cuts over a good model and aborts a bad one |
| `test_rag_eval.py` | Rank metrics; evidence@k; grounding accepts and rejects; abstention scoring; bootstrap; whole-doc parents trade words for evidence; a lying generator fails grounding; **characterization: a negation flip fools lexical grounding** |
| `test_agentic_rag.py` | Multi-hop finds what single-shot missed; duplicate query → STALLED; search cap → BUDGET; ungrounded answer → abstention; the model can't widen its permissions (and the attempt is logged) |

## Swapping in real components

- **Embeddings.** Implement `embed.Embedder` (`model_id`, `dim`, `embed(texts, input_type)`), or use `VoyageEmbedder` with `VOYAGE_API_KEY`. Return unit vectors. Change `model_id` whenever vectors stop being comparable.
- **Reranker.** Anything with `rerank(query, chunks) -> list[chunk_id]`. Keep the fail-open and unknown-id handling from `LLMReranker`.
- **Generator / agent.** `rag_pipeline.answer` and `agentic_rag.run` take any `LLMClient`. `get_client()` returns the real Anthropic client when a key is set.

The stand-ins are deliberately simple. The toy embedder doesn't know that "out of space" means "DiskPressure", and the fake reranker is lexical. So results that depend on semantics, such as reranker gains or HyDE, won't show up offline. Re-run the ablation with real components before drawing conclusions about them.
