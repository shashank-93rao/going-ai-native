# 03: Drift: input, model and judge

## The idea
An LLM feature's quality is a function of three things that move independently:

| Kind | What moves | Who moves it | Typical symptom |
|---|---|---|---|
| **Input drift** | The distribution of requests: new services, new languages, longer logs, a new customer segment, adversarial traffic | Your users and your upstream systems | Pass rate falls in one slice while the global average barely moves |
| **Model drift** | The model or serving stack behind the same request: a new snapshot behind an alias, a changed default (effort, context routing), an infra bug, *your own* harness or SDK upgrade | The provider, or a teammate | Diffuse, inconsistent degradation across slices. "It feels dumber" |
| **Judge drift** | The detector itself: the judge model is upgraded, the rubric is edited, or the human labellers' standards shift | You, often by accident | The SLI moves with no change in the system. Or worse, it stays flat while the system changes |

Your SLIs are a product of all three, so each needs its own detector, or you cannot tell which one moved.

## Why it matters
**Model drift is real and hard to see from the outside.** Anthropic's April 2026 postmortem describes three product-side changes that together looked like a broad regression. The default effort was lowered from `high` to `medium`. A bug cleared thinking history on every turn instead of once. A system-prompt line capping response length cost about 3% on a broader eval. The changes hit different traffic on different schedules, and the thinking-history bug got past code review, unit and end-to-end tests, and dogfooding ([Anthropic, "An update on recent Claude Code quality reports", 2026-04-23](https://www.anthropic.com/engineering/april-23-postmortem)). The September 2025 postmortem found three infrastructure bugs in which "each bug produced different symptoms on different platforms at different rates" ([Anthropic, 2025-09-17](https://www.anthropic.com/engineering/a-postmortem-of-three-recent-issues)).

