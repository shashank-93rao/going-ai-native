# 03: Calibration: TPR/TNR, the dev/test split, and the corrected pass rate

## The idea

Treat the judge as a binary classifier, and validate it the way you would validate any classifier ([Hamel Husain, "Using LLM-as-a-Judge"](https://hamel.dev/blog/posts/llm-judge/)). You need three things:

1. **Human labels** for the one failure mode the judge covers: 100-200 of them, with enough of each class ([Evals FAQ](https://hamel.dev/blog/posts/evals-faq/)).
2. **Two error rates, measured on held-out labels.** This module's convention is that positive means PASS:
   - **TPR** = P(judge says pass | human says pass). How often good outputs get through.
   - **TNR** = P(judge says fail | human says fail). How often bad outputs get caught. On most products this is the one that matters.
3. **A corrected production estimate.** The judge's observed pass rate on unlabeled traffic is biased by its own errors. The Rogan-Gladen estimator removes that bias ([Rogan & Gladen 1978](https://pubmed.ncbi.nlm.nih.gov/623091/)):

$$\hat\theta = \frac{p_{obs} + \mathrm{TNR} - 1}{\mathrm{TPR} + \mathrm{TNR} - 1}$$

Then you bootstrap a confidence interval that includes uncertainty in all three inputs.

> **Convention warning.** Some teams call the *failure* the positive class, because the judge is a defect detector. Then their "TPR" is this module's TNR. Write the convention at the top of every calibration report. `calibrate.py` puts it in the module docstring.

## Why it matters

**Accuracy lies when classes are imbalanced.** If 5% of outputs fail, a judge that always says PASS has 95% accuracy and a TNR of 0 ([Hamel](https://hamel.dev/blog/posts/llm-judge/)). `test_calibrate.py::test_accuracy_hides_a_useless_judge_on_imbalanced_data` checks exactly this case: accuracy 0.95, TNR 0.0, kappa 0.0.

**Raw judge pass rates are biased, in a predictable direction.** Suppose the true pass rate is θ. A judge passes good items at rate TPR and bad items at rate 1 − TNR, so:

$$p_{obs} = \mathrm{TPR}\cdot\theta + (1-\mathrm{TNR})(1-\theta)$$

With TPR = 0.92, TNR = 0.88 and an observed rate of 80%, the true rate is about 85%. That is the worked example in Hamel Husain's `validate-evaluator` skill ([hamelsmu/evals-skills](https://tessl.io/registry/skills/github/hamelsmu/evals-skills/validate-evaluator)), and `test_rogan_gladen_worked_example` reproduces it. The bias isn't always in the same direction. A lenient judge (low TNR) makes a bad system look better than it is. A strict judge (low TPR) makes a good system look worse. If you compare two systems whose outputs are distributed differently, an uncorrected judge can change the ranking.

**Small label sets give intervals too wide to act on.** Hamel's guide says that below about 60 examples the confidence intervals are often too wide to conclude anything. This module's own test split has 25 items, and it makes the point for you below.

## How to do it

### 1. Collect labels

- **One domain expert owns the labels.** Hamel argues for a single principal domain expert who defines quality ([Hamel](https://hamel.dev/blog/posts/llm-judge/)). If you use several labellers, measure their agreement with each other first ([01](01-when-you-need-a-judge.md)).
- **Each label is a verdict plus a critique.** The critique becomes few-shot material and tells you *why*, which matters when you iterate.
- **Get enough of each class.** Aim for 30-50 of each label in both dev and test where you can ([Hamel](https://hamel.dev/blog/posts/llm-judge/)). Eugene Yan suggests collecting 50-100 *fail* cases inside 200+ samples, sourced from real or weaker-model outputs, because synthetic defects tend to be either exaggerated or too subtle ([Eugene Yan, "Product Evals"](https://eugeneyan.com/writing/product-evals/)).

### 2. Split the labels before you look at the judge

Hamel recommends roughly 10-20% train (clear examples, used as few-shots), 40-45% dev (iterate here), and 40-45% test (hidden until the prompt is final, then run once) ([Hamel](https://hamel.dev/blog/posts/llm-judge/)). Assign splits with a hash of a stable id, so adding new labels never moves old ones between splits:

```python
def assign_split(row_id: str, fractions=(0.15, 0.40, 0.45)) -> str:
    h = int(hashlib.sha256(row_id.encode()).hexdigest(), 16) % 10_000 / 10_000
    return "train" if h < fractions[0] else ("dev" if h < fractions[0] + fractions[1] else "test")
```

This is the same reason you shard by a hash of the key rather than by insertion order: the assignment is a pure function of identity.

### 3. Iterate on dev only

Run the judge on dev. Read every disagreement, critique first. Change the rubric. Repeat. Stop when dev TPR/TNR plateau or meet your target.

### 4. Freeze, then read test once

Freeze the prompt, the model ID and the few-shots (hash them, see [06](06-who-validates-the-validators.md)), and run the judge on test. Report TPR and TNR with intervals. `calibrate.py` uses Wilson intervals because they behave sensibly at 0/n and n/n, where the textbook normal approximation gives nonsense. Add Cohen's kappa as a single chance-corrected agreement number. Eugene Yan treats 0.4-0.6 as substantial and above 0.7 as excellent ([Eugene Yan](https://eugeneyan.com/writing/product-evals/)).

### 5. Correct the production pass rate and bootstrap the CI

```python
def rogan_gladen(p_obs, tpr, tnr, clip=True):
    youden = tpr + tnr - 1
    if youden <= 0:
        raise ValueError("TPR + TNR must exceed 1; the judge is not informative")
    theta = (p_obs + tnr - 1) / youden
    return min(1.0, max(0.0, theta)) if clip else theta
```

Two details matter here:

- **The denominator is Youden's J = TPR + TNR − 1.** The correction divides by it, so it also scales up the noise. At J = 0.6 any error in `p_obs` grows by 1/0.6 ≈ 1.7x. At J = 0.2 it grows 5x. A barely-better-than-chance judge gives you a point estimate with an enormous interval, which is the honest answer.
- **The bootstrap resamples both sources of uncertainty.** Each iteration resamples the labeled test pairs (giving new TPR/TNR) *and* the production verdicts (giving a new `p_obs`), then applies the correction. Resamples with no passes, no fails, or J ≤ 0 are skipped and counted. `bootstrap_true_pass_rate` does this. The `judgy` package from the AI Evals course implements the same idea ([judgy on PyPI](https://pypi.org/project/judgy/)).

## Worked example: calibrating the incident-impact judge

**Round 1 on dev.** The first judge (`incident_keyword_judge`, "v1") passes a summary if it contains the exact affected count. On the 27 dev items it scores TPR 0.86 and TNR 0.38: it lets 8 of 13 wrong summaries through. Reading the disagreements shows two patterns:

```text
INC-2291-s5  human=fail judge=pass  "...delayed ... for 3,412 merchants across all regions..."      (scope)
INC-2317-s3  human=fail judge=pass  "...9,870 customers were double-charged at checkout..."         (severity)
INC-2403-s3  human=pass judge=fail  "Roughly a thousand password-reset emails went undelivered..."  (rounding)
```

**Round 2 on dev.** Add scope and severity contradiction checks, and accept fair rounding ("v2", `incident_rules_judge`). With a real model, this is where you would edit the rubric's claims and fail-if lines. Here the fake's rules play that role. Dev now looks excellent:

```text
[dev] binary v2:  TP 13  FN 1  FP 0  TN 13   TPR 0.93  TNR 1.00  kappa 0.93
```

**Freeze, then read test once.**

```text
$ python code/calibrate.py
(production verdicts are SIMULATED: true pass rate 0.70, n=500)
split=test  n=25  judge errors excluded=0
                judge=pass  judge=fail
  human=pass           11           2
  human=fail            3           9
TPR 0.85  95% CI [0.58, 0.96]
TNR 0.75  95% CI [0.47, 0.91]
accuracy 0.80  kappa 0.60
production: n=500  observed pass rate 0.682
corrected true pass rate 0.725  95% CI [0.434, 1.000]  (skipped 2 degenerate resamples)
```

These are real outputs from running the module's code against its offline fakes. The production stream is simulated, as the output says.

Read it the way you would read a load-test report:

1. **Dev overstated the judge.** TNR fell from 1.00 on dev to 0.75 on test. The v2 rules were written by reading dev disagreements, so they fit dev's particular errors. The test misses are new shapes that dev never showed: "us-east-1" when the impact was in all regions, "iOS and Android" when only iOS was affected, and "exposed account data". This is exactly why test is read once. If you now "fix" those three and re-read test, test has become a second dev set and you have no unbiased number left.
2. **The intervals are too wide to act on.** TNR could be anywhere from 0.47 to 0.91. The corrected pass rate is 0.725, but the interval runs from 0.43 to 1.00. That would not tell you whether a 5-point regression happened. With 25 test labels, this is the expected result.
3. **The correction moved the estimate in the right direction.** The observed rate (0.682) understated the simulated truth (0.70) because TNR < TPR here. The corrected point estimate (0.725) overshoots a little, which is ordinary sampling error at this n.

**How many labels would be enough?** The same estimator, run on simulated label sets with TPR 0.85, TNR 0.75, balanced classes, and 2,000 production verdicts (median of 5 seeds; this is a simulation, not a measurement of any real judge):

| Labeled test items | Median 95% CI width on corrected pass rate |
|---|---|
| 25 | 0.43 |
| 50 | 0.38 |
| 100 | 0.25 |
| 200 | 0.17 |
| 400 | 0.16 |

Width falls roughly with √n until about 200 labels. After that the production sample size starts to dominate. This is the quantitative argument behind "100-200 labels per failure mode". Beyond that point, spend your effort on more production verdicts and a better judge (a larger Youden's J), not on more labels.

## Pitfalls

- **Re-reading test.** Detect it from git history: if the test-split file or the frozen-prompt hash changed after a test run was reported, the test number is contaminated. Rotate in fresh labels as the new test set.
- **Reporting raw agreement.** Detect it by looking for a single "accuracy" or "% agreement" with no TPR/TNR next to it. Ask for the confusion matrix.
- **Calibrating on a different distribution from production.** TPR/TNR measured on last quarter's outputs, or on synthetic outputs, don't transfer automatically. If the judge is much worse on one segment (say, no-impact incidents), compute TPR/TNR per segment and correct per segment.
- **Correlated items.** This dataset has six summaries per incident. Items from the same incident aren't independent, so the bootstrap above is somewhat optimistic. Resample by `incident_id` (a cluster bootstrap) for an honest interval. Anthropic found clustered standard errors more than 3x naive ones on popular evals ([Anthropic, "A statistical approach to model evaluations"](https://www.anthropic.com/research/statistical-approach-to-model-evals)). See [Module 12](../12-hill-climbing/README.md).
- **Silently dropping judge errors.** If 4% of calls fail to parse and you exclude them, report that 4%. If errors correlate with hard items, excluding them biases TPR/TNR upward.
- **Applying the correction when J is near zero.** `rogan_gladen` raises at J ≤ 0. At J of 0.1-0.2 it won't raise, but the interval will be huge. Read the interval, not the point.
- **Clipping hides model misfit.** If many bootstrap samples clip at 0 or 1, the observed rate is outside [1 − TNR, TPR]. That usually means production differs from your labeled set.

## In your day job

- Add a calibration report to every judge's README: convention, label count by class, TPR/TNR with CIs, kappa, frozen prompt hash, judge model ID, and date.
- On dashboards, show the corrected pass rate with its CI next to the raw judge rate, and alert on the CI lower bound crossing your SLO. The Evals FAQ describes the same idea of alerting when a CI lower bound crosses a threshold ([Evals FAQ](https://hamel.dev/blog/posts/evals-faq/)).
- Budget about 200 labels per failure mode the first time, then about 20-50 fresh labels per month to keep the estimate honest ([06](06-who-validates-the-validators.md)).
