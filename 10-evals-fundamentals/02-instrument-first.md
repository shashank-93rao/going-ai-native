# 02: Instrument first

## The idea
You cannot analyze errors you cannot see. Before you write a grader, and ideally before real users arrive, make every run of the system produce a **trace**: a structured record of the input, every model call, every tool call, the agent's state at each step, the output, and the exact prompt version that produced it.

Hamel Husain and Shreya Shankar's course puts this at the start ("Designing for Evaluability", lecture 2): design a **trace data model** with nested spans, model and tool calls, permission denials and **prompt hashes**, and stand up a trace store before you have users ([Husain and Shankar, AI Evals for Engineers and PMs, syllabus](https://maven.com/parlance-labs/evals)). The reasoning is the same one you apply to a new service. You add tracing on day one because the incident you will need it for has not happened yet.

The data model is small. In this course it is the `ainative_kit.Tracer` span, one JSON line per finished span:

```text
{trace_id, span_id, parent_id, name, start, end, attrs: {...}, error}
```

The design decisions are about **what goes in `attrs`**, and about **what a trace is**.

## Why it matters
Error analysis ([03-error-analysis.md](03-error-analysis.md)) means reading about 100 traces. If a trace is scattered across three log systems, missing the input, or missing the prompt version, each one takes ten minutes to assemble instead of thirty seconds to read, and nobody reads 100 of them. Hamel's rule for this is "Remove ALL friction from looking at data" ([Hamel Husain, "Your AI Product Needs Evals"](https://hamel.dev/blog/posts/evals/)).

Missing prompt versions do the most damage. Say a team sees the misroute rate double on Tuesday. Three prompt edits and a model alias change shipped that week, and the logs record none of them. They cannot tell which change did it, so they cannot roll back the right thing. This is the same failure as a service whose logs lack the build SHA.

## How it works

### What a trace is
- **In an eval: one trace per trial.** The harness opens a root span `eval_trial` and the system's spans nest under it. A case run 5 times gives 5 traces, and you can compare them.
- **In production: one trace per request** (or per user session for multi-turn agents), with the same child spans. The FAQ's advice for multi-agent flows is to give each user request one trace ID and log every message with its source (which agent or tool) and its position in the sequence ([Husain and Shankar, "AI Evals FAQ"](https://hamel.dev/blog/posts/evals-faq/)).

The same span shapes in both places is what lets you turn a production trace into an eval case later ([04-datasets.md](04-datasets.md)).

### Attributes by span type
| Span | Required attrs | Why |
|---|---|---|
| root (`eval_trial` or `request`) | `case_id`/`request_id`, `trial`, `slice`; after grading, `passed`, `outcome` | Join traces to dataset rows and grader verdicts |
| system (`route_alert`, `agent_run`) | `prompt_version`, `prompt_hash`, `input`, `output`, `parse_error` | Which prompt produced which output, and did it parse |
| `llm_call` | `model`, `prompt_hash`, `stop_reason`, `input_tokens`, `output_tokens`, output text | Cost, truncation (`max_tokens`), the raw text before parsing |
| `tool:<name>` | `args` (truncated), `result` (truncated), `is_error`, `state` | What the agent did and saw; the state path for the transition matrix |
| permission or guardrail decisions | `action`, `decision`, `reason` | Denials are behavior too; Hamel's data model names them explicitly |

### The prompt hash
Hash everything that defines the prompt: the system prompt, the tool schemas, and the model ID if you pin it. Do not hash the rendered user turn, which changes on every request. Twelve hex characters is plenty.

```python
def prompt_hash(system: str, tools: list[dict] | None = None) -> str:
    blob = json.dumps({"system": system, "tools": tools or []}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:12]
```

Log it on the system span and on every model call span. Then the eval summary can refuse to compare runs with different hashes, and production dashboards can group by hash the way you group by build SHA. `eval_harness.summarize` prints the set of hashes seen. More than one hash in a single run means something changed mid-run, and the numbers are not comparable.

### Agent state
For agents, tag each span with a coarse `state` such as `inspect`, `edit`, `verify` or `report`. The coding agent maps tool names to states (`STATE_OF_TOOL` in `coding_task.py`). `error_analysis.summarize_traces` drops the per-turn `plan` noise and collapses repeats, so a trace reduces to a path like `inspect -> edit -> verify -> report`. That path is the input to the transition failure matrix.

