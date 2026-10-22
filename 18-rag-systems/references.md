# References

Grouped by what you'd use them for. "Read" dates are when this module checked the page. Vendor docs change, so re-check limits and model names before relying on them.

## Pipeline, failure framing, when not to use RAG

- **Anthropic, "Introducing Contextual Retrieval"** (2024-09). https://www.anthropic.com/engineering/contextual-retrieval (read 2026-10-22)
  *Take:* under 200,000 tokens (~500 pages), consider skipping RAG and putting the knowledge base in the prompt, with caching cutting latency by more than 2x and cost by up to 90%. Hybrid BM25 + embeddings with rank fusion; top 150 reranked to 20 with Cohere's reranker; failure rate 5.7% → 3.7% → 2.9% → 1.9%; top-20 beat top-10 and top-5; "$1.02 per million document tokens" for contextualization; Gemini and Voyage embeddings did best. Full numbers are tabled in Module 03, file 06.
- **Anthropic, prompting best practices, long-context section.** https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices (read 2026-10-22)
  *Take:* put long documents at the top, above the query; "queries at the end can improve response quality by up to 30 percent in tests"; wrap documents in `<document>` with `<source>` and `<document_content>`; ask for quotes first.
- **Anthropic, "Effective context engineering for AI agents."** https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents (read 2026-10-22)
  *Take:* pre-inference embedding retrieval vs just-in-time tool retrieval; Claude Code's hybrid (CLAUDE.md up front, glob/grep at runtime); "runtime exploration is slower than retrieving pre-computed data."
- **Chroma, "Context Rot: How Increasing Input Tokens Impacts LLM Performance"** (Hong, Troynikov, Huber, 2025-07-14). https://www.trychroma.com/research/context-rot (read 2026-10-22)
  *Take:* 18 models; performance varies with input length "even on simple tasks"; "even a single distractor reduces performance"; focused (~300 token) prompts beat full (~113k) prompts on LongMemEval across all models. Long context is a hypothesis to test, not a free win.
- **Jason Liu, "There are only 6 RAG evals"** (2025-05-19). https://jxnl.co/writing/2025/05/19/there-are-only-6-rag-evals/ (read 2026-10-22)
  *Take:* Q/C/A and the six relationships (C|Q, A|C, A|Q, C|A, Q|C, Q|A); tier 1 is retrieval precision and recall; "Answer seems wrong? Check faithfulness (A|C)."
- **Jason Liu, "RAG is more than just embedding search"** (2023-09-17). https://python.useinstructor.com/blog/2023/09/17/rag-is-more-than-just-embedding-search/ (read 2026-10-22)
  *Take:* single-embedding RAG as "demoware"; query/document embedding mismatch; multiple backends; query understanding with structured outputs (date ranges, filters, routing).

## Chunking and embeddings

- **Anthropic, Embeddings guide.** https://platform.claude.com/docs/en/build-with-claude/embeddings (read 2026-10-22)
  *Take:* Anthropic offers no embedding model and points to Voyage AI; `voyage-4` family (1024 default; 256/512/2048), `voyage-code-4`, domain models, `voyage-context-4` contextualized chunk embeddings; `input_type` query vs document; `output_dtype` int8/binary (4x/32x smaller); Matryoshka truncation then renormalize; Voyage vectors are unit-normalized.
- **Günther et al., "Late Chunking: Contextual Chunk Embeddings Using Long-Context Embedding Models"**, arXiv 2409.04701. https://arxiv.org/abs/2409.04701 (abstract read 2026-10-22)
  *Take:* embed the whole document, then chunk "after the transformer model and just before mean pooling."
- **Kusupati et al., "Matryoshka Representation Learning"**, arXiv 2205.13147. https://arxiv.org/abs/2205.13147 (abstract read 2026-10-22)
  *Take:* one vector usable at several prefix lengths; "up to 14x smaller embedding size for ImageNet-1K classification at the same level of accuracy." That's an image result, so measure text retrieval yourself.
