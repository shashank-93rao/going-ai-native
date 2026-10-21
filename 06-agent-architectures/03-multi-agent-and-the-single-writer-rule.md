# 03: Multi-agent systems and the single-writer rule

## The idea

A multi-agent system is several model contexts working on one task. The useful question is not how many agents to run but **what each extra agent contributes**: intelligence, or actions.

- **Intelligence** means reading, searching, researching, reviewing, critiquing and estimating. The output is *information* handed to someone else.
- **Actions** means writing files, committing, calling side-effecting APIs, or mutating shared state.

The course stance, from [01-gap-analysis](../research/01-gap-analysis.md): **single-writer principle. Parallelize reads and isolated tasks with verifiable criteria. Never let parallel writers share state.** That is the multi-agent version of a rule you already use: when one writer owns a piece of state, you don't need coordination for it, and readers can scale horizontally.

## Why it matters: the evidence on both sides

### For: Anthropic's research system

Anthropic's Research feature uses an orchestrator-worker design, with a Claude Opus 4 lead agent and Claude Sonnet 4 subagents searching in parallel. It "outperformed single-agent Claude Opus 4 by 90.2% on our internal research eval" ([Anthropic, "How we built our multi-agent research system"](https://www.anthropic.com/engineering/multi-agent-research-system)). The same post explains why:

- On BrowseComp, three factors explained 95% of the performance variance, and **token usage alone explained 80%**.
- Agents use about 4x the tokens of chat. Multi-agent systems use "about 15× more tokens than chats".
- Their summary: "Multi-agent systems work mainly because they help spend enough tokens to solve the problem."

The post is just as explicit about where it doesn't apply. Domains where agents must share the same context, or that have many inter-agent dependencies, "are not a good fit for multi-agent systems today". Coding is the named example, because it has fewer truly parallelizable tasks than research. Note also what the subagents do: **they search and read.** The lead writes the answer.

### Against: Cognition, June 2025

Walden Yan's "Don't Build Multi-Agents" gives two principles ([Cognition, 2025-06-12](https://cognition.com/blog/dont-build-multi-agents)):
1. "Share context, and share full agent traces, not just individual messages"
2. "Actions carry implicit decisions, and conflicting decisions carry bad results"

The example: a "Flappy Bird clone" is split into two subtasks, a background with pipes and a bird. One subagent builds a Super Mario-style background, and the other builds a bird that doesn't look or move like Flappy Bird's. The final agent has to merge two pieces built on incompatible assumptions. The recommendation was a "single-threaded linear agent", with a separate model compressing history for very long tasks.

### The update: Cognition, April 2026

