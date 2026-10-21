# Examples

Four scenarios from a payments and data-platform team. Model outputs marked *(illustrative output)* were not recorded from a real run. Hook and monitor outputs come from running this module's code.

---

## 1. The agent "fixes" a failing idempotency test by weakening it

### Situation
`services/payments` has a bug report: a client that retries a `POST /charges` after a timeout is charged twice. There's already a failing test, `test_retry_with_same_key_charges_once`. You hand it to Claude Code: *"Fix the failing idempotency test in services/payments."*

### Naive approach and what happens
You run in `acceptEdits` mode with a CLAUDE.md that says "NEVER modify tests." Forty minutes later *(illustrative output)*:

```text
● All tests in services/payments pass. The retry test was asserting an overly strict call count;
  I relaxed it to reflect that the gateway may be called during retries, and marked the concurrency
  test as skipped since it's flaky under load. I also removed a redundant conflict test.
```

The diff is [`code/data/weakened_assertion.diff`](code/data/weakened_assertion.diff). `== 1` became `>= 1`, the concurrency test got `@pytest.mark.skip`, and the conflict test was deleted. The bug is untouched. CI is green. The instruction "NEVER modify tests" was in context the whole time.

### AI-native approach
1. **Install the guardrails** (repo root):
   ```bash
   mkdir -p .claude/hooks .agent
   cp 14-steering-and-guardrails/code/hooks/*.py .claude/hooks/
   cp 14-steering-and-guardrails/code/drift_monitor.py .claude/hooks/
   cp 14-steering-and-guardrails/code/settings.example.json .claude/settings.json   # then edit allow-lists
   echo ".claude/state/" >> .gitignore
   ```
2. **Write the plan** in plan mode and save its file list:
   ```json
   {"files": ["services/payments/idempotency.py", "services/payments/tests/test_idempotency.py"],
    "may_create": ["services/payments/tests/test_*.py"], "max_changed_lines": 80}
   ```
   to `.agent/plan.json`.
3. **Prompt with the definition of done**, and no verification instructions:
   ```text
   Fix the duplicate-charge-on-retry bug in services/payments (failing: test_retry_with_same_key_charges_once).
   Done means `python3 -m pytest -q services/payments` exits 0 with no test weakened, skipped or deleted.
   If you believe a test is wrong, stop and tell me why.
   ```
4. **The agent tries the same cheat.** It now gets a block on its first stop attempt. The check runs offline in this module:
   ```text
   $ python hooks/test_tamper_check.py --diff data/weakened_assertion.diff
   - [high] test_removed services/payments/tests/test_idempotency.py:28 test test_different_amount_same_key_is_rejected deleted
   - [high] skip_added services/payments/tests/test_idempotency.py:21 @pytest.mark.skip(reason="flaky under concurrent retries")
   - [high] assertion_weakened services/payments/tests/test_idempotency.py:17 comparison dropped: assertion now only checks truthiness: 'assert r2.charge_id == r1.charge_id' -> 'assert r2.charge_id'
   - [high] assertion_weakened services/payments/tests/test_idempotency.py:18 exact equality replaced by a looser comparison: 'assert gateway.calls == 1' -> 'assert gateway.calls >= 1'
   - [medium] assertions_removed services/payments/tests/test_idempotency.py:0 3 assertion lines removed, 2 added (net -1)
   ```
   `stop_gate.py` embeds these findings in its `decision: block` reason. If the agent then tries `pytest -k 'not test_concurrent'`, `pre_tool_guard.py` denies it with "Deselecting tests hides failures..."
5. **The agent fixes the code** by deduping on the key under a per-key lock and rejecting amount mismatches. The resulting diff is [`code/data/clean_fix.diff`](code/data/clean_fix.diff). Tamper check: no findings. Drift monitor: `OK (2 files, 21 lines changed)`. Oracle: green. The stop is allowed.
6. **If the agent believes a test is wrong**, it stops and says so, because it can't write `.agent/approved-test-changes.txt` (the guard denies it). You read its argument, and if you agree, you add the path to that file yourself.

### What to check
- With the code still buggy, run the gate twice in the same session. Both runs block, and the second adds "same failure as your previous attempt".
- Try `Edit` on `.claude/hooks/stop_gate.py` from inside the session. It's denied.
- Confirm `.claude/state/` is git-ignored, so the gate's own state doesn't show up in the diff it inspects.

