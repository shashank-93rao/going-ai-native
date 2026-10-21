# 02: Statistics that keep you honest

## The idea

An eval score is an estimate. It comes from a sample of items, drawn from the "question universe" you care about, and it is answered by a stochastic system ([Anthropic, "A statistical approach to model evaluations"](https://www.anthropic.com/research/statistical-approach-to-model-evals); paper: [Miller, arXiv 2411.00640](https://arxiv.org/abs/2411.00640)). So every score needs an error bar, and every comparison needs a test that fits how the data were collected. Four ideas cover nearly every hill-climbing decision:

1. **Standard error and CI.** Report a score as mean ± 1.96·SE.
2. **Clustering.** When items share context (alerts from one incident, questions about one passage, tasks in one repo), their errors correlate. The naive SE is then too small, so use a cluster-robust SE.
3. **Pairing.** When you compare two variants on the same items, analyze the per-item *differences*. That removes the between-item variance both variants share, and it is the single biggest free gain in sensitivity.
4. **Power.** Before you run anything, compute the smallest effect the eval can detect. If that is bigger than the improvement you hope for, the climb cannot succeed. Fix the eval first.

The **noise check** puts all four into one procedure you run before round 1.

## Why it matters

The published numbers are blunt:
- Clustered SEs on popular evals "can be over three times as large as naive standard errors" (Anthropic, above). Ignore clustering and you will declare differences significant that are not.
- On Terminal-Bench 2.0, infrastructure configuration alone moved scores by **6 percentage points** (p < 0.01). Anthropic's advice is that "leaderboard differences below 3 percentage points deserve skepticism" until configurations are matched ([Anthropic, "Quantifying infrastructure noise"](https://www.anthropic.com/engineering/infrastructure-noise)).
- With 200 samples and 3% observed defects, the 95% CI is roughly 3% ± 2.4%, so you "can't confidently conclude" a 5% defect requirement is met. At 400 samples it is ± 1.7%. Halving the margin needs four times the samples ([Eugene Yan, "Product Evals in Three Simple Steps"](https://eugeneyan.com/writing/product-evals/)). `stats.py` reproduces both numbers, and `test_stats.py` checks them.
- Question-level score correlation between frontier models on popular evals is "between 0.3 and 0.7", which is why paired analysis is a "free" variance reduction (Anthropic, above).

And here is a finding from this module's own simulation, which the rest of the file explains. Run the same climb with 10 different seeds on a 160-incident eval. Real fixes, each worth about 4.5 points, are kept as rarely as **3 out of 10** times. Final test accuracy ranges from **74.9% to 89.4%**, depending on luck alone.

## How it works

### The unit of analysis

Score each item, average over the *k* repeats of that item, and run every statistic on those per-item means. `RunResult.item_scores` in `router_eval.py` is exactly this vector. Run-level averages throw away the pairing and the clustering, so do not use them for decisions.

### Standard error, three ways

| SE | Formula | Use when |
|---|---|---|
| Naive | s / √n | Items are independent (rare in practice) |
| Binomial | √(p(1−p)/n) | Quick planning for a 0/1 metric |
| Clustered (CR) | √( Σ_c (Σ_{i∈c} (x_i − x̄))² ) / n, times √(G/(G−1)) | Items share context. The default for anything agentic, multi-turn, or multi-question-per-document |

The design effect (SE_clustered / SE_naive)² tells you how many "effective" items you really have. If every cluster holds *k* perfectly correlated items, the design effect is *k*. `test_stats.py::test_perfectly_correlated_clusters_inflate_by_sqrt_k` builds 30 clusters of 9 identical scores and checks the SE ratio is 3.0: the ">3x" regime, from first principles. A useful property test: with one item per cluster and the G/(G−1) correction, the clustered SE equals the naive SE *exactly*. Hypothesis checks this on random inputs.

### Paired comparisons

For variants A and B on the same items, let d_i = b_i − a_i. Then

```
Var(d) = Var(a) + Var(b) − 2·ρ·sd(a)·sd(b)
```

When item difficulty dominates, ρ is large and Var(d) is small. In the running example (round 4 vs the round-2 best, dev), the per-item correlation between the two variants is 0.86. Cluster the d_i by incident, as `paired_diff(a, b, clusters)` does.

**McNemar** is the paired test for single 0/1 outcomes. Only the discordant items carry information: b01 (A failed, B passed) and b10 (A passed, B failed). With b01 = 10 and b10 = 2, the exact two-sided p is 2·Σ_{i≤2} C(12,i)/2¹² = 158/4096 = 0.0386 (a known-value test in `test_stats.py`). Use McNemar when you have one run per item. With repeats, use the paired difference of per-item means.

**Paired bootstrap** resamples *clusters* (not items) with replacement and recomputes mean(d). It makes no normality assumption, and it is the honest choice when a change affects few clusters. `paired_bootstrap(..., clusters=...)` returns the percentile CI and the share of resamples with d ≤ 0.

### Power and sample size

| Question | Function | Example |
|---|---|---|
| How wide is my CI? | `ci_halfwidth(p, n)` | p=0.03, n=200 gives ±2.4 pts (Eugene's number) |
| Items for a ±m CI? | `required_n_for_margin(p, m)` | p=0.03, ±1 pt needs 1,118 |
| Items per arm, independent samples? | `required_n_two_proportions(p1, p2)` | 70% vs 75% needs 1,251 per arm |
| Items, paired? | `required_n_paired(δ, sd_d)` | same 5 pts, ρ=0.5 needs 624 items |
| What can I detect? | `min_detectable_effect(se_d)` | MDE = (1.96 + 0.84)·SE_d at 80% power |

The pairing row is the argument for always evaluating variants on identical items. Pairing halves the eval size you need for the same power, and with ρ ≈ 0.86, as in our router, it does much better than that.

### Repeats versus items

Repeats average out **within-item** noise (sampling). They do nothing for **between-item** variance, which comes from which items you happened to draw and how a change's effect is spread across them. Anthropic's recommendation #3 ("reduce variance within questions" by resampling) is about the first kind only. The noise check measures the first kind. Real changes are dominated by the second. That gap is the most important practical fact in this file, and the worked example shows it.

### Infrastructure noise

For agentic evals, the resource budget is part of the task. Anthropic saw infra errors fall from 5.8% at strict resource enforcement to 0.5% uncapped, and recommends about 3x headroom over per-task specs, with the configuration reported. They also note pass rates anecdotally fluctuate with time of day (unquantified) ([Anthropic, "Quantifying infrastructure noise"](https://www.anthropic.com/engineering/infrastructure-noise)). The operational rules: run baseline and candidate **interleaved** on the same infrastructure in the same window; count infra errors separately from task failures (the router's `truncated` counter is one such count); and never compare against a baseline that ran last week on a different cluster. [Module 13](../13-testing-agentic-systems/README.md) covers separating infrastructure failures from model failures.

## Worked example

### The noise check

```bash
python noise_check.py --runs 6 --repeats 4 --min-effect 0.05
```

Simulated output on the 491-alert dev split:

| metric | value |
|---|---|
| runs x items | 6 x 491 |
| run accuracies | 68.8, 69.2, 69.5, 70.1, 70.7, 69.2 |
| SD of run accuracy | 0.7 pts |
| items that flipped across runs | 19.1% |
| SE of one run: naive / clustered | 2.1 / 2.6 pts |
| null paired diff (same config, two halves) | 0.8 pts |
| paired SE at 4 repeats | 0.6 pts |
| minimum detectable effect (80% power) | 1.7 pts |
| smallest effect you'd act on | 5.0 pts |

Verdict: OK. Two things are worth reading closely. First, run accuracies span 68.8 to 70.7 for the *same config*: a 2-point "improvement" between two single runs means nothing. Second, one item in five flips verdict across runs, so a single run's failure list is part noise. That is why the error analysis in concept 01 used majority-failed items over four repeats.

### Bad: two independent CIs

A teammate compares round 4 (tiebreak rule) with the current best like this:

```text
best   77.5% [74.1, 80.9]   (naive)
cand   79.8% [76.3, 83.3]   (naive)
"CIs overlap, so it's noise. Revert."
```

Two mistakes in one line. Overlapping CIs are not a test of the difference. And treating the two runs as independent throws away the pairing. As a difference, unpaired: **+2.2 [−2.5, 7.0]**.

### Good: paired, then clustered

```python
from stats import paired_diff, paired_bootstrap, mcnemar
paired_diff(best.item_scores, cand.item_scores)                 # +2.2 [0.5, 4.0]
paired_diff(best.item_scores, cand.item_scores, best.clusters)  # +2.2 [0.3, 4.2]
paired_bootstrap(best.item_scores, cand.item_scores, best.clusters)  # [0.4, 4.2], P(d<=0)=0.009
mcnemar(best.per_repeat[0], cand.per_repeat[0])                 # b01=26, b10=19, p=0.37
```

These are simulated values from the canonical run. Pairing turns an uninformative interval into a significant one, and clustering widens it slightly, as it should. The McNemar line shows the cost of a single repeat: on one run's 0/1 outcomes, the same change is invisible (p = 0.37). Repeats were what made it detectable.

### The trap: the noise check is a lower bound

The noise check said MDE = 1.7 points. Yet the measured CIs on real changes in the log have half-widths of **2 to 4 points**. Why? A null comparison only contains sampling noise spread thinly over all items. A real change concentrates its effect: the tie-break rule flips about 40% of the ~43 tiebreak alerts and leaves the other 448 alone, and those 43 sit in a handful of incidents. The per-item differences are lumpy, and clustering makes them lumpier.

Here is what that does to decisions. Same simulated system, same variants, same rules, 10 seeds each, three eval sizes:

| eval size (incidents / dev alerts) | v4-tiebreak kept | v5-owner-tool kept | v6b-effort-high kept | final test accuracy across seeds |
|---|---|---|---|---|
| 160 / 244 | 3 of 10 | 6 of 10 | 6 of 10 | 74.9 to 89.4 |
| 320 / 491 (this module's default) | 8 of 10 | 10 of 10 | 10 of 10 | 84.6 to 90.7 |
| 640 / 990 | 10 of 10 | 10 of 10 | 10 of 10 | 88.6 to 89.7 |

Each of those three fixes is worth about +4.5 points in expectation (computed analytically from the simulator). The no-op (v1) and the overfit (v3) were reverted in all 30 runs at every size, so the rules are not the problem. The problem is power. At 160 incidents, a real 4.5-point fix is close to a coin flip. One climb in three ends 10 points short, and nobody would know. Doubling the incidents fixed it. **Add clusters, not repeats:** repeats would have shrunk the noise-check MDE further, and it was already "OK".

The practical rule: treat the noise-check MDE as optimistic by roughly 2x for targeted changes. Size the eval so the *slice* you are fixing has enough clusters, typically at least 20 to 30 incidents in the failure family you are attacking.

## Pitfalls

| Pitfall | How to detect it |
|---|---|
| Naive SE on clustered items | Compute both. If clustered/naive > 1.2, you have clustering, and the naive number is lying |
| "CIs overlap so no difference" | You compared intervals instead of testing the paired difference |
| Run-level means as the unit | Your stats code never sees item IDs, so it can't pair or cluster |
| Common random numbers flattering the deltas | Candidate and best share a seed; with a real API you can't, so your CIs will widen in production |
| Significance shopping across a sweep | Four effort levels give four chances at a false positive at α = 0.05. Pick the winner on dev, confirm on test, or tighten α |
| A single run's failure list as ground truth | Flip rate > 10% in the noise check; use majority-over-repeats failures |
| Infra noise read as a model regression | Truncations, timeouts, and 5xx counted as wrong answers; track them separately |
| Eval too small for the slice | The family you target has fewer than ~20 clusters; real fixes keep getting reverted as "within noise" |

## In your day job
- Run `noise_check.py` (or its equivalent) on every new eval and paste the table into the eval's README. If anyone asks "is 2 points real?", point at the MDE.
- Store per-item scores with item IDs and cluster IDs for every eval run, never just the aggregate. Without them you can't pair, cluster, or bootstrap.
- Use `required_n_paired` when you plan an eval. A product manager asking to "detect 2-point regressions" is asking for a specific number of incidents. Tell them which number.
- When a change you believe in keeps losing as "within noise", count the clusters in its target slice before you abandon it.
