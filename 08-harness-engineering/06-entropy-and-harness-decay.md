# 06: Entropy management and harness decay

## The idea
A harness degrades in two directions at once:

1. **Codebase entropy.** Agents copy whatever patterns exist, including bad ones, at a volume no human reviewer can keep up with. Every sloppy helper, inconsistent log field and swallowed exception becomes a template for the next hundred changes.
2. **Harness decay.** Every harness component encodes an assumption about what the model cannot do on its own. Models improve unevenly. Some assumptions expire, so the component becomes dead weight. Some invert, so the component starts to hurt.

Entropy management is the continuous process that holds the codebase at a quality level: golden principles, enforced mechanically, with background cleanup agents and per-area quality scores. Decay management is the periodic process that holds the *harness* at the right size: prune and ablate on every model upgrade. Both are garbage collection. One collects code and the other collects scaffolding.

## Why it matters
- **OpenAI's harness team** reports that agents replicate existing patterns, including poor ones. Early on they spent every Friday, about 20% of the week, cleaning up "AI slop". That did not scale. They replaced it with a set of "golden principles" encoded in the repo, plus quality grades kept in the repo's docs and recurring background agents that open small refactor PRs, many of them auto-merged. Their framing is that technical debt is a high-interest loan, better paid down continuously in small increments ([OpenAI, "Harness engineering"](https://openai.com/index/harness-engineering/)).
- **Anthropic's harness posts** document decay directly:
  - context resets with a handoff file were essential on Sonnet 4.5 and were dropped on Opus 4.5 in favor of auto-compaction;
  - on Opus 4.6 the sprint structure was removed and the evaluator became a single pass at the end.

  The recommendation is to re-examine the harness with each new model, "stripping away pieces that are no longer load-bearing to performance" ([Anthropic, "Harness design for long-running application development"](https://www.anthropic.com/engineering/harness-design-long-running-apps)). The Managed Agents post makes the same point: "Harnesses encode assumptions that go stale as models improve" ([Anthropic, "Scaling Managed Agents"](https://www.anthropic.com/engineering/managed-agents)).
- **Components can invert.** Anthropic's Opus 5 guide says explicit verification instructions "cause over-verification on Claude Opus 5, and removing them reduces wasted tokens with no loss in quality. The same applies to legacy harness scaffolding that adds separate verification steps" ([Prompting Claude Opus 5](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5)). LangChain says its loop-detection middleware and similar guardrails are heuristics that will likely become unnecessary as models improve ([LangChain](https://www.langchain.com/blog/improving-deep-agents-with-harness-engineering)).
- **Practitioners disagree on how aggressive to be.** Hashimoto treats AGENTS.md as the core harness artifact, growing it one line per observed mistake. Huntley calls skill packs and AGENTS.md probabilistic, and recommends deleting them every few months and re-testing ([Huntley](https://ghuntley.com/agency/)). The course stance ([01-gap-analysis](../research/01-gap-analysis.md)) is to **treat context files as code: test with and without them, and prune on model upgrades.** The autonomy-rate ablation ([05](05-measuring-autonomy-rate.md)) is how you test.

## How to do it

### 1. Golden principles: few, mechanical, enforced
A golden principle is a taste rule you can check. Keep five to ten, each with an enforcer. For this service:

| # | Principle | Enforcer |
|---|---|---|
| G1 | One transaction primitive: `with tx(conn):` | lint INV006 |
| G2 | Only the relay publishes | lint INV002 |
| G3 | Every log record carries correlation ids (`order_id`, `event_id` when known) | lint (exercise): `log(...)` calls in `orders/` must pass `order_id=` |
| G4 | No wall clock, uuid or randomness in identity or hashing | lint INV005 |
| G5 | Event payloads are additive-only | schema compatibility check in CI |
| G6 | No new dependency or new table without an ADR | `check_docs` rule (exercise) |
| G7 | Every invariant in INVARIANTS.md has at least one enforcer | `check_docs` rule (exercise) |

A principle without an enforcer is a style-guide line, and it decays like one.

### 2. Quality scores per area
Compute a small score per module and regenerate it on a schedule, rather than writing it by hand:

```text
module              lint_suppressions  invariants_enforced  docs_fresh  agent_revert_rate_30d  grade
orders/api.py       0                  I1,I2,I5 (3/3)       yes         0/14                   A
orders/outbox.py    0                  I1,I3 (2/2)          yes         1/6                    A-
orders/consumer.py  1 (INV004, reason) I4 (1/1)             yes         2/5                    B
```
(illustrative output)

Use the score to point cleanup agents at the worst area, and to show reviewers where agent changes deserve more scrutiny. Do not use it as a target in its own right, or the agents will optimize the score (Goodhart). Keep a human reading the trend.

### 3. Background cleanup agents
A scheduled agent ([07-loops](../07-loops/README.md)) with a narrow brief:

```text
You are the cleanup agent for this repo. Pick ONE golden principle from
docs/golden-principles.md and ONE module with the lowest grade in QUALITY.md.
Find violations of that principle in that module. Make the smallest change that
fixes them with no behaviour change. Run `python tools/check.py`; it must pass.
Open a PR titled "cleanup(<module>): <principle id>" with a diff under 200 lines.
If you find a violation you cannot fix without a behaviour change, do not fix it:
open an issue describing it instead.
```
Rules that keep cleanup safe:
- **One principle, one module, one small PR per run.** Small diffs are reviewable in a minute, and conflicts stay rare.
- **Single writer per area.** Do not schedule a cleanup on a module where a feature agent is active ([06-agent-architectures](../06-agent-architectures/README.md)).
- **Auto-merge only the lowest risk tier**: mechanical changes with no behavior change, a green gate, and no edits to `tests/` or to the event contract. Everything else gets risk-tiered review ([17-ai-native-engineer-and-team](../17-ai-native-engineer-and-team/README.md)).
- **Doc-gardening is a cleanup agent too.** It fixes `check_docs` failures and stale descriptions, so that the map stays true.

### 4. Pruning AGENTS.md and the docs
- **Tag lines with their origin.** Write `<!-- added 2026-08-12 after agent wrote to customer_stats from api.py -->` next to the rule. When you review the file, a line whose origin you cannot explain is a deletion candidate.
- **Promote, then delete.** When a lint takes over a rule, delete the prose line. The check is now the source of truth, and a duplicate rule can drift.
- **Enforce a size cap**, as D4 in `check_docs.py` does, so that growth forces a decision.

### 5. The model-upgrade drill
When a new model or a new agent version arrives, run this before switching the team over:

1. **Baseline**: the current harness with the new model on the full suite, three trials. Compare per class with the old model.
2. **Prompt-side scaffolding audit**: grep AGENTS.md, skills and system prompts for "verify", "double-check", "make sure to test" and "use a subagent to". On models that self-verify, these are candidates for removal. Remove them as one ablation.
3. **Component ablation**: re-run with each harness component removed (`--ablate <name>`).
4. **Effort sweep**: re-tune reasoning effort, because defaults carried over from the old model are often wrong ([12-hill-climbing](../12-hill-climbing/README.md)).
5. **Decide and record**: for each component, keep, delete, or convert from prose to a check. Write it down as an ADR (`docs/adr/00NN-harness-for-<model>.md`), so the next upgrade starts from known ground.

Decision rule for each component:

| Ablation delta (held-out, with CI) | Decision |
|---|---|
| Rate drops beyond noise | Keep. If it is prose, try converting it to a check. |
| Within noise | Delete if it costs tokens or maintenance; keep if it is a cheap check. |
| Rate rises beyond noise | Delete now. The component is fighting the model. |

Verifiers are the exception: **keep checks even when they are "not needed".** A lint that a better model never trips costs nothing and guards against regressions, including the next model's new quirks. Prose instructions and process scaffolding are what you prune.

## Worked example: an upgrade drill on the order service
You move from model A to model B. Three trials per task, on 40 tasks: the eight here plus 32 seeded from your history. These numbers are **(illustrative output)**: they show the shape of the decision, not a measurement.

```text
                         model A   model B   B delta vs B-full (95% CI)
full harness             0.71      0.83
- skills (triage)        0.62      0.81      -0.02 (-0.07, +0.03)
- invariants             0.55      0.70      -0.13 (-0.20, -0.06)
- diagnose               0.58      0.66      -0.17 (-0.24, -0.10)
- "verify" lines         0.69      0.86      +0.03 (+0.00, +0.07)  tokens -18%
- lint                   0.66      0.77      -0.06 (-0.11, -0.01)
```
(illustrative output)

Reading it:
- **Diagnose and invariants stay load-bearing.** Model B cannot see production evidence or unwritten invariants any better than A could. Evidence and rules about *your* system do not decay with model capability.
- **The prompt-side "verify your work" lines now hurt slightly and cost 18% more tokens.** Delete them. The Stop-hook gate stays, because it is a check, not an instruction.
- **The triage skill is within noise on B.** It is cheap, and it only loads on incident tasks. Keep it for now, and re-test next upgrade. If you need the context budget, it is the first to go.
- **The lint still matters**, and it is a check, so it stays regardless.

Here is the bad version of the same moment: switch the model on Monday because the release notes say "better at coding", keep every prompt line, and discover three weeks later that token spend is up and incident fixes are no better. Nobody knows which part of the harness is responsible, because nothing was measured one axis at a time.

## Pitfalls
- **Slop Friday.** Batch cleanup by humans does not keep pace with agent throughput. *Detect it* when cleanup is a calendar event rather than a pipeline.
- **Cleanup that changes behavior.** "Refactors" that alter retry timing or error handling. *Detect it* by running the full gate plus the autonomy suite's hidden tests on cleanup PRs, and by banning edits to `tests/` and contracts in cleanup runs.
- **Score gaming.** Agents reduce `lint_suppressions` by deleting the code paths that needed them. *Detect it* by reviewing cleanup diffs that touch suppressions, and by tracking lines deleted per PR.
- **Deleting on noise.** Removing a component because one 8-task run looked flat. *Detect it* by requiring a CI on the delta and a held-out confirmation before deletion.
- **Never deleting.** The harness grows with every incident and nobody prunes. *Detect it* by tracking AGENTS.md line count and total context-file tokens per release.
- **Decay you cannot see.** Without an autonomy suite, decay shows up only as "the agent feels worse lately". *Detect it* by running the suite on a schedule, not only at upgrades.

## In your day job
- Write five golden principles for your service, each with an enforcer or a ticket to build one.
- Schedule one cleanup agent with the brief above, on one module, with auto-merge off for the first month. Review every PR and tune the brief.
- Add the model-upgrade drill to your team's model-adoption checklist, and record the outcome as an ADR.
- Next time you add an AGENTS.md line, add its origin comment, and ask whether it could be a lint instead.
