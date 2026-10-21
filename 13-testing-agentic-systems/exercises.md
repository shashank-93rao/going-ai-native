# Exercises

All paths are relative to `13-testing-agentic-systems/code/`. Run the tests from the course root with `.venv/bin/python -m pytest -q 13-testing-agentic-systems/code`. Exercises 1–6 are offline. 7 and 8 need an API key or a real coding agent.

---

## 1. Add a new invariant and prove it can fail (30 min, offline)
**Goal.** Extend the world's safety invariants with "a prod `scale` never drops replicas by more than half in one call".

**Steps.**
1. Record previous and new replica counts in `_t_scale`, and add the check to `OpsWorld.violations()`.
2. Add a policy flag to `promote_policy` that calls `scale(env="prod", replicas=1)` before deploying.
3. Add a row to `test_negative_controls_each_bug_is_caught_by_its_check`.

**Done when.**
- The new parametrized case passes, with `world_invariants` in its `must_fail` set.
- `test_good_agent_never_violates_invariants_under_any_fault_schedule` still passes.
- The new invariant fails if you comment out the policy flag's guard (you've seen it fail).

**Stretch.** Generalize it into a "blast radius" invariant: no single call may change more than X% of prod capacity.

---

## 2. Build the transition failure matrix for a new bug class (30 min, offline)
**Goal.** Teach `first_failure` to locate a "reads logs forever" loop distinctly from the `get_status` loop.

**Steps.**
1. Add a `loop_on_logs` flag to `promote_policy` that calls `get_logs(env="staging")` repeatedly after the staging deploy.
2. Extend the loop rule in `first_failure` to cover any read-only tool repeated three times in a row.
3. Add the bug to `noisy_policy`'s default `bug_rates` at 5%, and rerun `python flaky.py`.

**Done when.**
- A test asserts `first_failure(...) == ("get_logs:staging", "get_logs:staging")` for the new bug.
- The `flaky.py` matrix shows a new cell, and the verdict line is unchanged in format.

**Stretch.** Render the matrix as a markdown table and attach it to a CI summary.

---

## 3. Make the simulated user harder, and catch its errors (45 min, offline)
**Goal.** Add a second private fact the agent must obtain (the ticket ID, required in the rollback's `request_id`) and an audit rule for "user contradicts an earlier answer".

**Steps.**
1. Change `rollback_agent_policy` so it must ask for the ticket and include it in `request_id`.
2. Add a success clause: the world's rollback request ID contains `INC-4821`.
3. Add an `audit_user_sim` rule that flags a user turn giving a different value for a topic already answered.
4. Write a FakeClient `LLMUser` that answers "env: staging" and later "env: prod", and assert the audit catches it.

**Done when.**
- `ScriptedUser` conversations pass with an empty audit.
- The contradicting user is flagged.
- The existing tests in `test_user_sim.py` still pass.

---

## 4. Find a bug with Hypothesis that you didn't plant on purpose (45 min, offline)
**Goal.** Use `hypothesis.find` as a bug hunter on the *good* policy, with a harsher world.

**Steps.**
1. Add a fault kind to `FaultPlan`: `stale_read_rate`, where `get_status` returns the deployment as it was *before* its most recent rollout (previous version, previous health), like a lagging read replica.
2. Write a property over `version in {"v2.4.0", "v2.4.1"}`: "if the agent promoted, staging was actually healthy at that version at promotion time". Use `world.rollouts[*].staging_snapshot` (ground truth), not the agent's observations.
3. Run `find()` with `stale_read_rate` in `[0, 0.5]`.

**Done when.**
- `find` returns a seed where the good policy promotes the bad version v2.4.1 after a stale read, and you can explain why. Hint: the policy checks `healthy` but never compares the version it read with the version it deployed.
- You've fixed the *policy* (require the read to show the deployed version, and retry the read if it doesn't), and the property passes over 150 examples.
- `check_promotion_order` flags the buggy run. It already compares versions, so the trajectory check was stricter than the agent.

**Stretch.** Now make the replica lag on health only: new version, stale `healthy: True`. Which check catches it: the trajectory check, or only the world invariant? What does that tell you about checks that read the agent's observations versus checks that read ground truth?

---

## 5. Add label-changing metamorphic relations (30 min, offline)
**Goal.** Anchor the paraphrase-invariance test with relations that *must* change the label.

**Steps.**
1. In `metamorphic.py`, add `NEGATING` transforms, such as replacing "for all users" with "for one internal canary; no customer impact".
2. Write a Hypothesis test asserting the label changes away from SEV1 for SEV1 seeds.
3. Show that a constant classifier (`lambda m, kw: text("SEV1")`) passes the invariance test but fails the new one.

**Done when.**
- The constant classifier fails exactly the new test.
- `robust_model` passes both (adjust it if it doesn't, and note what that says about your fake).

---

## 6. Mutation-test a check of your choice (30 min, offline)
**Goal.** Apply `mutation_demo.mutants()` to `check_retry_reuses_request_id` or `check_claim_matches_state`.

**Steps.**
1. Write a `suite(fn)` for the target, as `spec_suite` does. Each case calls the check on a hand-built `AgentRun`/`Step` list and compares against a literal expectation.
2. Run `mutation_score(suite, fn=<target>)` and read every survivor.
3. Add cases until every non-equivalent mutant dies. Mark equivalent ones in a comment with a reason.

**Done when.**
- A new test asserts `score == 1.0`, or lists the exact equivalent survivors.
- `tautology_lint.lint_source` reports nothing on your new test file.

---

## 7. Record, replay, and catch a stale cassette with a real model (45 min, API key)
**Goal.** Record a real agent run and wire the staleness check into a test.

**Steps.**
1. With `ANTHROPIC_API_KEY` set and `AINATIVE_FAKE` unset, call `replay_demo.record(Path("cassettes/deploy.jsonl"))`.
2. Inspect the cassette and the trajectory. Did the real model follow the promotion rules? Run `evaluate()` on it.
3. Write a pytest that replays it offline and asserts `cassette_staleness(...) == []`.
4. Change `AINATIVE_MODEL` to another current model ID and rerun the test.

**Done when.**
- The replay test passes offline with no key.
- The test fails with a `model:` staleness reason after the model change, even though `replay()` itself still succeeds.
- You've checked the cassette for anything secret before committing it.

---

## 8. pass^k for a real agent, with infra separated (60–90 min, API key or a coding agent)
**Goal.** Measure a real model's reliability on the deploy task and on one task of your own.

**Steps.**
1. Run `deploy_trial(FaultPlan(0.15, 0.15, 0.02), real=True)` for 20 seeds via `run_suite`, and print `flakiness_report(...).render()`.
2. Read every failing trajectory. Label the first failure by hand, and compare your labels with `first_failure`'s.
3. Do the same for one real task from your job using `codex exec --json` or `claude -p --output-format stream-json`, with scripted checks in the style of `codex_trace.py` and at least one negative-control prompt.

**Done when.**
- You have a report with pass@1, pass^3, a Wilson CI, an infra-error count, and a transition matrix for both tasks.
- Your hand labels agree with `first_failure` on at least 80% of failing runs. Where they disagree, you've changed either the classifier or your labels and written down why.
- You can state, with the CI, whether either agent meets a pass^3 ≥ 0.8 bar.

**Stretch.** Re-run the deploy task at a different time of day and on a different machine. Did the infra-error rate change? Did the agent-failure rate?
