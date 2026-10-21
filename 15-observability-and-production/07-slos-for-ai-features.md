# 07: SLOs for AI features

## The idea
An SLO for an AI feature has the same structure as any other: an SLI (good events ÷ valid events), an objective, a window, an error budget, and a policy for when the budget runs out. The difference is what counts as a **good event**. "Returned 200 within 2 s" is necessary but tells you nothing about whether the answer was right. An AI feature needs at least one **quality SLI**, and usually one **cost SLI**, alongside availability and latency, all with error budgets and alerting rules.

Define the good event as a conjunction wherever you can:

> A request is **good** if it succeeded, had a first token within 1.5 s, passed every code check (schema, grounding, secret scan), and was not blocked by a guardrail.

The judge-based SLI stays separate, because it is sampled and has its own error rate ([02](02-online-evals-and-feedback.md)).

## Why it matters
Karpathy's "march of nines" is the right frame: "When you get a demo and something works 90% of the time, that's just the first nine", and "every single nine is a constant amount of work" ([Dwarkesh Podcast, 2025-10-17](https://www.dwarkesh.com/p/andrej-karpathy)). If each additional nine costs as much as the last, you need a number to decide whether the next one is worth buying.

Reliability across repeated attempts also compounds. Anthropic's evals guidance points out that at 75% per-trial success, the probability of succeeding on all of three trials (pass^3) is about 42% ([Anthropic, "Demystifying evals for AI agents"](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)). For a customer-facing agent that users invoke repeatedly, per-trial quality is not the number they experience. Their experience is closer to pass^k, the availability-style number ([Module 10](../10-evals-fundamentals/README.md) covers pass@k vs pass^k).

Without quality SLOs, two things happen. Quality regressions are found by users ([03](03-drift.md)). And nobody can say no to a cost-saving change, such as a cheaper model or lower effort, because there is no budget to spend.

## How it works

### The SLI menu
| SLI | Good event | Measured on | Typical objective (start here, then tune) |
|---|---|---|---|
| Availability | non-error response, including after retries and fallback | 100% | 99.9% |
| TTFT | first token < 1.5 s (streaming) | 100% | 99% |
| End-to-end latency | complete < 8 s | 100% | 99% |
| **Code-check quality** | all deterministic checks pass | 100% | 98–99.5%, from your current baseline |
| **Judge quality** | judge PASS, corrected for TPR/TNR | 5–20% sample | Baseline minus your non-inferiority margin |
| **Task outcome** | the *environment* says the task succeeded (ticket resolved, PR merged, tests green) | 100% where observable | Feature-specific |
| Safety / guardrail | no secret or PII in output; false-block rate under X | 100% / review sample | 100% for secret leaks (any breach pages) |
| **Cost** | cost per successful task ≤ budget | 100% | p95 under budget |
| **Cache hit rate** | `cache_read / (cache_read + cache_write)` | 100% | ≥ 85% for stable-prefix features |

"Task outcome" is the strongest SLI wherever you can observe it. Anthropic's eval guidance puts it as grading "what the agent produced, not the path it took" ([Anthropic](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)). In production that means reading the end state: whether the reservation exists in the DB, not whether the agent said it booked one.

