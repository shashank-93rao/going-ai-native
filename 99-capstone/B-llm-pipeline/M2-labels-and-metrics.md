# B-M2: Labels and metrics: field-level precision and recall
**Time:** one weekend day, mostly labeling. **Offline:** yes. **Modules:** [10](../../10-evals-fundamentals/README.md), [12](../../12-hill-climbing/README.md), [13](../../13-testing-agentic-systems/README.md).

## Goal
Grow the labeled set to at least 60 documents, including some that did not come from the generator, and report per-field precision and recall with bootstrap confidence intervals.

## Why per-field P/R and not accuracy
An extraction row has six scored fields with different failure shapes and different downstream costs. "Accuracy 74%" hides that `services_affected` has 0.42 precision on the offline baseline, which means the "impact minutes by service" report is mostly fiction. Precision and recall separate two different mistakes: asserting something false (hurts precision) and missing something true (hurts recall). Downstream consumers care about them differently. A dashboard that ranks services by impact tolerates missing a service better than inventing one.

Twenty documents is enough to see shapes, not to measure changes. With 20 documents, a field scored once per document has a 95% CI of roughly ±20 points at 50% accuracy. Practitioner numbers make the scaling concrete: 200 samples with 3% observed defects give a 95% CI of about ±2.4%, 400 samples about ±1.7%, so halving the margin takes 4x the samples ([Eugene Yan, "Product evals"](https://eugeneyan.com/writing/product-evals/), as summarized in the course research notes).

## Steps
1. **Generate more synthetic docs** for volume: `python make_postmortems.py --n 60 --seed 7 --out data_big`. Note that the generator's labels are correct *by construction*, which makes them a test of your pipeline, not of your labeling guide.
2. **Add at least 10 non-generator documents.** Options: write them yourself from incidents you remember (scrubbed), adapt public postmortems by rewriting them in your own words into the same structure, or ask a model to write deliberately messy ones and then label them yourself. These are the documents that will surprise you. Label them using only LABELING.md.
3. **Double-label a subset.** Have a colleague (or yourself a week later, blind) label 15 documents. Compute agreement per field. Where you disagree, the guide is ambiguous; fix it.
4. **Make the counting rules explicit.** `score.py` documents them at the top: a wrong scalar is both a false positive and a false negative. Decide whether you agree, and whether numeric fields get a tolerance (`--tol 2` treats ±2 minutes as correct). Record the decision in LABELING.md.
5. **Split.** 60% dev (you look at errors), 40% test (you do not). Stratify by `hard_features` and by source (generator vs your own).
6. **Report with CIs.** Use `bootstrap_ci` for micro F1, and extend it per field. Documents are the unit of resampling.
7. **Property tests on the scorer.** `test_pipeline_scaffold.py` has example-based tests. Add property-based ones with `hypothesis` (installed in the venv), for example:

```python
from hypothesis import given, strategies as st
from score import field_counts

services = st.lists(st.sampled_from(["checkout", "payments", "auth", "search"]), unique=True)

@given(pred=services, gold=services)
def test_set_counts_partition_the_union(pred, gold):
    tp, fp, fn = field_counts("services_affected", {"services_affected": pred}, {"services_affected": gold})
    assert tp + fp == len(pred) and tp + fn == len(gold)

@given(v=st.integers(0, 600), tol=st.integers(0, 5), delta=st.integers(-10, 10))
def test_tolerance_is_symmetric(v, tol, delta):
    a = field_counts("duration_minutes", {"duration_minutes": v + delta}, {"duration_minutes": v}, tol)
    b = field_counts("duration_minutes", {"duration_minutes": v - delta}, {"duration_minutes": v}, tol)
    assert a == b
```

## Worked example: why the counting rule matters
Two predictions for the same document, gold `severity = SEV2`:

| Prediction | Under "wrong = FP+FN" (scaffold) | Under "wrong = FP only" |
|---|---|---|
| `SEV3` | P falls, R falls | P falls, R unchanged |
| `null` | R falls | R falls |

Under the second rule, a pipeline that guesses on every document has better recall than one that abstains when unsure, even when its guesses are wrong. That rewards hallucination, the incentive problem OpenAI's hallucination paper describes for benchmarks that score abstention as a miss ([01-llms-for-systems-engineers](../../01-llms-for-systems-engineers/README.md), [10-evals-fundamentals](../../10-evals-fundamentals/README.md)). The scaffold rule makes a wrong answer strictly worse than no answer, which is what a downstream dashboard wants. Either rule is defensible. Pick one on purpose.

## Deliverables
- ≥60 labeled documents, ≥10 not from the generator, with source tagged per row
- Agreement numbers on the double-labeled subset, and the guide changes they caused
- `splits.json` (dev/test), frozen
- A score report per field: P, R, F1 with bootstrap CIs, on dev and test, sliced by source and by hard feature
- Property tests on the scorer

## Done when
- [ ] Every scored field has P and R with a CI on the test split.
- [ ] Results are sliced by source; generator docs and your own docs are reported separately.
- [ ] Inter-annotator agreement is reported for at least 15 documents.
- [ ] At least two property tests on `score.py` pass.

## Reuse
- `../code/score.py` (`score`, `field_counts`, `bootstrap_ci`), `../code/make_postmortems.py`
- Synthetic data for cold start, balanced sets: [10-evals-fundamentals](../../10-evals-fundamentals/README.md)
- Error bars and sample sizes: [12-hill-climbing](../../12-hill-climbing/README.md)
- Property-based testing of evaluators: [13-testing-agentic-systems](../../13-testing-agentic-systems/README.md)

## Pitfalls
- **Labeling with the model's output visible.** You will anchor on it. Label blind.
- **Only synthetic data.** The generator's traps are the ones its author thought of. Your own documents carry the ones nobody thought of.
- **Resampling fields instead of documents.** Fields within a document are correlated (a model that misreads the timeline gets both durations wrong). Bootstrap over documents.