### A viewer
You need a way to put one trace on one screen. `error_analysis.render_trace` is a 40-line version. A spreadsheet with one row per trace is also a fine first viewer ([Hamel Husain, "A Field Guide to Rapidly Improving AI Products"](https://hamel.dev/blog/posts/field-guide/)). Off-the-shelf trace stores (Langfuse, LangSmith, Braintrust, Arize, and others) do this at scale. [Module 09](../09-frameworks-langchain-langgraph/README.md) covers LangSmith, and [Module 15](../15-observability-and-production/README.md) covers production tracing. If you already run OpenTelemetry, look at its generative-AI semantic conventions before inventing attribute names.

## Worked example: instrumenting the router

**Bad version.** The first router logged this:

```python
resp = client.complete(messages, system=SYSTEM)
logger.info("router result: %s", resp.text[:100])
```

```text
2026-10-14T03:12:09Z INFO router result: {"decision": "route", "team": "payments", "severity": "SEV2", "rationale": "payments: Consumer group ledger-wri
```
(illustrative output)

What can you learn from that line? Very little:

- **No input.** You cannot tell whether "payments" was right.
- **No prompt version.** You cannot tell which of this week's three prompts produced it.
- **No join key.** You cannot link it to the page that fired or to a human's later correction.
- **Truncated.** The rationale is cut off at the exact point where it would have explained itself.
- **Free text.** You cannot query "all payments routes where the title mentions a Kafka topic".

**Good version.** `ticket_router.route_alert` opens two spans, and the harness wraps them in a root span:

```python
with tracer.span("route_alert", case_id=case_id, prompt_version=PROMPT_VERSION,
                 prompt_hash=p_hash, input=alert, state="route") as s:
    with tracer.span("llm_call", model=model or "default", prompt_hash=p_hash) as c:
        resp = client.complete([{"role": "user", "content": render_alert(alert)}],
                               system=ROUTER_SYSTEM_PROMPT, model=model, max_tokens=300)
        c.attrs.update(model=resp.model, output_text=resp.text, stop_reason=resp.stop_reason,
                       input_tokens=resp.usage.input_tokens, output_tokens=resp.usage.output_tokens)
    parsed, err = parse_router_output(resp.text)
    s.attrs.update(output=parsed, raw_output=resp.text, parse_error=err)
```

One real line from `traces.jsonl` (measured, from the fake model):

```json
{"name": "eval_trial", "trace_id": "3e88ed85747d", "span_id": "8f34011b", "parent_id": null,
 "attrs": {"case_id": "r037", "trial": 0, "slice": "secret_in_body", "passed": false, "outcome": "wrong"}, "error": null}
```

And the rendered view of a different trace, which is what a labeler reads:

```text
=== trace be5a52befa56  case=r023 trial=0 slice=misleading_keyword prompt=77a194b5ba4f
INPUT:  {"source": "prometheus", "title": "Consumer lag on payments-events topic", "body": "Consumer group ledger-writer lag 300k on topic payments-events; ledger postings delayed about 10 min; no customer-visible impact.", "service": "ledger-writer", "env": "prod"}
- eval_trial {}
  - route_alert {"state": "route"}
    - llm_call {"stop_reason": "end_turn"}
OUTPUT: {"decision": "route", "team": "payments", "severity": "SEV2", "rationale": "payments: Consumer group ledger-writer lag 300k on topic payments-even"}
STATES: route
```

Thirty seconds of reading gives you two open codes: it routed on the word "payments" in a topic name, and it called SEV2 despite "no customer-visible impact". Note that the rendered view **does not show `passed`**. The labeler should judge the output without being anchored by the grader's verdict. Graders are one of the things error analysis is checking.

The agent trace for the coding task reduces to a state path:

```text
=== trace f59a8a6371cd  case=c001-token-bucket trial=3 slice=coding prompt=a6b55736a984
...
    - tool:write_file {"state": "edit", "args": {"path": "ratelimit.py", "content": "class TokenBucket:\n ..."}, "result": "wrote ratelimit.py"}
    - tool:run_tests {"state": "verify", "args": {}, "result": "...1 passed in 0.04s\n"}
    - llm_call {"state": "plan", "stop_reason": "end_turn", "text": "Fixed the comparison in allow(); all tests pass."}
OUTPUT: "Fixed the comparison in allow(); all tests pass."
STATES: inspect -> edit -> verify -> report
```

(Measured, from the `partial_fix` fake trajectory.) The visible tests passed, and the hidden outcome check later failed. The trace shows exactly where: the `edit` changed only the comparison.

## Pitfalls
| Pitfall | How to detect it |
|---|---|
| Logging only the output | Pick a random trace and try to decide whether it was correct. If you need another system to find the input, the trace is incomplete. |
| No prompt hash, or hashing the rendered prompt | Group last week's traces by hash. You should see a handful of values, one per deploy. One value per request means you hashed the wrong thing; one value overall means you are not hashing at all. |
| Truncating model output before parsing | Search for `stop_reason == "max_tokens"`. Those traces are failures of your budget, not of the model's reasoning. |
| Traces contain secrets and PII | Grep your trace store for the `SECRET_PATTERN` in `graders.py`. The router's own traces contain the bearer token from case r037, because the input is logged verbatim. Restrict access to traces, and redact at ingest where you can without destroying what you need to analyze. |
| Tracing only failures | You cannot estimate prevalence, and you cannot find failures your detectors missed. Trace everything, sample when you read. |
| Different span shapes in eval and production | You cannot replay a production trace as an eval case. Use the same instrumentation code in both. |
| The labeler sees the grader verdict | Your human labels will agree with the grader suspiciously often. Hide verdicts in the viewer. |

## In your day job
- Add a `prompt_hash` attribute to every LLM call in your services this week, computed from the system prompt and tool schemas, and put it on the dashboard next to the build SHA.
- Make one trace per request, with the input, the raw model output and the parsed output, before you build any grader.
- Decide now who can read traces and how long they are kept. Traces are production data with the same privacy obligations as your logs.
- Build or adopt a viewer that shows one trace on one screen. If reading a trace takes more than a minute, fix that before you start error analysis.
