# A-M5: Hill-climb with error bars
**Time:** one to two weekends. **Offline:** no. **Modules:** [12](../../12-hill-climbing/README.md), [01](../../01-llms-for-systems-engineers/README.md), [02](../../02-prompting-as-specification/README.md), [08](../../08-harness-engineering/README.md).

## Goal
Improve the agent against the frozen M4 suite, one change at a time, and finish with a claim you can defend: "test-split pass@1 went from X to Y (paired difference Δ, 95% CI [a, b]) at Z tokens per episode".

## Why it matters
With 48 scenarios and one trial each, the offline baseline's 95% CI is [0.26, 0.53]: 28 points wide. A prompt tweak that moves the point estimate by 5 points is invisible at that resolution. Anthropic's infrastructure-noise study found that resource configuration alone moved Terminal-Bench 2.0 scores by 6 points, more than many leaderboard gaps ([Anthropic, "Quantifying infrastructure noise"](https://www.anthropic.com/engineering/infrastructure-noise)). If you do not measure your own noise first, you will keep changes that did nothing and revert changes that helped.

## Steps
1. **Noise check before round 1.** Run the unchanged agent on the train split 3 times (k=3 trials each). Compute the pass rate per repeat. The spread is your noise floor. Your smallest actionable change must be bigger than it ([Anthropic hill-climbing post](https://claude.dev/blog/automating-eval-design-and-hillclimbing/)). If it is not, add trials or scenarios before you start.
2. **Power, roughly.** For a paired comparison on n scenarios, the SE of the mean difference is about `sd(d_i)/sqrt(n)`, where `d_i` is per-scenario pass-rate difference. Estimate `sd(d_i)` from the noise check (two runs of the same agent). Pick n so that 1.96 × SE is smaller than the effect you care about.
3. **One root-cause change per round.** Pick the top category from M3. Make the smallest change that targets it. Possible surfaces, cheapest first:
   - tool descriptions and result formats
   - the system prompt (spec text, not examples copied from failures)
   - governors and loop structure (for example, a forced "verify" step before `resolve_incident` is allowed)
   - model and effort
   - architecture (plan-then-execute, a clean-context verifier)
4. **Run on train, compare paired.** Same scenarios, same k. Compute per-scenario mean pass for old and new, then the mean difference with a 95% CI.
5. **Decide with rules, not feelings**:
   - train up, test up: keep
   - train up, test flat: **revert** (overfit)
   - any regression on the regression suite or any safety check: revert
   - within noise: do not merge; log it and move on
6. **Log every round** in EXPERIMENTS.md, including reverts.
7. **Run one non-prompt dimension.** Swap the model (for example `claude-haiku-5-5` vs `claude-sonnet-5-5`) or effort, holding prompt fixed. Plot pass@1 vs tokens per episode. Pick a point on the frontier, not the top.
8. **Finish** on the best test-split version, report with CIs, and stop. If the final gain is within noise, the honest result is "no significant improvement", and that still passes the milestone if the log is rigorous.

## Worked example: paired difference
```python
import math
from collections import defaultdict

def paired_diff(grades_a, grades_b):
    """Per-scenario mean pass for A and B, then mean diff with a 95% CI. Scenarios are the unit."""
    def per_scenario(gs):
        d = defaultdict(list)
        for g in gs:
            d[g.scenario_id].append(1.0 if g.passed else 0.0)
        return {k: sum(v) / len(v) for k, v in d.items()}
    a, b = per_scenario(grades_a), per_scenario(grades_b)
    ids = sorted(set(a) & set(b))
    d = [b[i] - a[i] for i in ids]
    mean = sum(d) / len(d)
    sd = math.sqrt(sum((x - mean) ** 2 for x in d) / (len(d) - 1))
    se = sd / math.sqrt(len(d))
    return mean, (mean - 1.96 * se, mean + 1.96 * se)
```

Why paired: both versions face the same scenarios, and per-scenario difficulty is shared, so differencing removes it. Anthropic's error-bars paper recommends paired-difference tests for exactly this reason, and clustered SEs when items are correlated ([Miller, "Adding Error Bars to Evals"](https://www.anthropic.com/research/statistical-approach-to-model-evals)). Repeated trials of one scenario are such a cluster, which is why `summarize` clusters by scenario id.

## Worked artifact: EXPERIMENTS.md
(illustrative output; your numbers will differ)

```markdown
Suite: evals/splits.json sha256 3f9c… (train 29 scenarios, test 19), k=3, model claude-sonnet-5-5
Noise check (round 0, 3 repeats of baseline on train): 0.54, 0.59, 0.56 -> spread 5 pts. Act on Δ > 6 pts.

| # | Change (one) | Targets M3 category | Train pass@1 (Δ, 95% CI) | Test pass@1 | Safety | Tok/ep | Decision |
|---|---|---|---|---|---|---|---|
| 0 | baseline system_v1 | - | 0.56 | 0.53 | 2 dangerous | 9.8k | - |
| 1 | resolve_incident requires post-mutation get_metrics (loop rule) | no verification | 0.62 (+0.06 [+0.01, +0.11]) | 0.58 | 2 | 10.9k | keep |
| 2 | spec: "a flapping alert that is not firing now is a false alarm" | false-alarm mutation | 0.71 (+0.09 [+0.03, +0.15]) | 0.68 | 2 | 11.0k | keep |
| 3 | 3 worked examples from failing traces in prompt | traffic spike | 0.80 (+0.09 [+0.02, +0.16]) | 0.67 | 2 | 13.2k | REVERT: train up, test flat |
| 4 | scale tool description: "use when rps is far above baseline and errors are load-shedding" | traffic spike | 0.76 (+0.05 [-0.01, +0.11]) | 0.74 | 2 | 11.1k | keep? within noise on train; test up. Rerun k=5 -> +0.07 [+0.02, +0.12]: keep |
| 5 | model -> claude-haiku-5-5, same prompt | cost | 0.66 (-0.10 [-0.17, -0.03]) | 0.63 | 4 | 10.4k | revert |
```

Row 3 is the overfitting lesson Anthropic reports in its own hill-climbing write-up (a variant that added worked examples raised train while test stayed flat, and was reverted). The rule there is explicit: never paste failure content into the prompt ([Anthropic hill-climbing post](https://claude.dev/blog/automating-eval-design-and-hillclimbing/)). Note also that the safety column did not move in any round: prompt changes do not fix that. M6 does.

## Deliverables
- EXPERIMENTS.md with noise check, ≥4 rounds, at least one revert, at least one non-prompt dimension
- Final report: test-split pass@1, pass^3, label counts, judge-corrected summary quality, tokens and cost per episode, all with CIs
- The commit hash of every row

## Done when
- [ ] Noise check run and threshold stated before round 1.
- [ ] Each kept change has a paired CI on train that excludes zero, and test did not drop.
- [ ] The test split was evaluated once per round and never used to pick a change.
- [ ] The accuracy-vs-cost plot exists for at least two models or effort levels.
- [ ] Final claim stated with CI. If within noise, stated as such.

## Reuse
- `../code/grade.py` (`summarize`, `clustered_se`), your M4 suite
- Noise checks, paired tests, power, revert rules, cost frontier: [12-hill-climbing](../../12-hill-climbing/README.md)
- Harness changes vs prompt changes; ablate on model upgrade: [08-harness-engineering](../../08-harness-engineering/README.md)

## Pitfalls
- **Looking at test to decide.** It happens by accident: you glance at test, see it flat, and "just try one more tweak". Log the glance as a round.
- **Many changes per round.** You cannot attribute a gain. If you must batch, ablate afterwards.
- **Optimizing a broken grader.** If a round's gain comes from a weird trajectory, read five of them. Anthropic reports that its last step on one skill eval came from fixing broken graders ([hill-climbing post](https://claude.dev/blog/automating-eval-design-and-hillclimbing/)).
- **Ignoring cost.** A +3 point gain at 2x tokens is often not worth it for an agent that runs on every page.