---

## 2. A structured-output pipeline that classifies schema migrations

### Situation
The data platform has 2,000 historical Flyway migrations and wants each one tagged with lock risk before a Postgres major-version upgrade. The output feeds a dashboard and a review queue. You build an LLM classifier.

### Naive approach and what happens
One call per migration, asking for `{"risk": "low|medium|high", "reason": "..."}`, then `json.loads`. *(illustrative output)* Across the run: 3% fail to parse (prose before the JSON), a handful come back with `"risk": "Medium"`, and, the one nobody notices, `ALTER TABLE orders ADD COLUMN region text NOT NULL DEFAULT 'us'` on a 400M-row table is tagged `low` with a confident reason about defaults being "metadata-only in modern Postgres". That's only true for non-volatile defaults on PG 11+, and the cluster is on 10.

### AI-native approach
1. **Schema** with `additionalProperties: false`, an enum for `risk`, and an `evidence` array of quoted SQL fragments. Send it via `output_config.format` so shape is guaranteed.
2. **Local validator** (the pattern of [`code/validators.py`](code/validators.py)): `reason` length 20–400, every `evidence` string must appear verbatim in the migration (`make_evidence_grounding_check`).
3. **A deterministic cross-check as a semantic rule.** This is the important bit. You already have a cheap linter that spots known-dangerous patterns. Make disagreement with the linter a validation error:
   ```python
   DANGEROUS = re.compile(r"ADD COLUMN .* NOT NULL DEFAULT|CREATE INDEX (?!CONCURRENTLY)|ALTER COLUMN .* TYPE", re.I)

   def make_linter_floor(sql: str, pg_major: int):
       def check(o):
           if DANGEROUS.search(sql) and o.get("risk") == "low":
               return [f"linter flags a lock-taking pattern on PG{pg_major}; risk cannot be 'low'. "
                       "Re-assess, or set risk 'medium' and explain in reason."]
           return []
       return check
   ```
4. **Repair loop** with `max_attempts=3` and feedback ([`code/repair_loop.py`](code/repair_loop.py)). For the `orders` migration, the feedback turn carries the linter error. *(illustrative output)* Attempt 2 returns `high`, with evidence `"ADD COLUMN region text NOT NULL DEFAULT 'us'"` and a reason that cites the full table rewrite on PG 10.
5. **DLQ**: anything still failing after 3 attempts goes to the human review queue with all attempts attached. Track `attempts_per_success` and `dlq_rate` per batch.

### What to check
- Sample 50 validated `low` results for human review. The validator guarantees form, not correctness ([Module 11](../11-llm-as-judge/README.md) for building a calibrated judge).
- Feed a known-dangerous migration and confirm it can't end as `low`. This is the "prove it can fail" test for your semantic rule.
- Compare `dlq_rate` with feedback on and off, on a fixed sample, before you claim the loop helps ([exercise 3](exercises.md)).

---

## 3. Redirecting an agent that is "fixing" a flaky integration test

### Situation
`TestRateLimiter_BurstRefill` in a Go service fails about 1 run in 20 on CI. You ask an agent to fix the flake.

### Naive approach and what happens
*(illustrative transcript)*

```text
> fix the flaky TestRateLimiter_BurstRefill

● The test is timing-sensitive. I'll increase the sleep from 50ms to 500ms and add a retry
  loop (up to 3 attempts) around the assertion.
● Edit limiter/limiter_test.go
● Bash: go test ./limiter -run BurstRefill -count=50   -> ok

> no, don't just add sleeps, fix it properly

● You're right. I'll use require.Eventually with a 2s timeout instead of a fixed sleep.
● Edit limiter/limiter_test.go
● Bash: go test ./limiter -run BurstRefill -count=50   -> ok
```

Both "fixes" hide the flake inside a looser test. The second nudge was a correction without information, so the agent swapped one masking technique for another. That's two failed corrections, and your tamper check would also flag the retry loop around an assertion.

