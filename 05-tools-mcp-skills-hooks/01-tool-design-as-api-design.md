# 01: Tool design is API design for an unreliable client

## The idea

A tool is a contract between a deterministic system and a nondeterministic caller. Anthropic's tool-design guide frames it exactly that way, and its main claim is that the habits that make a good REST API (complete CRUD coverage, thin wrappers over endpoints) make a poor agent tool ([Anthropic, "Writing effective tools for agents"](https://www.anthropic.com/engineering/writing-tools-for-agents)). The agent doesn't need access to your data model. It needs to complete tasks, with the fewest tokens moving through its context and the fewest chances to call the wrong thing.

Each tool has four surfaces the model actually reads:
1. **The name**: chosen from a list on every turn, so it must be distinguishable at a glance.
2. **The description and input schema**: re-read on every turn. This is your API documentation *and* a prompt.
3. **The response**: copied into the context and kept there for the rest of the session.
4. **The error**: the model's input for its next attempt.

Bad tools fail on one of these four. Good tools are designed on all four, then tested with an eval.

## Why it matters

Three observations from Anthropic's own tool work:
- Claude's web search tool kept appending "2025" to queries, which biased the results. The fix was a better tool description, with no model change ([Anthropic](https://www.anthropic.com/engineering/writing-tools-for-agents)).
- In the SWE-bench agent, relative paths broke after the agent changed directories. Requiring absolute paths in the tool schema fixed it. The team reports spending "more time optimizing our tools than the overall prompt" ([Anthropic, "Building effective agents"](https://www.anthropic.com/engineering/building-effective-agents)).
- Claude Code caps tool responses at 25,000 tokens by default and warns above 10,000 for MCP output ([Claude Code MCP docs](https://code.claude.com/docs/en/mcp)). A single `SELECT *` gets near that cap.

That third point is measurable in this module's code. `bad_query_db(db, "SELECT * FROM payments")` against a 600-row table returns about 84,500 characters, roughly 21,000 tokens by the chars/4 estimate. That one call fills most of the default tool-output cap, and the result is a Python list of tuples with no column names.

## How to do it

### Name and namespace for selection
- **Namespace by service and resource**: `deploys_get_status`, `kafka_consumer_lag`, `logs_search`. Anthropic's examples are `asana_search` / `jira_search` (by service) and `asana_projects_search` / `asana_users_search` (by resource). They report that prefix vs suffix naming had "non-trivial effects" on their evals and that the effect varies by model, so treat naming as a parameter to test.
- **Unambiguous parameter names**: `user_id` rather than `user`, `since_minutes` rather than `window`. The unit belongs in the name.
- **Human-meaningful identifiers**: accept `merchant="Globex Rail"` and resolve it server-side. Anthropic reports that resolving UUIDs to meaningful names (or a 0-indexed scheme) "significantly improves Claude's precision in retrieval tasks by reducing hallucinations."

### Consolidate around tasks
Anthropic's examples: `list_users` + `list_events` + `create_event` becomes `schedule_event`; `read_logs` becomes `search_logs`; `get_customer_by_id` + `list_transactions` + `list_notes` becomes `get_customer_context`. The test is: *what is the next question the agent will ask after calling this?* If the answer is always "now aggregate it," do the aggregation in the tool.

### Make responses token-efficient
- **`response_format: "concise" | "detailed"`**. Concise returns what the model needs to reason; detailed adds the IDs it needs for a follow-up call. In Anthropic's Slack example, concise was 72 tokens vs 206 for detailed.
- **Always say "N of M"**. A page that looks like the full answer is a correctness bug: the model will conclude "there are 10 failed payments" when there are 420.
- **Paginate with an opaque cursor**, and say in the response how to fetch the next page.
- **Budget and truncate**, keeping head and tail for logs, and tell the model *how to narrow* ("add `level=ERROR`") rather than just "truncated."

### Write errors as instructions
An error message is a prompt. It should contain: what was wrong, the valid values or the nearest match, and the next tool to call. Compare:

| Opaque | Actionable |
|---|---|
| `KeyError: 'ledger-writer'` | `Unknown consumer group 'ledger-writer'. Did you mean 'ledger-writer-v2'? (Call kafka_list_consumer_groups to see all 3 options.)` |
| `OperationalError: no such column: merchant` | `SQL error: no such column: merchant. Tables: payments(id, merchant_id, ...), merchants(id, name). Join merchants to filter by merchant name.` |
| `ValueError: invalid literal for int()` | `cursor 'abc' is not valid. Pass back the exact cursor string from the previous page, or omit it.` |

Separate the two error classes. **Model-fixable** errors (bad argument, unknown name) go back as an `is_error: true` tool result. **Infrastructure** errors (API unreachable) say they're transient and how many retries make sense, so the model doesn't "fix" a correct call. In MCP Python SDK v2, only a `ToolError`'s message reaches the model; any other exception shows up as a generic "Error executing tool <name>" ([MCP Python SDK, what's new in v2](https://py.sdk.modelcontextprotocol.io/whats-new/)). So raising the right exception type decides whether the model can see the fix at all.

### Validate before executing
Bind arguments against the signature before calling the function, so a typo in an argument name returns "Accepted parameters: [...]" instead of a `TypeError` from somewhere inside your implementation. `ops_tools.call_tool` does this with `inspect.signature(fn).bind(**args)`.

## Worked example: redesigning `query_db`

Situation: on-call is paged for elevated payment failures. The agent has one database tool.

### Before

```json
{"name": "query_db",
 "description": "Query the database.",
 "input_schema": {"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]}}
```

The transcript below uses real tool outputs from `code/query_db_redesign.py` (`python query_db_redesign.py`). The model turns are illustrative.

```text
user: Payments are failing for Globex Rail. What's going on?

assistant (illustrative): -> query_db(q="SELECT * FROM payments WHERE merchant = 'Globex Rail' AND status_code = 'failed'")
tool_result (is_error): OperationalError: no such column: merchant

assistant (illustrative): -> query_db(q="SELECT * FROM payments WHERE status = 'failed'")
tool_result: [('pay_00002_3926f28c105d', 'm_c3a9e1d7-5b2f-4e86-8a14-7f0c2b9d6e35', 41428, 'USD', 'failed',
  'issuer_timeout', 1759999131, 'idem_953f48f1a09f76b5'), ('pay_00010_f6460a097c97', ... ]
  (11,017 chars, ~2,750 tokens, every merchant, every time window, no column names)
```

Why it fails, surface by surface:
- **Name/description**: "Query the database" gives no schema, so the model must guess (`merchant`, `status_code`).
- **Response**: no column names, no limit, no time filter, merchants as UUIDs. The model has to infer which tuple position is the failure code and which UUID is Globex.
- **Error**: the raw driver error says what's wrong but not what's right. The model guesses again.
- **Task fit**: the question is an aggregate ("failure rate and why"). The tool returns rows and makes the model do the `GROUP BY` in its head.

### After

Three tools, shaped around the questions on-call actually asks:

```json
{"name": "payments_failure_summary",
 "description": "Failure rate and failure-code breakdown for ONE merchant over the last N minutes, compared with the prior 24h. Start here for 'are payments failing for X' questions.",
 "input_schema": {"type": "object", "properties": {
   "merchant": {"type": "string", "description": "Merchant name, e.g. 'Globex Rail'."},
   "since_minutes": {"type": "integer", "minimum": 5, "maximum": 1440, "default": 60}},
   "required": ["merchant"]}}
```

plus `payments_search` (filtered, paginated, concise by default) and `payments_sql_readonly` (an escape hatch: one `SELECT`, `PRAGMA query_only` enforced by SQLite, row-capped, and errors that list the real columns).

```text
user: Payments are failing for Globex Rail. What's going on?

assistant (illustrative): -> payments_failure_summary(merchant="globex", since_minutes=30)
tool_result: merchant=Globex Rail window=30m payments=70 failed=42 failure_rate=60.0% (baseline prior 24h: 6.9% of 130).
failure codes in window: issuer_timeout=39, do_not_honor=2, card_declined=1.

assistant (illustrative): -> payments_search(merchant="Globex Rail", status="failed", since_minutes=30, limit=3)
tool_result: 3 of 42 payments (concise).
age_min=0 | amount_cents=39959 | status=failed | failure_code=issuer_timeout
age_min=0 | amount_cents=34780 | status=failed | failure_code=issuer_timeout
age_min=1 | amount_cents=15946 | status=failed | failure_code=issuer_timeout
[more payments available: call again with cursor='3' to get the next page.]

assistant (illustrative): Globex Rail's failure rate is 60% over the last 30 minutes vs 6.9% baseline, and 39 of 42
failures are issuer_timeout. This looks like an issuer-side outage, not our code.
```

And if the model reaches for raw SQL with the wrong column, the escape hatch teaches it the schema in one step:

```text
-> payments_sql_readonly(sql="SELECT merchant, COUNT(*) FROM payments GROUP BY merchant")
tool_result (is_error): SQL error: no such column: merchant. Tables: payments(id, merchant_id, amount_cents, currency,
status, failure_code, created_at, idempotency_key), merchants(id, name). Join merchants to filter by merchant name.
Timestamps are epoch seconds.
```

Measured (chars/4 estimate, from `python query_db_redesign.py`): the summary is about 46 tokens and answers the question. The unfiltered failed-rows dump is about 2,750 tokens and doesn't. `SELECT *` is about 21,000.

What changed, mapped to the rules: task-shaped consolidation (summary does the aggregation), semantic identifiers (`merchant="globex"` resolves to `Globex Rail`), enums on `status` and `failure_code`, "N of M" headers, a cursor, and errors that carry the schema. The escape hatch is still there because the summary tools will never cover every question. It just can't write, and it can't flood the context.

## Pitfalls

| Pitfall | How to detect it |
|---|---|
| Wrapping every endpoint 1:1 | Trace shows chains of `list_*` then `get_*` calls for one question. Count tool calls per task in your eval. |
| Concise mode that drops the IDs needed later | Model calls `detailed` immediately after every `concise` call, or hallucinates IDs. Grep traces for back-to-back calls of the same tool. |
| Silent truncation | Model states totals that equal your page size. Add an eval case where the true count exceeds `limit`. |
| Errors written for humans reading logs | `is_error` results followed by a retry with the same arguments. Track "repeat-after-error" rate in traces. |
| Catching every exception as "model error" | The model retries forever against a down dependency. Make infra errors say "transient; retry once, then report." |
| Descriptions that drift from behavior | Tool returns fields its description doesn't mention, or vice versa. Snapshot-test descriptions alongside implementations. |
| Optimizing tools without an eval | You can't tell whether a rename helped. Anthropic's loop: generate realistic multi-call tasks, run them, track accuracy, tool calls, tokens and errors, keep a held-out set ([Anthropic](https://www.anthropic.com/engineering/writing-tools-for-agents)). See [Module 10](../10-evals-fundamentals/README.md). |

## In your day job
- Pick the agent tool your team uses most. Run ten real tasks through it, count tokens per tool result, and find the one response that is over 2k tokens. Give it a `response_format` and an "N of M" header.
- Grep your traces for `is_error` results and read the next model turn after each. Every blind retry is an error message to rewrite.
- Replace any `query_db`/`run_sql` tool with one or two task-shaped tools for the top questions, and keep a read-only, row-capped escape hatch.
- Put tool descriptions under code review like API docs. A one-line description change is a behavior change.
