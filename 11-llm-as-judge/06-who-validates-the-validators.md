# 06: Who validates the validators: criteria drift, annotation queues, and judge drift

## The idea

A calibrated judge is a snapshot. It was measured against one set of human labels, written under one version of the criteria, with one judge model, on one distribution of outputs. All four of those change over time:

| What drifts | Example | Effect |
|---|---|---|
| **The criteria** | While labelling, the expert decides "roughly a thousand" for 1,050 emails is acceptable rounding | Old labels and the rubric disagree with the expert's current view |
| **The judge** | The provider ships a new model behind the alias you call; you edit one sentence of the rubric | TPR/TNR change with no change in the outputs |
| **The generator** | A new summary prompt produces a failure shape the judge has never seen | TPR/TNR on the new distribution are unknown |
| **The inputs** | A new incident category (third-party outages) starts appearing | Same as above |

Shreya Shankar and co-authors named the first of these **criteria drift**. In their study of EvalGen, a tool that helps people build LLM evaluators, they found that "users need criteria to grade outputs, but grading outputs helps users define criteria" ([Shankar et al., "Who Validates the Validators?", UIST 2024](https://arxiv.org/abs/2404.12272)). Some criteria only appear once you've looked at outputs. The paper's broader point is that LLM-generated evaluators inherit the flaws of the LLMs they grade, so a human has to stay in the loop.

The operational answer is a **standing labelling workflow**: a queue that keeps delivering a small stream of fresh human labels, a rule for when the rubric gets a new version, and drift alarms that compare the judge against those fresh labels.

## Why it matters

Without that workflow, a judge decays silently, the same way an alert rule does when the service behind it changes. Hamel Husain's guidance is direct: if he updates a model, he runs the calibration process again ([Hamel, "Using LLM-as-a-Judge"](https://hamel.dev/blog/posts/llm-judge/)). OpenAI's graders guide names the symptom to watch for: a high model-grader score combined with a low expert score means the grader is being gamed or has drifted ([OpenAI, Graders](https://developers.openai.com/api/docs/guides/graders)). Anthropic's harness-design work shows the judge side directly. The evaluator prompt started out lenient and superficial, and the team tuned it over several rounds by reading its logs ([Anthropic, "Harness design for long-running application development"](https://www.anthropic.com/engineering/harness-design-long-running-apps)).

The distributed-systems version: an SLO that nobody re-validates against user-reported pain eventually measures something users don't care about. A judge with no fresh labels is that SLO.

## How to do it

### 1. Pin and fingerprint the judge

Everything that defines the judge goes into one hash: the rendered system prompt (including few-shots), the tool schema, and the exact model ID. `judge.fingerprint(rubric, model)` computes it. Store it with every calibration report and every eval result:

```json
{
  "judge": "incident_customer_impact",
  "rubric_version": "3",
  "fingerprint": "<judge.fingerprint(rubric, model)>",
  "model": "claude-opus-5-5",
  "calibrated_on": "2026-10-12",
  "labels": {"test_pass": 52, "test_fail": 49, "labeller": "on-call lead, payments"},
  "test": {"tpr": 0.88, "tpr_ci": [0.77, 0.95], "tnr": 0.82, "tnr_ci": [0.69, 0.90], "kappa": 0.70},
  "generator": {"model": "claude-sonnet-5-5", "prompt_sha": "<sha of the summary prompt>"}
}
```

(The numbers above are illustrative, not measured.) If the fingerprint of the judge that produced a result doesn't match a calibration record, that result has no validated meaning. Fail the CI job, the same way you would fail a deploy whose config hash isn't in the release manifest. Calling a pinned model ID rather than a floating alias is what makes "the judge changed" an event you control, instead of something that happens to you.

### 2. Run an annotation queue

An annotation queue is a list of items waiting for human review, each shown with its full context and the judge's verdict and critique. LangSmith offers single-run queues (one output against a rubric) and pairwise queues (two outputs side by side) ([LangSmith docs, annotation queues](https://docs.langchain.com/langsmith/annotation-queues)). A spreadsheet or a 200-line internal web page works just as well. Hamel's advice is to remove all friction from looking at data: full context on one screen, one-click labels, free-text notes ([Hamel, "Field Guide"](https://hamel.dev/blog/posts/field-guide/)).

Fill the queue from four sources, and record which source each item came from:

| Source | Share | Why |
|---|---|---|
| Uniform random sample of production | ~50% | The only unbiased input for drift alarms and re-calibration |
| Items where two judge runs disagreed | ~20% | The ambiguous cases, where the rubric needs work |
| Judge FAILs on high-stakes paths (status-page summaries) | ~20% | Catches over-strict drift cheaply, and these get reviewed anyway |
| New categories or new generator versions | ~10% | Covers the distribution shift before it shows up in the metrics |

Only the random slice goes into the drift alarm and the TPR/TNR estimates. The targeted slices are over-represented hard cases, and they would bias the numbers. They feed rubric work and the next dev set.

A queue item:

```json
{"id": "q-2026-10-19-0142", "source": "random", "judge_fingerprint": "<fp>",
 "inputs": {"facts": "...", "summary": "..."},
 "judge": {"verdict": "pass", "critique": "Count 1,184 and scope 'Pro tier, all regions' match the facts."},
 "human": {"verdict": null, "critique": null, "rubric_question": null}}
```

The `rubric_question` field is where criteria drift gets caught. When a labeller can't decide, or decides against the rubric, they write the question down ("Is 'roughly a thousand' for 1,050 fair rounding?").

### 3. Handle criteria drift as a versioned change

When the expert's answer to a rubric question changes the rubric:

1. Bump `rubric_version` and write the decision into the rubric as a checkable claim ("A count differs from the facts by more than ordinary rounding (3,412 -> 'about 3,400' is fine)").
2. Find the existing labels the decision affects, and re-label them. Labels carry the rubric version they were made under.
3. Re-run dev, then make a **new** test read with the new fingerprint. The old calibration record stays as history; it doesn't silently become the new one.

This is a schema migration for your ground truth, and it deserves the same care: versioned, reviewed, with a backfill.

### 4. Alarm on drift

Every week, or every N fresh random-slice labels, compute the judge's confusion matrix on the new labels and compare it with the frozen calibration. `calibrate.drift_alarms` is a deliberately simple tripwire: it alarms when a recent rate falls below the baseline's Wilson lower bound, and asks for more labels when a class has too few recent examples to say anything.

```python
baseline = Confusion(tp=85, fn=15, fp=25, tn=75)          # frozen test calibration
recent   = Confusion(tp=17, fn=3,  fp=10, tn=10)          # this week's 40 random-slice labels
drift_alarms(baseline, recent)
# ['TNR drifted: recent 0.50 < baseline lower bound 0.66']
```

Watch these signals alongside it:

- **Raw judge pass rate vs corrected rate.** A widening gap means p_obs is moving into a region where the correction is doing most of the work.
- **Double-run flip rate** on a daily sample ([05](05-judge-biases.md)).
- **Bias probes** in CI, on every fingerprint change.
- **Judge-human divergence by category**, using the queue's `source` and the item's category.

### 5. Re-calibrate on model change

Treat these as triggers for a full re-calibration (new dev pass, then a new test read):

- the judge model ID changes, including "same family, new snapshot"
- the rubric or few-shots change (the fingerprint changes)
- the generator model or prompt changes enough to create new failure shapes (judge that by the dev-set disagreements, not by guesswork)
- a drift alarm fires

When you upgrade the *generator* model, run the old judge and the new generator against a fresh labeled sample *before* you trust the judge's verdict on the upgrade. This is the eval version of the model-upgrade drill in [Module 12](../12-hill-climbing/README.md). A judge calibrated on the old generator's mistakes may not recognise the new one's.

## Worked example: a quiet judge regression

(Illustrative scenario. The numbers are not from a real run.)

Your incident-impact judge has been stable for two months: TNR 0.82 on test. On Monday the platform team moves every LLM call from a pinned snapshot to the newest model in the same family, to save cost. The judge's raw pass rate on status-page drafts goes from 71% to 78% overnight. The product team is pleased: "summaries got better."

Nothing about the summaries changed. The fingerprint did. Because the judge result records carry `judge_fingerprint`, the CI gate fails on Tuesday: *no calibration record for fingerprint `9c1e...`*. Someone overrides it to unblock a release, and the weekly drift job then prints:

```text
TNR drifted: recent 0.58 < baseline lower bound 0.69
```

Reading the 12 new false passes in the queue shows a pattern. The new model accepts "partial" outages as matching "100% of requests failed" whenever the summary includes the right region. It reads claim 2 more loosely. The fix is a rubric edit: add "partial is not total" as an explicit fail-if example with a quote, run dev, then make a new test read. Then publish the corrected pass rate, which shows that the summaries had not got better at all.

What stopped this from turning into a quarter of bad decisions: the fingerprint in every result, a random-slice label stream, and a tripwire that compares against the frozen calibration.

## Pitfalls

- **Floating model aliases for judges.** Detect it by grepping judge configs for model names without a version or date. Pin them.
- **Only labelling what the judge flags.** Detect it by checking the queue's `source` mix. Without a random slice you can't estimate TPR at all, because you never see the judge's false negatives on items it passed.
- **Rubric edits without re-labelling.** Detect it by checking that every label carries a `rubric_version` and that the dev/test sets have a single version.
- **Letting an LLM write and validate its own rubric with no human labels.** EvalGen's premise is that a human grades a sample and the system keeps the evaluators that agree with those grades ([Shankar et al.](https://arxiv.org/abs/2404.12272)). LLM-proposed criteria are a fine starting point. LLM-only validation is circular.
- **Labeller fatigue.** Eugene Yan notes that human annotators miss defects when tired ([Eugene Yan, "Product Evals"](https://eugeneyan.com/writing/product-evals/)). Cap sessions at 30-45 minutes, and seed a few known-answer items to measure each labeller's own TPR/TNR.

## In your day job

- Add `judge_fingerprint` to every eval result row, and make CI refuse results whose fingerprint has no calibration record.
- Set up a weekly 20-50 item random-slice labelling session for each judge that gates something. Rotate the labeller, and keep the domain expert as the tie-breaker.
- Put "re-calibrate judges" on the checklist for every model upgrade, next to "re-run the eval suite".
- Keep a `RUBRIC_CHANGELOG.md` per judge. Each entry links the queue items that motivated the change.
