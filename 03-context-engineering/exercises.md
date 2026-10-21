# Exercises

Offline exercises use `FakeClient` and need no API key. Run tests from the course root with `.venv/bin/python -m pytest -q 03-context-engineering/code`.

---

## 1. Inventory a real agent's context (30 min, real coding agent)

**Goal.** Know where your tokens go before you optimize anything.

**Steps.**
1. Open a Claude Code (or Codex) session in your main work repo and do a realistic 20-minute task.
2. Run `/context` (Claude Code), or read token usage from your harness's traces.
3. Record tokens for: system prompt and tools, context files, history, and tool results.
4. Find the single largest tool result in the session and write down what a filtered version would have returned.

**Done when.** You have a table with the four categories and their token counts. You have named the top three consumers, and written one concrete change for each (cut, move behind a pointer, or filter at the tool).

**Stretch.** Repeat the same task after making the changes and compare the totals.

---

## 2. Trace the budgeter (45 min, offline)

**Goal.** Make context decisions observable, so a dropped section shows up in a trace and not as a mystery.

**Steps.**
1. In `code/context_budget.py`, add an optional `tracer: Tracer | None` parameter to `assemble`.
2. When a tracer is given, wrap assembly in `tracer.span("assemble_context", budget=...)` and set attrs `included`, `truncated`, `dropped`, `tokens` and `prefix_tokens`.
3. Write `test_assemble_emits_span` in a new test file. Assemble the triage sections at `budget=900` and assert the span's `dropped` contains `style_guide`.

**Done when.** The new test passes, all existing tests still pass, and `load_traces` on a JSONL file written by the tracer shows the span.

**Stretch.** Have `oncall_assistant.answer` pass the tracer through, and add a span for retrieval with the retrieved chunk ids.

---

## 3. Find and close a hole in the compaction contract (30 min, offline)

**Goal.** Pinned-fact patterns are a spec, so test them like one.

**Steps.**
1. The demo history mentions `partition 7` and `offset 99120`, and the episode record writes them as `p7/o99120`. Neither is pinned by `DEFAULT_PIN_PATTERNS`.
2. Write a failing test. Build a history where the user says "the poison message is p7/o99120", compact it with `lossy_fake_summarizer(lambda ln: "p7/" in ln)`, and assert `p7/o99120` survives.
3. Add a pattern that makes the test pass without pinning every number in the transcript.

**Done when.** The new test fails before your change and passes after it. `test_compaction.py` still passes, and `compact(demo_history(), ...)` pins no more than 8 facts. Over-pinning is its own failure, because a summary that is 90% "restored facts" isn't a summary.

**Stretch.** Measure summarizer recall: run `compact` with a real model (`get_client()`) on 10 synthetic incident histories and report the mean of `len(missing_from_summary) / len(pinned)`. Then change `SUMMARY_SYSTEM` and re-measure.

---

## 4. Beat the retriever's rank-1 without losing recall@5 (60-90 min, offline)

**Goal.** Experience the precision/recall trade-off from file 06 in your own hands.

**Steps.**
1. Run `python code/retrieval_eval.py` and note the baseline: contextualized recall@1 = 0.705 and recall@5 = 0.955.
2. Add 10 labelled questions to `data/retrieval_eval.jsonl`, taken from real alerts in your own world if you can. At least 3 should be symptom-phrased.
3. Try one improvement. Options: weight heading tokens separately (BM25F-style); put only the *heading*, not the title, in the prefix; or drop the "overview" chunks from the index and attach the overview text to every chunk's display text instead.
4. Re-run the eval on the old and new question sets.

**Done when.** Your change raises recall@1 on the extended set and does not lower recall@5, and `test_retrieval_eval.py` still passes. Update the floor in `test_contextualized_bm25_recall_floor` only if the new number is higher. Write two sentences on why the change worked.

**Stretch.** Implement real contextual retrieval: for each chunk, call `get_client()` with the whole runbook and the chunk, and Anthropic's prompt ending "Answer only with the succinct context and nothing else." Cache the generated contexts to a JSON file so tests stay offline, and compare against the title prefix.

