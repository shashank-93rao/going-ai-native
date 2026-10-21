# Examples: Monday-morning scenarios

Each scenario follows the same shape: situation, the naive approach and what happens, the AI-native approach step by step, and what to check. Model outputs that weren't actually run are labelled *(illustrative output)*. Calculator outputs are real runs of the code in [code/](code/).

---

## 1. Costing an LLM enrichment step in a data pipeline

**Situation.** Your data platform team wants to add an LLM step to a nightly pipeline. It reads each of ~200,000 support tickets per night, with a fixed 6,000-token instruction-and-taxonomy prefix, a ~700-token ticket, and ~150 tokens of JSON out, and tags it with a product area and a root-cause category. Product wants a cost estimate by Friday.

**Naive approach.** Someone multiplies 200k × 6,850 input tokens by the input price of the biggest model, adds output, gets a large number, and the project dies. Or they take the smallest model's price and forget the prefix is sent with every ticket, and the estimate is off by 10x the other way.

**AI-native approach.**

1. Measure the shape. Run `count_tokens` on the real prefix and on 50 sampled tickets. Don't use characters divided by four: tickets contain stack traces and IDs, which tokenize badly ([01](01-tokens-and-the-context-window.md)).
2. Note the workload properties. It's offline (so the Batch API, at 50% off, is an option), the prefix is shared (so it's cacheable), and output is small (so input dominates).
3. Model it with the calculator, using your own prices:

```python
from token_cost_model import EXAMPLE_PRICES, expected_request_cost, uncached_request_cost

for model in ("claude-haiku-5-5", "claude-sonnet-5-5"):
    p = EXAMPLE_PRICES[model]
    per_req_uncached = uncached_request_cost(p, 6_000, 700, 150)
    per_req_cached = expected_request_cost(p, 6_000, 700, 150, hit_rate=0.98)
    print(model, f"uncached ${per_req_uncached*200_000:,.0f}/night",
          f"cached ${per_req_cached*200_000:,.0f}/night")
```

```text
claude-haiku-5-5 uncached $149/night cached $44/night
claude-sonnet-5-5 uncached $2,980/night cached $758/night
```

4. Decide by measured quality, not by price alone. Label 200 tickets, run both models at `low` effort, and compare tag accuracy with error bars ([Module 12](../12-hill-climbing/README.md)). If the small model is within the error bar, the decision is easy.
5. Check whether the Batch API discount stacks with caching on your platform (Anthropic's pricing page says the multipliers stack), and re-run the numbers.

**What to check.** After the first night, sum `cache_read_input_tokens` over all requests and divide by total input. It should be near the share of input that is prefix (here 6,000/6,700 ≈ 90%). If it's near zero, find the invalidator before the second night. Also check output tokens per request. If they're far above 150, the model is being verbose or thinking, and output may now dominate the cost.

---

## 2. The parallel backfill that never hit the cache

**Situation.** You're backfilling ADR summaries for 400 services. Each request contains the same 30k-token architecture overview plus one service's ADRs. You mark the overview with `cache_control` and fire all 400 requests through a pool with concurrency 50. The cost is about what you'd pay without caching.

**Naive approach.** "Caching doesn't work for us." Turn it off.

**AI-native approach.**

1. Look at the usage fields on the first 50 responses. Each shows `cache_creation_input_tokens ≈ 30,000` and `cache_read_input_tokens = 0`.
2. Recall the mechanism: an entry becomes readable only after the response that writes it *begins streaming* ([04](04-prompt-caching-cost-and-latency.md)). Fifty simultaneous requests over a cold prefix each write their own copy.
3. Fix the scheduling, not the prompt:

```python
first = client.messages.create(**req(services[0]))        # writes the 30k prefix
# or stream it and proceed as soon as the first token arrives
with ThreadPoolExecutor(50) as pool:
    results = list(pool.map(lambda s: client.messages.create(**req(s)), services[1:]))
```

4. If the job is not latency-sensitive, consider the Batch API instead. It's 50% off input and output, and the docs say cache multipliers stack with the batch discount.

**What to check.** Requests 2 to 400 should show `cache_read_input_tokens ≈ 30,000`. If some don't, check whether the run took longer than the 5-minute TTL between bursts (there's a pool stall in the trace), and whether all workers send byte-identical prefixes (same tool order, same serialization).

---

## 3. A model upgrade that broke three things at once

**Situation.** You move a ticket-routing service from an older model to `claude-opus-5-5`. The request code was written a year ago:

```python
client.messages.create(model=MODEL, max_tokens=1024, temperature=0,
                       thinking={"type": "enabled", "budget_tokens": 2000}, messages=msgs)
```