**The sycophancy lesson concerns your *detectors*, not the model.** OpenAI shipped a GPT-4o update on April 25, 2025 and began rolling it back on April 28. The update added a reward signal from thumbs-up/down data, alongside other changes, which OpenAI believes together weakened the signal holding sycophancy in check. Offline evals looked fine, and the A/B test "seemed to indicate that the small number of users who tried the model liked it". Meanwhile, "some expert testers had indicated that the model behavior 'felt' slightly off", and OpenAI shipped anyway. Its stated fix is to treat behavioural issues as launch-blocking and to weight qualitative signals more heavily ([OpenAI, "Expanding on what we missed with sycophancy", 2025-05-02](https://openai.com/index/expanding-on-sycophancy/); passages as quoted by [Simon Willison](https://simonwillison.net/2025/May/2/what-we-missed-with-sycophancy/)).

> **Synthesis:** Every quantitative metric covers only what you thought to measure. A specific, repeatable "this feels off" from someone who uses the system every day is evidence of a failure mode that has no eval yet. The course rule is that **a qualitative red flag from an expert blocks promotion until someone writes an eval that explains it, or shows it is noise.** The expert's signal is not overruled by the existing metrics. It is converted into a new one.

## How it works

### Input drift detectors
1. **Slice your SLIs** by the dimensions that matter: input source, customer tier, language, length bucket, tool used. Global averages hide slice collapses (Simpson's paradox is the usual culprit).
2. **Distribution distance on cheap features.** For categorical features, such as alert source or detected language, use the Population Stability Index:
   `PSI = Σ (actual_i − expected_i) · ln(actual_i / expected_i)`.
   A common rule of thumb reads below 0.1 as stable, 0.1–0.25 as moderate shift and above 0.25 as large. These thresholds are folklore from credit scoring, so tune them on your own history.
3. **Unseen-category rate.** The share of inputs landing in "other", or failing to match any known service, is often the earliest signal and needs no statistics at all.
4. **Embedding clusters** (optional). Cluster a weekly sample of input embeddings and track the share of each cluster. A new cluster tells you what to read, but not whether it is bad.

### Model drift detectors
1. **Pin snapshots, and alert on `gen_ai.response.model` changes.** If you call an alias, the provider decides when your model changes. Record the response model on every span and alert when its value set changes.
2. **Record every knob as a span attribute.** Effort, max tokens, temperature, thinking mode, SDK version and harness version all count. Anthropic's effort-default change is exactly the kind of silent change that only shows up if `gen_ai.request.reasoning.level` is on the span.
3. **A canary probe suite.** Fifty to two hundred frozen inputs with code-checkable answers, run hourly against the production config. This is black-box probing, like a synthetic HTTP check, applied to quality. Because the inputs are fixed, input drift cannot explain a drop. Compare runs with a **paired** test (McNemar in `code/canary.py`), not by eyeballing averages. Run each case k≥3 times, since nondeterminism alone moves single-run scores ([Module 12](../12-hill-climbing/README.md) covers noise checks).
4. **Tie spikes to deploys.** Annotate dashboards with every prompt, model, SDK, harness and infra deploy. Anthropic lists failing to connect a spike in reports to a load-balancing change as one reason its 2025 incident lasted longer.

### Judge drift detectors
1. **Freeze the judge**: model snapshot, prompt and parsing code, all versioned together as `judge_id`. Never upgrade the judge and the system in the same week.
2. **An anchor set.** Keep 100–200 human-labelled traces that the judge re-scores weekly. Track its TPR and TNR on the anchor set. If either moves by more than the CI width, the judge drifted.
3. **Re-calibrate on upgrade.** A new judge model is a new instrument. Measure its TPR and TNR on the anchor set before it touches a production SLI, and plot old and new judges side by side for one window.
4. **Watch for criteria drift in the humans.** Shreya Shankar's EvalGen work found that people's criteria change as they grade outputs ([Shankar et al., "Who Validates the Validators?"](https://arxiv.org/abs/2404.12272)). Re-label a slice of the anchor set every quarter and measure inter-rater agreement with the original labels.

## Worked example
**Situation.** The alert summarizer's `grounded_service` SLI fell from 0.976 to 0.951 over a week. The on-call engineer's first theory was "the provider changed the model". Here is the bad response and the good one.

**Bad.** The engineer opens a ticket with the provider and switches the alias to a different model "to be safe". The SLI stays at 0.95, and the new model costs twice as much.

**Good: separate the three drifts in order.**

1. *Judge drift?* `grounded_service` is a code check, so there is no judge to drift. Eliminated. Had it been a judge SLI, you would re-score the anchor set first.
2. *Model drift?* Query the response models seen this week:
   ```sql
   SELECT "gen_ai.response.model", "gen_ai.prompt.version", count(*)
   FROM spans WHERE name LIKE 'chat %' AND ts > now() - interval '7 days' GROUP BY 1, 2;
   ```
   Only one model and one prompt version appear. The hourly probe suite shows 0 regressions and 1 fix across 150 paired cases, with McNemar p = 1.0. Eliminated.
3. *Input drift?* Compare the alert-source mix against the previous 4 weeks:

   | Source | Baseline | This week | (a − e)·ln(a/e) |
   |---|---|---|---|
   | kafka | 0.40 | 0.30 | 0.029 |
   | http | 0.30 | 0.25 | 0.009 |
   | db | 0.20 | 0.15 | 0.014 |
   | other | 0.10 | 0.30 | 0.220 |
   | **PSI** | | | **0.27** |

   "Other" tripled. Reading 20 of those traces shows a platform team started routing Kubernetes alerts to the summarizer, and those payloads put the service name in a `labels.app` field the prompt never mentions. The model guesses a service. Sliced, `grounded_service` is 0.99 on known sources and 0.80 on k8s alerts.

**Fix.** Add k8s examples to the prompt (v15), add a k8s slice to the offline suite, and ship v15 as a canary ([05](05-changes-as-deploys.md)). Then add the unseen-category rate to the dashboard, since it would have flagged this on day one.

All the numbers in this walkthrough are illustrative, but the PSI arithmetic is real.

## Pitfalls
- **Calling everything "model drift".** It is the most comfortable explanation, because it is someone else's fault. *Detect:* if your probe suite is flat and the drop is confined to a slice, the cause is input drift.
- **Probe suites that saturate.** If every probe passes at 100%, the suite cannot detect a 3% regression. Include probes the model passes about 80–95% of the time.
- **Upgrading the judge and the generator together.** You can no longer attribute the change. Stagger them by at least one full SLO window.
- **Overriding experts with dashboards.** This is the sycophancy failure mode. *Detect:* a launch review where someone says "it feels off" and the response is "the metrics are green". That should be a launch-blocking ticket, not a debate.
- **PSI on high-cardinality raw features.** PSI on raw service names with thousands of values is noise. Bucket first, and keep an explicit "unseen" bucket.
- **Ignoring your own harness as a source of model drift.** An SDK or harness upgrade changes what the model sees. Anthropic's thinking-history bug was in the harness, not the model.

## In your day job
- Pin model snapshots in config, put `gen_ai.response.model` on every span, and alert when its value set changes.
- Build a 150-case probe suite from last quarter's incidents. Run it hourly against production config and compare runs with a paired test.
- Give your judge an ID and an anchor set, and refuse to change it in the same week as anything else.
- Write the rule into your launch checklist: *a specific qualitative concern from a domain expert blocks promotion until it is explained by an eval.*
