# 06: Retrieval: agentic search vs vector RAG, and how to evaluate both

## The idea

Retrieval is just-in-time context loading applied to a corpus. There are two main families:

- **Agentic search.** The model drives ordinary tools such as `grep`/`rg`, `glob`, `ls`, `read_file` and `git log -S`, refining its queries as it learns. There is no index to build. Results are exact and come with locations (`file:line`). This is how Claude Code navigates a repo ([Anthropic, "Effective context engineering"](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)).
- **Vector RAG.** Chunk the corpus, embed each chunk, and at query time embed the question and return the nearest chunks. It matches on meaning, not spelling. It needs an index pipeline, and the index can go stale.

Between the two sit **lexical indexes** like BM25, which score chunks by rare-term overlap. They are fast, deterministic and good at identifiers. They are also the "keyword" half of hybrid retrieval.

And there is a third option people forget: **no retrieval**. Anthropic's Contextual Retrieval post says that if your knowledge base is smaller than 200,000 tokens (about 500 pages), you may be able to put the whole thing in the prompt, with prompt caching making that affordable ([Anthropic, "Introducing Contextual Retrieval"](https://www.anthropic.com/engineering/contextual-retrieval)). Context rot ([01](01-context-as-a-budget.md)) means "fits" still needs a measurement, but it's the baseline to beat.

## Why it matters

