# 12: Hill-Climbing
> After this module you can take an LLM system from "works about 70% of the time" to a measured, defensible ~90%. You change one thing per round, keep or revert each change with paired, clustered statistics, never fool yourself with your own dev set, and leave behind a CI gate that holds the gain.

## Why this matters

Every team that ships an LLM feature ends up tuning it. Without discipline, the tuning goes like this. Someone edits the prompt, runs the eval once, sees 74% where yesterday's run said 71%, and merges. Next week someone pastes three failing examples into the prompt and sees 79%. A month later production accuracy is about where it started, the prompt is 4,000 tokens of accreted patches, and nobody can say which line does anything. Every step looked like progress, and every step was inside the noise.

The numbers in this field are smaller than they feel. Anthropic found that clustered standard errors on popular evals "can be over three times as large as naive standard errors" ([Anthropic, "A statistical approach to model evaluations"](https://www.anthropic.com/research/statistical-approach-to-model-evals)). Infrastructure configuration alone moved Terminal-Bench 2.0 scores by 6 percentage points (p < 0.01) ([Anthropic, "Quantifying infrastructure noise in agentic coding evals"](https://www.anthropic.com/engineering/infrastructure-noise)). With 200 samples and 3% observed defects, the 95% interval is about 3% ± 2.4%, too wide to prove a 5% requirement ([Eugene Yan, "Product Evals in Three Simple Steps"](https://eugeneyan.com/writing/product-evals/)). A 3-point "win" on a 200-item eval is, most of the time, nothing at all.

Hill-climbing done properly is the payoff of the whole evals track. [Module 10](../10-evals-fundamentals/README.md) gave you a dataset and graders, and [Module 11](../11-llm-as-judge/README.md) gave you a judge you can trust. This module turns that check into a steering signal: a loop that climbs, a set of rules that refuses to climb on noise, and a gate that stops the next PR from sliding back down. It is the course thesis at its most concrete. **The eval is the verifier, and its error bars decide how much you are allowed to believe it.**

## The distributed-systems anchor

You have done this before as **performance tuning**. You benchmark a service, form a hypothesis from a profile ("allocation in the hot path"), change one thing, re-run the benchmark, and keep the change only if p99 moved by more than run-to-run jitter. You learned the hard way to warm up the JIT, pin CPU frequency, run enough iterations, compare distributions rather than single runs, and distrust a benchmark that only exercises the one code path you just optimized.

Every one of those habits has an analogue here:

| Perf tuning | Hill-climbing an LLM system |
|---|---|
| Benchmark jitter (GC, noisy neighbours) | Sampling nondeterminism, judge variance, API latency, infrastructure noise |
| A/A test before A/B | Noise check: run the baseline N times before round 1 |
| Same machine, same input for A and B | Paired comparison on the same items |
| Correlated requests (one hot tenant) | Clustered items (several alerts from one incident) |
| Microbenchmark that overfits one path | Dev set you've read 40 times; pasted failures in the prompt |
| Perf regression gate in CI | Eval gate on CI lower bounds |
| Cost per request vs latency curve | Accuracy vs cost Pareto frontier over model and effort |
| SLO with error budget | The "march of nines" as the stopping criterion |

**Where the analogy breaks.** A benchmark measures the system itself. An eval measures the system on a *sample* of a task distribution, and you choose that sample. So there is a second source of error that perf work rarely has: the eval can be unrepresentative, or can quietly turn into a copy of your current failures. Your optimizer is also unusual. When an agent does the climbing, it is a capable adversary that will find the cheapest way to raise the number, and that is not always the way you meant. A compiler never rewrote your benchmark harness. A coding agent might.

## Learning goals
- [ ] Run a noise check on a baseline and state the minimum detectable effect before changing anything.
- [ ] Compute naive, clustered, and paired standard errors, and explain when each one applies.
- [ ] Use McNemar, a paired bootstrap, and a sample-size formula to decide how many items and repeats an eval needs.
- [ ] Run a hill-climb with one change per round and an experiment log, keeping or reverting each change by explicit rules.
- [ ] Detect overfitting: dev up and test flat, pasted failures, and adversarially selected eval sets.
- [ ] Route each fix to the cheapest layer that can hold it (prompt, tools, harness, model, effort) and draw the accuracy-vs-cost frontier.
- [ ] Run the model-upgrade drill with an ablation, so you know which harness parts a new model makes dead weight.
- [ ] Decide when automated optimization (DSPy/GEPA, autoresearch-style loops) is safe to turn on, and which guards it needs.
- [ ] Ship a tiered CI eval gate that fails on confidence bounds, not point estimates.
- [ ] Use a reliability target in nines as the stopping criterion, and price the next nine.

## Reading order
1. [01-the-hill-climbing-loop.md](01-the-hill-climbing-loop.md): baseline, then hypothesis, one change, re-run, keep or revert; the experiment log; Karpathy's autoresearch pattern.
2. [02-statistics-that-keep-you-honest.md](02-statistics-that-keep-you-honest.md): noise checks, clustered and paired SEs, McNemar, power, and why the noise check underestimates real-change noise.
3. [03-train-test-discipline-and-overfitting.md](03-train-test-discipline-and-overfitting.md): splits, revert rules, Goodhart, reward hacking in your own loop, and the adversarial-sampling trap.
4. [04-what-to-climb-layers-and-cost.md](04-what-to-climb-layers-and-cost.md): prompt, tools, harness, model, effort; the Pareto frontier; the model-upgrade drill.
5. [05-automated-optimization.md](05-automated-optimization.md): DSPy/GEPA, bounded improve-loops, and autoresearch, with the guards each needs.
6. [06-ci-eval-gates.md](06-ci-eval-gates.md): tiered gates, CI-aware thresholds, and a GitHub Actions workflow.
7. [07-the-march-of-nines.md](07-the-march-of-nines.md): reliability targets as stopping criteria, and what each nine costs to *measure*.
- [examples.md](examples.md), [exercises.md](exercises.md), [references.md](references.md), [code/](code/README.md)

## The running example

Every concept file uses the same system. It is an **incident router**: an LLM reads a production alert and names the on-call team that owns the fix (payments, platform, data-pipeline, database, identity, edge). The eval has 969 alerts from 320 incidents, split by incident into dev and test. We climb it from 67.9% to 89.1% on test, with a full log in [code/runs/demo/experiments.md](code/runs/demo/experiments.md). The log shows:
- a no-op change reverted as noise,
- a change that won big on dev and lost on test, reverted,
- three real fixes at three different layers,
- an effort sweep where `high` wins, `xhigh` buys nothing for 1.65x the cost, and `max` loses.

**Honesty note.** The climb runs offline against a *simulated* model (`code/sim_model.py`), a seeded fake whose response to each lever is known. It does not measure Claude. It is a controlled world, built so you can watch the statistics and the rules work, and so you can rerun everything in seconds. Numbers from it are labelled "simulated" throughout. With `ANTHROPIC_API_KEY` set, the same scripts run against the real API.

## Prerequisites
- [Module 10: Evals fundamentals](../10-evals-fundamentals/README.md): datasets, error analysis, code graders.
- [Module 11: LLM-as-judge](../11-llm-as-judge/README.md): if your grader is a judge, calibrate it first, or you are climbing the judge's biases.
- Helpful: [Module 07: Loops](../07-loops/README.md) (governors and oracles) and [Module 08: Harness engineering](../08-harness-engineering/README.md) (harness changes as a climbable surface).

## Key takeaways
- **Noise check before round 1.** Run the baseline several times and compute the minimum detectable effect. If it is bigger than the smallest change you would act on, add items or repeats before you touch the system.
- **Paired and clustered by default.** Compare variants on the same items with a paired test, and cluster by whatever items share (incident, document, repo). Naive SEs on clustered data can be several times too small.
- **One change per round, and write it down.** Each row in the experiment log has a hypothesis from error analysis, the change, dev and test deltas with CIs, cost, and the decision. Reverted rows are as valuable as kept ones.
- **Dev up and test flat means revert.** Never paste eval failures into the prompt. Split by cluster, not by row. Treat the test set as a decision set you are slowly wearing out.
- **Fix at the cheapest layer.** Try prompt, then tools, then harness, then model and effort. Draw the cost frontier, and test every step on it with a paired comparison.
- **Re-run the drill on every model upgrade.** Re-draw the frontier and ablate each harness component. Scaffolding that helped the old model may be dead weight on the new one.
- **Automate the climb only after doing it by hand,** with a frozen evaluator, a fixed budget, a held-out split, and a leak check.
- **Gate CI on confidence bounds, not point estimates.** Gate on the lower bound for the absolute floor and on a paired regression test against the baseline, and use cheap tiers on every PR with the full eval when prompts change.
