# 02: Structured outputs, validators, and bounded repair loops

## The idea

When a model's output feeds a program, such as a ticketing system, a config generator or a migration planner, you need three separate layers. They are often conflated.

1. **Constrained decoding (shape).** The API compiles your JSON Schema into a grammar and masks tokens that would break it. You get parseable JSON with the required keys, the right types, and enum values. This is a guarantee about *syntax*.
2. **A local validator (constraints and semantics).** This is your code. It checks what the decoder does not enforce: numeric ranges, string lengths, patterns, and any rule that spans fields ("sev1 requires a runbook URL"). It can also check grounding ("every quoted evidence line appears in the input").
3. **A bounded repair loop (feedback control).** On a validation failure, send the *exact* errors back to the model and ask for a corrected object. Cap the attempts, stop if no progress is made, and send the record to a dead-letter path when the budget runs out.

The distributed-systems anchor is a schema-registry pipeline. Layer 1 is the Avro or Protobuf schema: it prevents malformed bytes. Layer 2 is the consumer-side validation that rejects a well-formed event with `amount_cents: -5`. Layer 3 is retry with a reason code, then the dead-letter queue. The analogy breaks in one place. A Kafka producer retry resends the *same* bytes, but a model retry produces *different* output, and you can steer it with the error message. That makes feedback much more valuable than in a byte pipeline.

## Why it matters

- **Shape is not truth.** OpenAI's Structured Outputs launch post lists the limits plainly: values can still be wrong, output can be truncated at `max_tokens`, and only a subset of JSON Schema is supported ([OpenAI](https://openai.com/index/introducing-structured-outputs-in-the-api/)).
- **The decoder does not enforce your constraints.** Anthropic's structured-outputs docs (checked 2026-10-19) list as unsupported in the schema: numerical constraints (`minimum`, `maximum`, `multipleOf`), string constraints (`minLength`, `maxLength`), array constraints beyond `minItems` of 0 or 1, and `additionalProperties` set to anything other than `false`. The SDK helpers move unsupported constraints into field descriptions and, for helpers that validate responses, still check them locally ([Anthropic, "Structured outputs"](https://platform.claude.com/docs/en/build-with-claude/structured-outputs)). So a schema saying `confidence` must be between 0 and 1 will happily decode `85`. Your validator is the only thing standing between that and a dashboard that shows 8500% confidence.
- **The guarantee has exceptions.** The same docs note that refusals (`stop_reason: "refusal"`) and truncation (`stop_reason: "max_tokens"`) can produce output that doesn't match the schema.

## How it works

### Layer 1: ask for the shape

On the Claude API (current as of 2026-10-19), JSON outputs use `output_config.format`. The older `output_format` parameter is deprecated and needs a beta header. Strict tool use (`"strict": true` on a tool definition) gives the same guarantee for tool inputs.

```json
{
  "model": "claude-sonnet-5-5",
  "max_tokens": 1024,
  "output_config": {
    "format": {
      "type": "json_schema",
      "schema": {
        "type": "object",
        "required": ["service", "severity", "category", "summary", "confidence"],
        "additionalProperties": false,
        "properties": {
          "service":  {"type": "string"},
          "severity": {"type": "string", "enum": ["sev1", "sev2", "sev3"]},
          "category": {"type": "string", "enum": ["consumer_lag", "broker_outage", "poison_message", "rebalance_storm", "unknown"]},
          "summary":  {"type": "string", "description": "20-280 chars"},
          "confidence": {"type": "number", "description": "0.0-1.0"}
        }
      }
    }
  },
  "messages": [{"role": "user", "content": "Triage this page: ..."}]
}
```

The course's `ainative_kit` client does not pass `output_config`, so the code in this module asks for JSON in the prompt and relies on layers 2 and 3. That is deliberate: it is the worst case, and it makes the repair loop do visible work. In production, use both.

### Layer 2: validate everything the decoder doesn't

