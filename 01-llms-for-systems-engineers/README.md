# 01: LLMs for systems engineers
> After this module you can reason about an LLM as a metered, nondeterministic, unevenly reliable remote dependency. You can estimate its cost and latency, measure its variance, budget its reliability in nines, and design around its two characteristic failure modes.

## Why this matters

Most bad LLM engineering comes from a wrong mental model of the component. People treat the model as a function ("set temperature 0 and it's deterministic"). They treat it as a database ("it knows our config keys"). They treat it as a colleague ("it agreed with my diagnosis"). Or they treat it as free ("it's just an API call"). Each of these leads to a specific failure: flaky tests, invented config, confirmation bias at incident time, and a bill eight times the estimate.

You already have the right mental model from distributed systems. You just need it calibrated to this component. It is a remote service that returns slightly different answers to the same request. Its latency is mostly a function of how much it writes. You pay per token in both directions, with a large discount for repeating a prefix byte for byte. Its correctness varies sharply by task type, in ways that don't track how hard the task looks to you. And when it doesn't know, it often answers anyway, in a confident tone, slanted toward what you seemed to expect.

This module covers the mechanics behind each of those properties precisely enough that you can do the arithmetic yourself: tokens, the context window and context rot, sampling, reasoning effort, prompt caching, cost and latency, jaggedness, the march of nines, hallucination and sycophancy. Every later module builds on this. Context engineering ([03](../03-context-engineering/README.md)) is about the window, loops ([07](../07-loops/README.md)) are about the nines, and evals ([10](../10-evals-fundamentals/README.md)) are about measuring the variance.

## The distributed-systems anchor

**The model is an unreliable, nondeterministic remote dependency.** Map it:

| You know | The LLM equivalent |
|---|---|
| A flaky downstream service | Same request, different response. Compare extracted fields, not bytes ([02](02-sampling-and-nondeterminism.md)) |
| Request size limits, payload cost | Tokens and the context window ([01](01-tokens-and-the-context-window.md)) |
| A CDN or prefix cache keyed on exact bytes | Prompt caching. One changed byte near the top is a cache miss for everything after ([04](04-prompt-caching-cost-and-latency.md)) |
| TTFB versus transfer time | TTFT (prefill) versus decode time (output tokens per second) |
| A query-planner optimization level or a timeout budget | Reasoning effort ([03](03-reasoning-models-and-effort.md)) |
| Serial availability, SLOs, error budgets | Per-step success to the power *n*, the march of nines ([05](05-jaggedness-and-the-march-of-nines.md)) |
| A replica that returns stale data with a 200 | Hallucination: confident, well-formed, wrong ([06](06-hallucination-and-sycophancy.md)) |
| A health check that passes while the service is broken | Sycophancy, and accuracy-only evals |

**Where the analogy breaks.**

- A flaky service is *usually* right and occasionally fails loudly. A model's failures are often silent and well-formed. No timeout or 5xx tells you the answer is wrong, so you have to build the check.
- A service's reliability is roughly uniform across endpoints. A model's is **jagged**: excellent on one task class and poor on an adjacent one, with no relationship to how hard either looks to you.
- Retries against a service are roughly independent. Retries against a model are often **correlated**, because the same misunderstanding repeats.
- A service doesn't care how you phrase the request. A model's output shifts with phrasing, ordering and what you appear to believe.

The course thesis applies directly. Because this dependency's failures are silent, **its output is only as trustworthy as the check you put after it**. Autonomy should scale with verifiability.

## Learning goals
- [ ] Estimate the token count, dollar cost and latency (TTFT plus decode) of a request from its shape, and verify the estimate with `count_tokens` and the `usage` fields
- [ ] Explain why greedy decoding is not deterministic on a shared inference server (batch invariance), and why current Claude models don't accept `temperature` at all
- [ ] Measure decision variance with a 20-sample probe, and distinguish it from surface variance
- [ ] Choose a reasoning effort level with a sweep, and guard against `max_tokens` truncation
- [ ] Explain prefix caching, compute the break-even hit rate, and find the silent invalidators in a prompt builder
- [ ] Convert a per-step success rate into run-level nines, and compute the ceiling a verifier puts on retries
- [ ] Explain why models hallucinate in terms of training and eval incentives, and score abstention separately
- [ ] Rewrite a leading prompt to resist sycophancy, and move identifier checks into code

## Reading order
1. [01-tokens-and-the-context-window.md](01-tokens-and-the-context-window.md): tokens, tokenization gotchas, the window, and context rot
2. [02-sampling-and-nondeterminism.md](02-sampling-and-nondeterminism.md): sampling, why temperature 0 isn't deterministic, and designing for variance
3. [03-reasoning-models-and-effort.md](03-reasoning-models-and-effort.md): thinking tokens, adaptive thinking, and the effort knob
4. [04-prompt-caching-cost-and-latency.md](04-prompt-caching-cost-and-latency.md): prefix caching, append-only prompts, cost math, TTFT
5. [05-jaggedness-and-the-march-of-nines.md](05-jaggedness-and-the-march-of-nines.md): the jagged frontier, p<sup>n</sup>, verifiers, and pass@k versus pass^k
6. [06-hallucination-and-sycophancy.md](06-hallucination-and-sycophancy.md): the incentives behind both failure modes, and the countermeasures
- [examples.md](examples.md), [exercises.md](exercises.md), [references.md](references.md), [code/](code/)

## Prerequisites
- [00: Orientation](../00-orientation/README.md) for the course thesis (autonomy scales with verifiability).
- Python 3.11+ and the course venv. No API key is needed for the tests. The exercises that use a real API cost cents.

## Key takeaways
- **Tokens are the unit of cost, latency and capacity.** Count them with the provider's endpoint, per model. Tokenizers change between model generations.
- **A full context window is a degraded context window.** Do the deterministic reduction (grep, SQL) first, and give the model a small, high-signal excerpt with the question at the end.
- **"Temperature 0" doesn't buy determinism**, because the server isn't batch-invariant, and current Claude models reject the parameter anyway. Test decisions, not strings. Use record and replay in CI.
- **Effort is a per-route configuration value backed by a sweep.** Set it explicitly, size `max_tokens` for it, and fail closed on `stop_reason != "end_turn"`.
- **Prompt caching is a byte-exact prefix cache.** Keep prompts append-only, freeze tools and the system prompt, and monitor cache read share as an SLI. A broken cache costs *more* than no cache.
- **Reliability multiplies.** 95% per step is 36% over 20 steps. Verifiers raise the ceiling. Retries only approach it.
- **Models hallucinate because guessing was rewarded.** Make abstention legal, require evidence, and validate identifiers in code.
- **Models agree with you.** Ask neutral questions, review in a fresh context, and never use "are you sure?" as a check.
