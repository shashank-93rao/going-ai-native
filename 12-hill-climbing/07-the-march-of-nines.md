# 07: The march of nines

## The idea

A hill-climb needs a stopping criterion, and "until it stops going up" is not one. The right criterion is a **reliability target**: a statement in nines, per task family, over a defined unit of work, that you commit to *before* round 1. "Test-split lower 95% bound ≥ 90% on alert routing, and ≥ 97% on easy alerts" is a stopping criterion. "Make it better" is a budget leak.

Karpathy's framing is the march of nines: "Every single nine is a constant amount of work," and "When you get a demo and something works 90% of the time, that's just the first nine" ([Dwarkesh Podcast, "AGI is still a decade away"](https://www.dwarkesh.com/p/andrej-karpathy), 2025-10-17). He describes the gap between a demo and a product as "very large... the demo is very easy, but the product is very hard." For you this is SLO thinking applied to correctness. Each nine cuts the error budget by 10x. Each one usually needs a different *kind* of fix, not more of the last one. And, the part people forget, each one needs a roughly 10x bigger eval to even *show* you hit it.

## Why it matters

Without a target, two things happen. You stop too early: 89% looks great after starting at 68%, but on-call gets 110 misroutes per 1,000 pages. Or you never stop, spending rounds on 0.5-point gains you cannot measure. The router climb in this module ended at 89.1% on test. Whether that is "done" depends entirely on a number nobody wrote down.

The unit of work matters too. Anthropic's eval guidance distinguishes pass@k from pass^k: at 75% per-trial success, the chance all three of three trials succeed is about 42% ([Anthropic, "Demystifying evals for AI agents"](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)). An incident with five alerts that must *all* route correctly, at 90% per alert, succeeds about 59% of the time (0.9⁵) if errors were independent. Within an incident they are correlated, so measure it rather than compute it. A per-alert nine and a per-incident nine are different targets.

## How it works

### Write the target like an SLO

```yaml
# code/data/targets.yaml
system: incident-router
unit: alert                     # also track: incident (all alerts in it routed correctly)
metric: routed_to_owning_team
measured_on: test split, clustered by incident, 3 repeats
targets:
  overall:      {lower_95_bound: 0.90}
  easy:         {lower_95_bound: 0.97}
  lookup:       {lower_95_bound: 0.95}   # has a tool; should be near-deterministic
cost_ceiling_per_1k: 10.00
stop_when: all targets met, OR 3 consecutive flat rounds (then re-scope), OR budget spent
```

The target is on the **lower bound**, like the CI gate in concept 06, so "met" means "met with confidence".

### What each nine costs to measure

To *demonstrate* accuracy ≥ target when the true error is half the allowed error, with a 95% bound and independent items (`stats.py`, normal approximation):

