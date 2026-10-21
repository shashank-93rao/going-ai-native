# 02: Sampling, temperature, and why "temperature 0" doesn't buy determinism

## The idea

At each step the model computes a score (a logit) for every token in its vocabulary. Softmax turns those scores into a probability distribution, and a **sampler** picks the next token from it. Then the chosen token is appended and the whole thing repeats. Everything you think of as "the model's answer" is one path through a tree of token choices.

The sampler has knobs:

| Knob | What it does | Effect |
|---|---|---|
| `temperature` | Divides logits before softmax. Below 1 sharpens the distribution, above 1 flattens it. 0 means greedy decoding (always take the argmax). | Lower means less diverse output |
| `top_p` (nucleus) | Keeps the smallest set of tokens whose probabilities sum to *p*, then renormalizes | Cuts off the long tail |
| `top_k` | Keeps only the *k* most likely tokens | Cuts off the long tail, more bluntly |

The folk belief is that `temperature=0` makes a model a pure function. It doesn't, for two independent reasons. First, the *serving system* isn't batch-invariant, so the logits themselves vary slightly from request to request. Second, on current Claude models you can't set temperature at all. Either way you are left with the same engineering stance: **the model is a nondeterministic dependency, and you design for that the way you design for a flaky network.**

## Why it matters

