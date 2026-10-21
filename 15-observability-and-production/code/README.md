# Module 15 code

Everything runs offline. Model calls go through `ainative_kit`, and the scripts use `get_client(fake=...)`, so they call the real API only when `ANTHROPIC_API_KEY` is set and `AINATIVE_FAKE` is not.

```bash
# from the course root
.venv/bin/python -m pytest -q 15-observability-and-production/code

# run a script (needs ainative_kit importable: `pip install -e .` once, or set PYTHONPATH=shared)
cd 15-observability-and-production/code
AINATIVE_FAKE=1 PYTHONPATH=../../shared ../../.venv/bin/python online_eval.py
```

| File | What it does | Run it to see |
|---|---|---|
| `otel_like.py` | Maps `ainative_kit.Tracer` spans to OpenTelemetry GenAI attribute names (checked against semantic-conventions-genai on 2026-10-19). Content is opt-in and redacted. Includes `TracedClient`, which wraps any `LLMClient` and records usage and prompt version | An exported `chat claude-sonnet-5-5` span and an `invoke_agent` span |
| `online_eval.py` | Summarizes traces, runs code checks on all of them, runs a judge on a consistent-hash sample, corrects the judge rate (Rogan–Gladen), computes SLIs with Wilson intervals, and evaluates threshold and multiwindow burn-rate alerts | An SLI table for 300 synthetic traces, plus the review-queue size |
| `router.py` | Cost-aware routing (cheap or strong), a cascade with an acceptance check, full-jitter retries honouring `retry-after`, deadline propagation, fallback on transient errors only, and a reserve/settle budget guard that degrades before refusing | One request that escalates from Haiku and absorbs a 529 |
| `canary.py` | Two-proportion z-test, exact McNemar for paired replay, sample sizing, and a non-inferiority PROMOTE/ROLLBACK/CONTINUE rule with alpha split across looks | Three canary verdicts and the n needed for a 2-point margin |
| `cache_incident.py` | Emulates prefix caching (5-minute TTL, minimum length) and replays the "timestamp in the system prompt" incident | Hit rate and cost per request for v14 and v15 |
| `pricing.py` | Rate card (USD/MTok, 2026-10-19), `cost_usd`, `cache_hit_rate` (reads ÷ cache-eligible tokens) and `cached_input_share` | (library) |
| `prod_fixtures.py` | Deterministic synthetic production traces for the alert-summarizer feature. Writes `data/prod_traces.jsonl` | (library, or writes the data file) |

Tests: `test_otel_like.py`, `test_online_eval.py`, `test_router.py`, `test_canary.py`, `test_cache_incident.py`.

Notes:
- The kit's `Usage` dataclass only has `input_tokens` and `output_tokens`, and `AnthropicClient` drops the cache counters. `TracedClient` and `Router` read `cache_read_input_tokens` and `cache_creation_input_tokens` from the usage object with `getattr`, so they pick them up if you pass the raw SDK usage through, and fakes can set them as attributes, as the tests do.
- If you put `Router` in front of the real Anthropic SDK, construct the SDK client with `max_retries=0`. The SDK retries twice by default, and two retry layers multiply.
- Prices change. Load them from config in real code.
- No extra packages are needed. `canary.py` uses `statistics.NormalDist` from the standard library.
