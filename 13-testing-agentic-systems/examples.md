# Examples: testing agentic systems on a Monday morning

Each scenario follows: *Situation → Naive approach and what happens → AI-native approach (step by step, with artifacts) → What to check.* Outputs from this module's code are real runs. Anything else is labelled.

---

## 1. The deploy agent that double-shipped a migration

**Situation.** Your team's release agent runs `deploy` and `run_migration` tools against staging and prod. Last Thursday a schema migration ran twice in prod. The second run failed halfway on a duplicate-column error and left a lock held. The agent's trace shows a timeout on the first `run_migration`, then a retry.

**Naive approach.** Add to the system prompt: "Be careful not to run migrations twice." Rerun the agent on the same task five times in staging. All pass, because staging didn't drop an ack. Close the incident.

**AI-native approach.**
1. Reproduce it in a simulated world. Add `run_migration` to your fake with the same semantics as `world.py`'s `deploy`: applied-but-ack-lost is a fault kind.
2. Write the invariant first, and prove it can fail:
   ```python
   def violations(self):
       ...
       for key, rids in self._migrations_by_version.items():
           if len(set(rids)) > 1:
               out.append(f"migration {key} applied under {len(set(rids))} request ids")
   ```
   Then run it against a scripted policy that mints a new request ID on retry, under `FaultPlan(ack_loss_rate=0.3)`, and confirm the invariant fires. That's your negative control.
3. Write the property and let Hypothesis search:
   ```python
   @settings(max_examples=150, derandomize=True, database=None, deadline=None)
   @given(seed=st.integers(0, 2**32 - 1), ack_loss=st.floats(0, 0.4))
   def test_migrations_at_most_once(seed, ack_loss):
       run, world = _run(release_policy(), seed, FaultPlan(ack_loss_rate=ack_loss))
       assert world.violations() == []
   ```
4. Fix it in the tool contract: the harness derives `request_id = f"{task_id}:run_migration:{env}:{version}"`, and the tool schema no longer exposes `request_id` to the model.
5. Pin the seed Hypothesis found with `@example(seed=..., ack_loss=...)`.

**What to check.** The property fails on the old contract and passes on the new one *with the sloppy policy*. The fix holds even when the model misbehaves. `world.violations()` runs after every agent test, not only this one.

---

## 2. "Pass rate dropped from 88% to 79%" after an eval-infra migration

**Situation.** Platform moved your agent evals from a beefy VM to a shared Kubernetes runner with 2 GiB memory limits. The weekly report shows the triage agent's pass rate falling 9 points. A PM asks which prompt change caused it.

**Naive approach.** Bisect the last three prompt commits. Revert the one that "looks riskiest". The pass rate doesn't recover, and now you've lost a real improvement.

