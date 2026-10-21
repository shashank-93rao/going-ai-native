# 05: Judge biases and how to probe for them

## The idea

A judge bias is a systematic dependence of the verdict on something that should be irrelevant: where an output appears, how long it is, who wrote it, or which run you are on. Calibration ([03](03-calibration.md)) measures a judge's total error on your label distribution. A bias probe isolates one cause of error by holding the content fixed and changing only the nuisance variable. It works like a controlled experiment, or a fault-injection test that varies one fault at a time.

The four you should probe for:

| Bias | What changes the verdict | Source |
|---|---|---|
| **Position** | Which slot an output is shown in, in pairwise comparisons | [Zheng et al. 2023 (MT-Bench)](https://arxiv.org/abs/2306.05685) |
| **Verbosity** | Length and apparent thoroughness, with the content held fixed | Zheng et al. 2023 |
| **Self-preference** | Whether the output came from the judge's own model | Zheng et al. 2023 ("self-enhancement"); [Panickssery et al. 2024](https://arxiv.org/abs/2404.13076) |
| **Run-to-run inconsistency** | Nothing: the same input gets a different verdict on a re-run | [Anthropic, "Automating eval design and hillclimbing"](https://claude.dev/blog/automating-eval-design-and-hillclimbing/) |

## Why it matters

The MT-Bench paper that popularised LLM-as-judge reports that strong judges reach over 80% agreement with human preferences, about the level humans reach with each other. The same paper names position, verbosity and self-enhancement bias as the main limitations ([Zheng et al. 2023](https://arxiv.org/abs/2306.05685)). Both results are true at once. Average agreement can be high while a specific bias still decides the verdicts that matter, which are usually the close calls in a comparison you are using to decide whether to ship.

Self-preference matters most in agent loops. Panickssery, Bowman and Feng found that LLM evaluators score their own outputs higher than other text that humans rate as equal in quality. They also found that a model's ability to recognise its own outputs correlates linearly with how strongly it prefers them ([Panickssery et al. 2024](https://arxiv.org/abs/2404.13076)). Anthropic's harness work found the agent-level version of the same thing: "agents reliably skew positive when grading their own work", and the fix was to split the generator from the evaluator ([Anthropic, "Harness design for long-running application development"](https://www.anthropic.com/engineering/harness-design-long-running-apps)). If the model under test is also grading its own outputs, its self-preference counts as an improvement in your metrics.

Run-to-run inconsistency is the most mundane bias, and the easiest to forget. If 8% of verdicts flip on a re-run, a 5-point "improvement" between two eval runs can be pure noise. Anthropic's tooling names "a grader that produces different verdicts on identical output" as a source of variance, and runs the grader twice to measure it ([Anthropic](https://claude.dev/blog/automating-eval-design-and-hillclimbing/)).

## How to do it

### Anthropic's three mitigations, as defaults

Anthropic's eval-building workflow bakes in three rules ([Anthropic](https://claude.dev/blog/automating-eval-design-and-hillclimbing/)):

1. **Blind, randomised pairwise.** "Reads both inputs in random order, without being told which is the baseline." `pairwise.py` runs both orders, which is stronger ([04](04-pairwise-reference-and-summary-evaluators.md)).
2. **A different model.** "You pick the judge model, and it should not be the model you are testing." Anthropic's docs give the same advice: use a different model to grade than the one that generated ([Anthropic docs, "Create strong empirical evaluations"](https://platform.claude.com/docs/en/test-and-evaluate/develop-tests)).
3. **Double-run consistency.** "Runs the grader twice on the same output, and reports whether the verdict changed."

### Probes, one per bias

All probes in `bias_probes.py` take a plain callable, so they work with a `FakeClient` in tests and with the real API in an exercise:

```python
pointwise = lambda item: judge(client, INCIDENT_IMPACT, item).passed
pairwise  = lambda task, first, second: ask_once(client, task, first, second, criterion)
```

**Verbosity, pointwise.** Take items the judge currently FAILs, append content-free padding, and re-judge. The padding restates nothing and adds no facts:

```text
 This summary has been prepared following our standard incident communication process. The team has
 reviewed the full timeline, the contributing factors and the follow-up actions in detail, and will
 continue to monitor the affected systems closely to ensure stability going forward.
```

The headline number is the fail-to-pass flip rate, which should be 0. A wrong summary doesn't become right because it got longer.

**Verbosity, pairwise.** Compare `x` against `pad(x)` in both orders. An unbiased judge says tie, or splits evenly. A rate well above 0.5 for the padded copy is verbosity bias.

**Position.** For each pair (a, b), ask (a, b) and (b, a). Measure the share of decided votes that go to slot 1 (unbiased: about 0.5), and the share of pairs whose verdict flips under the swap (unbiased: about 0).

**Run-to-run.** Judge each item twice (or k times) and count items with more than one distinct verdict. If you can set temperature to 0 on your judge, still measure this; it's often not zero.

**Self-preference.** You can't measure this from judge output alone, because you need to know what the right answer was. Collect human pairwise preferences on pairs where one side came from the judge's own model family, then compute:

```text
gap = P(judge picks own-family output) - P(human picks own-family output)
```

`self_preference_gap` does this. A gap well above 0 means that when you use this judge to compare your system against a competitor's model, the result is tilted.

## Worked example: probing five judges

`python code/bias_probes.py` runs every probe against two pointwise and three pairwise offline fakes, each with a known bias built in. This is real output from the module's code; the judges are heuristics, not models:

```text
== pointwise judges ==
-- rules judge (v2)
  verbosity (pointwise)        n=28   rate=0.00  expected~0.00  [ok]
  run-to-run (2 runs)          n=60   rate=0.00  expected~0.00  [ok]
-- lenient-on-long judge
  verbosity (pointwise)        n=24   rate=1.00  expected~0.00  [BIASED]
  run-to-run (2 runs)          n=60   rate=0.00  expected~0.00  [ok]
== pairwise judges ==
-- content-only
  position (slot-1 share)      n=12   rate=0.50  expected~0.50  [ok]
  position (swap flip rate)    n=10   rate=0.00  expected~0.00  [ok]
  verbosity (pairwise)         n=0    rate=0.50  expected~0.50  [ok]
-- always-first
  position (slot-1 share)      n=20   rate=1.00  expected~0.50  [BIASED]
  position (swap flip rate)    n=10   rate=1.00  expected~0.00  [BIASED]
  verbosity (pairwise)         n=20   rate=0.50  expected~0.50  [ok]
-- prefers-longer
  position (slot-1 share)      n=20   rate=0.50  expected~0.50  [ok]
  position (swap flip rate)    n=10   rate=0.00  expected~0.00  [ok]
  verbosity (pairwise)         n=20   rate=1.00  expected~0.50  [BIASED]
```

Three things to notice:

1. **The always-first judge passes the verbosity probe.** That isn't a bug. Because the probe runs both orders, pure position bias cancels to 0.5. If the probe had shown the padded copy first every time, this judge would have looked 100% verbosity-biased. Every probe has to control for the biases it isn't measuring.
2. **The content-only judge has n=0 on the pairwise verbosity probe.** Every vote was a tie, which is the correct answer when the two responses carry identical facts. A probe that only counts decided votes needs to report n, or "0 decided" looks like "0.5, fine".
3. **The lenient-on-long judge passes the run-to-run probe.** It's perfectly consistent, and consistently wrong. Consistency is necessary, but it tells you nothing about bias. Only the content-controlled probe catches this one.

Running the same probes against a real judge means swapping the client:

```python
from ainative_kit import get_client
client = get_client()                       # real API; needs ANTHROPIC_API_KEY
report = verbosity_probe_pointwise(lambda it: judge(client, INCIDENT_IMPACT, it, model="claude-opus-5-5").passed, rows)
print(report.line())
```

Whatever that prints is a measurement of your judge on your data. Don't assume any of the fake's numbers above carry over.

## Mitigations

| Bias | Mitigation in the rubric or prompt | Mitigation in the protocol |
|---|---|---|
| Position | "Order is random and carries no information" | Run both orders; a flip becomes a tie; report the inconsistency rate |
| Verbosity | "Length and fluency are not evidence"; put length in the out-of-scope list | Run the padding probe on every judge version; consider normalising or truncating inputs |
| Self-preference | none that works reliably | Use a judge from a different model family from both candidates; measure the gap against human pairwise labels |
| Run-to-run | Narrow the rubric (ambiguity drives flips); critique-then-verdict | Double-run on a sample of every eval; majority-vote 3 runs for high-stakes gates |

A **panel of smaller judges** is another option: several different models vote, which averages out model-specific biases. Eugene Yan summarises a study (PoLL) reporting that a panel of small judges was comparable to a single GPT-4 judge at roughly one-seventh of the cost ([Eugene Yan](https://eugeneyan.com/writing/llm-evaluators/)). Treat that as a reported result to test on your own task, not a guarantee.

## Pitfalls

- **Probing with the wrong control.** A verbosity probe that adds *facts* along with length is measuring something else. Make padding content-free, and check it: `test_padding_is_content_free` asserts there are no digits in the padding.
- **Probing once.** Bias depends on the judge model and the prompt. Re-run the probes when either changes ([06](06-who-validates-the-validators.md)).
- **Same family as the generator.** Detect it by putting the generator's and judge's model IDs side by side in the calibration report. If they are the same family, measure self-preference or switch.
- **Confusing leniency with self-preference.** A judge that passes everything also "prefers" its own outputs. Look at the gap relative to humans, not the raw rate.
- **Trusting a high agreement number to rule out bias.** 80% agreement can coexist with a large position bias on close pairs. Probe directly.

## In your day job

- Add the double-run and padding probes to the judge's CI. They are cheap: 20 items, 2-3 extra calls each.
- In every pairwise eval report, include the position-inconsistency rate next to the win rate.
- Write down the generator's and the judge's model families in the eval config, and fail the config if they match, unless someone explicitly overrides it with a reason.