Ten months later, "Multi-Agents: What's Actually Working" reports what did work, and the common thread is that **writes stay single-threaded** while the other agents add intelligence ([Cognition, 2026-04-22](https://cognition.com/blog/multi-agents-working)):
- **Clean-context code review.** Devin Review catches an average of 2 bugs per Devin-written PR, and about 58% of those are severe. It works best when "the coding and review agents do not share any context beforehand".
- **"Smart friend" escalation** to a stronger model. It worked when the primary model was itself frontier-class, and not when the primary was weaker.
- **Manager/child agents** in Devin. They needed substantial context engineering: managers were over-prescriptive, children wrongly assumed shared state, and children didn't report back by default.
- Unstructured swarms of negotiating agents are, in the author's words, "mostly a distraction."

### The isolated-writers exception: the C compiler

Nicholas Carlini's team of 16 parallel Claudes built a Rust C compiler that builds Linux 6.9, with no orchestrator ([Anthropic, "Building a C compiler with a team of parallel Claudes"](https://www.anthropic.com/engineering/building-c-compiler)). Those agents *did* write in parallel. It worked for three reasons:
- **Tasks were claimed with lock files** in `current_tasks/`, and git conflicts forced a second claimant to pick another task. That is optimistic concurrency.
- **Each task had its own oracle.** GCC-compiled kernel files served as the reference, so each agent could bisect to different bugs.
- **Tests had to be near-perfect,** because agents solve exactly what the verifier checks.

This is a partitioned-writer design. Ownership is disjoint, and each partition has an oracle. It is the "isolated tasks with verifiable criteria" half of the course stance, not a counterexample to it.

### Two more data points
- Multi-agent setups had **3.7x the rate of unintended solutions** on BrowseComp (0.87% vs 0.24%), meaning answers reached through leaked answers or a found answer key rather than by solving the problem ([Anthropic, eval awareness](https://www.anthropic.com/engineering/eval-awareness-browsecomp)). More agents means more search, and so more chances to find a leak.
- Anthropic's Opus 5 guide says the model coordinates subagents well, "with effective writer-verifier patterns and few cases of agents overwriting each other's work" ([Prompting Claude Opus 5](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5)). Better models reduce *byte-level* clobbering. They do not remove *decision-level* conflicts, which come from information that the parallel agents don't share.

## How it works: the single-writer rule, mechanically

> **Synthesis:** Cognition's "implicit decisions" are the agent version of *write skew*. Two transactions each read a consistent snapshot and write disjoint rows, so no row-level conflict exists, yet together they violate an invariant. Row locks and OCC on the written rows don't catch write skew. You need either serializable execution over the read set or a single writer. Agents make it worse, because the "read set" is everything the agent looked at and assumed, and you can't enumerate it.

The decision procedure:

| Question | If yes | If no |
|---|---|---|
| Does the helper only *read* and return information? | Parallelize freely (research, search, review, estimation) | Next question |
| Are the write sets disjoint **and** is there a per-partition oracle **and** a merge gate that checks cross-partition invariants? | Partitioned writers, with claims via OCC (the C compiler) | Next question |
| Otherwise | **One writer.** Helpers return notes, findings or proposals. The writer applies them serially against current state, and a check runs after each write. | |

What it looks like in code ([`code/single_writer.py`](code/single_writer.py)):

```python
def run_single_writer(client, repo, tasks, helper_questions) -> Outcome:
    # readers: fan out freely; they cannot write
    notes = "\n".join(ask(client, f"QUESTION: {q}\n\n{render(repo.snapshot())}", system=HELPER_SYSTEM)
                      for q in helper_questions)
    for task in tasks:
        snap = repo.snapshot()                        # the writer always sees the latest state
        for e in propose(client, task, snap, notes):
            repo.write(e["path"], e["content"], snap.get(e["path"], ("", 0))[1])
        problems = undefined_calls(repo.files)        # backpressure after every write
        ...
```

The [multi-writer example](examples.md#4-a-broken-multi-writer-design-and-the-fix) runs the broken design and the fix side by side. With OCC turned on, the broken design still produces a broken repo with zero conflicts reported.

### The harness-decay caveat: models now over-spawn

Every harness component "encodes an assumption about what the model can't do on its own" ([Anthropic, harness design](https://www.anthropic.com/engineering/harness-design-long-running-apps)), and "Harnesses encode assumptions that go stale as models improve" ([Anthropic, Managed Agents](https://www.anthropic.com/engineering/managed-agents)). For multi-agent, the assumption has *flipped*. Early harnesses had to coax models into delegating. Current ones have to restrain them:

- Anthropic's Opus 5 guide: the model "delegates to subagents more readily than prior models". Delegation "multiplies cost and time when applied to small tasks." It also says explicit "use a subagent to verify" instructions cause **over-verification** and should be removed ([Prompting Claude Opus 5](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5)).
- The guide's damping prompt (verbatim):

```text
Delegate to a subagent only for large tasks that are genuinely independent and parallelizable,
such as a wide multi-file investigation. Do not delegate work you can finish yourself in a
handful of tool calls, and do not use subagents to verify or double-check your own work. If one
subagent can complete the task, use one rather than several, and keep spawn counts low.
```

- The deterministic caps (per that guide, Claude Code 2.1.217 or later): `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`, `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS`, and the Agent SDK's `max_budget_usd`.
- Claude Code's agent-teams docs: "Three focused teammates often outperform five scattered ones" ([Claude Code docs, agent teams](https://code.claude.com/docs/en/agent-teams)).

Prefer the cap over the prompt. A prompt is a suggestion, while an environment variable or a `max_subtasks` argument is a limit. Then re-measure on each model upgrade, as [12-hill-climbing](../12-hill-climbing/README.md) describes, because the right cap moves.

## Worked example: design review of a three-agent feature team

**Situation.** A team proposes using agents to add per-tenant rate limiting to an API gateway (Go).

### Bad: three parallel writers

```yaml
# agents.yaml, as proposed
api_agent:      { task: "Add RateLimit middleware to router.go", writes: ["router.go", "middleware/*"] }
storage_agent:  { task: "Add Redis token-bucket store",          writes: ["ratelimit/store.go"] }
tests_agent:    { task: "Write tests for rate limiting",          writes: ["ratelimit/*_test.go"] }
```

The write sets look disjoint, so file-level conflicts are impossible. Here is what happens (illustrative, but this is the Flappy Bird pattern):
- `storage_agent` decides that the bucket key is `tenant:{id}` and that `Allow()` returns `(bool, error)`.
- `api_agent`, which never saw that decision, calls `store.Take(ctx, tenantID, 1)` and expects `(remaining int, err error)`.
- `tests_agent` writes tests against a third interface it inferred from the task text.
- The result: three files that are each internally plausible, none of them compiling against the others, and a merge agent asked to reconcile three sets of assumptions.

Every conflict here is a *decision* conflict: the interface, the key scheme, and the refill semantics. OCC, worktrees and file ownership don't touch any of them.

### Good: one writer, readers in parallel, a check after each step

```yaml
writer:
  task: "Implement per-tenant rate limiting per SPEC.md"
  writes: ["**"]
  gate_after_each_commit: ["go build ./...", "go test ./ratelimit/..."]
helpers:   # read-only tools: read, grep, go doc. No edit tools.
  - "List every middleware in router.go and the order they run in"
  - "Find existing Redis usage: client construction, key prefixes, timeouts"
  - "Summarise how tenant ID is extracted from the request today, with file:line"
reviewer:  # clean context: SPEC.md + final diff only (see 04)
  task: "Check the diff against SPEC.md. Report gaps with evidence lines."
```

With this design:
- The interface decision is made once, by the one agent that writes both sides of it.
- Helpers fan out on the questions that really are parallel (they're reads), and return 1-2k-token summaries instead of their whole traces.
- `go build` after every commit is backpressure. A broken interface is caught at the commit that introduces it.
- The review step gets more value from clean context than any extra writer would add.

## Pitfalls

- **"Disjoint files" taken to mean "independent".** Detect it by asking whether any task's output is another task's *input*: an interface, a schema or a naming convention. If so, the tasks are not independent.
- **Passing summaries where traces are needed.** Cognition's first principle. A child given a one-line task loses the parent's constraints. Detect it by reading a child's prompt cold: could *you* do the task correctly from that prompt alone?
- **Verification subagents on a model that already self-verifies.** On Opus 5 this is documented waste. Detect it by ablating the verification subagent on your eval set. If quality holds and tokens drop, remove it.
- **Spawn count set by the model.** Detect it by plotting subagents per run. Cap in config, not in prose.
- **Multi-agent as a substitute for a better single prompt.** If the gain disappears when you give a single agent the same token budget, you were buying tokens, not architecture. The research-system post says as much. Detect it with a matched-budget single-agent baseline.

## In your day job

- In design reviews, label every agent R (read-only) or W (writes). More than one W on shared state needs a partitioning argument, a per-partition oracle, and a merge gate. Without all three, collapse to one writer.
- Use subagents for wide reads such as codebase surveys, log searches and dependency inventories, and keep their outputs condensed.
- Set `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS` (or your framework's equivalent) explicitly, and revisit it on each model upgrade.
- When someone cites "+90%", ask what the single-agent baseline's token budget was.
