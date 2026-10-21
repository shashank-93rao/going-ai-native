# Exercises

Run everything from the course root. Offline exercises need no API key: set `AINATIVE_FAKE=1` to force the fakes even when a key is present.

---

## 1. Emit conformant GenAI spans (offline, 45 min)
**Goal:** your own LLM call sites produce spans that an OTel backend would recognise, with no content leaks.

**Steps**
1. Wrap a client with `otel_like.TracedClient` and make three calls inside an `agent_run` span, plus one `tool_call` span that raises `TimeoutError`.
2. Export every span with `to_otel()` and dump them as JSONL.
3. Add a test that fails if any exported attribute value contains `@` or `sk-ant-`.
4. Give one fake response `usage.cache_read_input_tokens = 5000` and check the token arithmetic.

**Done when**
- Span names match `chat {model}`, `execute_tool {tool}` and `invoke_agent {agent}`.
- `gen_ai.usage.input_tokens` equals input + cache read + cache write.
- `error.type == "TimeoutError"` and contains no message text.
- Your leak test passes with `capture_content=False` and with `capture_content=True`.

**Stretch:** install the OpenTelemetry SDK in a scratch venv (not the course venv) and export the dicts as real spans to a local collector or Jaeger.

---

## 2. Calibrate, sample and correct a judge (offline, 60 min)
**Goal:** see the corrected pass rate recover the truth, and see where it fails.

**Steps**
1. Generate 2,000 traces with `prod_fixtures.generate(n=2000, bad_rate=0.08)`. Ground truth is known: an output is bad if it came from `BAD_OUTPUTS`.
2. Write a fake judge with a configurable TPR and TNR that flips verdicts deterministically by trace-ID hash.
3. For (TPR, TNR) in {(0.95, 0.95), (0.9, 0.7), (0.6, 0.6)}, compute the raw rate, the corrected rate and the true rate on a 10% consistent-hash sample.
4. Now let the judge's *actual* TPR differ from the one you pass to `LLMJudge` by 0.05, which is what happens when calibration goes stale.

**Done when**
- You have a table of raw, corrected and true rates for all three judges.
- The corrected interval contains the true rate for the first two judges.
- You can state how many points of error a 0.05 stale-TPR error causes at your base rate.

**Stretch:** bootstrap the calibration set (resample the TPR and TNR estimates) and widen the reported interval accordingly.

---

## 3. Catch the cache incident before finance does (offline, 45 min)
**Goal:** turn [examples.md scenario 3](examples.md#3-incident-prompt-cache-misses-blew-the-budget) into automated detection.

**Steps**
1. Generate a healthy hour with `prod_fixtures.generate(cache_hit=0.95)` and a broken hour with `generate(cache_hit=0.0, seed=9, id_offset=10_000)`.
2. Run `compute_slis` and `evaluate_thresholds` on each with a `cache_hit_rate >= 0.85` rule.
3. Add a `cost_per_request_usd <= 0.009` rule.
4. Write the CI test from the postmortem (`test_system_prompt_is_cache_stable`) against `cache_incident.system_prompt` and confirm it fails for `"v15"`.

**Done when**
- The healthy hour raises no alerts. The broken hour raises both a cache alert and a cost alert.
- The CI test fails on v15 and passes on v14.

**Stretch:** extend `CachingFakeClient` with a minute-precision timestamp and measure the hit rate. Then explain why "round the timestamp" is still the wrong fix.

---

## 4. Build a router and prove its failure modes (offline, 60 min)
**Goal:** route, cascade, retry, fall back and enforce a budget, all under test.

**Steps**
1. Read `router.py` and `test_router.py`.
2. Add a test where Sonnet returns a spend-cap-style `APIStatus(429)` with **no** `retry_after`. Decide the right behaviour (hint: it will not recover) and change `is_retryable` or the router so it falls back immediately instead of retrying.
3. Add a per-tenant `Budget` map and a test showing that tenant A exhausting its budget does not affect tenant B.
4. Using the `escalated` attribute on the `route` span, compute the escalation rate over 1,000 fake requests in which the cheap tier fails 30% of the time.

**Done when**
- All existing tests still pass, and your new tests pass.
- The no-`retry-after` 429 makes exactly one attempt on the primary.
- Escalation rate is reported as 0.30 ± 0.03.

**Stretch:** compute the break-even acceptance rate at which the cascade costs less than always calling Sonnet, using the prices in `pricing.py`, and verify it empirically.

---

## 5. Size and run a canary (offline, 45 min)
**Goal:** feel how much data a quality canary needs, and why pairing helps.

**Steps**
1. Use `required_n_per_arm` for margins of 0.5, 1, 2 and 5 points at base rates of 0.80, 0.95 and 0.99.
2. Simulate 1,000 canaries where the canary is truly 1.5 points worse at a base rate of 0.95, with 1,500 sessions per arm. Count how often `decide` returns ROLLBACK, CONTINUE and PROMOTE.
3. Repeat with `looks=1` and `looks=5`.
4. Simulate the paired version: the same inputs, where 3% of inputs flip one way and 1.5% flip the other.

**Done when**
- You have a table of required n.
- The false-PROMOTE rate on a truly worse canary is below 5% for each `looks` setting.
- You can state how many paired cases detect a 1.5-point regression at 80% power, compared with unpaired.

**Stretch:** implement an alpha-spending (O'Brien–Fleming-style) boundary and compare its power with Bonferroni at 5 looks.

---

## 6. Write the SLO doc and dashboard spec for a real feature (real system, 90 min)
**Goal:** apply [07](07-slos-for-ai-features.md) and [examples.md scenario 1](examples.md#1-a-dashboard-spec-for-an-llm-feature) to something you own.

**Steps**
1. Pick an LLM feature at work, or the agent you build in [Module 99](../99-capstone/README.md).
2. Write its SLO doc with availability, TTFT, at least one code-check quality SLI, a cost SLI and a cache hit-rate SLI, plus an error-budget policy.
3. Write the dashboard spec YAML. For each of the last three incidents or bugs in the feature, mark which panel would have moved first.
4. Pull one week of real traces and compute the baseline for each SLI with `online_eval` (adapt `summarize` to your span shape).

**Done when**
- Every SLI has a measured baseline with n and an interval.
- Every past incident maps to a panel.
- Your product owner has agreed the error-budget policy in writing.

---

## 7. Kill a harness mid-run and resume it (real or fake API, 90 min)
**Goal:** implement the write-ahead session log from [06](06-durable-agent-infrastructure.md) and prove that resume is safe.

**Steps**
1. Build a minimal agent loop over `ainative_kit` with two tools: `create_ticket` (idempotent on a key) and `post_message` (not idempotent).
2. Append `tool_call_started` and `tool_call_finished` events to a JSONL session log. Implement `wake(session_id)`.
3. Write a test that raises an exception inside `post_message` after the side effect but before `tool_call_finished` is written, then calls `wake`.
4. Make `post_message` safe on resume by checking for the effect before redoing it.

**Done when**
- After the crash and `wake`, exactly one ticket and one message exist.
- The session completes.
- The log shows the replayed call.

**Stretch:** run two "harness versions" that differ in system prompt, pin sessions to the version they started on, and show that a session started on v1 finishes on v1 after v2 is deployed.
