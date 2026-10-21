# 05: CLAUDE.md and AGENTS.md: a map, not a manual

## The idea

A context file (`CLAUDE.md` for Claude Code, `AGENTS.md` for Codex and most other agents) is the one piece of context you pre-load into **every** session in a repo. That makes it the most expensive text you write per word, and the most leveraged.

OpenAI's harness-engineering team states the design rule well. About 100 lines that "give Codex a map, not a 1,000-page instruction manual", with a versioned `docs/` directory as the system of record. They add that "anything it can't access in-context while running effectively doesn't exist", so knowledge that lives in Slack or in someone's head has to move into the repo ([OpenAI, "Harness engineering"](https://openai.com/index/harness-engineering/)). Anthropic's Claude Code docs say "target under 200 lines per CLAUDE.md file. Longer files consume more context and reduce adherence." They also say to move anything that matters for only part of the codebase into path-scoped rules ([Claude Code docs, memory](https://code.claude.com/docs/en/memory)).

A map contains:

- what this repo is, in two lines
- the commands to build, test, lint and run, exactly as you'd type them
- the layout: which directory holds what
- the invariants an agent can't discover by reading code ("the ledger is append-only")
- pointers to where everything else lives, and when to read each

A manual contains everything else, and that is what you are cutting.

## Why it matters

Context files fail in two opposite directions, and practitioners disagree about which failure is worse.

- **Too much.** Every line competes for attention on every turn, and contradictions between lines make behaviour arbitrary: "if two instructions contradict each other, Claude may pick one arbitrarily" (Claude Code memory docs). The repomirror team found that a 1,500-word "improved" prompt made their agent slower and worse, and cut it back to 103 words ([repomirror](https://github.com/repomirrorhq/repomirror/blob/main/repomirror.md)). Anthropic's best-practices page lists the "over-specified CLAUDE.md" as a named failure pattern ([Claude Code best practices](https://code.claude.com/docs/en/best-practices)).
- **Too little, or the wrong thing.** An agent without a map greps blindly, and misses the one invariant that isn't visible in the code.

The two camps:

- **The context file is the core harness artifact.** One step in Mitchell Hashimoto's adoption guide is "engineer the harness": every agent mistake becomes either an AGENTS.md line or a purpose-built tool ([Hashimoto, "My AI adoption journey"](https://mitchellh.com/writing/my-ai-adoption-journey)). Boris Cherny is reported to describe the Claude Code team's habit the same way: when Claude does something wrong, they add it to CLAUDE.md (reported by VentureBeat, secondary).
- **Context files are probabilistic and decay.** Geoffrey Huntley argues that skill packs and AGENTS.md are probabilistic, that you should test them against runs without them, and that you should delete and re-test every few months because a new model can make old tuning counterproductive ([Huntley, "nobody should type code by hand anymore"](https://ghuntley.com/agency/)).

**Course stance** (from [01-gap-analysis](../research/01-gap-analysis.md)): treat context files as code. Test with and without them, and prune them on model upgrades. Both camps are right about a different phase of the file's life. Adding lines in response to observed failures is how the file grows correctly, and ablation is how it stays correct.

## How it works / how to do it

### The admission test for each line

Anthropic's question, applied line by line: "Would removing this cause Claude to make mistakes?" Then route each line to the cheapest place that still works:

| If the line is... | Put it in | Context cost |
|---|---|---|
| Needed in nearly every session, and not discoverable from the code | The root map | Every call |
| Relevant only in one directory | A nested `CLAUDE.md` / `AGENTS.md` in that directory | Only after the agent touches that directory |
| Relevant only for certain file types or paths | `.claude/rules/*.md` with `paths:` frontmatter | Only when a matching file is read or edited |
| A multi-step procedure (release, backfill, rotation) | A skill (`.claude/skills/<name>/SKILL.md`) | Name and description always; body on use |
| Enforceable by a tool (format, imports, forbidden paths) | A linter, a hook, or a permission rule | Zero, and it can't be ignored |
| Reference material (architecture, ADRs, API docs) | `docs/`, with a pointer from the map | Only when read |
| Something the model already does by default | Nowhere | Zero |

These are Claude Code mechanics as of October 2026. Subdirectory CLAUDE.md files "load on demand" when Claude reads or edits a file in that directory. Path-scoped rules load when a matching file is read, written or edited. `@path` imports "don't reduce its context cost, because imported files also load at launch". Block-level HTML comments (`<!-- ... -->`) are stripped before injection, so you can leave notes for human maintainers for free. Claude Code reads `AGENTS.md` when there is no `CLAUDE.md` ([memory docs](https://code.claude.com/docs/en/memory)). Codex aggregates AGENTS.md files with more specific ones later, capped at 32 KiB by default ([OpenAI, "Unrolling the Codex agent loop"](https://openai.com/index/unrolling-the-codex-agent-loop/)).

### Write lines that can be checked

The Claude Code docs: write instructions "concrete enough to verify". "Run `npm test` before committing" instead of "Test your changes"; "API handlers live in `src/api/handlers/`" instead of "Keep files organized". A verifiable line can also be *tested*: you can grep a transcript to see whether it was followed.

Use emphasis sparingly. Explain the *why* instead of shouting. Anthropic's prompting guide makes the same point with its ellipsis example: a reason ("the TTS engine can't pronounce them") generalizes better than "NEVER" ([prompting best practices](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices)).

## Worked example: a 600-line CLAUDE.md trimmed to a 90-line map

**Situation.** `billing-platform` is a monorepo with `ledger-api` (Go), `invoice-consumer` (Java, Kafka), Flyway migrations for Postgres, and Helm charts. Over 18 months its CLAUDE.md grew to 600 lines. Engineers complain that the agent ignores half of it.

**The bad version.** An inventory of the 600 lines:

| Section | Lines | What's wrong |
|---|---|---|
| Team history, owners, Slack channels | 45 | Not actionable by an agent |
| Architecture essay (2024) | 80 | Stale: describes a service that was split in 2025. Duplicates `docs/` |
| Go and Java style rules | 110 | `golangci-lint` and `spotless` already enforce 90% of them |
| Kafka consumer conventions | 60 | Only relevant inside `services/invoice-consumer/` |
| Migration rules | 50 | Only relevant inside `migrations/` |
| Release procedure (14 steps) | 70 | A procedure, needed about once a week |
| Pasted incident runbooks | 90 | Large and task-specific |
| "IMPORTANT / NEVER" list | 40 | 12 duplicates of rules above, and 3 contradictions |
| Testing how-to | 35 | 6 useful lines; the rest is a JUnit tutorial |
| Generic advice ("write clean code", "think step by step") | 20 | The model's default behaviour |

A few real-looking lines from it:

```markdown
- IMPORTANT: ALWAYS use table-driven tests in Go!!!
- Never use fmt.Println, use the logger.
- NEVER EVER edit a migration file.
- You may edit V0xx migrations if they haven't shipped yet.        <- contradicts the line above
- Our architecture follows hexagonal principles (see diagram in Confluence).  <- unreachable
- Use 4 spaces for Java indentation.                               <- spotless already enforces it
```

**The good version: the 90-line map.**

```markdown
# billing-platform

Payments ledger and invoicing. Go service `ledger-api` (HTTP, Postgres) and Java
service `invoice-consumer` (Kafka -> ledger). Money moves here: correctness beats speed.

## Commands (run from repo root)
- Build all: `make build`
- Unit tests, fast (<60s): `make test`
- One Go package: `go test ./services/ledger-api/internal/posting/...`
- One Java test: `./gradlew :invoice-consumer:test --tests '*SettlementTest'`
- Integration tests (needs Docker, ~6 min): `make it`
- Lint + format (CI runs the same): `make lint` / `make fmt`
- Local stack: `make up` (Postgres, Kafka, Redis via docker compose), `make down`
- Before you say a change is done: `make fmt lint test` must pass. Paste the tail of the output.

## Layout
- `services/ledger-api/` Go. `cmd/` entrypoints, `internal/posting/` double-entry logic,
  `internal/api/` handlers, `internal/store/` Postgres access (sqlc, generated, see below)
- `services/invoice-consumer/` Java 21, Kafka consumer. Has its own CLAUDE.md.
- `migrations/` Flyway SQL for ledger-db. Path rules in `.claude/rules/migrations.md`.
- `charts/` Helm. `deploy/<service>/values.yaml` holds per-env config.
- `runbooks/` on-call runbooks. Search them; don't paste them into chat.
- `docs/` system of record: architecture, ADRs, glossary. Start at `docs/README.md`.

## Invariants (not visible from the code alone)
- The ledger is append-only. Corrections are new reversing entries, never UPDATE/DELETE
  on `ledger_entries`. Why: auditors reconstruct balances from the entry log.
- Every write endpoint takes an `Idempotency-Key`; keys live in Redis for 24h.
  A retry with the same key must return the original response, not post twice.
- Money is `int64` minor units plus an ISO currency code. Never floats. Never mix currencies
  in one sum.
- `invoice_id` is unique per region, not globally. Always pair it with `region`.
- Kafka: at-least-once delivery. Consumers must be idempotent on `(region, invoice_id, version)`.
- Reads that must see a just-committed write go to the primary (`store.Primary()`).
  The replica can lag by seconds.

## Generated code: do not hand-edit
- `services/ledger-api/internal/store/db/` is generated by sqlc from `queries/*.sql`.
  Change the SQL, then run `make generate`.
- `api/openapi.yaml` is the source; `internal/api/gen/` is generated by `make generate`.

## Debugging and observability
- Local logs: `make logs svc=ledger-api`
- Staging logs: `billing-ctl logs --service <svc> --env staging --since 30m`
- Staging metrics: `billing-ctl metrics query '<promql>' --env staging`
- Trace a request: every response carries `X-Request-Id`; run `billing-ctl trace <id>`
- Reproduce a consumer bug: `make replay topic=invoices.v2 file=testdata/<case>.jsonl`
  replays recorded messages into the local stack.

## Environments and permissions
- Local stack: run anything.
- Staging: read-only commands only (`logs`, `metrics`, `trace`, `describe`).
- Production: never. If you think you need prod access, stop and explain why.
- Secrets: `make env` writes `.env.local` (gitignored). Never print, log or commit them.

## How we work
- Small PRs. One logical change per commit, message format `area: summary` (e.g. `posting: ...`).
- Fix the root cause; do not add sleeps or retries to make a test pass.
- New behaviour needs a test that fails before the change. Show it failing, then passing.
- If a task needs a schema change, stop and write a plan in `docs/plans/` first.
- Ask before: changing anything under `charts/`, touching prod config, adding a dependency.

## Where to look
| Need | Read |
|---|---|
| How posting and balances work | `docs/architecture/ledger.md` |
| Why we made a design choice | `docs/adr/` (index in `docs/adr/README.md`) |
| Domain terms (settlement, reversal, dunning) | `docs/glossary.md` |
| Releasing a service | the `release` skill (`/release`) |
| Backfills and data fixes | the `ledger-backfill` skill |
| An alert you're debugging | `runbooks/`, search by alert name |
| Testing conventions in depth | `docs/testing.md` |
| Kafka consumer conventions | `services/invoice-consumer/CLAUDE.md` |

## Gotchas that cost us incidents
- `allkeys-lru` on the idempotency Redis caused duplicate charges (INC-6120). The policy
  is `volatile-ttl`; there is a check in `make lint`.
- Integration tests read from the primary via `application-it.yml`. If a test needs a
  `sleep`, it is probably reading the replica.
- `make test` skips tests tagged `slow`; CI runs them. Run `make it` before claiming
  a consumer change is done.

<!-- Maintainers: keep this file under 100 lines. Every line must pass "would removing it
cause a mistake?". Procedures go to skills, path rules to .claude/rules/, style to linters.
Ablate on every model upgrade: see docs/agents/context-file-evals.md -->
```

That is 85 lines including blanks, so call it a 90-line map. The HTML comment at the bottom costs zero tokens in Claude Code because it is stripped before injection.

**What moved where:**

| From the old file | Now | Mechanism |
|---|---|---|
| Team history, Slack channels (45) | Deleted; owners are in `CODEOWNERS` | n/a |
| Architecture essay (80) | `docs/architecture/ledger.md`, rewritten; one pointer line | JIT read |
| Style rules (110) | Deleted; the 11 not enforced became `golangci-lint` and `spotless` rules | Linter (zero tokens) |
| Kafka conventions (60) | `services/invoice-consumer/CLAUDE.md` (24 lines) | Nested file, loaded on demand |
| Migration rules (50) | `.claude/rules/migrations.md` with `paths: ["migrations/**"]` (15 lines), plus a hook | Path-scoped rule plus enforcement |
| Release procedure (70) | `.claude/skills/release/SKILL.md` | Skill, body loaded on use |
| Pasted runbooks (90) | `runbooks/` already existed; one pointer line | JIT search |
| IMPORTANT/NEVER list (40) | 6 invariants with reasons, plus an environments-and-permissions block, in the map; 2 rules became hooks; duplicates and contradictions deleted | Map plus hooks |
| Testing how-to (35) | 4 lines in the map; the rest in `docs/testing.md` | Map plus JIT read |
| Generic advice (20) | Deleted | n/a |

The migration contradiction ("never edit" against "you may edit unshipped ones") got resolved by asking the owner, then **enforced** instead of being written down twice. The rule file:

```markdown
---
paths:
  - "migrations/**"
---
# Migration rules
- Never modify a migration that exists on `main`; a hook blocks it. Add a new V<n+1> file instead.
- Migrations must be expand/contract: add nullable column -> backfill -> enforce, in separate releases.
  Why: code rollback (see runbooks/deploy-rollback.md) must not require a schema rollback.
- Every migration needs a matching `U<n>__*.sql` undo script, even if it is a no-op.
- Run `make migrate-check` (applies to a throwaway Postgres and diffs the schema).
```

And the hook that makes "never modify a shipped migration" true no matter what the model decides, in `.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [{ "type": "command", "command": "scripts/hooks/block-shipped-migrations.sh" }]
      }
    ]
  }
}
```

The script reads the tool input as JSON on stdin, checks whether `tool_input.file_path` is under `migrations/` and already exists on `origin/main`, and exits with code 2 and a message ("add a new V<n+1> migration instead") if it is. Exit code 2 blocks the call and returns the message to the model. Hook mechanics are covered in [Module 05](../05-tools-mcp-skills-hooks/README.md) and [Module 14](../14-steering-and-guardrails/README.md). Check the current hooks docs for the exact input schema.

### Test it: with, without, and old against new

A context file is a change to the agent's behaviour, so it gets an A/B test. The protocol:

1. **Task suite.** Twenty tasks taken from the last two months of merged PRs, each with an objective check: the PR's tests, plus 2 or 3 grep-able rule checks. Examples: "no UPDATE on `ledger_entries`", "no edits to shipped migrations", "`Idempotency-Key` handled on the new endpoint".
2. **Three arms.** Old 600-line file, new 90-line map plus its satellites, and **no context file at all**.
3. **Trials.** Three runs per task per arm, because agent runs are noisy ([Module 12](../12-hill-climbing/README.md) covers why and how many).
4. **Metrics.** Pass rate, rule violations, tokens per task, turns per task.

(illustrative results; your numbers will differ)

| Arm | Pass rate | Rule violations / 60 runs | Median input tokens / task |
|---|---|---|---|
| No file | 52% | 19 | 410k |
| Old 600 lines | 63% | 11 | 520k |
| New 90-line map | 70% | 4 | 360k |

How to read a table like this, even an illustrative one:

- **"No file" is the important baseline.** If "no file" ties with your file, the file isn't earning its tokens. Huntley's point is that you can't know this without running the comparison.
- **Violations matter more than pass rate here.** They are the failures your tests don't catch.
- **With 20 tasks and 3 trials, a 7-point pass-rate gap may be noise.** Use a paired comparison per task before you declare a winner (see [Module 12](../12-hill-climbing/README.md)).

## Pitfalls

- **Treating the file as append-only.** Detect it: `git log --stat CLAUDE.md` shows only additions. Schedule a prune, and run the ablation on every model upgrade.
- **Contradictions across layers** (root map, nested file, rules, user-level file). Detect it: as of October 2026, Claude Code's memory docs describe a `/doctor prompt-audit` command that looks for conflicting and outdated instructions. Otherwise, grep for the same keyword across all instruction files.
- **Imports mistaken for savings.** `@docs/architecture.md` loads the file at launch, so it costs the same as pasting it. Use a plain pointer ("read `docs/architecture.md` when...") for JIT loading.
- **Rules that should be enforcement.** Detect it: any line containing "never" that a script could check. Move it to a lint, hook or permission.
- **Unverifiable lines.** "Write good tests" can't be checked. Detect it: for each line, ask what transcript evidence would show it was followed.
- **Stale pointers.** A map that points to a moved file is worse than no map. Detect it: a CI check that every path in the context file exists. That's a ten-line script, and a good first agent task.

## In your day job

- Count the lines in your repo's CLAUDE.md/AGENTS.md. If it's over 150, run the inventory table above on it this week.
- Add a CI check that every backticked path in the context file exists.
- Before adding a line after an agent mistake, ask whether a lint or hook could prevent the mistake instead.
- Run the three-arm ablation (none, current, candidate) on 10 to 20 real tasks before and after each major model upgrade.