Retrieval is the first link in the chain. If it fails, the generator is answering from the wrong evidence, and a fluent wrong answer is the worst outcome in an incident. Jason Liu: "If your retriever pulls irrelevant context, your generator is doomed from the start" ([Liu, "There are only 6 RAG evals"](https://jxnl.co/writing/2025/05/19/there-are-only-6-rag-evals/)).

The two families fail differently:

- **Agentic search misses on vocabulary.** The question says "out of space", the doc says "DiskPressure". Huntley's Ralph notes describe the coding version: an `rg` miss leads to "not implemented", which leads to a duplicate implementation ([Huntley](https://ghuntley.com/ralph/)).
- **Vector RAG misses on precision and staleness.** Embeddings blur `max.poll.interval.ms` and `session.timeout.ms` into "Kafka timeout config". An index built last Tuesday doesn't know about today's refactor. For code, which changes many times a day, that is a cache-invalidation problem.

## How it works / how to do it

### When each wins

| Corpus property | Favors |
|---|---|
| Exact identifiers matter (function names, config keys, error codes, alert names) | Agentic search / BM25 |
| Changes constantly (a code repo) | Agentic search (no index to keep fresh) |
| Results must be checkable by location | Agentic search |
| Users phrase things differently from the authors (symptoms vs internal names) | Embeddings, or hybrid |
| Large prose corpus (runbooks, tickets, wikis, postmortems) | Hybrid: BM25 + embeddings, then a reranker |
| Under ~200k tokens and stable | Try no retrieval with caching first |
| Low latency, no tool loop possible | Pre-computed RAG |

The course stance (from [01-gap-analysis](../research/01-gap-analysis.md)): **agentic search for code, vector or hybrid RAG for document Q&A, each with its own evals.** Anthropic's Agent SDK guidance puts agentic search over a well-organized folder structure first, and adds semantic search only when speed or query variety calls for it ([Anthropic, "Building agents with the Claude Agent SDK"](https://claude.com/blog/building-agents-with-the-claude-agent-sdk)). Jason Liu's coding-agent series reports that practitioners at Augment and Cline found grep and agentic search beating embeddings for coding agents (reported by Liu; [series index](https://jxnl.co/writing/2025/09/11/rag-series-index/)).

### Contextual retrieval

Chunking strips context. A runbook section titled "Mitigation" that says "scale out only up to the partition count" never says "Kafka". Contextual Retrieval prepends a short, model-written context to each chunk before embedding *and* before BM25 indexing. The generated context is "usually 50-100 tokens", written by a prompt that ends "Answer only with the succinct context and nothing else." Anthropic's measurements, using 1 minus recall@20 as the failure rate:

| Configuration | Top-20 retrieval failure rate |
|---|---|
| Baseline embeddings | 5.7% |
| Contextual embeddings | 3.7% (-35%) |
| + contextual BM25 | 2.9% (-49%) |
| + reranking | 1.9% (-67%) |

They also found passing the top 20 chunks to the model worked better than the top 10 or top 5, and put the one-time contextualization cost at "$1.02 per million document tokens" with prompt caching ([Anthropic, "Introducing Contextual Retrieval"](https://www.anthropic.com/engineering/contextual-retrieval)). Those are their datasets. Yours will differ, which is why you need the eval below.

### Evaluate in tiers, cheapest first

Jason Liu's framing: RAG has three objects (Question, Context, Answer) and six conditional relationships between them. Start with retrieval metrics, which are cheap and deterministic, before you judge generation. Diagnose by symptom: a missing answer points to retrieval, and a wrong answer points to faithfulness.

1. **Retrieval** (no model needed). Label 20 to 50 real questions with the chunk ids that answer them. Measure:
   - **recall@k**: fraction of relevant chunks in the top k
   - **hit@k**: was at least one relevant chunk in the top k
   - **MRR**: how high the first relevant chunk ranks
2. **Grounding** (deterministic first). Does every citation point at a chunk the model was actually shown? Does every command in the answer appear verbatim in a cited chunk?
3. **Faithfulness and relevance of prose** (LLM judge, calibrated). Is each claim supported by the cited text? Use a binary rubric and calibrate it against human labels ([Module 11](../11-llm-as-judge/README.md)).
4. **Abstention.** When the corpus doesn't cover the question, does the system say so? Score correct, abstain and wrong separately ([Module 10](../10-evals-fundamentals/README.md)).

## Worked example: an on-call assistant over runbooks

**Situation.** Billing's on-call engineers want to ask "what do I run for X?" at 3am and get an answer from the team's runbooks, with commands they can paste.

**Bad version.** Embed whole runbook files, return the top 1, and prompt "Answer the engineer's question using this runbook." No evals. (illustrative) In the first week it answers "how do I clear the invoice backlog?" with `kafka-consumer-groups --reset-offsets --to-latest`. That command appears in *no* runbook. The Kafka runbook in fact says "Never reset the group offset to latest; that silently drops invoices." The model generated a plausible Kafka command because the retrieved context didn't directly answer the question, and nothing checked the output.

**Good version.** The course code in `code/` builds this out of four pieces.

**1. Chunk by section, with ids.** `runbook_retriever.py` splits each runbook at `##` headings. A chunk id is `<runbook>#<section>`, e.g. `kafka-consumer-lag#mitigation`. Ids make citations checkable.

**2. Label questions.** `data/retrieval_eval.jsonl` has 22 questions written the way pages and Slack messages are phrased, including two deliberately hard ones:

```json
{"id": "q04", "question": "how do I mitigate kafka consumer lag", "relevant": ["kafka-consumer-lag#mitigation"]}
{"id": "q06", "question": "cancel a long running analytics query that is blocking WAL replay on the replica", "relevant": ["postgres-replication-lag#diagnosis", "postgres-replication-lag#mitigation"]}
{"id": "q20", "question": "the box is out of space", "relevant": ["node-disk-pressure#symptoms"]}
```

**3. Measure retrieval, with and without a contextual prefix.** Here the "context" is a deterministic `Runbook: <title>. Section: <heading>.` prefix, a zero-cost stand-in for model-written context. Real output:

```text
$ python code/retrieval_eval.py
plain           recall@1=0.750  hit@1=0.818  MRR=0.862  misses=7
contextualized  recall@1=0.705  hit@1=0.773  MRR=0.831  misses=8
plain           recall@3=0.909  hit@3=0.909  MRR=0.862  misses=2
contextualized  recall@3=0.864  hit@3=0.864  MRR=0.831  misses=3
plain           recall@5=0.909  hit@5=0.909  MRR=0.862  misses=2
contextualized  recall@5=0.955  hit@5=0.955  MRR=0.831  misses=1

Misses at k=5 (contextualized):
  q20 'the box is out of space'
     wanted ['node-disk-pressure#symptoms']
     got    ['kafka-consumer-lag#mitigation']
```

Read this as an engineer, not as a marketer:

- **The prefix helped recall@5 and hurt rank 1.** It rescued q04: the Kafka "Mitigation" chunk never says "Kafka", and without the prefix it isn't in the top 5 at all. But every chunk in a runbook now shares the title's terms, so the short "overview" chunk often wins rank 1. A title-only prefix is too blunt, and chunk-specific, model-written context is meant to fix exactly that. The lesson is not "contextualize" or "don't". It is that **you measure what you change**.
- **The remaining miss is lexical.** "Out of space" shares no terms with "DiskPressure" or "ephemeral-storage". The top hit is the Kafka chunk only because "scale *out*" matches "out". This is the case embeddings, or a hybrid, exist for. It is pinned as a characterization test (`test_known_lexical_gap_is_still_a_miss`), so a change that fixes it shows up as a test change you can see.
- **22 questions is small.** One question is about 4.5 points of recall. Before you trust a difference that size, add questions and see [Module 12](../12-hill-climbing/README.md) on noise.
- **Pick k from the data.** Recall plateaus at k=5 here, so the assistant retrieves 5 chunks and lets the budgeter drop the lowest-ranked ones if space is tight.

**4. Generate with citations, then check grounding.** The system prompt in `oncall_assistant.py`:

```text
You are the on-call assistant for billing-platform.
Answer only from the runbook chunks provided in <runbooks>. After every line that
states a fact or a command, cite the chunk id in square brackets, e.g. [kafka-consumer-lag#diagnosis].
Copy commands exactly as written in the chunk, inside backticks. If the chunks do not
answer the question, say "Not covered by the runbooks" and name the closest chunk.
```

Then `grounding_check` runs on every answer. It fails the answer if a citation names a chunk that wasn't shown, if a backticked command isn't a verbatim substring of a cited chunk, or if a line with a command has no citation. Here it runs against the bad answer from above, and against an answer that copies the runbook:

```python
>>> grounding_check("Reset offsets: `kafka-consumer-groups --reset-offsets --to-latest` [kafka-consumer-lag#mitigation]", shown)
GroundingReport(unknown_citations=[], ungrounded_commands=['kafka-consumer-groups --reset-offsets --to-latest'], ...)  # ok=False

>>> grounding_check("Force renewal with `cmctl renew -n billing ledger-api-tls` [tls-cert-expiry#mitigation]", shown)
# ok=True
```

Both cases are tests in `code/test_retrieval_eval.py`, along with one that wires a deliberately lying `FakeClient` through the whole pipeline. In production, a failed grounding check doesn't show the answer. It shows the retrieved chunks with a note that the generated answer could not be verified. That is the course thesis in miniature: the system is allowed to answer on its own exactly as far as its answers can be checked.

## Pitfalls

- **Judging answers before measuring retrieval.** Detect it: you have a faithfulness score but no recall@k. Build the labelled question set first. It takes an afternoon.
- **Evaluating on questions written by the doc authors.** They use the docs' vocabulary, so recall looks perfect. Detect it: take questions from real pages, Slack threads and tickets, and include symptom-phrased ones like q20.
- **Whole-document chunks.** The right section is diluted by five wrong ones. Detect it: low MRR even when hit@k is high.
- **Uncheckable citations.** "According to the runbook..." can't be verified. Use stable chunk ids and check them in code.
- **A stale index.** Detect it: answers cite content that has since been edited. Re-index on merge to the docs repo, and include an index version in traces.
- **RAG over code.** Detect it: the agent cites functions that were renamed last week. Use agentic search for code.
- **No abstention path.** Detect it: zero "Not covered" answers in a week of traffic. Either the corpus is perfect or the model is guessing, and it's not the corpus.

## In your day job

- Pick your team's runbooks or postmortems and write 20 labelled questions from real pages. That set is worth more than any embedding model choice.
- Add chunk-id citations and a verbatim-command check to any internal assistant that suggests commands.
- For code questions, give the agent `rg` and `git log -S` before you build an index.
- When someone proposes a better retriever, ask for recall@k on the labelled set, before and after.
