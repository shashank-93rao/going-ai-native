# 05: Structured outputs and JSON schemas

## The idea

When a program consumes the model's output, the output format stops being a style preference and becomes a **wire contract**. The schema is the contract, and there are three ways to hold the model to it, from weakest to strongest:

1. **Ask for JSON in the prompt, then validate and retry.** This works on any model and any client. It fails open: you find out about violations after the fact.
2. **Strict tool use.** You define a tool whose `input_schema` is your output shape and set `strict: true`. The API guarantees "schema validation on tool names and inputs".
3. **JSON outputs (constrained decoding).** You pass the schema in `output_config.format`. The API compiles it into a grammar and masks any token that would break it, so the response text is guaranteed to parse and match (with two exceptions, covered below).

None of the three guarantees **truth**. A schema can require that `evidence` is an array of strings. It can't require that those strings appear in the log. So every production classifier needs two validators: **shape**, which the mechanism can give you, and **meaning**, which you always write yourself.

## Why it matters

Prompting alone gets you most of the way, and a mechanism gets you the last nines. OpenAI's 2024 launch post for Structured Outputs reported that on its complex-schema eval, gpt-4o with Structured Outputs reached 100% adherence, against under 40% for gpt-4-0613 ([OpenAI, "Introducing Structured Outputs"](https://openai.com/index/introducing-structured-outputs-in-the-api/); the page returned 403 when re-checked for this module, so treat the exact figures as reported). The course's research notes also record a 93% figure for prompting alone on the newer model. That gap is the difference between a router that drops 7 alerts in 100 and one that drops none for format reasons.

Format reliability isn't the whole story, though. The worst triage failures are schema-valid: `{"category": "noise", "severity": "ignore", ...}` on an excerpt that shows a Postgres primary refusing connections. Shape validators pass it, and the alert disappears. That's why the meaning validators and the eval set ([06-prompts-as-deploys.md](06-prompts-as-deploys.md)) exist.

## How it works

### The Claude API surface (checked against the docs, October 2026)

```python
import anthropic
client = anthropic.Anthropic()

resp = client.messages.create(
    model="claude-sonnet-5-5",
    max_tokens=1024,
    system=system_prompt,
    messages=[{"role": "user", "content": f"<excerpt>\n{excerpt}\n</excerpt>"}],
    output_config={"format": {"type": "json_schema", "schema": TRIAGE_SCHEMA}},
)
if resp.stop_reason in ("refusal", "max_tokens"):
    raise TriageUnavailable(resp.stop_reason)      # never parse these
data = json.loads(next(b.text for b in resp.content if b.type == "text"))
```

Facts from the [structured outputs docs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs) that change how you design:

| Fact | Consequence |
|---|---|
| The old `output_format` parameter "has moved to `output_config.format`". The old one is deprecated and needs a beta header, or it returns a 400. | Grep your code for `output_format` before upgrading SDKs. |
| Objects must set `additionalProperties: false`. | Every object in your schema is closed. Adding a field is a schema change. |
| Unsupported: numeric `minimum`/`maximum`, string `minLength`/`maxLength`, recursive schemas, `minItems` other than 0 or 1. "If you use an unsupported feature, you'll receive a 400 error." | Length limits and ranges go in your semantic validator. `log_triage.py` checks the 200-character summary limit itself. |
| On refusal: "The output may not match your schema because the refusal message takes precedence." On `max_tokens`: "The output may be incomplete and not match your schema." | Check `stop_reason` before parsing. Constrained decoding has exactly these two holes. |
| "The first time you use a specific schema, there is additional latency while the grammar compiles." Grammars are cached for 24 hours from last use. | Warm new schemas in a canary before full rollout. |
| Changing `output_config.format` "will invalidate any prompt cache for that conversation thread." | Keep the schema fixed within a session. |
| Limits: 20 strict tools per request, 24 optional parameters across strict schemas, 16 union-typed parameters. | Prefer required fields with explicit `null`-able meanings over many optional ones. |

The course's `ainative_kit` client doesn't expose `output_config`. So `code/log_triage.py` uses tier 1 (ask, validate, retry) and keeps the validator you'd keep anyway on tier 3.

### Schema design rules for classifiers

1. **Closed enums, with an explicit abstain value.** `category` includes `unknown`, and `needs_human` is a boolean the router can act on. An abstain path is cheaper than a confident wrong answer ([Module 10](../10-evals-fundamentals/README.md) covers abstention-aware scoring).
2. **Fields a router reads are enums or booleans, never free text.** `severity: "page"` is routable. `"severity": "pretty bad"` is not.
3. **Add an evidence field for every decision a human will audit.** Then validate that the evidence is grounded in the input.
4. **Field meanings go in prose, field shapes go in the schema.** OpenAI's GPT-5.5 guide says to "Avoid describing the expected output schema in the prompt" when you use Structured Outputs. Keep the definitions of `page` and `ticket` in the prompt, because the schema can't carry them.
5. **Version the schema with the prompt.** Adding an enum value breaks any consumer with an exhaustive `switch`. That's a schema migration, so ship it as a new prompt version with a changelog entry, and update consumers first.

> **Synthesis:** for non-thinking runs, put `evidence` before `category` in the property order, so the label is generated after, and conditioned on, the quoted lines. With thinking on (the default on current Claude models), the order matters less, because the decision is made in the thinking block. This is a reasoned default, not a measured result. Test it on your own eval if it matters.

