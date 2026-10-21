# Module 01 code

Three small calculators that treat the model as a metered, nondeterministic remote dependency. All of them run offline. Only `nondeterminism_probe.py` calls a model, and it goes through `ainative_kit`.

| File | What it does | Concept file |
|---|---|---|
| `token_cost_model.py` | Cost per request from the API's usage fields, expected cost at a given cache hit rate, the break-even hit rate, the cost of a 30-turn agent loop under three prompt disciplines, and a parametric TTFT/latency model | [04-prompt-caching-cost-and-latency.md](../04-prompt-caching-cost-and-latency.md) |
| `nondeterminism_probe.py` | Sends the same request N times and reports distinct outputs, modal share, first divergence token, mean pairwise similarity, and agreement on an *extracted* answer | [02-sampling-and-nondeterminism.md](../02-sampling-and-nondeterminism.md) |
| `reliability_nines.py` | `p**n` chain success, per-step reliability needed for a run-level target, verifier-plus-retry math, and pass@k vs pass^k | [05-jaggedness-and-the-march-of-nines.md](../05-jaggedness-and-the-march-of-nines.md) |

## Run the tests (offline)

From the course root:

```bash
.venv/bin/python -m pytest -q 01-llms-for-systems-engineers/code
```

## Run the scripts

From this directory:

```bash
../../.venv/bin/python token_cost_model.py
../../.venv/bin/python reliability_nines.py
AINATIVE_FAKE=1 ../../.venv/bin/python nondeterminism_probe.py 20   # seeded fake
../../.venv/bin/python nondeterminism_probe.py 20                   # real API if ANTHROPIC_API_KEY is set
```

Notes:

- **Prices are parameters.** `EXAMPLE_PRICES` holds Anthropic list prices checked on 2026-10-19 against [the pricing page](https://platform.claude.com/docs/en/about-claude/pricing). Re-check them before you use the numbers for a budget. Build your own `Pricing(...)` for other models or providers.
- **The latency model's defaults are placeholders**, not measurements. Measure p50/p95 TTFT and output tokens per second for your route and pass them in.
- **The probe does not send `temperature`.** On current Claude models, Opus 5.5 and Fable 5.x reject sampling parameters, and Sonnet 5.5 rejects non-default values, with a 400 error (per the Claude API docs as of October 2026). To probe another provider that accepts `temperature=0`, pass it through `probe(..., temperature=0)`.
- The real-API run costs roughly N times one short request. With N=20 on Sonnet 5.5 that is well under a cent.
- `estimate_tokens` is a characters-per-token heuristic. For real counts, use the `count_tokens` endpoint (`client.messages.count_tokens(model=..., messages=...)`). Don't use OpenAI's `tiktoken` for Claude, because it is a different tokenizer.