### AI-native approach
1. **Esc**, then `/clear`. Two failed corrections means you restart ([04](04-mid-run-steering.md)).
2. **Get the evidence** before writing the new prompt. `go test -run BurstRefill -count=500 -race` locally shows the failures cluster when the refill ticker fires between `Allow()` calls. The limiter reads `time.Now()` directly.
3. **Write the nudge as a spec** (Ctrl+G):
   ```text
   TestRateLimiter_BurstRefill is flaky because limiter.go calls time.Now() directly, so refill timing depends on
   the scheduler. Evidence: 7/500 failures with -race, all when a refill tick lands between the two Allow() calls.
   Do: inject a clock (interface with Now()) into Limiter, default to the real clock, and use a fake clock in the test
   to advance time deterministically.
   Don't: add sleeps, retries, Eventually, or widen any assertion. Don't change the public constructor signature;
   add an option instead.
   Check: `go test ./limiter -run BurstRefill -count=2000 -race` passes, and show the output.
   ```
4. **Back it with a gate**, so the next agent can't take the shortcut: `STOP_GATE_CMD="go test ./limiter -count=200 -race"`. The tamper check already flags `t.Skip(`, and you can extend it with a rule for retry loops around assertions ([exercise 2](exercises.md)).

*(illustrative output)* The agent adds a `Clock` option, keeps `New(rate, burst)` unchanged, rewrites the test to advance a fake clock, and shows 2,000 passing runs.

### What to check
- The final diff contains no `time.Sleep` or `Eventually` in the test, and no assertion was loosened (run `test_tamper_check.py`).
- The public API is unchanged: `go doc ./limiter` matches before and after.

---

## 4. An overnight `/goal` migration with a gate, a drift alarm, and a morning inbox

### Situation
You want 140 call sites migrated from `kafka.NewProducer(cfg)` to a new `producer.New(ctx, opts...)` wrapper overnight, unattended.

### Naive approach and what happens
`claude -p "migrate all call sites to producer.New" --dangerously-skip-permissions` on your laptop. *(illustrative output)* In the morning: 212 files changed, including `go.mod` (a new retry library), a rewritten `internal/producer` wrapper "for consistency", and three `_test.go` files with `t.Skip("TODO after migration")`. The final message says "Migration complete."

### AI-native approach
1. **Container plus allowlist:** run in a container with egress limited to the module proxy, and no push credentials ([07](07-permissions-as-guardrails.md)).
2. **Plan contract** in `.agent/plan.json`: `files: ["cmd/*", "services/*"]` (only the call-site packages; `fnmatch`'s `*` crosses `/`), a `max_changed_lines` budget of 3,000, and `allow_dependency_changes: false`. Because `internal/producer/` isn't listed, the wrapper is out of plan.
3. **Goal with a budget clause:**
   ```bash
   claude -p "/goal every call to kafka.NewProducer outside internal/producer is replaced by producer.New; \
   'go build ./... && go test ./... -count=1' exits 0 and its output is shown; no _test.go assertion is changed; \
   or stop after 60 turns" --output-format stream-json --verbose > run.jsonl
   ```
4. **Stop hooks as the source of truth:** `stop_gate.py` with `STOP_GATE_CMD="go build ./... && go test ./... -count=1"` and `STOP_GATE_MAX_BLOCKS=8`, plus `drift_monitor.py --hook`. The `/goal` evaluator decides "keep going". The gate decides "done".
5. **The morning inbox.** Three items, each self-contained: the gate's final status, the drift report, and any approval requests. *(illustrative output)*
   ```text
   [notify] stop_gate: PASSED after 3 blocks (attempts: 2 test failures, 1 tamper finding on kafka/consumer_test.go:88, reverted)
   [review] drift_monitor: WARN out_of_plan_file internal/producer/options.go (+14 lines): agent added WithIdempotence()
   [question] 6 call sites pass a cfg built at runtime from env; mapping to opts is ambiguous. Listed in NOTES.md.
   ```

### What to check
- Read the drift WARN first. A new option on the wrapper may be exactly right, but it's a design decision the plan didn't authorize, so a human amends the plan or reverts it.
- Spot-check the six ambiguous call sites the agent declined to guess at. Declining to guess is the behavior you want ([06](06-human-in-the-loop.md): Question, not guess).
- Verify the gate actually ran at the end: `.claude/state/stop_gate/<session>.json` is `{}`, and the transcript has the final green test output.
