# Examples: tools, MCP, skills and hooks on a Monday

Model outputs below are `(illustrative output)` unless they come from this module's code, which is marked.

---

## 1. The log tool that ate the incident

**Situation.** During a payments incident, your agent calls `get_logs(service="payments-api")`. The tool wraps your log store's HTTP API and returns the last 1,000 lines.

**Naive approach and what happens.** Each call returns about 30k tokens, mostly INFO health checks. Claude Code saves an oversized MCP result to a file or truncates it, and the agent reasons over a fragment. After three calls the context is mostly log noise, and the agent's summary quotes a health-check line as the "error." (illustrative)

**AI-native approach.**
1. Rename and reshape: `logs_search(service, query, level, since_minutes, limit, cursor, response_format)`. A description that says "Always pass `query` or `level`; unfiltered searches return mostly INFO noise."
2. Enforce the budget in the tool, not in the model's goodwill: `limit` max 50, `since_minutes` max 1440, "N of M" header, cursor.
3. For a single huge blob (a stack trace or one JSON document), keep head and tail with `truncate_text(..., hint="Use logs_search with query='<exception class>' to find related lines")`.
4. Real output from `code/ops_tools.py`:

```text
5 of 14 log lines (concise).
age_min=0 | level=ERROR | msg=deserialization failed partition=3 offset=88123401: unknown enum value 'REFUND_PARTIAL'
...
[more log lines available: call again with cursor='5' to get the next page.]
```

**What to check.**
- p95 tokens per `logs_search` result in traces (target: under 2k).
- How often the agent pages past page 1. If it's often, the default `limit` is wrong. If it's never, it may not be noticing the cursor line.
- An eval case where the decisive line is on page 2.

---

## 2. Rolling an internal MCP server out to four teams

**Situation.** Your deploy-status MCP server ([03-mcp](03-mcp.md)) worked well for on-call over stdio. Now four teams want it, and two of them use agents with no shell.

**Naive approach and what happens.** Everyone copies the stdio config, each with their own long-lived API token in `.mcp.json`. Six weeks later there are nine forks of the server with drifting descriptions, one of which added a `rollback` tool, and nobody can say which agents can trigger rollbacks.

**AI-native approach.**
1. Run one Streamable HTTP deployment: bind behind your ingress, validate `Origin`, authenticate with your SSO-issued tokens. Make it stateless (the 2026-07-28 spec model), so it scales like any service.
2. Split by risk: `deploy-status` (read) and `deploy-actions` (rollback, pause). Different servers, different auth scopes.
3. Publish the read server in a project `.mcp.json`:

```json
{"mcpServers": {"deploy-status": {"type": "http", "url": "https://deploys.internal/mcp",
                                  "headers": {"Authorization": "Bearer ${DEPLOY_STATUS_TOKEN}"}}}}
```

4. Attach `deploy-actions` only to the release agent, whose `PreToolUse` hook returns `ask` for every `mcp__deploy-actions__.*` call.
5. Snapshot-test tool descriptions in the server repo. A description change goes through review like an API change, because it is one.

**What to check.**
- Server access logs: tool calls per agent identity. Any `deploy-actions` call from an unexpected agent is a config bug.
- Descriptions in prod match the reviewed snapshot.
- Per-team eval before and after switching to the shared server (no regressions from the description consolidation).

---

## 3. Verifying a backfill across 300 partitions

**Situation.** A data pipeline backfilled `events_daily` for 300 date partitions. You want to verify row counts against the source and find mismatches.

**Naive approach and what happens.** The agent has `warehouse_count(table, partition)`. It calls it 600 times (source and target). In practice it samples 12 partitions, finds them equal, and reports "backfill verified." (illustrative) The 3 bad partitions weren't in the sample.

**AI-native approach.** Code-as-action ([04-code-as-action](04-code-as-action.md)):
1. Give the agent a sandboxed `execute_python` with read-only `warehouse_count` bound in. The description says only printed output returns, capped at 2,000 chars.
2. The model writes:

```python
bad = []
for d in partitions("events_daily"):
    s, t = warehouse_count("raw.events", d), warehouse_count("events_daily", d)
    if s != t:
        bad.append((d, s, t, t - s))
print(f"{len(bad)} of {len(partitions('events_daily'))} partitions mismatch")
for row in sorted(bad, key=lambda r: abs(r[3]), reverse=True)[:20]:
    print(row)
```

3. The context gets about 4 lines instead of 600 results. The check is exhaustive, so "verified" means verified.
4. Save the script as `scripts/verify_backfill.py` in a `backfill-verification` skill.

**What to check.**
- The script's coverage: it should print the denominator (`of 300`). An answer without a denominator is a sample.
- Sandbox limits: wall-clock timeout and no write credentials to the warehouse.
- Per-call spans inside the sandbox, so the trace still shows 600 queries.

---

## 4. Gating `terraform apply`

**Situation.** Agents help with infra changes in a Terraform monorepo. They should be able to run `plan` freely and must never `apply` without a human.

**Naive approach and what happens.** A CLAUDE.md line, "Never run terraform apply." An agent fixing a drift issue runs `terraform apply -auto-approve -target=module.kafka` because the task said "make the drift go away." (illustrative)

**AI-native approach.**
1. Remove the possibility: the agent's environment has a plan-only role (read state, no write to the cloud provider). This is the real control.
2. Add the mistake-catcher anyway: a `PreToolUse` hook modeled on `code/hooks/block_kubectl_delete.py` that returns `ask` for `terraform apply` / `destroy` and `deny` for `-auto-approve`, with the reason "Run `terraform plan -out=tfplan` and show the summary; a human applies."
3. Add a `Stop` gate: if `*.tf` files changed in the session, `terraform fmt -check` and `terraform validate` must pass before the agent can finish.
4. Tests for the hook, using the same subprocess harness as `test_hook.py`.

**What to check.**
- Hook test coverage: `terraform -chdir=infra apply`, `tf apply` (an alias), `make apply` (a Makefile target that calls apply). The last one is invisible to a command-parsing hook, which is why step 1 exists.
- Stop gate: does it fire only when `.tf` files changed? Time it.

---

## 5. Turning the schema-migration runbook into a skill

**Situation.** Your team has a strict process for online schema migrations on a sharded Postgres fleet: expand, backfill in batches, dual-write, verify, contract. Agents keep proposing single-step `ALTER TABLE`s.

**Naive approach and what happens.** The 600-line migration guide goes in CLAUDE.md. It costs about 8k tokens per session, the agent still skips the verify step in long sessions, and unrelated sessions occasionally "helpfully" mention migrations. (illustrative)

**AI-native approach.**
1. Skill `online-schema-migration` with a description naming the triggers: "ALTER TABLE, add column, rename column, change type, drop column, index on a large table."
2. Body: the five phases as numbered steps, each ending in a **checkable artifact** (a migration file, a backfill job config, a verification query with expected output).
3. `scripts/check_migration.py`: lints a migration file for locking operations (`ALTER TABLE ... ADD COLUMN ... DEFAULT` on old Postgres versions, non-concurrent index creation) and prints violations. The skill says "run it on every migration you write."
4. `references/locking.md` for the lock-level table, loaded only when the script flags something.
5. A trigger eval with 15 prompts, including negative controls ("write a SELECT to count users by plan").

**What to check.**
- Trigger precision and recall on the eval.
- Task success with the skill vs without it on 5 real past migrations. If it doesn't move, the skill isn't earning its place.
- `check_migration.py` has its own unit tests. It's the part of the skill you can verify deterministically.
