# 02: Binary rubrics, checkable claims, and critique-then-verdict

## The idea

A good judge has three properties, and each one fixes a specific way judges fail:

1. **Binary output.** PASS or FAIL, not 1-5. A scale hides a threshold you never chose and never measured.
2. **A rubric made of checkable claims.** Each line is something a careful human could verify by pointing at text in the inputs: "the scope (region, tier, platform) matches the facts". It is never a quality adjective like "accurate" or "clear".
3. **Critique, then verdict.** The judge writes its reasoning, quoting the inputs, *before* it commits to a verdict. The structured-output schema enforces the order.

Anthropic's eval tooling describes the same design: the judge reads "the input, the output and a rubric written as checkable claims (not a 1-to-5 scale), and returns a score with its reasoning" ([Anthropic, "Automating eval design and hillclimbing"](https://claude.dev/blog/automating-eval-design-and-hillclimbing/)). Hamel Husain and Shreya Shankar recommend binary checks over Likert scales, with several specific binary checks if you need to track gradual progress ([Evals FAQ](https://hamel.dev/blog/posts/evals-faq/)).

## Why it matters

Here is a Likert grader from Anthropic's own docs, given as a worked example of an LLM-graded tone eval ([Anthropic docs, "Create strong empirical evaluations"](https://platform.claude.com/docs/en/test-and-evaluate/develop-tests)):

```text
Rate this customer service response on a scale of 1-5 for being {target_tone}:
<response>{model_output}</response>
1: Not at all {target_tone}
5: Perfectly {target_tone}
Output only the number.
```

It is a reasonable way to show the mechanics. As a production grader it has four problems:

- **What does a 3 mean?** Nobody wrote down the difference between a 3 and a 4. The judge invents one, and so does each human labeller, differently.
- **The threshold is hidden.** Eventually someone writes `score >= 4` in a dashboard query. That is the real classifier, and nobody calibrated it.
- **It isn't actionable.** A move from 3.6 to 3.4 tells you nothing about which outputs got worse or why.
- **"Output only the number" removes the reasoning.** You lose the critique you would need to debug the judge, and the model commits to a number without first working through the evidence.

The same anti-pattern, applied to incident summaries, is in `code/compare_judges.py`. Here is the score distribution from the offline Likert fake. The fake rewards surface specificity (numbers, regions, timestamps) and length, which is what an unanchored "quality" scale drifts toward in practice.

```text
$ python code/compare_judges.py          # offline fakes; these describe heuristics, not a real model
Likert score distribution (dev+test):
  human=pass: 1:1  2:1  3:13  4:9  5:3
  human=fail: 1:4  2:4  3:2  4:4  5:11
```

Eleven wrong summaries got a 5. Correct summaries cluster at 3-4. A confident, detailed, wrong summary ("3,412 merchants lost webhook events ... in us-east-1, the group stabilised at 10:05 UTC") looks *better* on a quality scale than a correct terse one.

## How to do it

**Step 1: write the question.** One sentence, answerable yes/no, naming the failure mode from error analysis. If you need "and", you need two judges.

**Step 2: write PASS claims.** These are conditions that must all hold. Each should name the evidence to look at. Write them by reading your human critiques: every critique that says why a FAIL is a FAIL turns into a claim or a fail-if line.

**Step 3: write FAIL-if triggers.** These are the specific shapes of failure you saw: root-cause-only summaries, hedging, counts that are off by more than rounding.

**Step 4: write out-of-scope lines.** Tell the judge what *not* to grade. Without them, judges grade everything they notice, and a tone problem turns into a FAIL on your impact judge.

**Step 5: put critique before verdict, in both the schema and the prompt.** With tool use, models usually emit properties in `input_schema` order. That is a strong tendency, not a documented guarantee, so the system prompt also says "Write the critique first, then decide". Put `critique` first:

```python
VERDICT_TOOL = {
    "name": "record_verdict",
    "description": "Record your critique and your binary verdict for this one check. Call exactly once.",
    "input_schema": {
        "type": "object",
        "properties": {
            "critique": {"type": "string",
                         "description": "2-5 sentences. Quote the specific text you checked and say which claim held or broke."},
            "verdict": {"type": "string", "enum": ["pass", "fail"]},
        },
        "required": ["critique", "verdict"],
    },
}
```

Note that `ainative_kit`'s `complete()` does not expose `tool_choice`, so the model is *asked* to call the tool. `judge.py` handles the case where it doesn't: it falls back to a JSON object in the text, and otherwise raises `JudgeOutputError`. An unparseable verdict is an error to count and investigate. It is never a silent pass.

**Step 6: decide what "can't tell" means.** Anthropic suggests giving the judge an "Unknown" option ([Anthropic, "Demystifying evals"](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)). This module's judges instead say "if you cannot verify a claim from the inputs, it fails", which keeps the output binary and the calibration maths simple. Both are defensible. If you add `unknown`, route those items to the human annotation queue ([06](06-who-validates-the-validators.md)), report the unknown rate as its own metric, and keep unknowns out of the TPR/TNR denominator.

## Worked example 1: the incident-impact judge

This is the system prompt that `judge.py` renders from the `INCIDENT_IMPACT` rubric. It is not hand-written as a single string; it is built from data, so you can diff and version it.

```text
You are a strict evaluator. You answer exactly one question with PASS or FAIL.
Question: Does the summary state the customer impact correctly, as given in the incident facts?

PASS only if ALL of these hold:
  1. If the facts say there was customer impact, the summary states who was affected (a count, or a
     segment such as a tier, region or platform) and what they experienced.
  2. Every customer-impact claim in the summary is supported by the facts: the scope (region, tier,
     platform, email type) matches, and the severity matches (delayed is not lost, slow is not failed,
     partial is not total).
  3. If the facts say there was no customer impact, the summary says so explicitly.

FAIL if ANY of these is true:
  - The summary describes only root cause or internal impact (tickets, dashboards, deploys paused).
  - The summary hedges ('may have affected customers') where the facts are definite.
  - A count differs from the facts by more than ordinary rounding (3,412 -> 'about 3,400' is fine).

Do NOT consider (another check covers these): tone, length, or writing quality; whether the root
cause is explained well; timeline accuracy.

Procedure: check each claim against the inputs, quoting the text you relied on. Write the critique
first, then decide. Length and fluency are not evidence. If you cannot verify a claim from the
inputs, it fails.
Respond only by calling the record_verdict tool once.
```

The item goes in the user turn, wrapped in tags so the critique can quote it:

```text
<facts>
Title: payments-events consumer lag after rebalance storm
...
Customer impact: webhook deliveries to 3,412 merchants in us-east-1 were delayed by 14-41 minutes.
No events were lost; all were delivered after recovery.
</facts>
<summary>
Between 09:12 and 10:05 UTC, a consumer rebalance storm on the webhook-dispatcher group in us-east-1
caused 3,412 merchants to lose webhook events. ...
</summary>
```

A good critique for that item looks like this (illustrative output):

```json
{"critique": "Claim 2 breaks on severity. The summary says merchants 'lose webhook events'; the facts say deliveries 'were delayed by 14-41 minutes' and 'No events were lost'. Count (3,412) and region (us-east-1) match.",
 "verdict": "fail"}
```

The critique is useful in three ways. When the judge and the human disagree, it shows you *which claim* the judge misapplied. It gives the human reviewer something to accept or reject in seconds. And critiques written by your domain expert become the few-shot examples (`with_few_shot` in `judge.py` takes them from the train split only).

## Worked example 2: the code-review judge

The question: "did the code-review comment identify a real bug?" Without a rubric, judges agree with confident comments. The rubric forces the judge to trace the code:

