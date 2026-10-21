# 02: Pillar 1, Understand: making the system legible to an agent

## The idea
An agent starts every session with amnesia. It knows the language and the libraries. It does not know:
- your service boundaries;
- which table belongs to whom;
- why the relay stops on the first failure;
- that `offset` and `event_id` are not interchangeable.

Pillar 1 is the set of artifacts that let it reconstruct that understanding *fast*, *on demand* and *correctly*:

| Artifact | Answers | Size |
|---|---|---|
| `AGENTS.md` (root) | Where is everything? What does "done" mean? What are the commands? | about 40–100 lines; a map |
| Nested `AGENTS.md` | Local rules for this directory | 5–20 lines each |
| `ARCHITECTURE.md` | Components, data flow, ownership, event contracts | 1–2 pages |
| `INVARIANTS.md` | What must never break, why, and what enforces it | one section per guarantee |
| `docs/adr/` | Why it is this way, and which alternatives were rejected | one page each |
| `docs/glossary.md` | What the overloaded words mean *here* | a table |
| Skills | Procedures loaded when the task matches (triage, migrations) | one SKILL.md each |
| Code search | Finding the code that the docs point at | tools, not docs |

The organizing principle is **progressive disclosure**. The always-loaded file is a short map. Detail lives one link away and gets loaded only when the task touches it. That is the same reason you put an index in front of a table rather than scanning it.

## Why it matters
OpenAI's harness team describes their AGENTS.md as about 100 lines that give the agent "a map, not a 1,000-page instruction manual". A versioned `docs/` directory is the system of record. They also make the point that knowledge sitting in Slack or Google Docs, which the agent cannot reach while it runs, effectively does not exist for it ([OpenAI, "Harness engineering"](https://openai.com/index/harness-engineering/)). Anthropic's long-running-harness work found that each new session "starts with amnesia". Their fix was durable files the next session reads first, such as progress notes and a feature list ([Anthropic, "Effective harnesses for long-running agents"](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)).

Mitchell Hashimoto's rule for growing these files is the most practical one you will find. Anytime an agent makes a mistake, engineer a fix so that it does not recur: either an AGENTS.md line or a purpose-built tool. "Each line in that file is based on a bad agent behavior" ([Hashimoto, "My AI Adoption Journey"](https://mitchellh.com/writing/my-ai-adoption-journey)).

The distributed-systems failure story is the one in [01](01-what-a-harness-is.md). An agent adding a request field cannot know it belongs in the idempotency hash unless something tells it, at the moment it is editing `create_order`.

## How to do it

### 1. AGENTS.md is a map
Keep it to the things the agent needs *on every task*:
1. **What this is**: two or three sentences, naming the main modules.
2. **Read before changing**: links to ARCHITECTURE, INVARIANTS, ADRs and the glossary, with one line each on when to read them.
3. **Definition of done**: one command. In this module that is `python tools/check.py`.
4. **Commands**: the five or six the agent will need, each with an example invocation. Willison's advice is to document shell commands in AGENTS.md with one example each, in preference to wrapping them in MCP ([Willison, "Designing agentic loops"](https://simonwillison.net/2025/Sep/30/designing-agentic-loops/)).
5. **Protocol for bugs and incidents**: a pointer to the skill.
6. **Conventions that a lint does not yet enforce.** Each one is a candidate for a lint. When the lint exists, delete the line.

Leave out style rules that a formatter handles, long explanations that belong in a linked doc, and anything that is true of all Python code.

