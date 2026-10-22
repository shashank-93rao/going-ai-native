# Exercises

Offline exercises use `FakeClient` and the stdlib code in `code/`, so they need no API key. Run tests from the course root with `.venv/bin/python -m pytest -q 18-rag-systems/code`, and scripts with `PYTHONPATH=shared .venv/bin/python 18-rag-systems/code/<file>.py`.

---

## 1. Break the indexer and let Hypothesis find it (30 min, offline)

**Goal.** Feel why the version check is the whole correctness story of an index consumer.

**Steps.**
1. In `code/ingest.py`, comment out the high-water-mark check at the top of `DocIndex.apply` (the `if e.version <= ...: return "stale"` block).
2. Run `test_ingest.py`. Read the shrunk failing example Hypothesis prints for `test_any_order_with_duplicates_converges_to_the_same_state`. It may be a wrong fingerprint (a resurrected doc) or an exception (re-adding a vector key that exists). Both are bugs a production consumer would hit.
3. Write down, in one sentence, the event order that broke it and which real-world event (consumer restart, partition rebalance, backfill) produces that order.
4. Restore the check. Then change it to `<` instead of `<=` and run again.

**Done when.** You have two failures (no check, and off-by-one), each explained in one sentence, and the original code is back with all tests green.

**Stretch.** Add a `"acl"` event type that changes only the ACL without a version bump, and write the property test that shows why that's a bad idea.

---

## 2. Measure the HNSW trade-off surface (45 min, offline)

**Goal.** Own the recall / work / memory curve rather than copy defaults.

**Steps.**
1. Write a script that builds `hnsw_lite.HNSW` over `random_unit_vectors(3000, 32)` for M in {4, 8, 16} and ef_construction in {32, 128}.
2. For each index, measure `recall_vs_exact` at ef_search in {10, 40, 160}, and record build time and `distance_calls` per query.
3. Estimate production memory for your own corpus with `1.1 * (4 * d + 8 * M)` bytes per vector (OpenSearch's float32 formula) for d in {256, 1024}.
4. Pick a configuration for "recall@10 ≥ 0.95 at minimum work", and write it as an ADR paragraph with the numbers.

**Done when.** You have a table with 18 rows (M × efC × ef_search), a memory estimate for your corpus at two dimensions, and a one-paragraph decision with a revisit trigger.

**Stretch.** Repeat on clustered data (sample centroids, then add small noise around them) and explain why recall improves.

---

## 3. Plug in a real embedding model (60 min, real API)

**Goal.** See how much of this module's retrieval behaviour came from the toy embedder.

**Steps.**
1. Get a Voyage key (or use another provider) and implement the `Embedder` protocol. `embed.VoyageEmbedder` is a starting point; check the request shape against the current docs.
2. In `rag_eval.retriever_fn`, let the embedder be chosen by an environment variable, and cache vectors on disk keyed by `(model_id, sha256(text))` so reruns are free.
3. Re-run the ablation table with the real model.
4. Look specifically at q04, q05, q08, q12, q19 and q30 (the symptom-phrased misses) for both embedders.

**Done when.** You have both ablation tables side by side, and a paragraph on which rows moved beyond the paired CI and why.

**Stretch.** Truncate the real vectors to 256 dims (Matryoshka) and measure the evidence@5 cost.

---

## 4. Equal-budget chunking (60 min, offline)

**Goal.** Compare chunkers fairly by fixing the context budget instead of k.

**Steps.**
1. Add a `pack(chunks, max_words)` function that takes ranked chunks until the word budget is used.
2. Change `per_question` to accept `max_words` instead of `k` and use `pack`.
3. Re-run the chunker rows at budgets of 100, 200 and 400 words.
4. Plot (or tabulate) evidence vs budget for fixed, heading, sentence-to-section and sentence-to-doc.

**Done when.** You can state, for this corpus, which chunker wins at each budget, with paired CIs, and whether the "fixed beats heading" result from [02](02-chunking-and-embeddings.md) holds at every budget.

**Stretch.** Add a sixth corpus doc type, a long design doc with 400-word sections, and see whether the winner changes.

---

## 5. A contradiction judge for negation flips (90 min, real API)

**Goal.** Close the gap pinned by `test_lexical_grounding_is_fooled_by_a_negation_flip`.

**Steps.**
1. Hand-write 30 (sentence, cited chunk) pairs from the corpus: 15 faithful and 15 that recommend something the chunk forbids or calls wrong (for example `allkeys-lru`, "reset the group offset to latest", "remove the memory limit").
2. Implement `contradiction_judge(client, sentence, chunk) -> bool` using the rubric in [07](07-evaluating-and-hill-climbing-rag.md), with a forced tool call for the JSON verdict.
3. Measure the judge's agreement with your labels (true positive rate, true negative rate). Iterate on the rubric until both are at least 0.9, following [Module 11](../11-llm-as-judge/README.md).
4. Wire it after `grounding_check` in `score_answer`, behind a flag, and flip the characterization test.

**Done when.** The judge's TPR and TNR on your 30 pairs are recorded, and the negation-flip test is inverted and passing with the judge on (using a `ReplayClient` cassette so CI stays offline).

**Stretch.** Measure judge cost and latency per answer, and decide whether it runs on every answer or only on answers that contain commands.

---

## 6. Freshness SLO with a canary and a reconciler (45 min, offline)

**Goal.** Detect a dead consumer, which lag histograms can't.

**Steps.**
1. Add a `canary` doc to the source and a function `tick(now)` that emits a new canary version every 60 simulated seconds.
2. Write a `probe(index, now, slo=300)` that searches for the canary and returns the served age.
3. Write a test that applies canary events for 10 minutes and then stops delivering events (the consumer is dead) while `now` advances, and asserts the probe fires within the SLO.
4. Add a reconciler test where one event is dropped from the stream, and assert `reconcile` reports it as `missing` or `stale`.

**Done when.** Both tests pass, and each fails if you remove the probe or the reconciler.

---

## 7. Build your own labeled set (2 hours, real data)

**Goal.** The highest-leverage artifact in this module, for your actual docs.

**Steps.**
1. Pull 60 real questions about your team's docs from Slack, pages or tickets.
2. For each, record `team`, `category`, `answerable`, `relevant_docs` and a verbatim `evidence` span. Include at least 6 unanswerable questions and 3 permission-dependent pairs.
3. Copy `test_corpus_data.py` and adapt it to validate your labels against your corpus.
4. Run your current assistant (or a quick hybrid baseline) and produce the per-stage report: evidence@5, recall@5, abstention split.

**Done when.** The label tests pass, the report exists, and you've written the three questions it raised that you couldn't have asked before.

---

## 8. Agentic vs single-shot on multi-hop questions (60 min, offline then real API)

**Goal.** Decide where the agentic loop pays for itself.

**Steps.**
1. Add five more multi-hop questions to `questions.jsonl` where a postmortem points to an ADR or runbook by id.
2. Run single-shot `rag_pipeline.answer` and `agentic_rag.run` with `fake_agent_responder` on all multi-hop questions. Record evidence found, steps and exit codes.
3. Repeat with a real model through `get_client()` and record tokens per question from the traces.
4. Write a routing rule: "use the agent when ...", based on the numbers.

**Done when.** You have a table of single-shot vs agentic on evidence, steps and tokens, and a routing rule backed by it.
