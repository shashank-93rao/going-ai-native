# 02: Chunking and embeddings

## The idea

Chunking decides **the unit you match** and **the unit you show**. Embedding decides **what "similar" means**. Both are schema decisions. You make them once and pay for them on every query, and changing either one means reprocessing the whole corpus. Treat them like choosing a partition key, not like a tuning knob.

Five chunking strategies matter in practice:

| Strategy | Match unit | Show unit | Good for | Breaks when |
|---|---|---|---|---|
| Fixed window (N tokens, overlap) | window | window | Unstructured prose, quick baselines | A command or a table row is cut at the edge |
| Structural / heading-aware | section | section | Runbooks, ADRs, docs with headings | Sections are tiny (lose context) or huge (dilute the match) |
| Semantic (split where adjacent-sentence similarity drops) | topic span | topic span | Long, weakly structured text | Expensive to compute; boundaries move when the embedder changes |
| Parent-child / small-to-big | sentence or small span | parent section or doc | Precise matching with enough surrounding context to act on | Parents get big, so token cost rises |
| Late chunking | chunk, embedded with the whole doc as context | chunk | Long documents where chunks rely on earlier text ("it", "this service") | Needs a long-context embedder that exposes token embeddings |

Late chunking runs the whole document through a long-context embedding model first, then mean-pools token vectors per chunk. Chunking is "applied after the transformer model and just before mean pooling" ([Günther et al., "Late Chunking", arXiv 2409.04701](https://arxiv.org/abs/2409.04701)). Voyage's `voyage-context-*` models ship a productized version: "contextualized chunk embedding models produce chunk-level vectors that capture full document context without manual metadata augmentation" ([Anthropic embeddings docs](https://platform.claude.com/docs/en/build-with-claude/embeddings), checked 2026-10-22).

**Contextual chunk headers** are the cheap relative of both ideas. You prepend "doc title > section" to the text you index, but not to the text you show. Anthropic's model-written version, and its numbers, are in [Module 03](../03-context-engineering/06-retrieval-agentic-search-vs-rag.md). The `chunking.py` chunkers do the deterministic version: `Kafka consumer lag on invoice-consumer (runbook, owner payments) > Mitigation`.

## Why it matters

The most common retrieval failure in this module's eval isn't a wrong document. It's the **right document, wrong section**. On-call engineers describe symptoms ("the box is out of space and pods keep getting kicked off"). Runbooks put symptoms in one section and the fix in another. Heading-aware chunking dutifully returns the *Symptoms* section, and the command you need is in *Mitigation*, two chunks away. Doc-level recall@5 says 0.97, and the answer-bearing span was shown only 79% to 82% of the time.

You'll only see that gap if you measure it. Doc-level labels hide chunking failures, so label the **evidence span** too ([07](07-evaluating-and-hill-climbing-rag.md)).

## How it works

### Choosing a chunker: decision rules

1. **Start structural** if your docs have headings. Section ids (`doc#section`) make citations human-checkable.
2. **Measure evidence@k, not just doc recall@k.** Doc recall can't tell a perfect chunker from a terrible one.
3. **Compare at equal token budget.** A strategy that shows twice as many words will find more evidence. That's not a free win, because it's a context-rot and cost trade ([01](01-the-rag-pipeline-as-a-system.md)).
4. **If sections are small and interdependent** (runbooks), match small and show big: index sentences, return the parent section or the whole doc.
5. **If chunks lean on earlier text** ("this service", "the above"), add contextual headers or use late or contextualized chunk embeddings.
6. **Size:** Anthropic notes chunks are typically "a few hundred tokens" and that size, boundaries and overlap all affect performance. They don't prescribe a value, and you shouldn't either. Sweep it on your eval.

### Choosing an embedding model

**Benchmarks are a prior, not an answer.** MTEB spans 8 task types, 58 datasets and 112 languages, and its own authors found "no particular text embedding method dominates across all tasks" ([Muennighoff et al., arXiv 2210.07316](https://arxiv.org/abs/2210.07316)). BEIR's zero-shot study across 18 datasets found "BM25 is a robust baseline", and dense retrievers "often underperform other approaches" out of domain ([Thakur et al., arXiv 2104.08663](https://arxiv.org/abs/2104.08663)). Your internal jargon (`invoices.v2`, `ndots`, `UC` flags) is out of domain for every public model. Shortlist from the leaderboard, then decide on your labeled set.

What to compare:

| Dimension | Why it matters | Example (Voyage via Anthropic docs, 2026-10-22) |
|---|---|---|
| Domain fit | Jargon, code, legal and finance vocab | `voyage-code-4`, `voyage-law-2`, `voyage-finance-2` exist for that reason |
| Query vs document mode | Asymmetric retrieval | `input_type="query"` / `"document"` prepends different instructions; the docs say not to omit it |
| Dimensions | Memory = n x d x bytes | `voyage-4`: 1024 default, also 256, 512, 2048 |
| Matryoshka truncation | Shrink stored vectors without re-embedding | Keep the leading dims and renormalize; only valid for MRL-trained models |
| Quantization | 4x (int8) or 32x (binary) less storage | `output_dtype`: float, int8/uint8, binary/ubinary |
| Context length | Long chunks, late chunking | 32,000 tokens for `voyage-4` family |
| Cost and latency | Ingestion bill, query p99 | Per-token pricing; check the live price page |

Matryoshka Representation Learning trains one vector to be useful at several prefix lengths. The paper reports "up to 14x smaller embedding size for ImageNet-1K classification at the same level of accuracy" ([Kusupati et al., arXiv 2205.13147](https://arxiv.org/abs/2205.13147)). That's an image-classification number, so for text retrieval, measure your own recall at 256 vs 1024 dims. `embed.truncate()` shows the operation. On the toy embedder it simply loses information, which is the honest result for a model that wasn't trained for it.

Anthropic doesn't offer an embedding model. Its docs point to Voyage AI and say "you should assess a variety of embeddings vendors" ([Anthropic embeddings docs](https://platform.claude.com/docs/en/build-with-claude/embeddings)).

### Embedding drift is a type error

Vectors from different models, or from the same model with different weights, live in different spaces. A cosine between them is a number with no meaning. Treat the model id as part of the vector's type:

- Tag every stored vector with `embedding_model_id` (`DocIndex.model_id` in `ingest.py`).
- Refuse queries whose embedder id differs from the index's. `ingest.py` raises `StaleModel` rather than return garbage ranked confidently.
- A model change is a **migration** (dual-write, backfill, shadow-read, cutover), never an in-place config change. See [06](06-ingestion-freshness-and-correctness.md).

The toy embedder makes this concrete. `HashedNgramEmbedder.fit()` learns an IDF table, and its `model_id` includes a hash of that table. Refit on a different corpus and the id changes, the same way a provider's model version would.

## Worked example: chunkers on the platform-docs corpus

**The toy embedder, honestly.** `embed.py` hashes character 3-to-5-grams into 512 dims with TF-IDF weights. It captures morphology but not meaning:

```text
$ PYTHONPATH=shared .venv/bin/python 18-rag-systems/code/embed.py
hashgram-d512-27dc6f03
rebalancing vs rebalance-storm sentence: 0.128
'out of space' vs ephemeral-storage:     0.048  (no semantics: expect low)
```

A trained model would put "out of space" near "ephemeral-storage". This one can't. So in this corpus, the DiskPressure runbook includes the sentence "Engineers usually report this as the box being out of space." That's **doc-side query expansion**: write the users' vocabulary into the doc. It's a legitimate fix in real systems too, and it's why q04 retrieves the right doc at all.

**How the three chunkers split one runbook** (real output from `chunking.py`):

```text
--- fixed(40/10): 5 chunks
  rb-kafka-consumer-lag#w0   'Owner: payments. Pager alert: `InvoiceConsumerLagHigh` (lag > 50k mess'
  rb-kafka-consumer-lag#w1   'log end offset. Messages-in is steady while records-consumed drops. Ch'
  ...
--- heading: 5 chunks
  rb-kafka-consumer-lag#overview   ...
  rb-kafka-consumer-lag#symptoms   'Invoices appear in the ledger late. The committed offset of group `inv'
  rb-kafka-consumer-lag#diagnosis  'Check lag per partition with `kafka-consumer-groups --bootstrap-server'
  rb-kafka-consumer-lag#mitigation 'Scale out only up to the partition count; extra replicas sit idle. `ku'
--- parent-child: 13 children -> 5 parents
```

**Bad version: pick the chunker by intuition.** "Heading-aware is obviously better for runbooks." Here's what the eval says (real output, hybrid retrieval, 38 answerable questions, k=5):

```text
config                                     recall@5    MRR  nDCG@5  evid@5  words   evid@5 delta vs row 1 [95% CI]
bm25 heading, no header (Module 03 style)     0.965  0.974   0.949   0.789    108   +0.000 [+0.000, +0.000]
hybrid RRF heading + header                   0.965  0.987   0.964   0.816    101   +0.026 [-0.053, +0.105]
hybrid fixed 40w                              0.978  0.961   0.953   0.921    178   +0.132 [+0.000, +0.263]
hybrid fixed 40w + header                     0.978  0.974   0.963   0.947    172   +0.158 [+0.026, +0.289]
hybrid sentence -> section                    0.978  0.974   0.965   0.816    107   +0.026 [-0.053, +0.105]
hybrid sentence -> whole doc                  0.978  0.974   0.965   1.000    396   +0.211 [+0.079, +0.342]
hybrid heading + header, k=9                                         0.868    184   (evidence@9)
hybrid heading + header, k=15                                        0.868    303   (evidence@15)
```

Read it like an engineer:

- **Doc recall barely moves (0.965 to 0.978).** If that were your only metric, you'd conclude chunking doesn't matter.
- **Evidence@5 moves a lot.** The sections in these runbooks are 20 to 40 words, so a heading chunk holds the symptom *or* the fix, rarely both. Fixed 40-word windows straddle section boundaries and catch both.
- **Equal budget check.** Is "fixed wins" just "fixed shows more words"? At k=9 the heading chunker shows a similar number of words (184 vs 172) and still finds less evidence (0.868 vs 0.947). Even at k=15 it stays at 0.868, because the missing *Mitigation* sections never rank. So on this corpus the windows really are better units. On long design docs with 500-word sections, the result could flip. That's why you run the table.
- **Small-to-big with whole-doc parents finds everything** (1.000) at nearly 4x the words of heading chunks. For short runbooks, showing the whole runbook is a reasonable choice. For 30-page design docs it would be context rot by construction.
- **Error bars.** With 38 questions, one question is 2.6 points. Only deltas whose 95% CI excludes zero are real here: fixed+header and sentence-to-doc. The header alone shows +0.000 on this corpus ([Module 12](../12-hill-climbing/README.md) on paired comparisons).

**Good version.** Pick "sentence to whole-doc" for runbooks and postmortems (short, interdependent sections), and keep heading chunks with headers for ADRs and long guides. Record the decision with the table above in an ADR, and re-run the table when the corpus mix changes.

## Pitfalls

- **Evaluating chunkers with doc-level labels.** Detect it: chunker changes never move your metric. Add evidence-span labels.
- **Comparing chunkers at different token budgets.** Detect it: the "winner" also has the highest words-shown column. Compare at equal budget.
- **Embedding headers into the shown text.** Detect it: answers quote "Kafka consumer lag on invoice-consumer (runbook, owner payments) >". Index the header, show the body.
- **Mixing embedding model versions in one index.** Detect it: recall drops for old docs only after a partial re-embed. Tag vectors with the model id and refuse mismatches.
- **Picking a model from the MTEB average.** Detect it: no domain eval in the decision record. Run your labeled set on the top three candidates.
- **Truncating non-Matryoshka vectors.** Detect it: recall falls off a cliff at lower dims. Only truncate models documented as MRL-trained, and measure.

## In your day job

- Add an `evidence` field (a verbatim answer span) to every labeled question, and report evidence@k next to recall@k.
- Run a chunker table like the one above on your corpus before the first production index build, at two token budgets.
- Put `embedding_model_id` on every vector row and in every query trace, and make a mismatch an exception.
- Grep your docs for the words users actually type (from Slack and pages). Where the docs never use them, add a sentence. It's the cheapest retrieval fix there is.
