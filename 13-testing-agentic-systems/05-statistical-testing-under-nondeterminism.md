# 05: Statistical testing under nondeterminism

## The idea
A live agent test is a Bernoulli trial. Run it once and you learn almost nothing: a pass is consistent with a 50% agent, and a fail is consistent with a 95% one. So you run it N times, count passes c, and estimate two quantities:

- **pass@k**, the probability that *at least one* of k attempts passes. It measures capability, and it's what matters when a human or a verifier picks the best of k.
- **pass^k**, the probability that *all* k attempts pass. It measures reliability. τ-bench introduced it to evaluate the reliability of agent behavior over multiple trials ([Yao et al.](https://arxiv.org/abs/2406.12045)).

Both use the unbiased combinatorial estimators over n trials with c passes:

```python
pass_at_k  = 1 - comb(n - c, k) / comb(n, k)
pass_hat_k = comb(c, k) / comb(n, k)
```

The second idea is that **a trial has three outcomes, not two**: pass, fail (the agent got it wrong), and infra_error (the environment broke). Infra errors get retried on a fresh environment and reported separately. They never count as agent failures, and agent failures are never retried away.

*Course synthesis:* pass^k is your availability, pass@k is your best case. If an on-call agent handles the same alert class 5 times a week, the number that matters for trust is pass^5, not pass@1.

## Why it matters
Consistency decays fast. Anthropic's evals guide works the arithmetic: at 75% per-trial success, pass^3 is about 42% ([Anthropic, "Demystifying evals"](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)). On τ-bench retail, GPT-4o's pass^8 was under 25% ([Yao et al.](https://arxiv.org/abs/2406.12045)). A team that reports pass@1 of 75% and ships has shipped something that fails at least once in any three uses more often than not.

Infrastructure noise is just as large. On Terminal-Bench 2.0, Anthropic measured a 6-point swing from infrastructure configuration alone (p < 0.01). Infra errors fell from 5.8% at strict 1x resource enforcement to 0.5% uncapped. Anthropic recommends distrusting leaderboard gaps under about 3 points without matched configurations, and running evals at different times of day and on different days ([Anthropic, infra noise](https://www.anthropic.com/engineering/infrastructure-noise)). If your harness counts an OOM as an agent failure, you'll be tuning the prompt against your container limits.

## How it works

### 1. Choose N from the decision you need to make
The Wilson interval on a pass rate is honest at the edges, unlike mean ± 1.96·SE, which collapses to zero width at 0/n and n/n. From `flaky.wilson`:

| Observed | 95% Wilson interval | What it lets you claim |
|---|---|---|
| 20/20 | [0.84, 1.00] | "At least ~84%", **not** "100%" |
| 35/40 | [0.74, 0.95] | Can't distinguish 80% from 90% |
| 0/20 | [0.00, 0.16] | "Broken": treat it as a deterministic regression |

Rule of thumb: **N = 10 for a per-PR smoke tier, N = 30–50 for a nightly reliability tier.** To compare two variants you need the paired tests and power analysis from [Module 12](../12-hill-climbing/README.md). Don't eyeball two pass rates.

### 2. Classify each trial at the source
```python
def trial(seed):
    world = OpsWorld(seed=seed, faults=faults)
    run = run_agent(client, world, TASK)
    if run.stop_reason == "infra_error":          # raised by the environment, not judged
        return Trial(seed, "infra_error")
    bad = failed(evaluate(run, world, "payments", "v2.4.0"))
    return Trial(seed, "fail" if bad else "pass", bad, transition=first_failure(run, world, ...))
```
The classification has to come from where the error was raised (`InfraError` in the world, a container exit code, a harness timeout), not from reading the transcript afterwards.

### 3. Retry infra on a fresh environment, never retry model failures
```python
def run_with_infra_retry(trial_fn, seed, max_infra_retries=2):
    for attempt in range(max_infra_retries + 1):
        t = trial_fn(seed + 1_000_000 * attempt)      # new environment, same task
        if t.status != "infra_error":
            return t
    return t
```
This is the same rule as retrying idempotent requests on a 503 and not on a 400.

### 4. Turn the numbers into a verdict
`flaky.verdict()` encodes a CI policy (*course synthesis*, so tune the thresholds):

| Condition | Verdict | Action |
|---|---|---|
| infra rate > budget (5%) | `ENVIRONMENT` | Fix the harness. The model results are not interpretable yet |
| c = n | `STABLE` | Keep in the blocking gate |
| c = 0 | `BROKEN` | Regression. Block and bisect |
| pass^k_gate < threshold | `FLAKY` | Quarantine from the blocking gate, run nightly, file a *behavior* bug with the transition matrix |
| otherwise | `FLAKY BUT WITHIN BUDGET` | Keep it, and track the trend |

**Quarantining is not deleting.** A quarantined agent test keeps running in the nightly tier, with an owner and an exit criterion: back to STABLE, or pass^3 ≥ 0.8 for two weeks. The rule is the same as for flaky integration tests. It matters more here, because agent flakiness *is* the product's reliability.

### 5. Report per-task, then average
τ-bench averages pass^k over tasks: compute c and n per task, then take the mean of `comb(c,k)/comb(n,k)`. Pooling all trials across tasks overstates reliability when a few tasks always pass and a few always fail. Report the worst tasks next to the average.

## Worked example: the flakiness report
`python flaky.py` runs the deploy task 40 times against a world with 15% transient errors, 15% lost acks and 2% infra crashes. The noisy policy occasionally skips verification (10%), stops early (5%), or mints new request IDs on retry (10%).

**Bad analysis: one pass, no infra separation.**
```text
$ run the agent once -> PASS     # ship it
```
or, at best, a run counted as pass/fail only:
```text
trials: 40  pass: 32  fail: 8     # 3 of those "fails" were API-server crashes
```

**Good analysis.** Without infra retry first, then with it:
```text
== without infra retry ==
trials: 40  pass: 32  fail: 5  infra_error (excluded): 3
pass rate: 32/37  95% CI [0.72, 0.94]
pass^k: k=1: 0.86  k=3: 0.64  k=5: 0.46
verdict: ENVIRONMENT: infra error rate 8% > budget 5%; fix the harness, not the prompt

== with infra retry on a fresh environment ==
trials: 40  pass: 35  fail: 5  infra_error (excluded): 0
pass rate: 35/40  95% CI [0.74, 0.95]
pass@k: k=1: 0.88  k=3: 1.00  k=5: 1.00
pass^k: k=1: 0.88  k=3: 0.66  k=5: 0.49
failing checks: claim_matches_state x2, outcome:prod_at_version x2,
                staging_verified_before_prod x2, retry_reuses_request_id x1
verdict: FLAKY: pass^3 below 0.80; quarantine from the blocking gate and file a model-behavior bug
```

Three things to read off this:
1. **The model-failure count didn't change (5 → 5).** Infra retry recovered the 3 crashed trials, all of which passed on a fresh environment, and hid no agent failure. `test_end_to_end_report_on_noisy_agent` asserts `with_retry.fails == no_retry.fails`.
2. **pass@3 is 1.00 and pass^3 is 0.66.** As a best-of-3 tool, this agent looks perfect. As an unattended deployer, it fails at least once in every three tries a third of the time.
3. **The bug rate and the failure rate differ.** `new_id_on_retry` was drawn in about 10% of runs, yet `retry_reuses_request_id` failed only once, because the bug only shows when a retry actually happens. Rare-path bugs need fault rates high enough to exercise the path. That's why the property tests in [06](06-property-based-and-metamorphic-testing.md) search over fault rates up to 40%.

## Pitfalls
- **Reporting pass@k as reliability.** *Detect:* any dashboard showing "pass@5" for an unattended agent. Ask whether a human really picks the best of 5.
- **Infra errors in the denominator.** *Detect:* failures whose transcript ends mid-tool-call, or with a harness timeout or exit code 137. Count them separately.
- **Retrying until green.** `pytest --reruns 3` on an agent test turns pass^k into pass@k without anyone noticing. *Detect:* grep CI configs for rerun flags on agent suites.
- **Correlated trials.** Running all N trials concurrently on one box or at one time of day correlates infra failures, and sharing a workspace correlates agent failures. *Detect:* infra failures that cluster by timestamp or host. Spread trials out and isolate them ([04](04-record-replay-and-sandboxes.md)).
- **Too-small N for the claim.** "It went from 8/10 to 10/10" is not a result. *Detect:* overlapping Wilson intervals. Use the paired analysis in Module 12.
- **A flakiness budget nobody owns.** *Detect:* quarantined tests older than a month with no linked issue.

## In your day job
- Change your agent eval harness to emit `pass | fail | infra_error` per trial, with infra classified where the error is raised.
- Add pass^k (k = 3 or the number of times a week the agent sees that task class) to the eval report, next to pass@1, with Wilson intervals.
- Set an infra-error budget (5% is a reasonable start). When it's exceeded, the eval run is invalid, not a regression.
- Write a quarantine policy for agent tests: who owns each one, which tier it runs in, and what gets it back into the gate.