```text
Question: Does the review comment identify a real bug that this diff introduces or leaves in the changed lines?
PASS only if ALL of these hold:
  1. The comment names a concrete defect: wrong behaviour, data loss, a race, a leak, a security hole,
     or an operational hazard (lock, unbounded wait, retry storm).
  2. The defect is actually present in the post-diff code shown. Trace the code; do not take the
     comment's word for it.
FAIL if ANY of these is true:
  - The comment is a style, naming or convention remark.
  - The comment is a question or a suggestion with no identified defect.
  - The claimed defect is not real (for example it misreads a language or library guarantee), or the
    diff fixes rather than introduces it.
```

Three rows from `code/data/code_review_comments.jsonl` show why claim 2 matters:

| id | Diff | Comment | Human |
|---|---|---|---|
| CR-001 | `go c.store.Upsert(...)` then `c.commit(msg)` | "The offset is now committed before the upsert finishes ... at-least-once into at-most-once." | pass |
| CR-006 | `HashMap` -> `ConcurrentHashMap`, using `merge` | "ConcurrentHashMap.merge is not atomic, so increments can still be lost." | fail: `merge` is atomic per key |
| CR-014 | closure now takes `id` as a parameter | "This closure captures the loop variable, so every goroutine processes the last id." | fail: the diff *fixes* this |

CR-006 and CR-014 are confident, technical and wrong. A judge without claim 2 tends to pass them, because they sound like what a senior reviewer would write. CR-009 is a harder case. The comment says "on our Postgres 10 primary" and the human labeller knows that's true, but the judge can't verify it from the inputs. Under "if you cannot verify, it fails" the judge will fail a comment the human passes. This is a rubric decision, not a judge bug: either give the judge the deployment context as an input, or accept the false negative and know it is there.

## Worked example 3: Likert vs binary, same labels

Here are the frozen test-split results from `python code/compare_judges.py` (offline fakes, 25 test items). The Likert threshold was chosen on dev to maximise TPR+TNR, which is the most generous treatment the Likert judge can get.

```text
[test] likert (score >= 3 means pass)        [test] binary v2
             judge=pass  judge=fail                      judge=pass  judge=fail
human=pass        12           1             human=pass       11           2
human=fail         7           5             human=fail        3           9
TPR 0.92  TNR 0.42  kappa 0.35               TPR 0.85  TNR 0.75  kappa 0.60
```

The Likert judge looks fine if you only look at TPR. It passes nearly every good summary. It also passes 7 of 12 bad ones. On a status page, a false PASS means publishing a wrong statement about customer impact. That is the cell you care about, and TNR is the metric that measures it. [03](03-calibration.md) builds out these numbers properly, with confidence intervals.

## Pitfalls

- **Adjectives in the rubric.** Detect it by searching your rubric for "accurate", "clear", "good", "appropriate". Replace each one with the observable property it stands for.
- **Verdict before critique.** Detect it by checking schema order, or whether the prompt says "answer PASS/FAIL then explain". Reverse it.
- **Rubric written before reading data.** Detect it by asking whether each claim traces to at least one human critique. Claims with no source in the data are guesses. Criteria emerge from grading ([06](06-who-validates-the-validators.md)).
- **Treating parse failures as passes.** Detect it by grepping your harness for `except: return True`, or default-pass behaviour. Count errors separately (`judge_many` records `"error"`).
- **Few-shot examples from the test set.** Detect it by checking that few-shot ids are disjoint from dev and test ids. This is leakage, and it inflates every number you report. `test_judge.py` asserts that few-shots come only from train.
- **Several binary checks squashed back into one score.** Keep them separate. If you need a single ship/no-ship number, combine them with explicit rules ("all guardrail judges pass") rather than a weighted average ([Eugene Yan, "Product Evals"](https://eugeneyan.com/writing/product-evals/)).

## In your day job

- Rewrite your highest-traffic Likert judge as a binary judge with checkable claims. Keep the old one running in shadow for a week and compare both against 50 fresh human labels.
- Store rubrics as data (a dataclass, YAML, or JSON), render them into prompts, and review rubric changes in PRs like any other config change.
- When a judge disagrees with a human, read its critique before touching the prompt. The critique usually names the claim that is ambiguous.
