# Exercises

Exercises 1 to 3 run offline with this module's code. Exercises 4 to 7 need a real coding agent (Claude Code or Codex) and a repo you work in. Prefer a real service, since toy repos hide the hard parts.

---

## Exercise 1: Break the fan-out driver on purpose (offline, 30 min)

**Goal:** Understand every control in `fanout.py` by watching it fire.

**Steps**
1. `cd 04-agentic-coding-workflows/code && ../../.venv/bin/python migrate_demo.py --keep /tmp/mig`. Read `/tmp/mig/results.jsonl`.
2. Rerun with `--concurrency 1` and compare `wall_seconds` and `agent_seconds` to the first run.
3. Write a `targets.txt` with the 40 files from `/tmp/mig/services` (`ls /tmp/mig/services/*.py > /tmp/mig/targets.txt`), and run `fanout.py` directly (with `--results /tmp/mig/scratch.jsonl`, so the step 1 results stay clean) with `--canary 3` after moving `svc_05_shipment.py` (the `fail` target) to the top of the list. Observe that the batch aborts.
4. Run with `--max-failures 1 --concurrency 1` (again into `scratch.jsonl`), and count how many targets are `cancelled`.
5. Fix the planted failures by deleting the `# FAKE:` lines, then rerun with `--resume --results /tmp/mig/results.jsonl`. Confirm that only the previously failed targets ran again (time it, or count lines appended).

**Done when**
- You can explain in one sentence each why `svc_12`, `svc_20` and `svc_33` end with different statuses.
- The canary run from step 3 shows `cancelled` for 37 targets.
- The `--resume` run in step 5 appends exactly 3 new lines to `results.jsonl`, all `ok`.

**Stretch:** Add a `--budget-usd` flag to `fanout.py` that trips the breaker once summed `cost_usd` exceeds it, with a test using `fake_agent.py`'s fixed $0.01 per call.

---

## Exercise 2: Catch tautological tests (offline, 30 min)

**Goal:** Learn to spot tests that can't fail, and learn where heuristics stop.

**Steps**
1. Write five tests for a small function in your language of choice (e.g. `fingerprint(body)` from scenario 1): two good, and one each of asserts-the-mock, swallowed, and oracle-from-impl.
2. Run `python tautology_lint.py your_test.py`. Check that it flags the three bad ones.
3. Write a **metamorphic** test (e.g. `fingerprint(body) == fingerprint(reordered(body))`). Run the linter and see the false positive. Write one sentence on why the test is valid.
4. For one of your good tests, introduce a bug in the implementation by hand. Confirm the test fails. Do the same for the asserts-the-mock test, and confirm it still passes.

**Done when**
- The linter output lists exactly your three planted bad patterns, plus the metamorphic false positive.
- You have a two-row table: "bug introduced → good test fails, mock test passes".

**Stretch:** Add a `mocked-sut` rule to `tautology_lint.py`: flag `patch("...X")` inside `test_X*`. Add a test for it in `test_review_tools.py`.

---

## Exercise 3: A reviewer that can't hallucinate evidence (offline, 30 min; optional real API)

**Goal:** See why constraining reviewer output in *code* beats asking nicely in the prompt.

**Steps**
1. Read `diff_reviewer.py`. Run `AINATIVE_FAKE=1 ../../.venv/bin/python diff_reviewer.py`.
2. Write a test using `FakeClient` that returns three findings: one with valid evidence, one `style`, and one whose evidence string isn't in the diff. Assert that only the first survives.
3. Optional, with `ANTHROPIC_API_KEY` set: run it on a real diff of yours against a real SPEC.md. Count how many findings come back and how many survive the filter.

**Done when**
- Your new test passes in `pytest -q 04-agentic-coding-workflows/code`.
- (If step 3 was done) you've recorded raw vs. kept counts, and judged by hand whether each kept finding is real.

---

## Exercise 4: Explore-plan-implement-verify on a real ticket (real agent, 60-90 min)

**Goal:** Feel the difference the plan review makes.

**Steps**
1. Pick a ticket in your repo that touches 2 to 4 files.
2. Session 1, plan mode (`claude --permission-mode plan`, or read-only Codex): run explore questions with file:line evidence. Ask for a plan that names files, tests and the verification command.
3. Open the plan with `Ctrl+G`. Make at least one substantive edit, a decision the agent got wrong or didn't surface.
4. Implement. End your prompt with the exact verification command and "show the output".
5. Record: the number of corrections you made during implementation, and whether you had to `/clear`.

**Done when**
- The plan file, your edit (as a diff), and the final verification output are saved alongside the PR.
- The PR passes your normal review with no "wrong layer" or "wrong design" comments.

---

## Exercise 5: Interview to SPEC.md, then a fresh-session implementation (real agent, 2-3 h)

**Goal:** Run the full spec-driven loop on something with real failure modes.

**Steps**
1. Choose a feature involving concurrency, retries or money (an idempotent endpoint, a dedupe step in a consumer, a rate limiter).
2. Run the interview prompt from [03](03-spec-driven-development.md), seeded with your known constraints.
3. Edit SPEC.md by hand until every requirement has an ID and a named test, and "Non-goals" and "Done when" are non-empty.
4. Fresh session: plan.md. Fresh session: implement phase by phase, with red/green per phase.
5. Clean-context review against SPEC.md, plus one mutation spot check on the most important invariant.

**Done when**
- Every requirement ID appears in at least one test name or docstring.
- The mutation spot check makes at least one test fail. If none does, you've found an untested invariant: write the test, and re-check.
- `git diff --stat main` matches SPEC section 5, or each deviation is explained in the PR.

**Stretch:** Turn "Done when" into a Stop-hook gate (scenario 1, step 4) and run the implementation session with it.

---

## Exercise 6: Fan out a real mechanical change (real agent, 2 h)

**Goal:** Use `fanout.py` with `claude -p` or `codex exec` on 10 to 50 real targets.

**Steps**
1. Find a real mechanical-but-not-sed change in your codebase: a deprecated API, a logging call that needs structured fields, or a config key rename with per-site defaults.
2. Write the per-target verifier first. Prove it fails on an unmigrated target.
3. Write `prompt.md`, including an explicit "if unsure, change nothing and end with FAIL" escape hatch.
4. Run with `--canary 3 --max-failures 5 --retries 1 --results results.jsonl`, with commits through `--on-success`.
5. Do the aggregate review from scenario 3, step 5.

**Done when**
- `results.jsonl` exists, and every non-`ok` target has a one-line disposition (prompt fix, hand fix, or out of scope).
- You report `claimed_ok_but_not_ok`, `needed_retry`, `cost_usd` and wall time for the batch.
- The commit history shows only driver-made commits, one per target.

**Stretch:** Run the same batch with both `claude -p` and `codex exec --sandbox workspace-write`, and compare success rate, retries and cost on identical targets.

---

## Exercise 7: Measure whether delegation helped you (real agent, spread over a week)

**Goal:** Replace the feeling with a number (the METR perception gap).

**Steps**
1. List 8 or more comparable small tasks from your backlog (similar size and type).
2. Before starting each one, predict the time with and without an agent. Flip a coin to choose which way you do it.
3. Record wall time to merged PR, review rounds, and any post-merge fix.
4. At the end, compare predicted vs. actual for each arm.

**Done when**
- You have a table of at least 8 tasks with arm, predicted time, actual time, review rounds and post-merge fixes.
- You've written down one task type where the agent clearly helped, and one where it didn't (or where you can't tell yet with this sample size).

**Stretch:** Bring it to [Module 12](../12-hill-climbing/README.md) and put an error bar on the difference.
