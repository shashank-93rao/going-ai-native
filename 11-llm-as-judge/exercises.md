# Exercises

Run everything from the course root. Offline exercises need no API key. Exercises marked **[API]** need `ANTHROPIC_API_KEY`, and cost a few cents to a dollar at current prices, depending on the model you pick.

---

## 1. Grader triage on the incident data (offline, 30 min)

**Goal.** Feel the difference between a code check and a judge on the same data.

**Steps.**
1. Write `code/impact_checks.py` with two code checks over `data/incident_summaries.jsonl`:
   - `mentions_impact(summary)`: True if the summary contains a count, a percentage, or "no customer impact".
   - `count_matches(facts, summary)`: True if the facts' affected count (use `judge_fakes.impact_count`) appears in the summary.
2. Compute each check's confusion matrix against `human_label` on dev with `calibrate.confusion`.
3. For each check, list the dev items it gets wrong, and label each one with the reason: rounding, scope, severity, hedge, or other.

**Done when.**
- Both checks have tests in `code/test_impact_checks.py`, and `pytest -q 11-llm-as-judge/code` passes.
- You have a three-line note saying which failure mode `mentions_impact` should own on its own, and which errors only a judge could catch. It must cite at least two item ids.

**Stretch.** Make `mentions_impact` a pre-filter in front of `incident_rules_judge`, and show how dev TNR of the *combined* grader changes.

---

## 2. Rogan-Gladen by hand, then a cluster bootstrap (offline, 45 min)

**Goal.** Understand where the corrected estimate and its interval come from.

**Steps.**
1. By hand: a judge has TPR 0.90 and TNR 0.70, and passes 640 of 800 production items. Compute the corrected pass rate. Then compute it again with TNR 0.60, and explain the difference in one sentence.
2. Check both answers with `calibrate.rogan_gladen`.
3. The incident data has six summaries per incident, so the items aren't independent. Add `bootstrap_true_pass_rate_clustered(rows, prod, cluster_key="incident_id")`, which resamples whole incidents.
4. Compare its CI width against the unclustered version on the test split.

**Done when.**
- Your hand answers match `rogan_gladen` to 3 decimal places (the first is 0.833).
- A test asserts that the clustered function is deterministic for a fixed seed, and that it returns an interval containing the point estimate.
- You record both CI widths and say which one you would put on a dashboard.

---

## 3. Likert vs binary with a real model **[API]** (45 min)

**Goal.** Reproduce the Likert-vs-binary comparison with a real judge instead of fakes.

**Steps.**
1. In a scratch script, use `get_client()`, then `compare_judges.likert` and `judge.judge` with `INCIDENT_IMPACT`, on the dev and test splits. Pass `model="claude-opus-5-5"` or another current model.
2. Pick the Likert threshold on dev with `compare_judges.best_threshold`, and apply it to test unchanged.
3. Print both test confusion matrices, and the Likert score histogram by human label.
4. Wrap the client in `RecordingClient` so you can replay the run offline later.

**Done when.**
- You have a cassette file and a replay that reproduces your printed numbers with `ReplayClient`.
- You can state the test TNR of both judges, with Wilson CIs, and which wrong summaries the Likert judge rated highest.
- You have written down whether the real model reproduces the "confident wrong summaries score high" pattern. Either answer is fine, as long as it's backed by the histogram.

---

## 4. Calibrate the code-review judge **[API]** (60 min)

**Goal.** Calibrate a reference-free judge on hard negatives.

**Steps.**
1. Assign splits to `data/code_review_comments.jsonl` with `calibrate.assign_split` (use `fractions=(0.2, 0.4, 0.4)`).
2. Run `judge(client, CODE_REVIEW_BUG, row)` with a real model on dev. For each disagreement, read the critique and decide whether the rubric, the label, or the judge is wrong.
3. Make at most two rubric edits. Freeze. Run test once.
4. Repeat test with a second model from a different tier (for example `claude-haiku-5-5`), and compare.