### Retry, as a bounded loop

When validation fails, send the errors back and ask again, at most once or twice. Two rules:

- **Append a user turn.** Never prefill an assistant turn (it returns a 400 on current Claude models).
- **Bound it, and log the attempt count.** A classifier that needs a retry on 30% of inputs has a prompt bug, and the attempt-count metric is how you find it.

## Worked example: the log-triage classifier

The schema, from `code/log_triage.py`:

```python
TRIAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "category": {"type": "string", "enum": ["infra", "dependency", "app_bug", "config", "data", "noise", "unknown"]},
        "severity": {"type": "string", "enum": ["page", "ticket", "ignore"]},
        "service": {"type": "string"},
        "summary": {"type": "string"},
        "evidence": {"type": "array", "items": {"type": "string"}, "minItems": 1},
        "needs_human": {"type": "boolean"},
    },
    "required": ["category", "severity", "service", "summary", "evidence", "needs_human"],
    "additionalProperties": False,
}
```

The semantic validator, which checks what no schema can:

```python
def semantic_errors(obj, excerpt):
    errs = []
    flat = " ".join(excerpt.split())
    for line in obj.get("evidence", []):
        if " ".join(line.split()) not in flat:
            errs.append(f"evidence not found verbatim in excerpt: {line[:60]!r}")
    if len(obj.get("summary", "")) > MAX_SUMMARY:          # maxLength isn't supported by the API
        errs.append(...)
    if obj.get("category") == "unknown" and obj.get("needs_human") is not True:
        errs.append("category 'unknown' requires needs_human=true")
    return errs
```

The prompt (`code/prompts/log_triage/v2.md`) carries what the schema can't:

- **The cost asymmetry**: "A wrong `page` wakes someone at 3am; a wrong `ignore` hides an outage. When in doubt between the two, choose `page`."
- **A definition for each enum value.** `dependency` is "something we call (database, broker, third-party API) is failing or throttling us", which settles the Postgres-refused-connections case.
- **Settled signatures** from past incident reviews (`OOMKilled` maps to `infra`/`page`). These are the team's institutional knowledge, written down where the model can use it.
- **Three examples**: a clear `infra`, a `noise`, and an `unknown` with `needs_human: true`. The third is there so the model learns abstention is a valid output.

The check pipeline in `check()`: `stop_reason` gate, then strict parse (prose around the JSON is a violation), then schema, then semantics. Here is the retry path, taken from `test_log_triage.py`. The FakeClient returns `"severity": "critical"` first:

```text
attempt 1 -> {"category": "infra", "severity": "critical", ...}
  check(): $.severity: 'critical' is not one of ['page', 'ticket', 'ignore']
attempt 2 messages: [user <excerpt>, assistant <bad json>, user "Your response failed validation:
  - $.severity: 'critical' is not one of [...]  Respond again with only the corrected JSON object."]
attempt 2 -> valid; span attrs: {prompt_ref: "log_triage@v2#abc", attempts: 2, ok: true}
```

The conversation ends on a user turn, the attempt count is on the span, and the prompt version is on the span. When the retry rate climbs after a deploy, the trace tells you which `prompt_ref` caused it.

Here is a real run of the offline demo (`python log_triage.py`, simulated model):

```json
{
  "category": "dependency",
  "severity": "page",
  "service": "payments-api",
  "summary": "payments-api: upstream stripe returned 429 Too Many Requests",
  "evidence": ["2026-10-02T03:20:11Z payments-api upstream stripe returned 429 Too Many Requests"],
  "needs_human": false
}
```

## Pitfalls

| Pitfall | How to detect it |
|---|---|
| **Treating schema-valid as correct.** | Track valid rate and accuracy as separate columns, as `ab_harness.py` does. If they move together you're not measuring meaning. |
| **Constraints the API ignores or rejects** (`maxLength`, `minimum`). The SDK helpers may move them into descriptions, but the raw API won't. | A 400 at deploy time, or values that violate a limit you thought was enforced. Put every limit in the semantic validator. |
| **Parsing a `max_tokens` or `refusal` response.** | Assert on `stop_reason` before `json.loads`, and alert on the rate of each. |
| **Enum drift between prompt and schema.** The prompt defines `critical`, but the schema doesn't have it. | Generate the enum list in the prompt from the schema constant, or test that every enum value appears in the prompt's definitions. |
| **Lenient parsing that hides contract violations**, such as a regex that pulls the first `{...}` out of prose. | It masks a prompt that isn't asking clearly enough. Parse strictly, count violations, and fix the prompt. |
| **Unbounded retries.** | The attempt-count histogram. Cap at 1 or 2 and fail to `needs_human`. |
| **Schema changes deployed before consumers.** | Treat a new enum value like a new protobuf enum value: consumers first, producer second. |

## In your day job

- For every LLM call whose output a program reads, write the schema as a constant next to the call, validate shape and meaning, and log `stop_reason` and attempt count.
- On the Claude API, move JSON-producing calls to `output_config.format` (or strict tools for classification), and keep your semantic validator.
- Add `unknown` (or an empty list) to every classifier you own, and route it to a human queue. Then measure how often it fires.
