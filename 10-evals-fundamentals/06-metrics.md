# 06: Metrics

## The idea
A pass rate is a mean over trials. It hides three things you need: **how consistent** the system is on a given task, **how it fails** (declining vs being confidently wrong), and **where** it fails (which slice). This file covers three metrics that bring them back:

1. **pass@k vs pass^k**. pass@k is the probability that *at least one* of k independent trials succeeds. pass^k (read "pass hat k") is the probability that *all* k succeed. pass@k measures capability. pass^k measures reliability ([Anthropic, "Demystifying evals for AI agents"](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents); [Yao et al., τ-bench](https://arxiv.org/abs/2406.12045)).
2. **Abstention-aware scoring**. Score correct, abstain and wrong separately, and make a wrong answer cost more than declining ([Kalai et al., "Why Language Models Hallucinate"](https://arxiv.org/abs/2509.04664)).
3. **Per-slice metrics**: every number broken down by slice, because aggregates hide regressions.

## Why it matters
**Reliability.** At 75% per-trial success, pass^3 is 0.75³ ≈ 42% ([Anthropic, "Demystifying evals"](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)). τ-bench introduced pass^k for this reason. In its retail domain even strong function-calling agents such as gpt-4o succeeded on "<50% of the tasks", and pass^8 was under 25% ([Yao et al.](https://arxiv.org/abs/2406.12045)). Anthropic's think-tool post reported τ-bench airline results both ways: pass^1 of 0.584 vs 0.332 baseline, and pass^5 of 0.340 vs 0.100 ([Anthropic, "The think tool"](https://www.anthropic.com/engineering/claude-think-tool)). A reliability metric drops much faster than the headline number.

**Guessing.** OpenAI's hallucination paper argues that models keep hallucinating partly because "standard training and evaluation procedures reward guessing over acknowledging uncertainty". Accuracy-only scoring is like a multiple-choice exam with no penalty for wrong answers. OpenAI's post on the paper gives a SimpleQA comparison from the GPT-5 system card ([OpenAI, "Why language models hallucinate"](https://openai.com/index/why-language-models-hallucinate/)):

| Model | Abstained | Accurate | Wrong |
|---|---|---|---|
| gpt-5-thinking-mini | 52% | 22% | 26% |
| o4-mini | 1% | 24% | 75% |

On accuracy alone, o4-mini "wins" by 2 points. It is also wrong almost three times as often. (These numbers are as reported in OpenAI's post. The post itself returned 403 when this module was written, so they come from the course research notes.)

## How it works

### pass@k and pass^k from n trials
Run each task n ≥ k times and count c passes. Use the unbiased estimators rather than raising the per-task pass rate to the power k:

```python
from math import comb

def pass_at_k(n, c, k):  # P(at least one of k passes)
    return 1.0 - comb(n - c, k) / comb(n, k)

def pass_hat_k(n, c, k):  # P(all k pass)
    return comb(c, k) / comb(n, k)
```

The pass@k estimator is the standard one from OpenAI's Codex paper ([Chen et al., 2021](https://arxiv.org/abs/2107.03374)). The pass^k estimator is its mirror image, and the one τ-bench uses. Compute per task, then average over tasks. **Do not compute p^k on the aggregate pass rate.** A suite with half its tasks at 100% and half at 50% has a pass rate of 75%, and an actual pass^3 of (1 + 0.125)/2 ≈ 56%, not 42%. Reliability is a per-task property.

### Which one your users feel
| Situation | Metric | Why |
|---|---|---|
| The system runs once and its output is used (router, support reply, classifier) | pass^1, and pass^k for consistency on repeated similar inputs | Nobody re-rolls a page at 03:00 |
| A verifier can pick the good attempt among k (hidden tests, a type checker) | pass@k | You actually get the best of k, at k times the cost |
| A human retries until satisfied | pass@k, discounted by the human's time | The human is the verifier |
| Customer-facing agent with consistency expectations | pass^k | Users notice when the same request works on Monday and fails on Tuesday |

This is the course thesis in one table. **pass@k is only available to you if you have an oracle that can tell which attempt succeeded.** Without one, you get pass^1 at best. The more verifiable the task, the more of the gap between pass^k and pass@k you can capture by sampling and checking.

In SRE terms, pass^k is availability: every one of k requests has to succeed. pass@k is "it works with retries", and retries only help if you can detect failure.

### Read the gap
- **pass@k ≈ pass^k:** failures are deterministic. The same tasks fail every time. These are prompt or logic bugs, and error analysis finds them.
- **pass@k ≫ pass^k:** failures are stochastic. The system *can* do the task and doesn't reliably. Fixes include removing ambiguity, constraining the output, lowering temperature where you control it, or best-of-k with a verifier. Separate this from infrastructure noise before acting on it ([Module 12](../12-hill-climbing/README.md), [Module 13](../13-testing-agentic-systems/README.md)).

### Abstention-aware score
Classify every trial into one of three outcomes (`graders.classify_outcome`):

- **correct**: all gating graders pass. Abstaining on a case that *should* be abstained counts here.
- **abstain**: the system declined a case it should have answered.
- **wrong**: everything else, including malformed output (in production, nobody gets paged).

Then score correct = +1, abstain = 0, wrong = −penalty. The hallucination paper proposes stating a confidence target in the instructions: "Answer only if you are >t confident, since mistakes are penalized t/(1-t) points" ([Kalai et al.](https://arxiv.org/abs/2509.04664)). At t = 0.75 the penalty is 3. The router's system prompt states this threshold, and `eval_harness.py --penalty 3` scores against it, so the model is told the same rules it is graded by.

Choose the penalty from the cost of a wrong answer relative to a decline. For the router, a decline sends the alert to a human triage queue (minutes of delay). A wrong route wakes the wrong team and delays the right one. A penalty of 3 is conservative.

### Per-slice metrics
Every metric above is also computed per slice and per split (`summarize(...)["by_slice"]`). Aggregates hide regressions: a prompt change that fixes 6 keyword-trap cases and breaks both secret cases nets +4, and the secret leak is the one that blocks the launch. Two cautions:

- **Small slices are noisy.** With 4 cases, one case flipping moves the slice by 25 points. Report n next to every slice rate, and see [Module 12](../12-hill-climbing/README.md) for confidence intervals. Eugene Yan works the example: with 200 samples and a 3% observed defect rate, the 95% interval is about ±2.4%, too wide to prove a 5% requirement ([Eugene Yan, "Product Evals in Three Simple Steps"](https://eugeneyan.com/writing/product-evals/)).
- **Gate on slices, not just the aggregate.** "No slice regresses by more than one case, and `secret_in_body` stays at 100%" is a better release rule than "overall pass rate ≥ X".

## Worked example: an accuracy drop that is an improvement

The router's fake model has a second variant, `--cautious`, which abstains unless exactly one team's keywords match. Compare the two over 43 cases × 5 trials:

```bash
python eval_harness.py --trials 5 --k 1 3 --out base.jsonl
python eval_harness.py --trials 5 --k 1 3 --cautious --out cautious.jsonl
```

**Bad report** (what a dashboard with only accuracy shows):

```text
baseline   accuracy 44.7%
cautious   accuracy 41.9%   (-2.8 pts)  -> reject
```

**Good report** (measured, from the two runs above):

| Variant | pass@1 | pass@3 | pass^3 | correct | abstain | wrong | score (penalty 3) |
|---|---|---|---|---|---|---|---|
| baseline | 0.4465 | 0.4814 | 0.4186 | 0.4465 | 0.0233 | 0.5302 | **−1.1442** |
| cautious | 0.4186 | 0.4186 | 0.4186 | 0.4186 | 0.2093 | 0.3721 | **−0.6977** |

Read it row by row:

- **Wrong answers fell from 53% to 37%.** The cautious variant gave up 2.8 points of correct answers, and in exchange cut wrong answers by 15.8 points and sent 18.6 points more to the triage queue. At a penalty of 3, that is a large improvement.
- **pass^3 did not move, and pass@3 fell to meet it.** The baseline's only stochastic behavior was its random tie-breaking between matching teams. Those tie cases sometimes passed by luck, which is what put pass@3 above pass^3. The cautious variant abstains on ties, so it is fully deterministic, and the luck is gone. Consistency is a feature an on-call rotation will notice.
- **Per slice**, the `misleading_keyword` slice went from 10% correct and 90% wrong to 0% correct, 100% abstain, 0% wrong. That converts four kinds of misroute into triage-queue items, which is the right trade until the ownership rules are fixed.
- **Both scores are still negative.** Under this scoring, a router that abstained on *everything* would score 0 and beat both. That is a real finding, not an artifact. The router as it stands is worse than sending every alert to a human. The fake was built that way, but production systems end up there too, and only an abstention-aware metric shows it.

A dashboard that shows only accuracy rejects a change that halves the damage. One that shows the three-way split and the score accepts it, and shows what to fix next.

## Pitfalls
| Pitfall | How to detect it |
|---|---|
| Reporting pass@k for a system nobody re-rolls | Ask how the output is consumed. If there is no verifier picking among attempts, pass@k overstates what users get. |
| p^k on the aggregate pass rate | Your pass^k is lower than the per-task estimate on a heterogeneous suite. Compute per task. |
| One trial per task | pass@k and pass^k are undefined (the harness skips k > n). Run at least k trials, and more for tight estimates. |
| Accuracy without the error rate | A change "improves accuracy" and doubles wrong answers. Always print correct, abstain and wrong together. |
| Counting a malformed output as an abstain | Malformed outputs reach nobody. Count them as wrong, as `classify_outcome` does. |
| The penalty in the grader but not the prompt | The model is graded on rules it was never told. State the threshold in the instructions. |
| Slice rates without n | A slice "drops 25 points" on one case. Print n, and use intervals from Module 12. |

## In your day job
- Run every task at least 3 to 5 times and put pass^k next to pass@1 on your eval dashboard.
- Add an explicit "I don't know" path to every LLM feature that can decline, state its price in the prompt, and score it three ways.
- Define release gates per slice, with a hard 100% gate on safety slices such as secrets.
- When pass@k ≫ pass^k, look for ambiguity and a missing verifier before you look at the prompt wording.