- **Muennighoff et al., "MTEB: Massive Text Embedding Benchmark"**, arXiv 2210.07316. https://arxiv.org/abs/2210.07316 (abstract read 2026-10-22)
  *Take:* 8 tasks, 58 datasets, 112 languages; "no particular text embedding method dominates across all tasks."
- **Thakur et al., "BEIR: A Heterogenous Benchmark for Zero-shot Evaluation of Information Retrieval Models"**, arXiv 2104.08663 (NeurIPS 2021 Datasets & Benchmarks). https://arxiv.org/abs/2104.08663 (abstract read 2026-10-22)
  *Take:* 18 datasets; "BM25 is a robust baseline"; re-ranking and late interaction best zero-shot at high cost; dense retrievers often underperform out of domain.

## Indexes and vector stores

- **Malkov & Yashunin, "Efficient and robust approximate nearest neighbor search using Hierarchical Navigable Small World graphs"**, arXiv 1603.09320. https://arxiv.org/abs/1603.09320 (abstract read 2026-10-22)
  *Take:* layered proximity graphs, "logarithmic complexity scaling", heuristic neighbour selection for high recall on clustered data. `hnsw_lite.py` follows the structure without the heuristic.
- **pgvector README** (v0.8.7). https://github.com/pgvector/pgvector (read 2026-10-22)
  *Take:* HNSW defaults `m=16`, `ef_construction=64`, `hnsw.ef_search=40`; IVFFlat `lists` = rows/1000 (≤1M) or sqrt(rows), `probes` = sqrt(lists); dimension limits (vector 2,000, halfvec 4,000, bit 64,000); "filtering is applied *after* the index is scanned" and the 10%-filter example; iterative scans (`strict_order`/`relaxed_order`, `max_scan_tuples` 20,000); partial indexes and partitioning for filters; binary quantization with re-ranking.
- **Pinecone, "Hierarchical Navigable Small Worlds (HNSW)"** (Faiss series). https://www.pinecone.io/learn/series/faiss/hnsw/ (read 2026-10-22)
  *Take:* only M affects memory; mL = 1/ln(M); SIFT1M recall/time "from 80%-1ms to 100%-50ms."
- **Pinecone, "Product Quantization"** (Faiss series). https://www.pinecone.io/learn/series/faiss/product-quantization/ (read 2026-10-22)
  *Take:* 4096 bits → 64 bits; IndexPQ 98.4% memory reduction at ~50% recall; IVFPQ 52% at nprobe=48. Quantize for candidates, re-rank with full vectors.
- **OpenSearch k-NN index docs** (2.x). https://docs.opensearch.org/2.9/search-plugins/knn/knn-index/ (via search, 2026-10-22)
  *Take:* HNSW memory estimate `1.1 * (4 * dimension + 8 * M)` bytes per vector (float32); replicas multiply it.
- **Weaviate, Filtering concepts.** https://docs.weaviate.io/weaviate/concepts/filtering (read 2026-10-22)
  *Take:* pre- vs post-filtering; ACORN default since v1.34; automatic flat search when a filter matches less than ~15% of the dataset.
- **Patel et al., "ACORN: Performant and Predicate-Agnostic Search Over Vector Embeddings and Structured Data"**, arXiv 2403.04871. https://arxiv.org/abs/2403.04871 (abstract read 2026-10-22)
  *Take:* predicate-subgraph traversal on HNSW; 2 to 1,000x throughput over prior filtered-search methods at fixed recall.
- **Pinecone, "Implement multitenancy."** https://docs.pinecone.io/guides/index-data/implement-multitenancy (read 2026-10-22)
  *Take:* "one namespace per tenant" for physical isolation and cheap tenant deletion; metadata filtering when isolation isn't strict, with whole-namespace scan cost.

## Fusion and reranking

- **Cormack, Clarke & Büttcher, "Reciprocal Rank Fusion outperforms Condorcet and individual Rank Learning Methods"**, SIGIR 2009, pp. 758 to 759. https://research.google/pubs/pub36196/ · PDF https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf
  *Take:* `Σ 1/(k + rank)` with k=60 fixed in a pilot; beats individual systems and Condorcet Fuse on TREC. The PDF's text couldn't be extracted by this module's tools; formula and k were confirmed via the paper's abstract listings and Elastic's implementation docs.