[`code/validators.py`](code/validators.py) is a stdlib JSON-Schema-lite validator (pydantic isn't in the course venv, and you should be able to read the whole thing in five minutes). Its design choices:

- **Report every error, not the first.** One repair round can then fix them all. A validator that stops at the first error turns a 1-retry fix into a 3-retry fix.
- **Precise paths.** `$.affected_partitions[2]: -3 is below minimum 0` tells the model exactly what to change.
- **Semantic checks only after the schema passes.** Cross-field rules on a malformed object produce confusing errors.
- **Grounding checks are cheap.** "Each evidence string must appear verbatim in the input" is a one-line substring test, and it catches a large class of fabricated quotes.
- **Cap the feedback.** `format_errors_for_model` caps the list at 10, so a garbage output can't flood the context.

### Layer 3: repair with feedback, bounded

[`code/repair_loop.py`](code/repair_loop.py):

```python
for n in range(1, max_attempts + 1):
    resp = client.complete(messages, system=system, max_tokens=max_tokens)
    obj, errs = check_output(resp.text, schema, checks)          # parse -> schema -> semantic
    if resp.stop_reason == "max_tokens":
        errs = [ValidationError("$", "output truncated ...; be more concise", "parse")] + errs
    if not errs:
        return RepairResult(True, obj, "valid", attempts)
    if frozenset(map(str, errs)) == prev_fingerprint:            # same errors twice: not converging
        return RepairResult(False, obj, "no_progress", attempts)
    messages += [{"role": "assistant", "content": resp.text},
                 {"role": "user", "content": FEEDBACK_TEMPLATE.format(errors=format_errors_for_model(errs))}]
```

The three governors:

| Governor | Why |
|---|---|
| `max_attempts` (default 3) | Hard cost bound. 12-Factor Agents (factor 9) suggests breaking the loop after about 3 consecutive errors and escalating ([HumanLayer, 12-factor-agents](https://github.com/humanlayer/12-factor-agents)). |
| no-progress stop | If the error set is identical twice in a row, the feedback isn't helping. More attempts just burn money. |
| failure-specific feedback | Truncation gets "be more concise". Parse errors get the position. Schema errors get paths. "Try again" is not feedback. |

**Feedback vs blind retry.** A blind retry re-samples the same prompt and hopes. With feedback, the second sample is *conditioned on what went wrong*. `test_blind_retry_resends_identical_prompt_and_stops_on_no_progress` shows the mechanical difference: the blind path sends byte-identical messages, while the feedback path sends the errors.

**Cost math (hypothetical numbers, to reason with; measure your own).** Suppose 90% of first attempts are valid and feedback repairs 80% of failures per round. Then P(valid within 3 attempts) = 1 − 0.1 × 0.2 × 0.2 = 99.6%, and the expected number of calls is 1 + 0.1 + 0.02 = 1.12. A blind retry that only re-rolls the 90% first-pass rate gets 1 − 0.1³ = 99.9% if failures are independent. But they usually are not: the same ambiguous input fails the same way. That correlation is why blind retries plateau, and it is the same reason retrying a deterministic 400 from a downstream API never helps.

### What happens after the budget

A failure after the budget is a **dead letter**, not a crash and not a silent default. Write the input, every attempt, and every error set to a DLQ table, and page or queue it for a human ([06-human-in-the-loop.md](06-human-in-the-loop.md)). The DLQ is also your best eval data: every row is a real input your prompt can't handle ([Module 10](../10-evals-fundamentals/README.md)).

## Worked example: triaging a consumer-lag page

The input is a real-looking PagerDuty page plus four log lines from an `orders-billing` consumer group that is in a rebalance storm (the full text is `ALERT` in `repair_loop.py`). The pipeline turns it into a ticket.

**The bad version** is a single call, `json.loads`, done. On the first attempt the fake model (scripted to make the mistakes models commonly make) returns:

```json
{"service": "orders-consumer", "severity": "SEV1", "category": "rebalance_storm",
 "affected_partitions": [4, 5, 11, 5], "summary": "Rebalance storm.", "confidence": 85}
```

wrapped in a ```json fence. With constrained decoding, `SEV1` would have been forced into the enum, but `confidence: 85` and the 16-character summary would still pass, because the decoder doesn't enforce `maximum` or `minLength`. Without a validator, the ticket ships with 85 as a probability and no runbook link on a sev1.

**The good version.** Running `python repair_loop.py` offline gives this output. It was measured, but the "model" is a scripted `FakeClient`, so it demonstrates the loop mechanics, not model behavior:

```text
--- attempt 1: 3 error(s)
    [schema] $.severity: 'SEV1' is not one of ['sev1', 'sev2', 'sev3']
    [schema] $.summary: length 16 is below minLength 20
    [schema] $.confidence: 85 is above maximum 1
--- attempt 2: 1 error(s)
    [semantic] $ (rule evidence_grounded): evidence not found verbatim in the alert/log input: 'member orders-consumer-3 left group because poll interval exceeded'
--- attempt 3: 0 error(s)
=> ok=True stop_reason=valid
```

The second request carried this feedback turn, which is exactly what the model sees:

```text
Your previous output failed validation. Errors:
<validation_errors>
- $.severity: 'SEV1' is not one of ['sev1', 'sev2', 'sev3']
- $.summary: length 16 is below minLength 20
- $.confidence: 85 is above maximum 1
</validation_errors>
Return the complete corrected JSON object and nothing else. Change only what the errors require;
keep every other field as it was. If a field cannot be filled truthfully from the input, use the
schema's 'unknown' option or lower confidence rather than inventing a value.
```

Note attempt 2. The object is now schema-valid, including a correct runbook URL, but the evidence string is a *paraphrase* of the log line. A schema can't catch that; the grounding check can. The duplicate partition `5` in attempt 1 wasn't reported until the schema passed, because semantic checks only run on schema-valid data.

## Pitfalls

- **Valid but wrong.** Every layer here checks form and internal consistency, not whether `rebalance_storm` is the right diagnosis. *Detect:* sample validated outputs into an error-analysis queue, and add an LLM-judge or human label for correctness ([Module 11](../11-llm-as-judge/README.md)).
- **Lenient parsing hides prompt bugs.** "Find the first `{` and parse from there" turns a model that is chatting instead of answering into a silent success. *Detect:* log how often your parser needed to strip something. `extract_json` tolerates exactly one fence, nothing more.
- **Repair rounds that change correct fields.** A model asked to fix `confidence` sometimes rewrites the summary too. *Detect:* diff the attempt *n* and attempt *n*+1 objects. Fields that weren't in the error list shouldn't change. The feedback template asks for this explicitly.
- **Retrying refusals.** A `stop_reason: "refusal"` isn't a format error. Retrying it with "fix your JSON" is pointless and can look like pressure. Route refusals to a separate path.
- **Unbounded or context-growing retries.** Each feedback round appends the previous output and the errors. For big objects, consider sending only the last attempt plus the errors, rather than the whole history.
- **Case-sensitive enums with human-ish values.** Anthropic's docs note enum values may differ in capitalization. Decide whether to normalize (`.lower()`) before validating or to reject. Either way, decide on purpose.

## In your day job

- For every LLM call whose output is parsed by code, write down the three layers. If layer 2 is "we call `json.loads`", you have a production incident waiting.
- Put cross-field business rules (sev1 needs a runbook, refunds need an order id, the migration's `down` must reverse `up`) in a semantic-check list next to the schema, and unit-test them like any other validator.
- Give the repair loop a DLQ and look at it weekly. Its contents are your next eval cases.
- Track `attempts_per_success` and `dlq_rate` as SLIs. A jump after a prompt or model change is a regression even when final success stays flat ([Module 15](../15-observability-and-production/README.md)).
