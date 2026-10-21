# B-M6: CI gate and drift monitoring
**Time:** one weekend day. **Offline:** yes, with cassettes. **Modules:** [12](../../12-hill-climbing/README.md), [15](../../15-observability-and-production/README.md), [07](../../07-loops/README.md), [17](../../17-ai-native-engineer-and-team/README.md).

## Goal
Make the pipeline safe to change and safe to leave running: a CI gate that blocks real regressions and passes noise, and a monitor that notices when production documents stop looking like your labeled set.

## Why it matters
Your M4 result holds for your labeled set and for today's model. Two things will break it. A teammate edits the prompt (a deploy), or the input distribution shifts: a new team starts writing postmortems with a different template, or with no Impact section at all. The first needs a gate. The second needs a monitor, because you have no labels for production data. Both are the pipeline version of "prompt changes are deploys" ([15-observability-and-production](../../15-observability-and-production/README.md)).

## Steps
1. **Gate design.** On every PR that touches prompts, pipeline code or model config, run the pipeline on the test split and compare paired against the main-branch predictions.
   - Fail if any field's F1 drops and the paired 95% CI's upper bound is below zero.
   - Fail if cost per document rises more than a set percentage.
   - Fail if the parse-failure or validator-problem rate rises.
   - Warn (do not fail) when a change is within noise.
2. **Make it cheap.** Main-branch predictions are stored as an artifact. The PR run uses `ReplayClient` for any unchanged stage. Only changed stages call the API.
3. **Test the gate itself.** Seed a regression (for example, remove the "final severity" rule from the prompt) and confirm the gate fails. Make a no-op change (reword a comment in code) and confirm it passes. A gate never shown to fail is decoration.
4. **Drift monitor on unlabeled data.** Run nightly over new documents and compute label-free signals:
   - validator-problem rate (detection > duration, enum violations, detection = 0)
   - null rate per field
   - document-shape stats: length, presence of each `##` section, header presence
   - output distribution: share of each severity and root-cause category
   Compare each to the labeled-set baseline with a simple test (for proportions, a two-proportion z-test or a fixed threshold you justify).
5. **Bookmark the nightly run.** Process documents after the last processed id, not "the last 24 hours" ([07-loops](../../07-loops/README.md)).
6. **Runbook.** When the drift alarm fires: sample 20 new documents, label them, score, and decide whether to add them to the labeled set and re-run M4.
7. **Ownership.** Who approves a gate override? Write it down ([17-ai-native-engineer-and-team](../../17-ai-native-engineer-and-team/README.md)).

## Worked example: the gate
```python
"""ci_gate.py: compare PR predictions with main-branch predictions on the frozen test split."""
import json, sys
from score import SCALAR_FIELDS, SET_FIELDS, load_jsonl, score, paired_bootstrap

def field_only(preds, field):
    return {k: {"doc_id": k, field: v.get(field)} for k, v in preds.items()}

def gate(main_path, pr_path, labels_path, max_cost_increase=0.15):
    labels, main, pr = load_jsonl(labels_path), load_jsonl(main_path), load_jsonl(pr_path)
    failures, warnings = [], []
    for f in SCALAR_FIELDS + SET_FIELDS:
        lab = {k: {"doc_id": k, f: v.get(f)} for k, v in labels.items()}
        cmp = paired_bootstrap(field_only(main, f), field_only(pr, f), lab, n_boot=1000)
        if cmp["ci95"][1] < 0:
            failures.append(f"{f}: F1 {cmp['delta_f1']:+.3f}, CI {cmp['ci95']}")
        elif cmp["delta_f1"] < 0:
            warnings.append(f"{f}: F1 {cmp['delta_f1']:+.3f} within noise, CI {cmp['ci95']}")
    cost = lambda p: sum(r.get("_tokens_in", 0) + r.get("_tokens_out", 0) for r in p.values())
    if cost(main) and cost(pr) > cost(main) * (1 + max_cost_increase):
        failures.append(f"tokens +{cost(pr) / cost(main) - 1:.0%} (limit {max_cost_increase:.0%})")
    parse = lambda p: sum(not r.get("_parse_ok", True) for r in p.values())
    if parse(pr) > parse(main):
        failures.append(f"parse failures {parse(main)} -> {parse(pr)}")
    return failures, warnings

if __name__ == "__main__":
    fails, warns = gate(*sys.argv[1:4])
    print(json.dumps({"failures": fails, "warnings": warns}, indent=2))
    sys.exit(1 if fails else 0)
```

Why per field: a change that improves `services_affected` by a lot and breaks `severity` a little can raise micro F1 and still corrupt the severity report. The gate protects each downstream consumer separately.

Why the CI's upper bound and not the point estimate: with 25 test documents, a single flipped document moves a field's F1 by several points. Failing on point estimates makes the gate flaky, and flaky gates get overridden, then ignored.

### Testing the gate (illustrative output)
```text
seeded regression: removed "use the FINAL severity" from prompt
  failures: ["severity: F1 -0.280, CI [-0.440, -0.120]"]    exit 1   (correct)
no-op change: reworded a code comment, replayed from cassette
  failures: []  warnings: []                                 exit 0   (correct)
```

## Worked example: a drift signal
A new team's postmortems have no `## Impact` heading. Your M4 pipeline routes `services_affected` to the Impact section, falls back to Summary, and recall drops. You have no labels, but the monitor sees it:

```text
nightly 2026-11-03  docs=41
  section_present.impact     baseline 1.00   tonight 0.61   ALERT
  null_rate.services          baseline 0.00   tonight 0.07   ALERT
  validator_problem_rate      baseline 0.02   tonight 0.03   ok
```
(illustrative output)

The fix is not a prompt tweak tonight. It is the runbook: label a sample, add a document shape to the labeled set, re-run M4's chunking round on the new shape.

## Deliverables
- `ci_gate.py` and CI config, with the seeded-regression and no-op tests as automated tests
- `drift_monitor.py` with label-free signals and thresholds, tested on a shifted batch (generate one by editing the generator's template, for example removing the Impact section)
- `RUNBOOK.md` for gate failures and drift alarms

## Done when
- [ ] The gate fails a seeded regression and passes a no-op change, both in automated tests.
- [ ] The gate is per field, uses paired CIs, and checks cost and parse failures.
- [ ] The drift monitor fires on a shifted batch and stays quiet on a fresh in-distribution batch.
- [ ] The runbook says who does what when either fires.

## Reuse
- `../code/score.py` (`paired_bootstrap`), `../code/make_postmortems.py` (edit `render` to produce shifted batches)
- CI gating on evals: [12-hill-climbing](../../12-hill-climbing/README.md)
- Drift monitoring and cost budgets: [15-observability-and-production](../../15-observability-and-production/README.md)

## Pitfalls
- **Gating on micro F1.** One dominant field hides the others.
- **A gate that hits the live API for every PR.** Slow and noisy. Replay unchanged stages.
- **Drift thresholds set by eye on one night.** Run the monitor on several in-distribution batches first to see its natural variation.
