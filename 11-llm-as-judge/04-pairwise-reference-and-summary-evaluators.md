# 04: Pairwise, reference-based and summary evaluators

## The idea

So far every judge has been **pointwise**: one output in, PASS/FAIL out. There are three other shapes, and choosing the right one often matters more than how you word the prompt.

| Shape | Input | Output | Use it when |
|---|---|---|---|
| Pointwise, reference-free | output (+ task inputs) | pass/fail per item | You can state the property without a gold answer. The incident judge is this shape: the facts are inputs, not a gold summary. |
| **Reference-based** | output + a gold answer | pass/fail: "is it equivalent to the reference on property X?" | You have gold answers (seeded bugs, known root causes, expected SQL results). This is usually easier and more reliable than reference-free. |
| **Pairwise** | output A + output B | A, B or tie | You are comparing two systems (prompt v1 vs v2, model X vs Y), or the criterion is subjective. |
| **Summary (aggregate)** | all outputs of a run | one number for the run | The metric is not a mean of per-item scores: F1, a corrected pass rate, a win rate with a CI, "no category regressed". |

Eugene Yan's survey of the research suggests direct scoring for objective criteria (faithfulness, toxicity) and pairwise comparison for subjective ones (tone, persuasiveness), and reports that pairwise agrees better with humans ([Eugene Yan, "Evaluating the Effectiveness of LLM-Evaluators"](https://eugeneyan.com/writing/llm-evaluators/)). LangSmith ships all four shapes: per-run evaluators, `evaluate_comparative` for pairwise experiments, and `summary_evaluators` that receive the whole experiment's inputs and outputs as lists ([LangChain, pairwise evaluations](https://blog.langchain.dev/pairwise-evaluations-with-langsmith); [LangSmith docs, summary evaluators](https://docs.smith.langchain.com/evaluation/how_to_guides/summary)).

## Why it matters

**Pointwise scores saturate when comparing two good systems.** When both prompts pass 92% of items, pointwise PASS/FAIL can't tell you which is better on the remaining 8%, or on items where both pass but one is clearly better. LangChain's stated motivation for pairwise experiments is exactly this case: independent scores tie at the top ([LangChain](https://blog.langchain.dev/pairwise-evaluations-with-langsmith)).

**Reference-free judging is the hardest version of the task.** "Is this a real bug?" makes the judge re-derive the answer from the diff. "Does this comment identify the same defect as the reference?" only asks it to compare. If you can build references cheaply (by seeding bugs, replaying incidents with known causes, or using human-written gold summaries), do it.

**Some decisions are about the run, not the item.** "Ship if the corrected pass rate's lower bound is above 0.85 and no incident category regressed" can't be expressed as an average of per-item scores. Write it as a summary evaluator and version it.

## How to do it

### Pairwise, done safely

Anthropic's eval tooling describes the protocol: when there is a baseline, "the judge instead reads both inputs in random order, without being told which is the baseline, and picks the better one" ([Anthropic, "Automating eval design and hillclimbing"](https://claude.dev/blog/automating-eval-design-and-hillclimbing/)). `pairwise.py` goes one step further and runs **both** orders for every pair, which removes position bias from the result instead of just randomising it:

```python
def combine(v_ab: str, v_ba: str) -> PairResult:
    """Map two order-specific votes back to A/B. Disagreement becomes a tie."""
    as_ab = {"1": "a", "2": "b", "tie": "tie"}[v_ab]
    as_ba = {"1": "b", "2": "a", "tie": "tie"}[v_ba]
    if as_ab == as_ba:
        return PairResult(as_ab, True, (v_ab, v_ba))
    return PairResult("tie", False, (v_ab, v_ba))
```

Recording a flipped verdict as a tie is Eugene Yan's recommendation ([Eugene Yan, "Product Evals"](https://eugeneyan.com/writing/product-evals/)). It also gives you a free diagnostic: the **inconsistency rate**, the share of pairs where the verdict flipped. A high rate means the judge can't tell the two apart on this criterion. Either the systems really are equivalent, or the criterion is underspecified.

Rules the code enforces:
- The judge sees "Response 1" and "Response 2". Neither the user turn nor the system prompt ever says "baseline" or "candidate" (`test_compare_runs_both_orders_blind` checks this).
- The judge is told that order carries no information, and that length and confidence are not evidence.
- The criterion is a single sentence about one property, the same discipline as a pointwise rubric.
- Report the win rate with ties counted as half, the inconsistency rate, and a significance check. `sign_test_p` gives an exact two-sided sign test with ties dropped. It is a sanity check for small n; [Module 12](../12-hill-climbing/README.md) covers paired tests and power properly.

Calibrate a pairwise judge as well. Have a human pick the better of 50-100 pairs, then measure how often the judge agrees on pairs where the human expressed a preference.

### Reference-based

Give the judge the reference, and narrow the question to equivalence on one property:

```text
Question: Does the review comment identify the same defect as the reference?
<diff>...</diff>
<reference_defect>Offset committed before the write completes; upsert error discarded. A crash after commit loses the message (at-least-once becomes at-most-once).</reference_defect>
<comment>...</comment>
PASS only if ALL of these hold:
  1. The comment names the same mechanism as the reference (ordering of commit vs write, or the dropped error).
  2. The comment does not misstate the consequence (e.g. "duplicate processing" instead of "message loss").
Do NOT consider: other issues the comment raises, wording, politeness.
```

The reference turns "is it a real bug?" (trace Go semantics and Kafka commit behaviour from scratch) into "is it the same bug?" (compare two descriptions). The trade-off: references go stale when the code changes, and many tasks have several valid answers. If you use one reference where several answers are valid, you will fail correct outputs and get a low TPR.

### Summary evaluators

A summary evaluator is a function from the whole run to a number. Here is the corrected pass rate as one, in the shape LangSmith's `summary_evaluators` accept (lists in, `{key, score}` out):

```python
from calibrate import bootstrap_true_pass_rate

FROZEN = {"human_test": [...], "judge_test": [...]}   # test-split labels from calibration, loaded from a file

def corrected_pass_rate(outputs: list[dict], reference_outputs: list[dict]) -> dict:
    prod = [o["judge_label"] == "pass" for o in outputs]
    est = bootstrap_true_pass_rate(FROZEN["human_test"], FROZEN["judge_test"], prod)
    return {"key": "impact_pass_rate_corrected_lo95", "score": est.lo}
```

Gate on `lo95`, the lower bound, rather than the point estimate. That is the eval version of alerting on a p99 rather than a mean.

## Worked example: is the new summary prompt better?

You have two prompts for drafting incident summaries. The baseline tends to describe root cause. The candidate puts an explicit "Customer impact:" line first. For each of the 10 incidents, A is the baseline's draft and B is the candidate's. `python code/pairwise.py` runs the blinded, swapped protocol with an offline content-only fake:

```text
$ python code/pairwise.py
pairs=10  B wins=10  A wins=0  ties=0  position-inconsistent=0
B win rate (ties=0.5): 1.00   sign test p=0.002
```

Now run the same pairs through a judge with pure position bias, `first_position_judge`, which always says "Response 1":

```text
compare(..., BAD, GOOD)  ->  PairResult(winner='tie', consistent=False, votes=('1', '1'))
```

Every pair becomes a tie with an inconsistency flag, and the B win rate is exactly 0.50. A position-biased judge can't make a fake winner under this protocol; all it can do is make you blind. If you had run only one order, with the candidate always shown first, this judge would have reported a 100% win rate for the candidate. That's the failure the protocol exists to stop.

Here is what a real judge's critique should look like for a pair (illustrative output):

```json
{"critique": "Response 1 states '640 customers in ap-south-1 had a full API outage for 11 minutes', matching the facts' '100% of API requests ... failed ... 640 customers'. Response 2 reports only that 'deploys to ap-south-1 were paused', which is internal impact. On the criterion (customer impact stated correctly) Response 1 is better.",
 "winner": "1"}
```

## Pitfalls

- **One order only.** Detect it by checking whether every pair produced two judge calls. If not, your win rate includes position bias. Two calls per pair doubles the cost, and the cost is worth it.
- **Unblinded labels.** Detect it by grepping prompts for "baseline", "current", "new", "v2", or model names. Judges and humans both favour the label they expect to win.
- **Pairwise on a criterion that should be pointwise.** "Which summary has the correct count?" has an absolute answer, so use a pointwise judge. Pairwise answers "which is better", not "is it good enough". Two bad outputs still produce a winner.
- **Win rate without the tie and inconsistency rates.** A 0.60 win rate with 40% inconsistent pairs is a very different result from 0.60 with 2%.
- **Stale references.** Detect it by date-stamping each reference and re-reviewing references older than the last major code change in their area.
- **Summary evaluators that average away the tail.** A mean pass rate can rise while one category collapses. Add a per-category floor: "no `incident_category` below 0.8".

## In your day job

- For prompt or model A/B decisions in [Module 12](../12-hill-climbing/README.md), use pairwise with both orders, blinding, and a judge from a different model family than either candidate.
- Where you can seed the answer (bug-injection suites, replayed incidents with known causes), switch from reference-free to reference-based judging. It is cheaper to calibrate and has higher TPR/TNR.
- Write your ship gate as a summary evaluator in code, check it into the repo, and have CI call it, instead of having a human eyeball a dashboard.
