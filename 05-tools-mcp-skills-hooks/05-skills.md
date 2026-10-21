# 05: Skills: runbooks that load on demand

## The idea

A **skill** is a folder containing a `SKILL.md` file (YAML frontmatter plus Markdown instructions) and, optionally, scripts, reference docs and assets. It packages *procedural* knowledge, such as "how we triage consumer lag" or "how to cut a release," so the agent can apply it without you pasting it into every prompt.

The core mechanism is **progressive disclosure** in three levels ([Anthropic, "Equipping agents for the real world with Agent Skills"](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills); [Agent Skills spec](https://agentskills.io/specification)):

| Level | What loads | When | Size guidance |
|---|---|---|---|
| 1. Metadata | `name` + `description` of every installed skill | Session start, always | ~100 tokens per skill |
| 2. Instructions | The `SKILL.md` body | When the task matches the description, or on `/skill-name` | < 5,000 tokens; under 500 lines |
| 3. Resources | Files in `references/`, `assets/`; output of `scripts/` | Only when the instructions point there and the task needs it | Unbounded, because it isn't loaded |

Scripts are the important special case: they're **executed, not loaded**. A 300-line parser costs the context only its output.

Skills became an open standard in December 2025. The spec is at agentskills.io, and Claude Code, the Claude apps and the API all read the same format.

## Why it matters

Without skills, procedural knowledge ends up in one of two bad places:
- **CLAUDE.md / AGENTS.md**, loaded on every turn of every session, including the 95% of sessions that have nothing to do with Kafka. It's a recurring token cost and a source of instruction conflicts.
- **The engineer's head**, retyped as a long prompt at 3am.

Skills fix the cost problem (about 100 tokens until needed) and the reuse problem (versioned in the repo, reviewed like code). Willison's comparison: skills keep the efficiency of a CLI ("a few dozen tokens" per skill at session start) without requiring you to build one, at the cost of requiring a filesystem and code execution ([Willison](https://simonwillison.net/2025/Oct/16/claude-skills/)).

A caution the course takes seriously: skills are probabilistic. They may not trigger, and they may be followed loosely. Huntley's advice is to test with and without them and to delete and re-test them periodically, since a newer model can make old tuning counterproductive ([Huntley, "nobody should type code by hand anymore"](https://ghuntley.com/agency/)). Treat a skill as code with tests.

## How to do it

### The folder

```text
.claude/skills/investigate-kafka-consumer-lag/    # project skill; ~/.claude/skills/ for personal
├── SKILL.md                    # required: frontmatter + the procedure
├── references/
│   ├── causes.md               # cause catalog: loaded only at the decision step
│   └── commands.md             # read-only commands and PromQL
├── scripts/
│   └── lag_summary.py          # executed, never read into context
└── assets/
    └── incident-note-template.md
```

### Frontmatter rules (spec plus Claude Code)
- `name`: 1–64 chars, lowercase letters, digits and single hyphens, and it must match the directory name.
- `description`: 1–1024 chars (the spec limit). Say **what it does and when to use it**, with the words a user or alert would contain. This is the trigger. Claude Code truncates `description` + `when_to_use` at 1,536 characters in its listing ([Claude Code skills docs](https://code.claude.com/docs/en/skills)).
- Claude Code adds optional fields such as `disable-model-invocation: true` (only you can invoke it, for skills with side effects like deploy), `user-invocable: false` (only Claude can), `allowed-tools`, `context: fork` (run in a subagent), and `paths` (globs that limit auto-loading). Outside Claude Code, only the spec's fields (`name`, `description`, `license`, `compatibility`, `metadata`, `allowed-tools`) are accepted.

### Writing the body
- Write the **procedure**, not background. Steps, decision points, the output format.
- Say explicitly which scripts to **run** and which files to **read**. Anthropic's guidance: "It should be clear whether Claude should run scripts directly or read them into context as reference."
- Keep references **one level deep** from `SKILL.md`, and link them at the step where they're needed.
- Encode the **boundaries**: what the skill must never do (for triage, no offset resets).
- Put the hard-won gotchas in. They're the part a model doesn't already know.

### Testing a skill
OpenAI's skill-eval write-up gives a usable recipe: 10–20 prompts mixing explicit invocation, implicit invocation and **negative controls** (prompts that should *not* trigger the skill), with deterministic checks on the traces ([OpenAI, "Testing Agent Skills Systematically with Evals"](https://developers.openai.com/blog/eval-skills)). Measure two things separately: **trigger precision/recall** (did it load when it should, and only then) and **task success when loaded**.

## Worked example: "investigate a Kafka consumer lag alert"

### Before

Your team's lag runbook is a 400-line Confluence page. Someone pastes it into CLAUDE.md. Now every session, including "fix this CSS," carries it. When a lag alert does come in, the agent reads the whole thing, then runs `kafka-consumer-groups.sh --describe` and gets back 96 rows of offsets, which it reads line by line. Halfway through, it suggests `--reset-offsets --to-latest`, because the runbook mentions it in a "last resort" section and nothing says the agent is not allowed to do that.

### After

`code/skills/investigate-kafka-consumer-lag/SKILL.md` (frontmatter and the first step):

```markdown
---
name: investigate-kafka-consumer-lag
description: Triage a Kafka consumer lag alert (ConsumerLagHigh, ConsumerGroupLagGrowing, Burrow WARN/ERR) down to
  a cause and a safe next action. Use when an alert, page or user mentions consumer lag, a consumer group falling
  behind, offsets not advancing, or a stuck partition. Read-only investigation; it never resets offsets or restarts
  consumers itself.
---

# Investigate a Kafka consumer lag alert

Goal: within ~10 minutes, classify the lag into one of the causes in references/causes.md, with evidence, and
propose the least risky next action. You are read-only. Never run `kafka-consumer-groups.sh --reset-offsets`,
`--delete`, or restart pods. Those go in your recommendation for a human.

## Step 1: Get the lag shape (always)

Run describe for the group, then pipe it through the bundled summarizer. Execute the script; do not read it into context.

    kafka-consumer-groups.sh --bootstrap-server "$KAFKA_BOOTSTRAP" --describe --group "<group>" \
      | python3 scripts/lag_summary.py
```

The real file continues with Step 2 (is it growing: two samples or a 30-minute PromQL range), Step 3 (branch on `shape=`), Step 4 (fill the incident template), and a Gotchas section (committed vs processed offsets, message lag vs time lag, transient "unassigned" during rebalances).

What the script turns 6 rows (or 96) into, run against `code/data/describe_poison_partition.txt` (real output):

```text
group=ledger-writer-v2 topics=payments.events partitions=6 total_lag=48692 max_lag=48211 median_lag=101
top: payments.events[3]=48211 owner=ledger-writer-7d9f-1-77a, payments.events[0]=120 owner=ledger-writer-7d9f-0-3c1, ...
unassigned_partitions=none
shape=single_partition
```

`shape=single_partition` sends the agent to the poison-message / hot-key branch, and only then does it read `references/causes.md`:

```markdown
| Poison message | `single_partition`; that partition's offset not moving; repeated deserialize/validation errors
  naming one offset | Logs filtered by `partition=<n>`; offset unchanged across two samples | Fix forward (deploy a
  consumer that tolerates the value) or route the record to a DLQ. Skipping the offset loses data: needs owner sign-off |
```

Token accounting for a non-Kafka session: the ~90-token description. For a lag incident: description, the roughly 750-token body (about 3.4k characters), the script's 4-line output, and one reference file. The 400-line runbook never loads.

Why each piece is there:
- The **description** lists alert names and user phrasings ("falling behind", "stuck partition") because those are the trigger words.
- **Read-only boundaries are in the body**, in the first paragraph. They are also enforced elsewhere: the skill doesn't grant offset-reset permissions, and a hook or RBAC blocks it ([06-hooks](06-hooks.md)). The skill text is advice; the gate is the guarantee.
- The **script classifies**, so the branch decision is deterministic and testable (`test_skill.py` checks `single_partition` and `unassigned` fixtures).
- The **template** forces "unknown" instead of guesses, and requires every claim to cite the command that produced it.

`code/test_skill.py` checks the parts you can check offline: frontmatter against the spec, every link resolves and is one level deep, the body is under 500 lines, and the script's classification on fixtures. Trigger behavior needs a real model; that's [exercise 4](exercises.md).

## Pitfalls

| Pitfall | How to detect it |
|---|---|
| Vague description ("Kafka helper") | Skill doesn't load on real alerts. Run implicit-invocation prompts and check traces for the skill load. |
| Over-broad description | Loads on unrelated sessions. Include negative controls ("why is my Kafka producer test flaky?") in the trigger eval. |
| Everything in SKILL.md | Body over 500 lines; reference tables loaded on every invocation. Split into `references/`. |
| Scripts the agent reads instead of runs | Trace shows a `Read` of `scripts/*.py`. Say "execute, do not read" and keep script usage in the body. |
| Boundaries only in prose | Skill says "never reset offsets"; nothing enforces it. Pair with a hook or with credentials that can't do it. |
| Skill rot | The skill references a dashboard or flag that no longer exists. Run the skill's eval on a schedule and on model upgrades; delete skills that no longer move the eval. |
| Untrusted skills | A downloaded skill's script makes network calls. Anthropic: install only from trusted sources, and audit scripts, dependencies and network access first. |

## In your day job
- Pick the runbook your team pages on most. Turn its procedure into a skill with one deterministic script for the first diagnostic step. Leave the background prose behind.
- Move anything in CLAUDE.md that applies to fewer than half your sessions into a skill.
- Write ten trigger prompts (including three negative controls) and check your skill loads when it should and only then.
- When an agent session goes well, have it write the working commands back into the skill (Anthropic recommends this), then review that diff like any other.