**Done when.**
- You report TPR/TNR on test for both models, with n per class. With only 20 rows, also write one sentence on why these CIs can't support a decision.
- You have classified CR-009 (the Postgres 10 case) as one of: rubric gap, missing input, or acceptable false negative, with a reason.
- Your rubric edits are a diff against `CODE_REVIEW_BUG`, each tied to a specific item id.

**Stretch.** Write 20 more rows (10 real bugs, 10 confident false alarms) from your own team's review history, and re-calibrate.

---

## 5. Bias-probe a real judge **[API]** (45 min)

**Goal.** Measure position, verbosity and run-to-run behaviour on a real model.

**Steps.**
1. Use the probes in `bias_probes.py` with `judge(...)` and `pairwise.ask_once(...)` wrapping a real client.
2. Run: `verbosity_probe_pointwise` on all 60 incident rows, `double_run_consistency` with `runs=3` on 30 rows, and `position_probe` plus `verbosity_probe_pairwise` on 10 pairs.
3. Re-run the pointwise verbosity probe after deleting "Length and fluency are not evidence" from the rubric (pass a modified `Rubric` built with `dataclasses.replace`).

**Done when.**
- You have a table of probe name, n, rate and flagged, for both rubric versions.
- You can say whether removing the line changed the verbosity flip rate, quoting n.
- The run-to-run rate is reported with n, and if it isn't 0, you list the flipping item ids and what makes them ambiguous.

---

## 6. Be the labeller: criteria drift in practice (offline, 60 min)

**Goal.** Experience criteria drift and measure your own agreement with the dataset's labels.

**Steps.**
1. Hide the `human_label` and `human_critique` columns, and label the 25 test-split incident rows yourself: pass/fail plus one sentence each. Time yourself.
2. Every time you hesitate, write a `rubric_question`.
3. Unhide the labels, and compute your agreement and kappa with `calibrate.confusion`, treating the dataset as the "judge".
4. Turn your top two rubric questions into rubric claims (as text edits to `INCIDENT_IMPACT`).

**Done when.**
- You report kappa between you and the dataset, and the number of disagreements.
- You have at least two `rubric_question`s, each tied to a row id, and a proposed rubric diff.
- You have a one-paragraph answer: should the dataset labels change, or your labels? Who decides, under the principal-domain-expert rule?

---

## 7. Drift drill (offline, 30 min)

**Goal.** Detect a judge regression with the tools in [06](06-who-validates-the-validators.md).

**Steps.**
1. Treat `incident_rules_judge` as the calibrated baseline. Compute its test-split `Confusion`.
2. Treat `padded_lenient_judge` as "the new model the platform team switched to". Build a "recent" sample: pad every test summary with `bias_probes.pad`, judge it with the new judge, and compute the confusion against the human labels.
3. Run `calibrate.drift_alarms(baseline, recent, min_per_class=5)`.
4. Compute `judge.fingerprint` for both setups. Write a short CI check that fails when a result row's fingerprint isn't in a dict of calibration records.

**Done when.**
- `drift_alarms` fires on TNR, and you have pasted its message.
- Your CI check has a test with one known and one unknown fingerprint.

---

## 8. Pairwise prompt A/B, end to end **[API]** (60-90 min)

**Goal.** Run a real blinded, swapped pairwise comparison between two generator prompts.

**Steps.**
1. Write two summary-generation prompts: A ("summarise this incident") and B (impact-first, with an explicit "Customer impact:" line). Generate one summary per incident with each, using `claude-sonnet-5-5`.
2. Compare A vs B with `pairwise.compare`, using a *different* judge model (for example `claude-opus-5-5`).
3. Also score every summary with the pointwise `INCIDENT_IMPACT` judge.
4. Report the pairwise summary (win rate, ties, inconsistency, sign test p) and the pointwise pass rates for A and B.

**Done when.**
- Every pair has exactly two judge calls in the cassette, and no judge prompt contains "A", "B", "baseline" or a model name.
- You state whether pairwise and pointwise agree in direction, and if they don't, which you trust and why.
- With 10 incidents, you write down how many incidents you'd need for the sign test to detect a 70/30 split at p < 0.05. Use `sign_test_p` to find the smallest n.
