# 06: Long-running harnesses with external state

## The idea

A task that spans many context windows needs **memory that lives outside the model**: files and git that each new session reads at start and updates before it ends. Every session starts with amnesia, and Anthropic is explicit that compaction alone is not enough to fix that ([Anthropic, "Effective harnesses for long-running agents"](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)). The harness supplies the continuity: a frozen spec, a machine-readable list of what's done and what isn't, a human-readable progress log, a reproducible environment script, and git history as the audit trail.

This is Ralph ([05](05-ralph-loops.md)) grown up. It still runs one unit of work per session, but the state has a schema, there's an initialiser that creates it, and there's a startup ritual that every session follows.

## Why it matters

Anthropic names two failure modes of a long project run from a high-level prompt alone, even with Opus 4.5 on the Agent SDK:
- **Overreach:** the agent builds everything at once, runs out of context mid-feature, and leaves the work undocumented.
- **Premature completion:** a later session sees existing progress and declares the project done.

Both are state failures, not intelligence failures. In distributed-systems terms, overreach is a transaction too large to commit before the lease expires, and premature completion is reading a stale replica and acting on it.

The payoff for getting state right is long unattended runs. OpenAI reports GPT-5.3-Codex at Extra High effort running about **25 hours uninterrupted** on a blank repo, using about 13M tokens and producing about 30k lines (a design tool with collaboration, layers, history and export), with durable memory in four Markdown files. Their summary: "The result was not perfect or production-ready, but it was real and testable." ([OpenAI, "Run long horizon tasks with Codex"](https://developers.openai.com/blog/run-long-horizon-tasks-with-codex)).

## How it works

### Anthropic's initializer + coding agent

```mermaid
sequenceDiagram
    participant H as Harness
    participant I as Initializer session
    participant C as Coding session (n)
    participant D as Disk + git
    H->>I: different first prompt, same tools
    I->>D: init.sh, feature_list.json (200+ items, all passes:false), claude-progress.txt, git commit
    loop each later session, fresh context
        H->>C: same coding prompt
        C->>D: pwd; read git log + claude-progress.txt + feature_list.json
        C->>D: run init.sh, smoke e2e test (is the tree healthy?)
        C->>C: pick highest-priority failing feature, implement ONE
        C->>D: e2e test as a user (browser), flip passes:true only if it passed
        C->>D: git commit, append progress note
    end
```

The details that matter:
- **The initializer uses a different user prompt** but the same system prompt, tools and harness. It writes `init.sh`, `claude-progress.txt`, a JSON feature list with more than 200 features all initially failing, and an initial commit.
- **JSON rather than Markdown** for the feature list, because the model is less likely to rewrite JSON inappropriately. Agents may only flip `passes`.
- **Startup ritual:** `pwd`, read the git log and progress notes, pick the highest-priority failing feature, run `init.sh` and a smoke end-to-end test *before* starting new work, so a broken tree gets fixed first.
- **End-to-end testing as a user.** Browser automation replaced unit-test-or-curl "done" checks, which had let broken features through. (Known blind spot reported in the article: native alert modals.)
- **Test protection:** "It is unacceptable to remove or edit tests because this could lead to missing or buggy functionality."

Anthropic's prompting docs give the same pattern in prompt form, including "Call pwd; you can only read and write files in this directory." and "Review progress.txt, tests.json, and the git logs.", and they recommend a fresh context window over compaction for multi-window work ([Anthropic, prompting best practices](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices)).

### Planner, generator, evaluator, and sprint contracts

Anthropic's follow-up added roles ([Anthropic, "Harness design for long-running application development"](https://www.anthropic.com/engineering/harness-design-long-running-apps)):
- A **planner** turns a 1–4 sentence prompt into a spec and stays high-level, so spec errors don't cascade.
- A **generator** works in sprints, one feature at a time, using git.
- An **evaluator** clicks through the app, API and database, with a hard threshold per criterion.
- Before each sprint, generator and evaluator negotiate a **sprint contract**: what will be built and how success will be checked. They communicate through files. Sprint 3 had 27 criteria.

The numbers: a solo run took 20 minutes and $9, and the core feature was broken. The full harness took 6 hours and $200 (more than 20x the cost) and was much more functional. A later Opus 4.6 build of a DAW took 3 hours 50 minutes and $124.70 over three build/QA rounds. The harness also changed with the model. Context resets with a handoff artifact were essential on Sonnet 4.5, which showed "context anxiety". They were dropped on Opus 4.5 in favour of auto-compaction, and on Opus 4.6 the sprints were removed and the evaluator became a single pass at the end. The article's principle: "every component in a harness encodes an assumption about what the model can't do on its own". Re-test those assumptions on every model upgrade ([08-harness-engineering](../08-harness-engineering/README.md)).

### OpenAI's four files

| File | Role | Mutability |
|---|---|---|
| `Prompt.md` | Frozen spec: goals, non-goals, constraints, "done when" checks | Read-only after kickoff |
| `Plans.md` | Milestones small enough for one loop, each with acceptance criteria and validation commands; the stop-and-fix rule; **decision notes "to prevent oscillation"** | Append and tick |
| `Implement.md` | Runbook: Plans.md is the source of truth, validate after each milestone, keep diffs scoped | Rarely changes |
| `Documentation.md` | Status and audit log | Append-only |

The loop they describe is plan, edit, run tools (tests, build, lint, typecheck), observe, repair, update docs, repeat.

### Durable logs instead of context

Anthropic's Managed Agents design goes one step further. The **session** is an append-only event log outside the context, the **harness** is stateless, and the **sandbox** is cattle. A harness crash is recovered with `wake(sessionId)` and a replay of the log, and a sandbox failure becomes a tool error that Claude can retry on a fresh container ([Anthropic, "Scaling Managed Agents"](https://www.anthropic.com/engineering/managed-agents)). Because the log is queryable, compaction doesn't have to make irreversible choices. If you've run event-sourced services, this is the same design: the log is the truth, and the context window is a materialised view.

### Choosing the state store

| Store | Good for | Weak at |
|---|---|---|
| `feature_list.json` / `tests.json` | Pass/fail status per item, machine-checked | Dependencies between items |
| `Plans.md` / `fix_plan.md` | Ordering, rationale, decision notes | Being edited inappropriately (prose invites rewrites) |
| `claude-progress.txt` / `Documentation.md` | What happened, in order | Querying |
| git (commits, tags, branches) | Atomic checkpoints, rollback, blame | Unstructured status |
| Issue graph (Beads: `bd ready`, `bd update <id> --claim`) | Dependency-aware queues, atomic claims for parallel agents ([Beads](https://github.com/steveyegge/beads)) | Another tool to run and trust |
| Session event log (Managed Agents) | Replay, resumability, audit | Requires platform support |

## Worked example: a Kafka consumer migration over many sessions

Situation: move 40 consumers from a hand-rolled offset-commit wrapper to the platform's idempotent consumer library. Each consumer is small. All 40 together won't fit in one context, and a reviewer must be able to tell what's done.

**Bad version: a Markdown TODO list.**

```markdown
## TODO
- migrate billing consumers
- migrate ledger consumers (careful with dedupe!)
- ...
```

Session 6 rewrites this list "for clarity", merges two lines and drops "careful with dedupe!". Session 9 sees most boxes ticked and reports the migration complete, though ledger-replay was never run end to end. There's no machine-checkable notion of done, and the plan is as writable as the code.

**Good version: initializer output.**

`feature_list.json` (one entry per consumer; agents may change only `passes`):

```json
[
  {"id": "C-07", "category": "ledger", "consumer": "ledger-postings-v2",
   "description": "Migrate to platform IdempotentConsumer with dedupe key (account_id, posting_id)",
   "steps": ["replay fixture topic ledger.postings.dup3 with 3x duplicates and 10% reordering",
             "assert ledger_balance(account) equals the fixture's expected balance",
             "assert consumer lag returns to 0 within 30s"],
   "verify": "make verify CONSUMER=ledger-postings-v2",
   "passes": false}
]
```

`claude-progress.txt` (append-only):

```text
2026-10-18 s05  C-06 billing-refunds: migrated; verify green; commit 3f1a9c2.
2026-10-18 s05  NOTE dedupe store needs DEDUPE_TTL >= max replay window (72h) or replays double-post. Added to AGENT.md.
2026-10-18 s06  C-07 ledger-postings-v2: verify red, 3 duplicate postings on reordered input. Not done. Hypothesis: key must include partition epoch.
```

Coding-session prompt (the startup ritual made explicit):

```markdown
Call pwd; you can only read and write files in this directory.
Read the last 30 lines of claude-progress.txt, `git log --oneline -20`, and feature_list.json.
Run ./init.sh, then `make verify CONSUMER=<last passing consumer>` as a smoke test. If it fails, fix that first.
Pick the first entry with "passes": false. Migrate that ONE consumer.
Run its "verify" command. Only if it exits 0, set its "passes" to true. Never edit any other field or any test.
Commit, append one line to claude-progress.txt, and exit.
```

The **harness check** that makes the JSON rule real, run by the loop driver after each session rather than trusted to the prompt:

```python
import subprocess

def feature_list_guard(before: list[dict], after: list[dict]) -> list[str]:
    """Allow only passes:false->true flips, each backed by a green verify run."""
    problems = []
    if [f["id"] for f in before] != [f["id"] for f in after]:
        return ["feature list ids added, removed or reordered"]
    for b, a in zip(before, after):
        if {k: v for k, v in b.items() if k != "passes"} != {k: v for k, v in a.items() if k != "passes"}:
            problems.append(f"{a['id']}: fields other than 'passes' changed")
        if not b["passes"] and a["passes"] and subprocess.run(a["verify"], shell=True).returncode != 0:
            problems.append(f"{a['id']}: flipped to passes=true but verify fails")
        if b["passes"] and not a["passes"]:
            problems.append(f"{a['id']}: regressed to false (investigate, don't hide)")
    return problems
```

If the guard returns problems, the driver reverts the session's commit, as `ralph.py` does for premature claims, and the next session starts from the last good state. Session 9's false "complete" can't happen: `C-07` stays `false` until `make verify` agrees.

## Pitfalls

| Pitfall | How to detect it |
|---|---|
| Overreach: several features per session | Commits touching multiple feature ids; sessions ending mid-feature with uncommitted diffs |
| Premature completion | Count `passes:true` entries whose verify command fails when re-run; should be 0 |
| Agent edits the plan or tests to fit | The guard above; diff `spec`/`test` paths per session |
| Broken tree inherited by the next session | Startup smoke test fails; make "fix the smoke test first" a rule |
| Progress log grows without bound | Summarise older entries into a "state of the world" header; keep the tail |
| Oscillation between two designs | Repeated reverts in git log; require decision notes in Plans.md ("tried X, rejected because Y") |
| Harness tuned for an old model | After an upgrade, ablate components (resets, sprints, evaluator) and re-measure cost and quality |

## In your day job
- For any agent task you expect to need more than one session, have the first session write `feature_list.json`, `init.sh` and a progress file, and nothing else. Review that before any code gets written.
- Put the verify command for each item *in the item*. "Done" is then a lookup plus an exit code, and you can re-check it at any time.
- Run a guard like `feature_list_guard` in the loop driver, not in the prompt.
- Keep decision notes. They're the cheapest way to stop a fresh-context agent from undoing yesterday's design choice.