| target | true accuracy | items needed (independent) | with design effect ~1.5 (the router's) | zero-failure shortcut: n with 0 errors |
|---|---|---|---|---|
| 90% | 95% | 73 | ~110 | 31 |
| 99% | 99.5% | 765 | ~1,150 | 300 |
| 99.9% | 99.95% | 7,680 | ~11,500 | 3,000 |

The last column is the "rule of three": with zero failures in n trials, the one-sided 95% upper bound on the failure rate is about 3/n. Each nine multiplies the eval by roughly 10. The router's 969-alert eval can certify about one nine, comfortably. A 99.9% claim on it would be a statement about the model's confidence, not yours. Before you promise a nine, check that you can afford the eval that proves it, labelling cost included.

### What each nine costs to build

The kind of fix changes as you climb. A rough map, from this module's climb and the course's other modules (*course synthesis*):

| From → to | Typical source of errors | Typical fix | Router example |
|---|---|---|---|
| ~70% → 90% | Spec ambiguity, missing rules, missing knowledge | Prompt and tool layer (concepts 01, 04) | Queue definitions, tie-break, `lookup_owner` |
| 90% → 99% | Long tail of genuinely hard inputs; model reasoning limits; format failures | Effort/model; harness mechanisms (validators, retries, structured output); **abstention** | Effort `high`; strict parse plus retry; "unknown" goes to a human triage queue |
| 99% → 99.9% | Rare input classes; upstream data quality; eval label errors | Architecture: cascades, ensembles or verifier voting, deterministic pre-routing for known patterns, better labels | Regex pre-router for alerts whose service is in the catalog; model only for the rest |

The middle row has a move that is easy to miss: **abstention converts errors into escalations.** If the router may answer `team: unknown` (which goes to a human triage queue), score correct, abstain, and wrong separately, as [Module 10](../10-evals-fundamentals/README.md) teaches. Then set the target on *wrong* answers, with a separate budget for abstentions. A misroute pages the wrong person at 3 a.m. An abstention adds a minute of triage. They do not cost the same, so do not count them the same.

### Stopping rules

1. **All targets met on the test lower bound:** stop. Run the lockbox once. Ship behind the CI gate.
2. **Three flat rounds:** stop proposing. Bucket the remaining failures by cause (concept 01, step 8). If the residue is label noise or ambiguous tasks, fix the eval. If it is a capability ceiling, change the *kind* of fix (go down the table above), or re-scope the target.
3. **Budget spent:** stop and report the gap to target with CIs, plus the price of the next nine as an estimate. That is a planning input, not a failure.

## Worked example

### Bad: "keep climbing"

```text
wk1  67.9 -> 89.1 on test. great progress!
wk2  tried 6 more prompt tweaks, +0.4, -0.8, +1.1 (n.s.), +0.2 ... reverted most
wk3  "we're at 89-90%, let's keep going"
```

There was no target, so there was no stop. Week 2 spent six rounds on effects far below the eval's MDE (concept 02). Week 3 is a sunk-cost loop.

### Good: target, gap, and price of the next nine

Before round 1, the team wrote the `targets.yaml` above. After the canonical climb (simulated numbers from `code/runs/demo/experiments.md`):

```text
overall test accuracy   89.1 [86.6, 91.6]   target lower bound >= 90.0   NOT MET (gap ~3.4 pts on the bound)
per-family (dev, best)  ambiguous 87  easy 90  lookup 91  reasoning 88  tiebreak 88
cost                    $8.58 / 1k alerts                          ceiling 10.00   OK
```

Reading it as an SLO review:

- **The overall miss is ~3.4 points on the lower bound.** The interval is 5 points wide at this eval size, so a system whose true accuracy is 91% would still miss the bound. Part of the gap is the eval, not the router. To check a true 92% against a 90% bound, you need about 700 independent alerts, or about 1,060 at the router's design effect, on test alone. The current test split has 478.
- **"easy" at 90% is suspicious.** These alerts name the service outright. A ceiling there usually means label noise or a parse failure, not a capability gap. Read those failures first. They are the cheapest points left. (In the simulator, easy-alert errors are random noise by construction. In a real system, they are where eval bugs hide.)
- **The next fixes come from the next row of the table,** not more prompt text. Add a deterministic pre-router for alerts that name a cataloged service. Add a `team: unknown` abstention path for multi-signal alerts where the model's answers disagree across repeats.
- **Concept 04's frontier says opus/high is +2.0 [0.5, 3.4] over sonnet/high** at about 2x the API cost. Under the misroute cost model that is clearly worth it, and it is the cheapest single step toward the target.

The decision memo writes itself: one eval expansion (more test incidents), one model step, and two architecture changes, each to be judged by the same loop and gated by the same CI check.

## Pitfalls

| Pitfall | How to detect it |
|---|---|
| No written target before round 1 | The stop decision is made in a meeting, by mood |
| Target on the point estimate | "We hit 90%" with a lower bound at 87% |
| Promising a nine the eval cannot measure | Target 99.9% on a 1,000-item eval; compare with the table above |
| One global number | Per-family accuracy hidden; a 70% family is averaged away by easy items |
| Per-item target for a per-session product | Users experience incidents or sessions; measure pass^k or session success |
| Counting abstentions as errors | No abstain path, so every uncertain case is a coin flip that pages someone |
| More prompt text for the second nine | Kept rows late in the climb are all prompt sections, each adding ~1 point within noise |

## In your day job
- Add a targets file next to every eval: unit, metric, per-family lower-bound targets, cost ceiling, stop rules. Review it the way you review an SLO.
- Before you agree to a reliability number, run the sample-size math, and include labelling cost in the estimate for the next nine.
- Give LLM components an explicit abstain path and score it separately. It is the cheapest way to buy a nine on *wrong* answers.
- When the climb stalls, switch fix types (prompt to mechanism to architecture) rather than trying harder at the same layer.
