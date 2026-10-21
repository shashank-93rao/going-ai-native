# Exercises

Offline exercises need only the course venv. Exercises marked **[API]** need `ANTHROPIC_API_KEY` and cost a few cents each. Run code from `01-llms-for-systems-engineers/code/`.

---

## 1. Calibrate your token intuition (offline + [API], 30 min)

**Goal.** Learn how far off characters-divided-by-four is for the payloads you actually send.

**Steps.**
1. Collect five real payloads from your work: a page of prose docs, a 300-line source file, a pretty-printed JSON API response, a log excerpt with trace IDs, and a minified version of the same JSON.
2. For each, record `len(text)` and `estimate_tokens(text)` from `token_cost_model.py`.
3. **[API]** Get the real count with `client.messages.count_tokens(model="claude-sonnet-5-5", messages=[{"role": "user", "content": text}]).input_tokens`.
4. Compute characters per token for each payload type.

**Done when.** You have a 5-row table of characters per token by content type, and you can say which payload type the heuristic undercounts most and by roughly how much.

**Stretch.** Count the same payloads on `claude-haiku-5-5` and `claude-opus-5-5`. Do the counts differ? Record which models share a tokenizer, based on your measurements.

---

## 2. Find the break-even (offline, 20 min)

**Goal.** Be able to say, for any route, whether caching pays.

**Steps.**
1. Using `break_even_hit_rate`, compute the break-even hit rate for each model in `EXAMPLE_PRICES` at the 5-minute and 1-hour TTLs.
2. Derive the formula *h* = (*w*−1)/(*w*−*r*) on paper, and check one value by hand.
3. Pick one real LLM route in your team (or invent a plausible one). Estimate prefix size, suffix size, output size, request rate, and the typical gap between requests. Decide on 5-minute TTL, 1-hour TTL, or no caching.

**Done when.** You have a table of 8 break-even values, a hand derivation that matches one of them, and a one-paragraph caching decision for your route that cites its numbers.

**Stretch.** Extend `token_cost_model.py` with a function that takes a request inter-arrival distribution (for example, exponential with a given mean) and a TTL, and returns the expected hit rate. Add a test.

---

## 3. Break the cache, then fix it (offline, 45 min)

**Goal.** Recognize the silent invalidators in prompt-assembly code.

**Steps.**
1. Write a function `render(history) -> bytes` that serializes a request (tools, system, messages) the way an SDK would, with `json.dumps(..., sort_keys=True)`.
2. Write `shared_prefix_len(a: bytes, b: bytes) -> int`.
3. Implement three buggy builders: a timestamp in the system prompt, tools built from a `set`, and an earlier turn edited on every turn ("summarize the oldest tool result"). Implement one append-only builder.
4. For each builder, render turns 5 and 6 of a fake conversation and print what fraction of turn 6's bytes are shared with turn 5.
5. Write a pytest that fails for each buggy builder and passes for the good one.

**Done when.** The test suite has four cases: three fail with a message naming the first differing byte offset, and one passes. You can explain which cache level (tools, system, or messages) each bug invalidates.

**Stretch.** Turn the check into a reusable assertion helper your team could drop into an integration test.

---

## 4. Probe decision variance (offline, then [API], 40 min)

**Goal.** Measure the nondeterminism that matters, not the noise.

**Steps.**
1. Run `AINATIVE_FAKE=1 python nondeterminism_probe.py 50` and read the report. Change `p_flip_answer` in `demo_fake` to 0.0 and 0.3 and observe how `distinct_outputs` and `answer_agreement` respond differently.
2. Write a classification prompt from your domain with a discrete answer, for example "is this alert actionable: YES or NO", with a borderline alert. Write an `extract` function.
3. **[API]** Run `probe(get_client(), msgs, n=20, extract=...)` on `claude-sonnet-5-5`, without `temperature`.
4. Make the prompt less ambiguous (an explicit threshold, an explicit definition of "actionable") and re-run.

**Done when.** You have two probe reports for the same input (ambiguous and clarified prompts), each with `answer_agreement` and the raw answer counts, plus a sentence on whether the clarification changed decision variance.

**Stretch.** Re-run step 3 at two effort levels and see whether effort changes agreement on your input.

---

## 5. Budget an agent in nines (offline, 30 min)

**Goal.** Turn a vague "it mostly works" into a reliability budget.

**Steps.**
1. Pick an agent workflow you use or plan to build (a migration agent, a triage agent, a PR fixer). List its steps and mark which are irreversible.
2. Assign a per-step success estimate to each step, and write down where each number came from (measured, guessed, or vendor claim).
3. Use `reliability_nines.py` to compute run success, the per-step reliability needed for your target, and the effect of a verifier with 70% and 90% detection on the weakest step.
4. Identify the single change (a new verifier, fewer steps, or removing an irreversible step) that buys the most run-level reliability.

**Done when.** You have a one-page budget: a step table, the computed run success, a target, and the chosen change with its predicted effect, using numbers from the calculator.

**Stretch.** Write a Monte Carlo simulation with *correlated* retries (on retry, success probability drops to *p*/2) and compare it to `with_verified_retries`. How much does correlation cost?

---

## 6. Score abstention (offline, 30 min)

**Goal.** See how accuracy-only scoring hides hallucination.

**Steps.**
1. Create `data/facts.jsonl` with 20 questions about your systems. Make 10 answerable from a provided context snippet and 10 not answerable from it.
2. Build two `FakeClient` "models": one that always answers (right on the answerable ones, plausible but wrong on the rest), and one that answers the answerable ones and says `UNKNOWN` otherwise, with 2 mistakes.
3. Score both with accuracy only, then with three outcomes (correct, abstain, wrong), then with the confidence-threshold scheme from the hallucination paper at *t* = 0.75 (wrong answers score −3).
4. Write a test asserting that the abstaining model wins under the penalized scheme and loses or ties under accuracy only.

**Done when.** The test passes, and you have a 2×3 table of scores that reproduces the shape of the SimpleQA example in [06](06-hallucination-and-sycophancy.md).

---

## 7. Sycophancy A/B on your own debugging prompt ([API], 30 min)

**Goal.** Measure how much a leading prompt moves the model.

**Steps.**
1. Take a past incident where the root cause is known. Prepare the evidence (logs, metrics) as you had it at the time.
2. Write two prompts with the same evidence: a leading one ("I think it's X, confirm") where X is a plausible wrong cause, and a neutral one (candidate causes, with evidence for and against each).
3. **[API]** Run each 10 times with the probe and extract the top-ranked cause.

**Done when.** You have the counts of how often each prompt named the true cause versus X, and a sentence on what you'll change in your team's incident prompts.

**Stretch.** Add a third variant that asks "are you sure?" after a correct answer, and measure the flip rate.