- **Elastic, Reciprocal rank fusion.** https://www.elastic.co/docs/reference/elasticsearch/rest-apis/reciprocal-rank-fusion (read 2026-10-22)
  *Take:* `score += 1.0 / (k + rank)`, `rank_constant` default 60.
- **Cohere, Reranking best practices.** https://docs.cohere.com/docs/reranking-best-practices (read 2026-10-22)
  *Take:* rerank-v5.0 up to 10,000 docs per request; `max_tokens_per_doc` default 4096; chunk long docs yourself for control.
- **Voyage AI, Rerankers.** https://docs.voyageai.com/docs/reranker (read 2026-10-22)
  *Take:* `rerank-3` / `rerank-3-lite`; cross-encoders "jointly process a pair of query and document"; ≤1,000 docs, 8,000-token queries, 32,000 query+doc, 600K total tokens per request.

## Query side and agentic RAG

- **Gao, Ma, Lin & Callan, "Precise Zero-Shot Dense Retrieval without Relevance Labels" (HyDE)**, arXiv 2212.10496. https://arxiv.org/abs/2212.10496 (abstract read 2026-10-22)
  *Take:* generate a hypothetical document, embed it with Contriever, retrieve real documents; the encoder bottleneck filters the generated details.
- **Asai et al., "Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection"**, arXiv 2310.11511. https://arxiv.org/abs/2310.11511 (abstract read 2026-10-22)
  *Take:* retrieval on demand; reflection tokens to critique passages and generations; controllable at inference.
- **Yan, Gu, Zhu & Ling, "Corrective Retrieval Augmented Generation"**, arXiv 2401.15884. https://arxiv.org/abs/2401.15884 (abstract read 2026-10-22)
  *Take:* a lightweight retrieval evaluator whose confidence triggers actions; web search as an extension; decompose-then-recompose filtering. (The three confidence labels often quoted for CRAG weren't on the abstract page and aren't used here.)
- **Edge et al., "From Local to Global: A Graph RAG Approach to Query-Focused Summarization"**, arXiv 2404.16130; **Microsoft GraphRAG docs.** https://arxiv.org/abs/2404.16130 · https://microsoft.github.io/graphrag/ (read 2026-10-22)
  *Take:* "RAG fails on global questions directed at an entire text corpus"; entity graph, Leiden hierarchical communities, bottom-up community summaries; global, local, DRIFT and basic search modes; gains in comprehensiveness and diversity at the ~1M-token scale. Indexing cost is not quantified in what was read, so it's hedged in the text.

## Evaluation

- **RAGAS metrics.** https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/ · faithfulness https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/faithfulness/ · response relevancy https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/answer_relevance/ (read 2026-10-22)
  *Take:* context precision/recall, noise sensitivity, faithfulness (supported claims divided by total claims), response relevancy (3 generated questions by default, mean cosine to the user input).
- **OpenAI, File search tool.** https://developers.openai.com/api/docs/guides/tools-file-search (read 2026-10-22)
  *Take:* a hosted comparison point: vector stores, "semantic and keyword search", `max_num_results` trading tokens and latency for quality, metadata filters, `file_citation` annotations, results only returned when you `include` them. Default chunking parameters weren't on this page and aren't quoted here.

## Cross-links in this course
- [Module 03, file 06](../03-context-engineering/06-retrieval-agentic-search-vs-rag.md): agentic search vs RAG, Contextual Retrieval numbers, first eval tiers, BM25 runbook retriever.
- [Module 07](../07-loops/README.md): governors and typed exit codes, reused in `agentic_rag.py`.
- [Module 11](../11-llm-as-judge/README.md): binary rubrics and calibration for faithfulness, relevance and contradiction judges.
- [Module 12](../12-hill-climbing/README.md): paired statistics, sample size and CI gates for ablations.
- [Module 15](../15-observability-and-production/README.md): trace attributes, log retention and redaction.
- [Module 16](../16-security-and-containment/README.md): prompt injection via retrieved content, the lethal trifecta, confused deputies.
