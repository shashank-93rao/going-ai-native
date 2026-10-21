# Code: context engineering, retrieval and memory

Stdlib only, plus `ainative_kit` for model calls. Every script runs offline: with no `ANTHROPIC_API_KEY` (or with `AINATIVE_FAKE=1`) it falls back to a deterministic `FakeClient`.

Run all tests from the course root:

```bash
.venv/bin/python -m pytest -q 03-context-engineering/code
```

Run a script from the course root (the repo `conftest.py` puts `shared/` on the path for tests; scripts need `PYTHONPATH`):

```bash
cd 03-context-engineering/code
export PYTHONPATH=../../shared
```

| File | What it shows | Run |
|---|---|---|
| `context_budget.py` | Assembles a prompt from prioritized sections under a token budget. Selection is by priority; layout is stable-first so the cacheable prefix is byte-identical across calls. Required sections never get dropped silently. | `python context_budget.py` |
| `compaction.py` | `clear_tool_results` (lightest), `compact` (model summary + verbatim tail + **checked** pinned facts), and `EventLog` (evicted turns stay queryable). | `python compaction.py` |
| `runbook_retriever.py` | BM25 over `data/*.md` runbooks, chunked at `##` headings, with an optional contextual prefix per chunk. | `python runbook_retriever.py "consumer group falling behind"` |
| `retrieval_eval.py` | recall@k, hit@k, MRR over `data/retrieval_eval.jsonl`, and a deterministic grounding check for answers. | `python retrieval_eval.py` |
| `oncall_assistant.py` | The pipeline end to end: retrieve, budget, answer, check grounding. Uses the real model when a key is set. | `python oncall_assistant.py "force cert renewal"` |

## Measured results (this corpus, this tokenizer)

`python retrieval_eval.py` on 40 chunks from 8 runbooks and 22 labelled questions:

```text
plain           recall@1=0.750  hit@1=0.818  MRR=0.862  misses=7
contextualized  recall@1=0.705  hit@1=0.773  MRR=0.831  misses=8
plain           recall@3=0.909  hit@3=0.909  MRR=0.862  misses=2
contextualized  recall@3=0.864  hit@3=0.864  MRR=0.831  misses=3
plain           recall@5=0.909  hit@5=0.909  MRR=0.862  misses=2
contextualized  recall@5=0.955  hit@5=0.955  MRR=0.831  misses=1
```

Read it carefully. The title prefix *raises* recall@5 (it rescues the Kafka "Mitigation" chunk, which never says "Kafka") but *lowers* rank-1 precision, because every chunk of a runbook now shares the same title terms and the short "overview" chunk wins ties. A model-written, chunk-specific context (real Contextual Retrieval) is meant to avoid exactly that. The one remaining miss, "the box is out of space", has no lexical overlap with "DiskPressure / ephemeral-storage". That is the case embeddings exist for. The numbers are from 22 questions, so one question is about 4.5 points: treat differences smaller than that as noise.

## Using the real API

`oncall_assistant.py` and `compaction.py` call `get_client(fake=...)`. With a key set they use `ainative_kit.DEFAULT_MODEL`. The grounding check still runs, and that is the point: it is how you find out whether the real model copies commands verbatim.

## Tests

| Test file | Checks |
|---|---|
| `test_context_budget.py` | priority drop order, loud failure on required overflow, tail truncation for logs, prefix identity across calls, property test that the budget is never exceeded |
| `test_compaction.py` | critical facts survive a lossy summarizer, tail kept verbatim, split never orphans a `tool_result`, evicted turns queryable in the log, tool-result clearing |
| `test_runbook_retriever.py` | chunk ids, tokenizer, exact-identifier ranking, idf behaviour, contextual prefix effect |
| `test_retrieval_eval.py` | metric math, labels reference real chunks, recall floor as a regression gate, a characterization test for the known miss, grounding accept/reject, end-to-end with fake and with a "hallucinating" fake |
