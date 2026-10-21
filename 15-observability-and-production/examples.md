# Examples

Four scenarios from running one LLM feature in production. The feature is the **alert summarizer**: a PagerDuty-style alert plus a log excerpt goes in, and a JSON triage note `{service, severity, summary, runbook}` comes out and is posted to the incident channel. It serves about 1M requests a day across a large engineering org, on `claude-sonnet-5-5` with a 6,000-token stable prefix.

---

## 1. A dashboard spec for an LLM feature

**Situation.** The feature has been live for two months. The only dashboard is the service template: RPS, 5xx rate, p99 latency. All three have been green throughout two user-reported quality regressions.

**Naive approach and what happens.** Someone adds a "token usage" panel (sum of `input_tokens`) and an "avg judge score" panel fed by a nightly job. The token panel undercounts by roughly 4x, because Anthropic's `input_tokens` excludes cached tokens. The judge panel shows 8.7/10 every day, regressions included, so it gets ignored.

**AI-native approach.**

1. **Start from questions on-call has to answer**, not from available metrics. Is it up? Is it right? Is it affordable? Did something change?
2. **Write the spec as a reviewed file** (`dashboards/alert-summarizer.yaml`) so changes are diffable:

```yaml
dashboard: alert-summarizer
annotations: [deploys.prompt_version, deploys.model, deploys.harness, deploys.judge_id, provider.status]
default_slice: gen_ai.prompt.version          # every quality and cost panel splits by config version
rows:
  - name: Golden signals
    panels:
      - {title: Requests/min,              q: "count(span: chat *) by 1m"}
      - {title: Availability after fallback, q: "ratio(root.status=ok)", slo: 0.999}
      - {title: TTFT p50/p95/p99,          q: "pXX(gen_ai.response.time_to_first_chunk)", slo: "p99<1.5s"}
      - {title: 429 / 529 / fallback rate, q: "rate(error.type in [429,529]); rate(app.fell_back)"}
  - name: Quality (100% code checks)
    panels:
      - {title: schema_valid,        q: "online_eval.schema_valid",        show: [value, wilson_ci, n], slo: 0.99}
      - {title: grounded_service,    q: "online_eval.grounded_service",    show: [value, wilson_ci, n]}
      - {title: no_secret_in_output, q: "online_eval.no_secret_in_output", alert: "any failure pages"}
      - {title: Error budget remaining (quality_code, 30d), q: "slo.quality_code.budget_remaining"}
  - name: Quality (sampled judge)
    panels:
      - {title: faithful (corrected), q: "online_eval.judge_faithful", show: [value, ci, raw, n],
         note: "judge faithful-judge@haiku-5-5/r4, TPR .95 TNR .95 on anchor set 2026-10-01"}
      - {title: Judge anchor-set TPR/TNR (weekly), q: "judge_calibration.{tpr,tnr}"}
  - name: User signals
    panels:
      - {title: Thumbs-down per 1k sessions, q: "rate(feedback=-1)*1000"}
      - {title: Negative follow-up rate,     q: "online_eval.no_negative_followup"}
      - {title: Review queue depth / converted to eval cases, q: "review_queue.{open,converted}"}
  - name: Cost
    panels:
      - {title: Cost per request p50/p95, q: "pXX(cost_usd)", slo: "p95 <= $0.009"}
      - {title: Spend today vs budget,    q: "sum(cost_usd) by 1d; budget.limit"}
      - {title: Prefix cache hit rate,    q: "sum(cache_read)/sum(cache_read+cache_write)", slo: ">=0.85"}
      - {title: Distinct system-prompt hashes per hour, q: "count_distinct(app.system.sha256) by 1h", expect: "<= live config versions"}
      - {title: Tokens per request by type, q: "avg(gen_ai.usage.{input,cache_read.input,cache_write.input,output}_tokens)"}
      - {title: Escalation rate (cascade), q: "rate(app.escalated)"}
  - name: Drift
    panels:
      - {title: Response models seen,       q: "count by gen_ai.response.model", alert: "new value"}
      - {title: Alert-source PSI vs 4w baseline, q: "psi(app.input_source)", warn: 0.1, alert: 0.25}
      - {title: Unseen-source share,        q: "ratio(app.input_source='other')"}
      - {title: Hourly probe suite (paired vs last-known-good), q: "probe.mcnemar_p; probe.regressions"}
```

3. **Every quality number shows n and an interval.** Every judge number shows the raw rate next to the corrected one. Every panel splits by config version by default.
4. **Review the dashboard against the last two incidents.** For each one, which panel would have moved first? If none, add one.