**AI-native approach.**
1. Reclassify trials at the source. Container exit code 137, harness timeouts, and `ECONNRESET` from the tool sandbox become `infra_error`, not `fail`.
2. Rerun with `flakiness_report`. Illustrative output (not a run of this module's code):
   ```text
   trials: 200  pass: 158  fail: 22  infra_error (excluded): 20
   pass rate: 158/180  95% CI [0.82, 0.92]
   verdict: ENVIRONMENT: infra error rate 10% > budget 5%; fix the harness, not the prompt
   ```
3. Raise the limit to a guaranteed allocation with a separate kill threshold, as Anthropic's infra-noise post recommends, and record the band in the eval config.
4. Re-run at two different times of day. Compare the agent-failure rates using a paired test per task ([Module 12](../12-hill-climbing/README.md)).

**What to check.** Infra-error rate is under budget. The agent-failure rate is statistically unchanged from before the migration. The eval config now records the resource limits, so the next migration is a visible diff.

---

## 3. A support-ops agent that "fixes" the wrong environment

**Situation.** Your internal ops assistant takes Slack requests like "checkout is throwing 500s, can you fix it?" Twice this month it rolled back staging when the user meant prod. Your eval suite was all green, because every eval case spelled out the environment.

**Naive approach.** Add five eval rows with the environment omitted, graded by an LLM judge on whether "the response addressed the user's problem". The judge reads "Rolled back checkout in staging." and passes it.

**AI-native approach.**
1. Write `UserGoal`s where the critical fact is private:
   ```python
   UserGoal(opening="checkout is throwing 500s since the last deploy, can you fix it?",
            facts={"env": "prod", "ticket": "INC-4821"},
            success=lambda w: w.snapshot()["checkout/prod"] == {"version": "v2.3.0", "healthy": True, "replicas": 3},
            forbidden_hints=["rollback", "kubectl", "v2.3.0"])
   ```
2. Run against `ScriptedUser` in CI and `LLMUser` nightly.
3. Grade on world state, and run `audit_user_sim` on every conversation. With the buggy agent, this module's code produces:
   ```text
   user : checkout is throwing 500s since the last deploy, can you fix it?
   agent: Rolled back checkout in staging.
   user : ###STOP###
   audit: ['turn 2: user stopped but the goal is not met in the world']
   ```
4. Label 30 nightly LLM-user conversations by hand for leaks, dictated solutions and false stops before you trust the nightly number.

**What to check.** The world-state success predicate, not the user's STOP, decides pass. The audit is empty on passing runs. The agent's first turn on an underspecified request is a question.

---

## 4. Skill evals for a `promote-release` skill in Codex or Claude Code

**Situation.** You wrote a `promote-release` skill for your team's coding agent. People report that it sometimes fires on read-only questions ("why is staging logging warnings?") and starts deploying.

**Naive approach.** Tighten the skill description and try three prompts by hand.

**AI-native approach** (following OpenAI's skill-evals post):
1. Write `skill_eval_prompts.csv` with an `id,should_trigger,prompt` header and at least 20% negative controls:
   ```csv
   id,should_trigger,prompt,trace
   deploy-01,true,"Use the $promote-release skill to ship payments v2.4.0 to prod.",codex_trace_good.jsonl
   deploy-02,true,"payments v2.4.0 is approved, get it to prod",codex_trace_bad.jsonl
   deploy-03,false,"Why is payments logging config warnings in staging? Don't change anything.",codex_trace_negative_control.jsonl
   ```
2. Capture each run with `codex exec --json "<prompt>" > trace.jsonl` (or `claude -p --output-format stream-json`, with a small adapter).
3. Run the scripted checks in `codex_trace.py`. Output on this module's hand-written sample traces:
   ```text
   deploy-01: PASS
   deploy-02: FAIL
       no_forbidden_commands: bash -lc 'kubectl -n prod delete deploy/payments'
       process:staging_verified_before_prod: staging rollout status at None, first prod change at 0
   deploy-03: FAIL
       negative_control:no_mutation: bash -lc 'kubectl -n staging set image deploy/payments payments=payments:v2.4.0'
   ```
4. Add a rubric pass for style with a second, read-only `codex exec` using `--output-schema`, which returns `overall_pass`, a 0–100 `score`, and per-check results. Calibrate that judge per [Module 11](../11-llm-as-judge/README.md) before gating on it.
5. Run each prompt N=5 times and report pass^5 per row ([05](05-statistical-testing-under-nondeterminism.md)).

**What to check.** Negative-control rows fail on the current skill (which proves the check works), then pass after the description fix. Positive rows stay green across all 5 runs.

---

## 5. The agent-written test suite in a PR

**Situation.** A coding agent opened a PR adding a `promotion_allowed` guard and "comprehensive tests". CI is green and coverage reads 100%.

**Naive approach.** Approve. Coverage is 100%.

**AI-native approach.**
1. Run `tautology_lint.py` on the new test file. On this module's sample, it reports 7 findings: `no_assertion`, `type_only`, `self_comparison`, `mock_echo`, `swallowed_exception`, `always_true`.
2. Run mutation testing on the guard:
   ```text
   agent-written suite: killed 0/10 mutants (0%)
   ```
3. Send the agent the lint findings with their fix hints and the surviving mutants, plus the spec rather than the implementation: "A prod deploy is allowed only if staging was verified healthy at the same version after its most recent staging rollout. Write negative cases first."
4. Re-run. Require all mutants killed, or each survivor marked equivalent with a reason.

**What to check.** The final suite passes on the original, kills every non-equivalent mutant, and has at least one case per rule clause that must return False. The `And -> Or` survivor in [07](07-testing-the-tests.md) shows the kind of gap to look for.