### Alert on burn rate, not on point estimates
Use the multiwindow, multi-burn-rate scheme from the [Google SRE Workbook](https://sre.google/workbook/alerting-on-slos/). For a 30-day window:

| Budget consumed | Long window | Short window | Burn rate | Action |
|---|---|---|---|---|
| 2% | 1 h | 5 min | 14.4 | Page |
| 5% | 6 h | 30 min | 6 | Page |
| 10% | 3 d | 6 h | 1 | Ticket |

The long window establishes significance. The short window (1/12 of the long one) confirms the problem is still happening, so the alert clears quickly after a rollback. `online_eval.burn_rate_alerts()` implements this with a `min_n` guard.

**Two AI-specific adjustments:**
1. **Low objectives cap the burn rate.** With a 98% objective the maximum possible burn is 50x, and a regression to 8% bad is only 4x, which a 14.4x page threshold will never catch. Quality SLOs often sit at 95–99%, so either tighten the objective on code-check SLIs (which can be near 100%) or lower the page thresholds and accept a slower page.
2. **Sampled SLIs need longer windows.** A 10% judge sample at 300 requests per hour gives 30 judgements per hour, which is too few for a 5-minute short window. Use the code-check SLIs for fast paging, and use the judge SLI for the 6 h and 3 d tiers only.

### Error-budget policy
Write it down in advance, as you would for any service:
- **Budget remaining:** prompt, model and cost-saving changes ship through the normal gates ([05](05-changes-as-deploys.md)).
- **Budget exhausted:** freeze all non-fix prompt and model changes for the feature. The next deploy must be a fix with an eval case reproducing the failure.
- **Cost SLO exhausted:** freeze changes that add tokens (longer prompts, higher effort, more retrieval) until the cost SLI recovers.

The policy is what turns "should we switch to the cheaper model?" from a debate into arithmetic. If the switch costs 0.8 points of the quality SLI and the budget has 1.5 points left this month, ship it. If it has 0.3, don't.

## Worked example
**Bad version:**
```yaml
slo: alert-summarizer
objective: 99.9% availability
alert: error_rate > 1% for 5m
```
This pages on provider outages, which you can do nothing about, and stays silent while 25% of summaries name the wrong service.

**Good version**, the SLO doc that lives in the feature's repo:
```yaml
feature: alert-summarizer
window: 30d
slis:
  availability:   {good: "status=ok after retries/fallback",        objective: 0.999}
  ttft:           {good: "time_to_first_chunk < 1.5s",              objective: 0.99}
  quality_code:   {good: "schema_valid AND grounded_service AND no_secret_in_output", objective: 0.99}
  quality_judge:  {good: "faithful-judge@haiku-5-5/r4 PASS (corrected; TPR .95 TNR .95)",
                   sample: "sha256(trace_id) 10%", objective: 0.95, alert_tiers: [6h, 3d]}
  cost:           {good: "cost_usd <= 0.009",                        objective: 0.95}
  cache_hit_rate: {threshold: ">= 0.85 over 1h",                     action: ticket}
  secret_leak:    {threshold: "== 0",                                action: page-immediately}
policy:
  budget_exhausted: "freeze non-fix prompt/model changes; next deploy needs a reproducing eval case"
owner: payments-oncall
```

The burn-rate alerts doing their job. In this scenario a bad prompt deploy makes 25% of outputs fail `quality_code` for 40 minutes, against a 0.5% baseline. The output is real, from `burn_rate_alerts` on that synthetic event stream:

```text
page   quality_code burning 16.9x over 1h (short 23.3x), objective 0.99
ticket quality_code burning 3.2x over 72h (short 3.2x), objective 0.99

# ten minutes after rollback
ticket quality_code burning 3.2x over 72h (short 3.2x), objective 0.99
```

The page fires once the hour-long window crosses 14.4x, and **clears ten minutes after the rollback** because the 5-minute window is clean again. The ticket stays open, which is correct: over the 72-hour window the budget is still burning at more than 1x, and the incident deserves a postmortem. The same 25% failure lasting only 20 minutes produces 8.6x over the hour and pages nobody. That is also correct for a 99% SLO, because it consumed about 1% of the monthly budget.

## Pitfalls
- **Quality SLIs measured only offline.** An eval suite score is not an SLI. It measures last week's inputs on a test config. *Detect:* the SLO doc names no production data source.
- **Composite SLIs that hide the cause.** "Good = all checks pass" pages quickly, but the alert must name which component failed. Emit per-check SLIs as well, and put the breakdown in the alert text.
- **Judge-only quality SLOs.** If the judge drifts, the SLO drifts with it ([03](03-drift.md)). Pair every judge SLI with at least one code-check SLI on the same failure mode where one exists.
- **Objectives set from aspiration.** "99.9% correct" on a feature currently at 96% puts you permanently out of budget, and the policy will be ignored. Start from the measured baseline and tighten it.
- **Ignoring cost as an SLO.** A cost regression is a reliability problem for the business. The cache incident in [examples.md](examples.md) would have paged on a cost SLI hours before finance noticed.
- **Paging on provider outages you cannot mitigate.** Page on *your* availability after fallback. Track provider availability as a dependency SLI on a dashboard.

## In your day job
- Write the SLO doc above for one LLM feature this week. Start with code-check quality and cost, which need no judge.
- Wire the burn-rate tiers to your existing alerting (Prometheus recording rules or your vendor's SLO feature). The math in `online_eval.py` is about 20 lines and maps directly.
- Agree the error-budget policy with your product owner *before* the next "can we use a cheaper model?" conversation.
- Review the SLOs quarterly. As the baseline improves, raise the objectives, and drop SLIs that never fire and never informed a decision.
