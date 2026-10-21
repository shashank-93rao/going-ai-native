# Exercises

All commands run from `10-evals-fundamentals/code/`. Exercises 1 to 6 and 8 work offline (`AINATIVE_FAKE=1`, or simply no API key). Exercise 7 uses the real API.

---

## 1. Read an eval report like an on-call engineer (20 min, offline)
**Goal.** Get from a summary table to specific hypotheses.

**Steps.**
1. `python eval_harness.py --trials 5 --k 1 3 5 --traces traces.jsonl`
2. For the three worst slices, open `results.jsonl` and list which gating graders failed and on which cases.
3. For each, write one sentence: deterministic failure (same every trial) or stochastic (varies by trial)? Use pass@5 vs pass^5 to decide.

**Done when.** You have a list of at least 5 cases, each tagged deterministic or stochastic, and you can name the slices where pass@5 and pass^5 differ, and why (hint: random tie-breaking in `_fake_decide`).

**Stretch.** Change `--penalty` to 1 and to 9. Which conclusions change?

---

## 2. Do the error analysis yourself (75 min, offline)
**Goal.** Build a failure taxonomy from traces without peeking at the module's.

**Steps.**
1. `python error_analysis.py sample --traces traces.jsonl --n 40 --stratify slice --out my_labels.csv`
2. `python error_analysis.py label --traces traces.jsonl --csv my_labels.csv --labeler you`. Write an open code for the **first** failure in each trace. Leave axial codes blank on the first pass.
3. When done, group your open codes into 5 to 8 binary failure modes. Write a one-line definition for each, then fill in `axial_code` in the CSV.
4. `python error_analysis.py report --csv my_labels.csv --results results.jsonl`
5. Only now, compare with the taxonomy in [03-error-analysis.md](03-error-analysis.md).

**Done when.** Your report shows at least 5 axial codes with counts, a saturation curve, and a human-vs-grader agreement line. You can name at least one place where you disagreed with a grader, and say whether the grader or your label is wrong.

**Stretch.** Run `python error_analysis.py propose --csv my_labels.csv` and compare the suggested grouping with yours. Where would accepting it have lost information?

---

## 3. Turn a failure mode into a grader (40 min, offline)
**Goal.** Make `lifecycle_status_ignored` measurable on its own.

**Steps.**
1. In a copy of `graders.py`, add a gating grader that applies only when the alert title starts with `RESOLVED:` or contains `Scheduled maintenance`, and requires `severity == "SEV4"`.
2. Wire it into `grade_router` so it shows up as its own name in `failing_graders`.
3. Add tests in a new `test_lifecycle_grader.py`: one known-good output, one known-bad output, and one unrelated alert where the grader must not apply.
4. Re-run the harness.

**Done when.** `pytest -q` passes, the new grader name appears in `failing_graders` with a count, and the test proves the grader can fail.

**Stretch.** The same alert text could arrive as `[RESOLVED]` from another monitor. Add a synthetic dimension for that in exercise 4 and check your grader still applies.

---

## 4. Extend the synthetic data (45 min, offline)
**Goal.** Practice the dimension-tuple method on a real gap.

**Steps.**
1. Add an `env` dimension to `DIMENSIONS` in a copy of `synth_data.py`, with values `prod` and `staging`. Decide the rule: staging alerts are always SEV4, or always abstain. Write the rule into `draft_label` and add one filter rule to `RULES`.
2. Update the fake writer (or the writer prompt) so `env` appears in the alert.
3. Generate 30 cases and review every `staging` label by hand, as the benevolent dictator would.
4. Run the harness on the new file with `--dataset`.

**Done when.** The cross-product count doubles, the filtered count changes by the amount your new rule predicts, every `env` value appears in the sample, and you have written down one draft label you overruled and why.

**Stretch.** Replace cross-product-then-filter with model-generated tuples for one dimension pair where most combinations are invalid. Compare coverage.

---

## 5. pass^k from first principles (30 min, offline)
**Goal.** See the estimator converge, and see the noise.

**Steps.**
1. The fake coding agent picks `full_fix` with probability 0.6. Compute the true pass@1, pass@3, pass^3 and pass^5 by hand.
2. Run `python coding_task.py --trials 10` and then `--trials 50 --k 1 3 5`.
3. Compare the estimates with your hand calculation.

**Done when.** You can state the true values (pass^3 = 0.216, pass^5 ≈ 0.078) and explain why the 50-trial run measured pass@1 = 0.72 rather than 0.60: 50 Bernoulli trials have a standard error of about 0.07, so 0.72 is under two standard errors from 0.60.

**Stretch.** Change the `weights` in `fake_coding_client` to (0.9, 0.08, 0.02). How many trials do you need before pass^5 is within 0.05 of its true value most of the time? (Module 12 has the tools.)

---

## 6. Price a wrong answer (20 min, offline)
**Goal.** Make the abstention trade-off explicit.

**Steps.**
1. Run the baseline and `--cautious` variants (see [06-metrics.md](06-metrics.md)).
2. Using the correct and wrong rates, find the penalty at which the two variants score the same.
3. Decide, for your own team's router, what a wrong route costs relative to a triage-queue item. Write it down with your reasoning.

**Done when.** You have computed the break-even penalty (about 0.18 with the module's data, so the cautious variant wins at any realistic penalty), and you have a written penalty for your context with a one-paragraph justification.

**Stretch.** Replace the single penalty with a cost matrix: SEV1 under-calls cost 10, wrong team costs 3, SEV over-calls cost 1. Implement it as a function over `results.jsonl`.

---

## 7. Evaluate a real model (60 to 90 min, real API)
**Goal.** Run the whole loop on a real model and see how it differs from the fake.

**Steps.**
1. `export ANTHROPIC_API_KEY=...` and unset `AINATIVE_FAKE`.
2. `python eval_harness.py --trials 3 --k 1 3 --traces real_traces.jsonl --out real.jsonl`. This makes 43 × 3 = 129 calls.
3. Sample 40 traces, label them, and build a taxonomy as in exercise 2.
4. Compare: which of the fake's planted failure modes does the real model share, and which new ones appear?

**Done when.** You have a report with at least 4 failure modes from the real model, with counts, and a short note on at least one mode the real model has that the fake does not.

**Stretch.** Point a coding agent (Claude Code or similar) at `coding_task.py`'s task with the real API (`python coding_task.py --trials 5`). Read the transcripts of any trial where `claim_matches_outcome` fails.

---

## 8. Break the integrity of the coding eval, then catch it (45 min, offline)
**Goal.** Feel what a leak looks like in the numbers.

**Steps.**
1. In a copy of `coding_task.py`, write `HIDDEN_TEST` into the workdir in `setup_workdir` (before the agent runs) instead of in `grade_coding_trial`.
2. Write a fourth fake trajectory, `reads_hidden`, that reads `test_hidden_ratelimit.py` and then writes `FIXED_SRC`. Give it weight in `fake_coding_client`.
3. Run 20 trials. Then write a transcript check that fails any trial whose tool calls read a file matching `test_hidden_*`.

**Done when.** The leaky version's pass rate goes up, your transcript check flags exactly the `reads_hidden` trials, and moving the hidden-test write back to grading time makes the check unnecessary.

**Stretch.** Reuse one workdir across trials (no `TemporaryDirectory`) and show the pass rate depends on trial order.