**Naive approach.** Change `MODEL`, deploy, and watch the error rate.

**What happens.** Every request returns 400, because Opus 5.5 rejects sampling parameters and `budget_tokens`. You remove those two arguments. Requests now succeed, but some return `stop_reason: "max_tokens"` with no text block, because thinking is always on and `max_tokens=1024` is too small. Then the routing accuracy dashboard moves, because Opus 5.5 defaults to `medium` effort and you never set one.

**AI-native approach.** Treat the model change as a dependency upgrade with a migration checklist ([03](03-reasoning-models-and-effort.md), [Module 12](../12-hill-climbing/README.md) model-upgrade drill):

1. **API surface.** Remove `temperature`, `top_p`, `top_k` and `budget_tokens`. Set `output_config={"effort": ...}` explicitly.
2. **Tokens.** Re-run `count_tokens` on your top prompts with the new model ID. Tokenizers differ across generations, and Anthropic documents up to about 1.35x more tokens for the Opus 4.7-era tokenizer than for earlier ones.
3. **Limits.** Size `max_tokens` for thinking plus the answer, and fail closed when `stop_reason != "end_turn"`.
4. **Cache.** Caches are model-scoped, so expect one cold-cache day of higher cost.
5. **Quality.** Run the eval at two effort levels before picking one.

**What to check.** In canary: the 400 rate is 0, `max_tokens` stops are near 0, cache read share recovers within an hour, and routing accuracy is within the error bar of the old model at the chosen effort.

---

## 4. Should the runbook agent restart pods by itself?

**Situation.** An ops agent handles "consumer lag high" alerts. It reads metrics, checks recent deploys, inspects consumer group state, and today *proposes* a remediation (restart a pod, scale the deployment, pause a partition) for a human to approve. The team wants it to act without approval at night.

**Naive approach.** "It's been right on every incident we've watched this month." That was 11 incidents.

**AI-native approach.**

1. Count steps and irreversibility. A typical run is about 12 steps, all read-only except the final action. Restarting one pod is reversible and low blast radius. Scaling to zero is not.
2. Measure per step from traces of the last 3 months of proposals, labelled by on-call ([Module 10](../10-evals-fundamentals/README.md)). Suppose the remediation-choice step is right 94% of the time and the read steps are right more than 99.5% of the time.
3. Do the arithmetic:

```text
$ python -c "from reliability_nines import *; print(chain_success(0.995, 11) * 0.94)"
0.8895...
```

That's about 89%. Roughly one autonomous action in nine would be wrong, with nobody watching.

4. Narrow the scope until it's checkable. Allow autonomous action only for "restart a single pod whose consumer is stuck in a rebalance loop", where a deterministic precondition (a rebalance count above a threshold in 10 minutes, from the broker's metrics) must hold and a deterministic postcondition (lag decreasing within 5 minutes) is checked, with automatic escalation if it fails. Everything else stays propose-only.
5. Write it down as an SLO: wrong autonomous actions fewer than 1 per quarter, with the error budget reviewed monthly.

**What to check.** Count autonomous actions where the postcondition failed. Spot-check that the precondition check is in code and not in the prompt ([Module 14](../14-steering-and-guardrails/README.md)). Track how often incidents fall outside the autonomous scope. If that's most of them, the automation isn't buying much.

---

## 5. The review bot that approves everything

**Situation.** Your LLM PR reviewer flags almost nothing on PRs whose descriptions say "small safe refactor, no behavior change". Last week one of those removed a `synchronized` block and caused a production race.

**Naive approach.** Add "Be critical! Find bugs!" to the system prompt. Now it flags style nits on every PR and engineers mute it.

**AI-native approach.**

1. Recognize the pattern as sycophancy toward the author's framing ([06](06-hallucination-and-sycophancy.md)). The PR description is a leading prompt.
2. Remove the framing. The reviewer gets the diff, the touched files, and the repo's invariants doc ([Module 08](../08-harness-engineering/README.md)), but not the PR description.
3. Ask a neutral, structured question:

```text
For each changed hunk: does it change behavior? Answer YES, NO, or UNSURE, with the specific
line and the reason. Pay attention to locking, memory visibility, ordering, and error paths.
```

4. Build a regression eval. Take 30 past PRs with known bugs, give each an "it's safe" description, and measure recall with and without the description ([Module 11](../11-llm-as-judge/README.md)).

**What to check.** Recall on the seeded-bug set should not change when you add a reassuring description. If it does, the reviewer is still reading the framing somewhere. Also track the UNSURE rate. A reviewer that never says UNSURE is guessing ([06](06-hallucination-and-sycophancy.md)).