Horace He and colleagues at Thinking Machines Lab sampled Qwen3-235B 1,000 times at temperature 0 with the same prompt ("Tell me about Richard Feynman"), 1,000 tokens each. They got **80 distinct completions**. The most common one appeared 78 times. All 1,000 agreed for the first 102 tokens. At token 103, 992 continued with "Queens, New York" and 8 with "New York City", and from there the texts went their separate ways ([Thinking Machines, "Defeating Nondeterminism in LLM Inference", 2025-09-10](https://thinkingmachines.ai/blog/defeating-nondeterminism-in-llm-inference/)).

That is the shape you'll see in your own systems: long identical prefixes, then a fork, then permanent divergence. Generation is autoregressive, so a single different token changes the input for every token after it. In an agent, the fork can be the choice of the *first tool call*, and then the entire trajectory differs.

## How it works

### Why greedy decoding is still nondeterministic

The common explanation is "GPUs run things concurrently and floating-point addition isn't associative". That is true but incomplete. The Thinking Machines post shows that a single forward pass on typical inference kernels is run-to-run deterministic, and that atomic adds "are not necessary for the vast majority of kernels". The real cause is a lack of **batch invariance**: kernels such as matmul, attention and RMSNorm pick different reduction strategies depending on batch size, which changes the floating-point rounding, which changes the logits in the last few bits. When two candidate tokens are nearly tied, those bits flip the argmax.

Batch size depends on how many *other* users' requests the server happens to be processing alongside yours. In the post's words, "the load (and thus batch-size) nondeterministically varies!" From your side of the API, the server is nondeterministic even though each kernel is deterministic.

It can be fixed, at a price. With batch-invariant kernels, all 1,000 completions were identical. The batch-invariant matmul was about 20% slower than cuBLAS, and end-to-end on Qwen3-8B the run went from 26 s (default vLLM) to 55 s (unoptimized deterministic), then 42 s with an improved attention kernel. Hosted APIs are not obliged to make that trade, and you should assume yours doesn't.

There are further sources of variance that have nothing to do with numerics:

- **Model and serving changes.** An alias can move to a new snapshot, and providers change serving infrastructure. Anthropic's September 2025 postmortem describes three infrastructure bugs (context-window routing errors, TPU output corruption, and an approximate top-k compiler bug) that degraded output quality for some requests ([Anthropic, "A postmortem of three recent issues"](https://www.anthropic.com/engineering/a-postmortem-of-three-recent-issues)).
- **Harness changes.** Your own code renders the prompt. A changed tool order, a timestamp, or a different retrieved document is a different input.
- **Thinking.** Reasoning tokens are sampled too. A different chain of thought can reach a different answer.

### Current Claude models: no temperature at all

As of October 2026, the Claude API docs list sampling parameters (`temperature`, `top_p`, `top_k`) as **removed** on Opus 5.5 and the Fable 5.x family, returning a 400 if sent. Sonnet 5.5 and Haiku 5.5 reject non-default values. Thinking is always on for Opus 5.5 and Fable 5.x, and the knob you get instead is `effort` ([03-reasoning-models-and-effort.md](03-reasoning-models-and-effort.md)). Older models still accept `temperature`.

So "pin temperature to 0 for reproducibility" is not even an option on the default course model. The `ainative_kit` client only sends `temperature` when you pass one, and the probe in `code/` never does.

### The engineering stance

You already know how to build on a nondeterministic dependency. Map the techniques:

| You'd do this for a flaky remote service | Do this for an LLM call |
|---|---|
| Never compare responses byte for byte; compare the fields you depend on | Extract the decision (a verdict, a JSON field, a diff) and compare *that* |
| Validate responses against a schema at the boundary | Structured outputs plus a semantic validator ([Module 14](../14-steering-and-guardrails/README.md)) |
| Idempotency keys for side effects | Make tool side effects idempotent, because a retried or re-planned step may issue the same call twice |
| Record and replay traffic in tests | `RecordingClient` / `ReplayClient` in `ainative_kit`, so unit tests are deterministic ([Module 13](../13-testing-agentic-systems/README.md)) |
| Measure error rates, not single requests | Run the same input N times and measure agreement. That's the probe in `code/nondeterminism_probe.py` |
| Quorum reads | Self-consistency: sample k times and take the majority answer, when the answer is discrete and the extra cost is justified |

The useful distinction is **surface variance** versus **decision variance**. Two root-cause explanations that word things differently but name the same cause are fine. Two runs that name different causes are a reliability problem. Your probe has to measure the second, not the first.

## Worked example: a flaky severity classifier in an alerting pipeline

Your team added an LLM step to the alert pipeline. It reads an alert plus recent logs and emits a severity (`SEV1` to `SEV4`) that decides whether to page. The integration test is flaky.

**Bad version.**

```python
def test_classifier_pages_on_disk_full():
    out = client.complete(
        [{"role": "user", "content": ALERT_DISK_FULL}],
        temperature=0,  # "makes it deterministic"
    ).text
    assert out == "Severity: SEV2. The /var/lib/kafka volume is at 97%..."
```

Why it fails:

1. On Sonnet 5.5 or Opus 5.5 the request returns a 400, because `temperature` isn't accepted there. Someone "fixes" the test by switching to an older model, and now the test exercises a model you don't ship.
2. On models that accept temperature, the exact-string assertion still fails intermittently, because of batch-dependent numerics and model updates.
3. Even when it passes, it tests the wrong property. The pipeline cares about `SEV2`, not the prose.

**Good version.** Separate the three questions: does the code handle the model's output correctly (deterministic, use a fake or a replay), how stable is the decision (statistical, use a probe), and is the decision correct (an eval, [Module 10](../10-evals-fundamentals/README.md)).

```python
# 1. Unit test: deterministic. The fake stands in for the model; we test parsing and routing.
def test_sev2_routes_to_pager():
    fake = FakeClient([text("SEVERITY: SEV2\nDisk at 97% on broker-3.")])
    assert route_alert(fake, ALERT_DISK_FULL).pager is True


# 2. Stability check: statistical. Run against the real model on a schedule, not on every commit.
from nondeterminism_probe import probe

def severity(text: str) -> str:
    return text.strip().splitlines()[0].removeprefix("SEVERITY:").strip()

report = probe(get_client(), [{"role": "user", "content": ALERT_DISK_FULL}], n=20, extract=severity)
assert report.answer_agreement >= 0.95, report.summary()
```

Running the probe offline against its seeded fake (from `code/`, `AINATIVE_FAKE=1 python nondeterminism_probe.py 20`) prints this. The numbers come from the fake's seeded perturbations, not from a real model:

```text
runs=20 distinct_outputs=10 modal_share=35% first_divergence=token 1 mean_similarity=0.968 answer_agreement=85% answers={'poll-timeout': 17, 'session-timeout': 3}
```

Read it the way you'd read a flakiness report. Ten distinct strings out of 20 runs, with 0.968 mean similarity, is surface noise, and you don't care about it. An 85% agreement on the extracted verdict is decision variance, and you do. If the real model shows that on a paging decision, you have three fixes, from cheapest to most expensive:

1. Make the input less ambiguous. Give the classifier explicit thresholds ("SEV2 if a broker volume is above 95%") so the decision isn't near a tie.
2. Move the decision out of the model. If disk percentage decides severity, compute it in code and let the model write only the summary.
3. Pay for redundancy: sample three times and page on the majority, accepting roughly three times the cost and latency.

Option 2 is the course thesis in miniature. Whatever you can make checkable and deterministic, you should.

## Pitfalls

| Pitfall | How to detect it |
|---|---|
| Sending `temperature=0` to a current Claude model | A 400 `invalid_request_error` mentioning sampling parameters. Remove the argument. |
| Exact-match assertions on model text in CI | Grep tests for `assert .*\.text ==`. Replace each with extraction plus a fake or replay. |
| Measuring variance on the prose instead of the decision | Your probe reports high "distinct outputs" and you panic, or low distinctness and you relax. Always pass an `extract` function. |
| Probing with N=3 | With 3 runs you can't tell 90% agreement from 99%. Use 20 or more, and report the count, not just the percentage. |
| Treating one passing run as evidence | Any single sample is one draw from a distribution. Require the probe or an eval with an error bar ([Module 12](../12-hill-climbing/README.md)). |
| Non-idempotent tool side effects | Re-run an agent task twice from the same state and diff the side effects (tickets created, messages sent). Duplicates mean you need idempotency keys. |

## In your day job

- Delete `temperature=0` from code that targets current Claude models, and delete any test that depends on it.
- For every LLM decision that triggers an action (page, merge, refund, delete), write down the extracted field and run a 20-sample probe before launch. Put the agreement rate in the design doc.
- Use `RecordingClient` once against the real API, then `ReplayClient` in CI, so unit tests are deterministic and cost nothing.
- When a user reports "it gave a different answer yesterday", treat it like a heisenbug report: capture the exact rendered request, then probe it.