---

## 5. Trim your context file and A/B it (2-3 hours, real coding agent)

**Goal.** Apply file 05 to a real repo and measure the result.

**Steps.**
1. Inventory your repo's CLAUDE.md/AGENTS.md using the table in [05-context-files.md](05-context-files.md): section, lines, problem, destination.
2. Write the map (aim for 100 lines or fewer), plus the satellites: nested files, path-scoped rules, skills, linter rules and hooks.
3. Pick 10 tasks from recently merged PRs. For each, write the check: its tests plus 1 or 2 grep-able rule checks.
4. Run each task twice under three arms: no file, old file, new map. Use fresh sessions and a git worktree per run.
5. Record pass, rule violations, input tokens and turns.

**Done when.** You have a 3-arm results table with 60 runs. You've written a one-paragraph decision that says whether the "no file" arm was beaten and by how much. The new map is in a PR with a CI check that every path it mentions exists.

**Stretch.** Re-run the "no file" and "new map" arms on a different model, and note which lines stopped mattering.

---

## 6. Watch the cache with real requests (30 min, needs `ANTHROPIC_API_KEY`)

**Goal.** See cache-prefix discipline in the `usage` fields rather than take it on faith.

**Steps.**
1. Using the `anthropic` SDK directly (`ainative_kit` deliberately doesn't expose `cache_control`), send two requests with the same 2,000-token system prompt marked `cache_control: {"type": "ephemeral"}` and different user messages.
2. Print `cache_creation_input_tokens`, `cache_read_input_tokens` and `input_tokens` for both.
3. Add `f"Current time: {datetime.utcnow()}"` as the first line of the system prompt and repeat.
4. Move the timestamp into the user message and repeat.

**Done when.** You have three pairs of usage numbers showing: a write and then a read; two writes (timestamp at the top); and a write and then a read again (timestamp moved). Your explanation cites the prefix-order rule from [04-cache-prefix-discipline.md](04-cache-prefix-discipline.md).

**Stretch.** Shrink the system prompt below the model's documented minimum cacheable length and show that nothing is cached and no error is raised.

---

## 7. Add a faithfulness judge on top of the grounding check (60 min, offline then real)

**Goal.** Cover the claims that the deterministic check can't see. A sentence can cite the right chunk and still misstate it.

**Steps.**
1. Write `faithfulness_judge(answer_line, cited_chunk_text, client) -> bool` with a binary rubric: "Is every factual claim in LINE directly supported by CHUNK? Answer PASS or FAIL, then one sentence of reason."
2. Test it with a `FakeClient` that returns `FAIL` when the line contains "latest", and check that the pipeline surfaces it.
3. Hand-label 30 (line, chunk) pairs from assistant outputs, then run the judge with a real model and compute TPR and TNR against your labels.

**Done when.** The offline test passes, and you report TPR and TNR on 30 labelled pairs, with the disagreements listed. See [Module 11](../11-llm-as-judge/README.md) for calibration and how many labels you really need.

---

## 8. Build a typed episodic memory store (60 min, offline)

**Goal.** Put the [07](07-memory-taxonomy.md) design into code.

**Steps.**
1. Create `episode_store.py` with `EpisodeStore(path)`, which appends JSONL records shaped like the INC-7731 example (`episode_id`, `alert`, `root_cause`, `actions`, `rejected`, `expires`, `source`).
2. Add `search(query, k)` using the BM25 class from `runbook_retriever.py` over `alert + root_cause + actions`, skipping expired records.
3. Make writes append-only: `correct(episode_id, field, value)` appends a correction record, and `get(episode_id)` folds corrections in order.
4. Write tests for search, expiry, and the fold.

**Done when.** The tests pass. A search for "duplicate charges retry" returns the INC-6120 record from your seed data. An expired record never appears. `get` returns the corrected value while the original line is still present in the file.

**Stretch.** Have `oncall_assistant.answer` query the episode store first, and cite episodes as `[episode:INC-6120]` in a way the grounding check understands.