Tool-specific loading: Codex aggregates AGENTS.md files from the repo root down to the working directory, with more specific files later and a default 32 KiB cap ([OpenAI, "Unrolling the Codex agent loop"](https://openai.com/index/unrolling-the-codex-agent-loop/)). Claude Code reads `CLAUDE.md`. Per its memory docs as of 2026, subdirectory files are pulled in when the agent works in that subtree, and a CLAUDE.md can import another file with `@path`. Either point `CLAUDE.md` at `@AGENTS.md` or symlink it, so that you maintain one file. Check your agent's current docs, because this behavior changes.

### 2. INVARIANTS.md: the most valuable file in a distributed system
Most "AI broke prod" stories in distributed systems are invariant violations that pass unit tests. Write each invariant with four fields:

```markdown
## I4. Idempotent consumers
**Rule.** A consumer inserts (consumer, event_id) into processed_events in the same
transaction as its read-model write, and skips the event on conflict. Dedupe on
event_id, which is the outbox row id.
**Why.** Delivery is at-least-once in two ways: broker redelivery of uncommitted
offsets (same offset), and relay republish after a crash between publish and mark
(new offset). Dedupe on (partition, offset) handles only the first.
**Enforced by.** lint INV004; test_consumer_skips_redelivered_message; repro.py republish
**Typical break.** Dedupe key built from msg.partition/msg.offset. Symptom: read-model
drift after a relay restart.
```

The **Typical break** field earns its keep. It is the failure you have seen, written so the agent can recognize itself about to make it. The **Enforced by** field turns the doc into an index of checks, and it tells you where enforcement is missing.

Use this checklist to find the invariants you have not written down:

| Category | Questions to answer |
|---|---|
| Ordering | Ordered per what key? Who preserves it: the producer, the broker, the consumer? What happens on partial failure? |
| Idempotency | Which operations are idempotent, and keyed by what? What goes into the request hash? How long are keys retained? |
| Delivery and retry | At-most-once or at-least-once? Where do duplicates come from (broker, producer retry, relay crash)? Which retries are safe? |
| Consistency | Which reads are strongly consistent, read-your-writes, or eventual? Which tables are derived and rebuildable? |
| Atomicity | Which writes must commit together? Where are the dual writes, and what protects them (outbox, saga)? |
| State machines | Legal transitions? What is emitted on each? Which are terminal? |
| Time | Whose clock? Is wall time ever part of identity or hashing? What timeouts and TTLs apply? |
| Limits and backpressure | Batch sizes, rate limits, queue bounds. What happens at the bound: drop, block, or shed? |
| Schema and compatibility | Which event and API changes are additive-only? Who are the consumers? |

### 3. ARCHITECTURE.md: ownership and contracts
Write a data-flow diagram, a table of module → owned tables → responsibility, and the event contracts. The ownership table is what stops an agent from writing to `customer_stats` from the API layer. The event table tells it that adding a payload field is a contract change. The sample service's [ARCHITECTURE.md](code/sample_service/ARCHITECTURE.md) is a page long.

### 4. ADRs: the "why" and the rejected alternatives
An agent that does not know *why* will happily "simplify" the outbox into publish-on-commit. The **Rejected alternatives** section of an ADR is what prevents that, because it records that the simplification was considered and why it lost. See [ADR-0001](code/sample_service/docs/adr/0001-transactional-outbox.md). Add an AGENTS.md rule: *do not reverse an ADR silently; write a new one.*

### 5. A glossary for overloaded words
"Offset", "replay", "lag", "conflict" and "drift" each mean something specific in this service. A one-line definition each, in a table, removes a whole class of plausible misreadings. This matters more for agents than for humans, because agents bring the *average* meaning of a word from training.

### 6. Nested AGENTS.md and skills for progressive disclosure
- **Nested AGENTS.md** holds local, high-precision rules: "`_remember` must be inside the same transaction as the write". It is loaded only when the agent works in that directory. See [orders/AGENTS.md](code/sample_service/orders/AGENTS.md).
- **Skills** hold procedures: a `SKILL.md` with a `name` and a `description` in YAML frontmatter. The description is what is visible up front, and the body loads when the task matches ([Anthropic, "Equipping agents for the real world with Agent Skills"](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills)). The triage runbook in this module is a skill ([SKILL.md](code/sample_service/.claude/skills/triage-incident/SKILL.md)), because it is a procedure that is irrelevant to most tasks.

Decision rule: a *fact about a place* goes in a nested AGENTS.md, a *procedure for a situation* goes in a skill, and a *rule you can check* goes in a lint.

### 7. Code search the agent can use
The course stance ([01-gap-analysis](../research/01-gap-analysis.md)) is that agentic search (grep, ripgrep, file reads) works for code, and vector RAG is for document Q&A. Make your code greppable for it:
- use stable, unique names for log events (`relay.publish.failed`);
- keep one name per concept, so you do not have `event_id` in one module and `msg_id` in another;
- avoid generated or minified code in the tree the agent searches.

For monorepos too large to grep, give the agent a code-search CLI or MCP server, and measure whether it helps (ablation, [05](05-measuring-autonomy-rate.md)).

### 8. Docs are the system of record, so test them
A stale map is worse than no map, because the agent trusts it. Make staleness fail the build. This module's [check_docs.py](code/sample_service/tools/check_docs.py) checks four things:
- D1: every path in the docs exists;
- D2: every lint rule's `see:` anchor exists;
- D3: every module appears in ARCHITECTURE.md;
- D4: AGENTS.md stays under 80 lines.

OpenAI describes a related approach: linters that keep docs fresh, plus a recurring doc-gardening agent that opens fix-up PRs ([OpenAI](https://openai.com/index/harness-engineering/)).

## Worked example: the manual vs the map

### Bad: AGENTS.md as a manual (excerpt, 400 lines total)
```markdown
# Engineering Guidelines
We value clean code. Use meaningful variable names. Prefer composition over
inheritance. Write tests for everything. Our idempotency approach is important,
please be careful with it. The outbox pattern is used for events (see the wiki).
... [380 more lines: formatting rules, PR etiquette, a history of the service] ...
```
Why it fails:
- "Be careful with idempotency" is not actionable.
- "See the wiki" points at a place the agent cannot reach.
- The 380 lines of generic advice dilute the five lines that matter, because everything in the always-loaded context competes for attention ([03-context-engineering](../03-context-engineering/README.md)).
- Nothing is checkable, so nothing tells you when it goes stale.

### Good: the map, the invariant and the check
The sample service's [AGENTS.md](code/sample_service/AGENTS.md) is 37 lines. It links to INVARIANTS.md, which states I1–I5 with enforcers, and it defines done as a single command. Now rename a heading during a refactor, and add a module without documenting it:

```text
$ sed -i '' 's/## I3. Per-key ordering/## I3. Ordering/' INVARIANTS.md
$ touch orders/refunds.py
$ python tools/check_docs.py
ERROR D2 lint INV003: anchor #i3-per-key-ordering not found in INVARIANTS.md
ERROR D3 ARCHITECTURE.md does not list orders/refunds.py
check_docs: 2 problem(s)
```
That output is real. The lint's remediation text points at the anchor, so a broken anchor means the agent would follow a dead link at the exact moment it needs the explanation. Because `check_docs` runs inside `tools/check.py`, the doc rot fails the same gate as a broken test.

## Pitfalls
- **The append-only AGENTS.md.** Each mistake adds a line and nothing is ever removed. *Detect it* when the line count goes up month over month. Enforce a cap (D4), and when a lint takes over a rule, delete the prose.
- **Invariants without enforcers.** *Detect it* when the "Enforced by" column is empty. Each empty cell is either a test to write or a sign that the invariant is aspirational.
- **Docs written for humans, not agents.** Narrative history and "as discussed" references give the agent nothing to act on. *Detect it* by asking the agent "what would you check before changing X?" and seeing whether its answer cites your doc.
- **Instruction conflicts across files.** Root AGENTS.md says one thing, a nested file or skill says another. OpenAI's GPT-6 guidance notes that the model is literal about AGENTS.md and skill files, and recommends auditing conflicts ([02-prompting-as-specification](../02-prompting-as-specification/README.md)). *Detect it* by grepping for the same keyword across all context files.
- **Docs that only exist outside the repo.** *Detect it* when an agent asks a question whose answer is in Confluence. Move that answer into the repo.

## In your day job
- Write INVARIANTS.md for one service this week, using the checklist table. Expect to discover at least one invariant your team disagrees about. That disagreement is a finding in its own right.
- Cut your root AGENTS.md (or CLAUDE.md) to a map under 100 lines. Move everything else into linked docs or skills.
- Add a docs-freshness check to CI. Path and anchor existence alone catches most rot.
- Adopt Hashimoto's rule with a twist: every agent mistake becomes either a doc line *or a check*, and you prefer the check.
