# 15: Observability & production
> After this module you can run an LLM feature the way you run any other tier-1 service. You will have traces in a standard schema, quality SLIs with error budgets, online evals that page someone, cost and latency budgets you enforce in code, and prompt or model changes that ship through canaries and roll back cleanly.

## Why this matters
An LLM feature can return HTTP 200 at p99 300 ms and still be broken. The output may be wrong, fabricated, unsafe or quietly worse than last week, and none of your existing dashboards will show it. Anthropic's September 2025 postmortem describes three overlapping infrastructure bugs that degraded Claude's output for weeks. Its standard evaluations did not catch them, partly because "Claude often recovers well from isolated mistakes", and at the worst hour 16% of Sonnet 4 requests were affected ([Anthropic, "A postmortem of three recent issues"](https://www.anthropic.com/engineering/a-postmortem-of-three-recent-issues)). Availability monitoring would have shown green the whole time.

The other failures are just as quiet. One prompt edit can invalidate your prompt cache and multiply input cost several times over, with no change in quality to warn you. A provider can ship a model update that passes your offline suite while expert users feel something is off. In April 2025 OpenAI rolled back a GPT-4o update even though offline evals and A/B tests looked fine, because the model had turned sycophantic. Some expert testers had said the behaviour "felt" slightly off, and the team shipped anyway ([OpenAI, "Expanding on what we missed with sycophancy"](https://openai.com/index/expanding-on-sycophancy/)). Long-running agents add a further problem: deploying a new harness kills every run that is in flight unless you designed for it.

None of this needs new SRE principles. It does need new SLIs, new sampling strategies, a different idea of what a "deploy" is, and an honest account of which checks work on nondeterministic output.

## The distributed-systems anchor
**SRE for a dependency whose correctness you cannot assert with an equality check.** You already know SLOs, error budgets, burn-rate alerts, canaries, soak periods, rainbow (blue/green) deploys and idempotent retries. All of them carry over, and the code in this module uses them almost unchanged.

The analogy breaks in three places:

| SRE assumption | Where it breaks for LLM features |
|---|---|
| A "bad event" is cheap to detect (5xx, timeout) | Detecting a bad answer costs money (a judge call) or a human. You **sample**, and the detector has its own error rate, so the SLI must be corrected for it |
| A deploy is a code change you control | Prompt edits, model version bumps, judge upgrades and provider-side changes are all deploys. Some of them are not yours to schedule |
| Requests are independent | Agent runs are long, stateful sessions. A deploy can land mid-run, and a retry can repeat a side effect |

## Learning goals
- [ ] Emit LLM spans using OpenTelemetry GenAI attribute names, and decide which content attributes to capture, hash or drop
- [ ] Build an online eval pipeline: code checks on all traffic, a calibrated judge on a consistent-hash sample, and a corrected pass rate with confidence intervals
- [ ] Name the three kinds of drift (input, model, judge) and set up a detector for each
- [ ] Enforce a cost budget with admission control, route between cheap and strong models with a cascade, and treat prompt-cache hit rate as an SLO
- [ ] Ship a prompt or model change as a canary with a non-inferiority decision rule, a soak period and a one-step rollback
- [ ] Design agent infrastructure that survives a harness crash and a deploy mid-run: session logs, `wake(sessionId)`, sandboxes as cattle, rainbow deploys
- [ ] Write SLOs for an AI feature that include quality SLIs, and alert on burn rate rather than point estimates

## Reading order
1. [01-tracing-for-llm-systems](01-tracing-for-llm-systems.md): the span data model, OTel GenAI conventions, and what is sensitive
2. [02-online-evals-and-feedback](02-online-evals-and-feedback.md): sampling production into checks and judges, guardrail metrics, feedback signals, A/B tests
3. [03-drift](03-drift.md): input drift, model drift, judge drift, and the sycophancy lesson
4. [04-cost-and-latency-engineering](04-cost-and-latency-engineering.md): budgets, routing, caching, batching, rate limits, timeouts, fallbacks
5. [05-changes-as-deploys](05-changes-as-deploys.md): versioned configs, canaries, soak, rollback, and the statistics behind a canary verdict
6. [06-durable-agent-infrastructure](06-durable-agent-infrastructure.md): session logs, resumability, cattle sandboxes, rainbow deploys
7. [07-slos-for-ai-features](07-slos-for-ai-features.md): quality SLIs, error budgets and burn-rate alerts
- [examples.md](examples.md): a dashboard spec, a model-switch rollout plan, a cache-miss cost incident, and a judge-drift scare
- [exercises.md](exercises.md): seven hands-on exercises
- [code/](code/): `otel_like.py`, `online_eval.py`, `router.py`, `canary.py`, `cache_incident.py`, with tests
- [references.md](references.md)

## Prerequisites
- [10-evals-fundamentals](../10-evals-fundamentals/README.md): trace-first instrumentation and error analysis. This module is that idea running in production.
- [11-llm-as-judge](../11-llm-as-judge/README.md): binary rubrics and TPR/TNR calibration. Online judges are useless without them.
- [12-hill-climbing](../12-hill-climbing/README.md): error bars, paired tests and the model-upgrade drill. Canary analysis reuses the same statistics.
- Helpful: [01-llms-for-systems-engineers](../01-llms-for-systems-engineers/README.md) on prompt caching, and [06-agent-architectures](../06-agent-architectures/README.md) on durable state.

## Key takeaways
- **Availability SLOs are necessary and nowhere near sufficient.** Every LLM feature needs at least one quality SLI, measured on production traffic, with an error budget.
- **Run code checks on 100% of traffic and judges on a consistent-hash sample.** Report the judge's pass rate corrected for its measured TPR/TNR, with a confidence interval. Never report the raw rate as fact.
- **Prompt edits, model bumps, judge upgrades and SDK upgrades are all deploys.** Each one gets versioning, a canary, a soak period, and rollback by flipping a pointer.
- **A canary passes on non-inferiority, not on "no significant difference".** Pick the margin before you start. Prefer paired shadow replay, since pairing needs far fewer samples.
- **Prompt-cache hit rate is a cost SLO.** A timestamp at the top of a system prompt can multiply input cost several times over, and quality dashboards will not notice.
- **Budgets are admission control.** Reserve the worst case before the call, settle the actual cost after, and degrade to a cheaper tier before you refuse a request.
- **Agents need the infrastructure of long-lived jobs:** an append-only session log outside the harness, resume from the last event, disposable sandboxes, and rainbow deploys so runs in flight finish on the version they started with.
- **Qualitative alarms from experts block a launch** until someone writes an eval that explains them. Aggregate metrics only cover what you thought to measure.
