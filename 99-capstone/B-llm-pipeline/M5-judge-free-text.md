# B-M5: A judge for free-text fields
**Time:** one day, mostly labeling. **Offline:** labeling yes; judge runs need a key. **Modules:** [11](../../11-llm-as-judge/README.md), [10](../../10-evals-fundamentals/README.md).

## Goal
Score the fields code cannot: `summary`, `action_items`, and the themes produced by `reduce_themes`. Use binary criteria, calibrate the judge against your own labels, and report TPR and TNR on a held-out set.

## Why it matters
Free-text fields are where pipelines rot unnoticed. A summary can be fluent and wrong. An action-item list can silently drop the one item that matters. Using an LLM judge here is reasonable, but the judge is itself a model, so it needs its own test set. The course stance: judges only with binary rubrics, calibration against human labels, and drift alarms ([01-gap-analysis](../../research/01-gap-analysis.md)).

## Steps
1. **Decide the criteria by reading outputs.** Read 30 summaries and action-item lists from your M4 pipeline next to their documents. Write down what makes one bad. Typical criteria:
   - `summary.FAITHFUL`: every claim is supported by the document.
   - `summary.ROOT_CAUSE`: the summary states the root cause, not just the symptom.
   - `action_items.COMPLETE`: every action item in the document appears (paraphrase allowed).
   - `action_items.NO_INVENTED`: no item appears that is not in the document.
   - `themes.GROUNDED`: every theme's count matches the items assigned to it.
   Note that `COMPLETE` and `NO_INVENTED` are recall and precision for a free-text list. The same separation as M2.
2. **Check whether code can do it first.** `themes.GROUNDED` can be checked by code if you make the reduce return item ids per theme. Restructure the output rather than judging it.
3. **Write one judge prompt per criterion**, each returning `{"reasoning": ..., "verdict": "PASS"|"FAIL"|"UNKNOWN"}`.
4. **Label ~120 outputs yourself** per criterion, blind to the judge. Split ~20% dev for prompt iteration, ~80% held out.
5. **Report TPR, TNR and counts** on the held-out set. Use a different model for the judge than for the pipeline.
6. **Bias checks**:
   - *Length:* does the judge pass longer summaries more often at equal human labels? Bin by length and compare pass rates within each human label.
   - *Position (pairwise only):* if you use pairwise comparison between pipeline versions, run both orders and count disagreements.
7. **Corrected rates.** Report the judge's observed pass rate and the corrected estimate `(p_obs + TNR − 1) / (TPR + TNR − 1)`, with a bootstrap CI over your labeled set.
8. **Drift check after a pipeline change.** When M4 changes the summary prompt, re-label 30 new outputs and re-check TPR/TNR. A judge calibrated on v1 summaries may misjudge v3 summaries, because the distribution of mistakes changed.

## Worked example: the `COMPLETE` judge
Bad:

```text
Are these action items good? Answer yes or no.
```

Why it fails: "good" invites the judge's own opinion of what the team *should* do. It will pass a list that sounds sensible and omits a real item.

Better:

```text
You check whether an extracted list of action items is complete.

<document_action_items> contains the action items exactly as written in the postmortem.
<extracted> contains the list a pipeline produced.

For each item in <document_action_items>, decide whether <extracted> contains an item with the
same meaning (paraphrase is fine; a narrower or broader item is not).

Return JSON:
{"missing": ["<document items with no match>"], "verdict": "PASS" if missing is empty else "FAIL"}

<document_action_items>
{gold_section}
</document_action_items>
<extracted>
{pred_items}
</extracted>
```

Two design choices to notice. The judge is given the document's own Action Items *section*, not the whole document, so it does less reading and has less to be distracted by. And the output lists the missing items, which makes every FAIL auditable in seconds when you label.

The verdict is deterministic given `missing`, so you can compute it in code from the list and treat the judge as an extractor, which is easier to calibrate.

Calibration result format (illustrative output):

```text
action_items.COMPLETE   held-out n=96   judge model: claude-opus-5-5   pipeline model: claude-haiku-5-5
                 human PASS   human FAIL
judge PASS            70           3
judge FAIL             6          17
TPR = 70/76 = 0.921   TNR = 17/20 = 0.850
observed pass 0.760 -> corrected (0.760 + 0.850 - 1) / (0.921 + 0.850 - 1) = 0.791
```

## Deliverables
- Criteria list with the reason each exists (the M3-style observation that motivated it)
- One judge per criterion, plus code checks where possible
- Labels, dev/held-out split, confusion matrices, TPR/TNR per criterion
- Length-bias check; position check if you use pairwise
- Drift re-check after one M4 change

## Done when
- [ ] Every judged criterion is binary and has TPR and TNR on held-out labels (≥100 total labels across criteria, or the honest count with CIs).
- [ ] At least one criterion was moved from a judge to code.
- [ ] Judge model differs from pipeline model.
- [ ] Corrected pass rates reported next to observed ones.
- [ ] A drift re-check after a pipeline change is reported.

## Reuse
- `../code/pipeline_v0.py` (`reduce_themes`, `REDUCE_PROMPT`)
- Binary rubrics, critique shadowing, TPR/TNR, judge drift: [11-llm-as-judge](../../11-llm-as-judge/README.md)
- [Hamel Husain, "Using LLM-as-a-judge"](https://hamel.dev/blog/posts/llm-judge/); [Shankar et al., "Who Validates the Validators?"](https://arxiv.org/abs/2404.12272)

## Pitfalls
- **One judge, many criteria.** A judge asked five questions answers the easiest one well and the rest by vibe. One criterion per call.
- **Agreement instead of TPR/TNR.** If 80% of outputs pass, "always PASS" scores 80% agreement.
- **Labeling with the judge's reasoning visible.** You will be persuaded. Label first.