**What to check.**
- For each past incident, a panel exists that would have moved within an hour. The two quality regressions show up on `grounded_service` sliced by version, and the cost incident in scenario 3 shows up on the cache hit rate and the distinct-hash count.
- Token panels include all four counters.
- Every number with a denominator also displays that denominator.

---

## 2. A rollout plan for switching models

**Situation.** Finance asks whether the summarizer can move from `claude-sonnet-5-5` to `claude-haiku-5-5`. At list prices, Haiku 5.5's input, cache and output rates are 1/20th of Sonnet 5.5's ([pricing, checked 2026-10-19](https://platform.claude.com/docs/en/about-claude/pricing)).

**Naive approach and what happens.** Someone runs the 300-case offline suite once on Haiku, sees 96.0% against Sonnet's 97.3%, calls it "basically the same", and flips the model string on Friday. On Monday, `grounded_service` is down 4 points on Kubernetes alerts (a slice holding 8% of the suite), and the on-call channel is full of wrong service names. The rollback takes a code deploy.

**AI-native approach: a written plan, reviewed like an RFC.**

```markdown
# Rollout: alert-summarizer v16 (model: claude-haiku-5-5), parent v15 (claude-sonnet-5-5)
Owner: @alert-summarizer-owner   Approver: payments-oncall lead   Rollback: `flagctl set alert-summarizer.current v15`

## Success criteria (fixed before any data is seen)
- quality_code: non-inferior to v15 within 1.0 pt (one-sided 95% bound), overall AND per input source
- judge_faithful (corrected): non-inferior within 2.0 pts
- secret_leak: zero. cost p95 <= $0.002. TTFT p99 <= 1.5 s

## Gates
1. Offline: regression suite x3 runs per config, report mean and CI per slice. Effort sweep low/medium on Haiku.
2. Harness ablation: re-test prompt lines that exist for Sonnet-specific failure modes; drop any that do not help Haiku.
3. Shadow replay: 2,000 sampled production inputs from last week through v15 and v16. Exact McNemar per slice.
   Expect ~1,500 needed per arm for a 2-pt margin unpaired; paired needs fewer, but we take 2,000 for slice power.
4. Canary: 1% (24 h) -> 5% (48 h, includes a weekday peak) -> 25% (72 h) -> 100%.
   Session-level hash routing. Decide with canary.decide(margin=0.01, looks=3).
5. Kill switches (automatic rollback): any secret leak; quality_code burn > 14.4x on 1h/5m; fallback rate > 2%.

## Known risks
- Cold cache: assume caches are not shared across models, so expect a cost and TTFT bump in the first minutes of each canary step.
- Haiku 5.5 long-prompt pricing is higher above 100k tokens; our p99 prompt is 11k, so it does not apply. Verify.
- Judge is haiku-5-5. Judging Haiku outputs with a Haiku judge risks correlated blind spots, so switch the judge to
  sonnet-5-5 for this rollout ONLY after re-calibrating it on the anchor set, one week BEFORE the canary.

## Decision record
(filled in at each gate with the canary.decide() output and a link to the run)
```

What the gates produced (illustrative numbers):
- Offline: overall −0.9 points, but the k8s slice was −4.1 ± 2.0. Gate 2 found that the k8s examples were present but Haiku ignored the `labels.app` instruction placed early in the prompt. Moving it next to the examples recovered the slice, and that became v16.1.
- Shadow replay on v16.1: 28 regressions against 22 fixes across 2,000 pairs. `decide_paired(pairs, margin=0.01)` gives McNemar one-sided p = 0.24 and a lower bound of −0.88 points, inside the 1-point margin, so PROMOTE. With 31 regressions instead of 28, the lower bound would be −1.05 points and the verdict CONTINUE. Margins bite.
- The canary went through three looks with CONTINUE, CONTINUE, PROMOTE. The cost SLI dropped from $0.0070 to about $0.0004 per request.

**What to check.**
- The success criteria were written before any data was seen, and the per-slice criteria were applied.
- The judge change happened in a separate week from the model change.
- The rollback is a single flag flip, and someone rehearsed it during the 1% step.

---

## 3. Incident: prompt-cache misses blew the budget

**Situation.** On a Tuesday, finance flags that LLM spend for the payments org is running about 4x its daily average. No quality alert has fired. The summarizer is the largest consumer.

**Naive approach and what happens.** The team suspects a traffic spike and checks RPS, which is flat. Next they suspect a pricing change and open a provider ticket. A day later someone suggests "switching to a cheaper model". Meanwhile the overspend continues.

**AI-native approach.**

1. **Look at the token split, not the total.** `gen_ai.usage.cache_write.input_tokens` per request went from roughly 0 to 6,000 at 14:02 on Monday. `cache_read` went from 6,000 to 0. The prefix cache hit rate fell from about 0.99 to 0.00.
2. **Find what changed the prefix.** The distinct-`app.system.sha256`-per-hour panel went from 1 to 3,600 at 14:02: one new prefix per second, because the timestamp has second precision. The deploy annotation at 14:01 is config v15. The diff:

```diff
-SYSTEM = RULES
+SYSTEM = f"Current time: {now_utc():%Y-%m-%d %H:%M:%S} UTC\n" + RULES   # "so the model knows the date"
```

3. **Quantify it** with `code/cache_incident.py`, which emulates exact-prefix caching with a 5-minute TTL. This is real output of the simulation:

```text
v14: hit rate 1.000, $0.00271/req, $2,711/day at 1M req/day
v15: hit rate 0.000, $0.01186/req, $11,864/day at 1M req/day
```

   The simulation uses a 3,780-token prefix and about 300 tokens of alert per request. On Sonnet 5.5 that prefix costs $0.000378 as a cache read and $0.00945 as a cache write, a 25x difference. Every request became a cache write.
4. **Mitigate in one step.** Roll back the config pointer to v14. The hit rate recovers within one TTL window.
5. **Fix it properly** (v15.1). Put the timestamp in the *last* user message, where it costs about 15 uncached tokens:

```python
messages = [{"role": "user", "content": f"Current time: {now_utc():%Y-%m-%d %H:%M} UTC\n\n{alert_payload}"}]
```

6. **Write the postmortem, with the detection gap as the headline:**

```markdown
## Detection gap
Detected by finance after ~20 h. Quality SLOs were green (correctly: quality was unchanged).
No cost SLO existed. No cache hit-rate SLO existed.
## Action items
- [ ] SLO: cache_hit_rate >= 0.85 over 1h -> ticket; drop of >30 pts in 15 min -> page   (owner: @oncall)
- [ ] SLO: cost per request p95 <= $0.009 -> burn-rate alerts                         (owner: @oncall)
- [ ] CI test: render the system prompt twice, 2 s apart, with different request data; assert byte-identical
- [ ] Alert: distinct system-prompt hashes/hour > number of live config versions
- [ ] Shadow-replay gate reports cost per request and cache hit rate alongside quality
```

The CI test is the one that matters most, because it makes this class of bug impossible to merge:

```python
def test_system_prompt_is_cache_stable():
    a = build_request(alert=ALERT_1, now=T0)
    b = build_request(alert=ALERT_2, now=T0 + 2.0)
    assert a["system"] == b["system"] and a["tools"] == b["tools"]
```

**What to check.**
- The hit-rate SLO is defined over cache-eligible tokens, not all input.
- The shadow-replay gate in [05](05-changes-as-deploys.md) now reports cost, so a future v15 fails the gate before it reaches the canary.
- Anthropic's April 2026 postmortem described the same mechanism at a larger scale: a harness bug that dropped thinking blocks caused cache misses, which Anthropic believes drained usage limits faster than expected ([Anthropic](https://www.anthropic.com/engineering/april-23-postmortem)).

---

## 4. Judge drift: a scare that wasn't a regression

**Situation.** `judge_faithful` (corrected) falls from 0.96 to 0.92 overnight. No config deploy happened. The code-check SLIs are flat.

**Naive approach and what happens.** On-call assumes model drift, rolls the summarizer back to last week's config "to be safe", and the judge SLI stays at 0.92. Two engineers spend the day reading traces that look fine.

**AI-native approach.**
1. **Check the detector first.** The judge's deploy annotations show `judge_id` changed from `r4` to `r5` at 23:10. A teammate had "tidied" the rubric wording.
2. **Re-score the anchor set** (150 human-labelled traces) with both judge versions:

   | judge | TPR | TNR |
   |---|---|---|
   | r4 | 0.95 | 0.95 |
   | r5 | 0.90 | 0.96 |

   (illustrative numbers)
3. **Interpret.** r5 rejects more good outputs. Recomputing the corrected rate with r5's real TPR gives about 0.96 again: the system did not change, the instrument did.
4. **Fix the process, not just the judge.** Revert to r4. Require that any `judge_id` change ships with an anchor-set calibration, runs in parallel with the old judge for one window, and never lands in the same week as a system change.

**What to check.**
- The code-check SLIs were flat. That alone ruled out most real regressions, which is why every judge SLI should be paired with code checks.
- The dashboard's judge calibration panel would have shown the TPR change the next morning.
