# References

Fetched or re-checked on 2026-10-19 unless noted.

## Core

- **Anthropic, "Building effective agents"** (Schluntz and Zhang, 2024-12-19). https://www.anthropic.com/engineering/building-effective-agents
  *Take:* the augmented LLM, the workflow/agent definitions, the five patterns with their "when to use" lines (quoted verbatim in [02](02-five-workflow-patterns.md)), and "add multi-step agentic systems only when simpler solutions fall short." The page now carries a note pointing to newer tooling, but the taxonomy stands.

- **Anthropic, "How we built our multi-agent research system"** (2025-06-13). https://www.anthropic.com/engineering/multi-agent-research-system
  *Take:* +90.2% over single-agent Opus 4 on an internal research eval. Token usage explains 80% of BrowseComp variance (three factors explain 95%). About 4x tokens for agents and about 15x for multi-agent vs chat. The poor-fit statement about shared context and coding. Early failures such as "spawning 50 subagents for simple queries". Resume from the point of failure, and rainbow deploys. Synchronous subagents as a bottleneck.

- **Cognition (Walden Yan), "Don't Build Multi-Agents"** (2025-06-12). https://cognition.com/blog/dont-build-multi-agents
  *Take:* the two principles (share full traces, and actions carry implicit decisions), the Flappy Bird failure, and "single-threaded linear agent" as the default.

- **Cognition (Walden Yan), "Multi-Agents: What's Actually Working"** (2026-04-22). https://cognition.com/blog/multi-agents-working
  *Take:* writes stay single-threaded. Clean-context review (about 2 bugs per PR, about 58% severe). Smart-friend escalation works only with a strong primary. Manager/child needs heavy context engineering. Swarms are "mostly a distraction".

- **Anthropic, "Building a C compiler with a team of parallel Claudes"** (Carlini, 2026-02-05). https://www.anthropic.com/engineering/building-c-compiler
  *Take:* the partitioned-writer exception. Lock files in `current_tasks/`, git conflicts as OCC, per-task oracles (GCC as reference), and near-perfect tests. Read it alongside Cognition: they agree once you separate isolated-with-oracle from shared-state writes.

- **LangSmith docs, "Double texting"**. https://docs.langchain.com/langsmith/double-texting
  *Take:* the four strategies (enqueue as default, reject, interrupt, rollback) and their exact semantics, including that rollback discards the original run input and that interrupt must handle partially completed tool calls. The docs place this in LangSmith Deployment (Agent Server). Check the API reference for the parameter name in your SDK version.

## Durability

- **Anthropic, "Scaling Managed Agents: decoupling the brain from the hands"** (2026-04-08). https://www.anthropic.com/engineering/managed-agents
  *Take:* session = append-only event log, harness = stateless loop, sandbox = cattle. Recover a harness crash by replaying the log. "Harnesses encode assumptions that go stale as models improve."
- **Anthropic, "Building effective agent automations"** (2026-10-08). https://claude.dev/blog/building-effective-agent-automations/
  *Take:* idempotent posting, a "maybe posted" state, bookmarks instead of time windows, and a ledger with stable IDs. This is the in-doubt pattern for scheduled agents. Pairs with [07-loops](../07-loops/README.md).
- **Claude Code docs, "How Claude Code works"**. https://code.claude.com/docs/en/how-claude-code-works
  *Take:* sessions as JSONL, edits checkpointed before applying, remote side effects not checkpointable, and queued messages read after the current tool calls.
- **Claude Code docs, "Dynamic workflows"**. https://code.claude.com/docs/en/workflows
  *Take:* "A workflow moves the plan into code". Deterministic replay (`Date.now()` and `Math.random()` throw). Agent caps, and the "two rounds with no progress" stop rule.

## Reviewers and harness decay

- **Anthropic, "Prompting Claude Opus 5"** (living doc). https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5
  *Take:* the model delegates more readily, verbatim damping prompt, `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH` / `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS` / `max_budget_usd` (Claude Code 2.1.217+). Remove "use a subagent to verify" to avoid over-verification. Ask reviewers to report everything and filter separately.
- **Anthropic, "Harness design for long-running application development"** (2026-03-24). https://www.anthropic.com/engineering/harness-design-long-running-apps
  *Take:* "agents reliably skew positive when grading their own work". Every harness component encodes an assumption about what the model can't do alone. Sprints were removed on a newer model.
- **Anthropic, "How the Claude Code team does code review"** (2026-10-15). https://claude.dev/blog/solving-code-review-at-anthropic/
  *Take:* fresh-context review before the PR, parallel hunters plus verifier voting, style findings dropped after an A/B test, risk tiers, REVIEW.md. The reported outcome (merged PRs more than 2x, reverts down more than 40%) is one team's numbers.
- **Anthropic, "How we built Claude Code auto mode"** (2026-03-25). https://www.anthropic.com/engineering/claude-code-auto-mode
  *Take:* the reasoning-blind transcript classifier as a model for check independence.
- **Claude Code docs, subagents and agent teams**. https://code.claude.com/docs/en/sub-agents, https://code.claude.com/docs/en/agent-teams
  *Take:* non-fork subagents don't see history (restate rules), give each teammate its own files, and "Three focused teammates often outperform five scattered ones."
- **Claude Code docs, best practices**. https://code.claude.com/docs/en/best-practices
  *Take:* the writer/reviewer split, and the warning that gap-finding reviewers always find gaps.
- **Anthropic, "Eval awareness in Claude Opus 4.6's BrowseComp performance"** (2026-03-06). https://www.anthropic.com/engineering/eval-awareness-browsecomp
  *Take:* multi-agent runs had 3.7x the rate of unintended solutions (0.87% vs 0.24%).

## Also useful

- **OpenAI, "A practical guide to building agents"** (2025). https://cdn.openai.com/business-guides-and-resources/a-practical-guide-to-building-agents.pdf
  *Take:* "maximize a single agent's capabilities first". The manager vs decentralized multi-agent patterns. When to build an agent at all. (Month of publication from memory, not re-checked.)
- **LangChain Academy, Intro to LangGraph**: Module 3 (time travel) and Module 6 (double texting). https://academy.langchain.com/courses/intro-to-langgraph
  *Take:* hands-on checkpointers and time travel, the framework counterpart to [`code/run_log.py`](code/run_log.py). Continue in [09-frameworks-langchain-langgraph](../09-frameworks-langchain-langgraph/README.md).
- **Steve Yegge, Gas Town** (2026). https://github.com/steveyegge/gastown
  *Take:* the extreme pro-multi-agent counterpoint, with 20-30 parallel instances, a merge-queue role that runs verification, and a stuck-agent detector. Details come from secondary sources and the README. Treat claims beyond the README as reported, not verified.

## Not verified, so not used as fact
- OpenAI's GPT-6 multi-agent beta defaults (e.g. `max_concurrent_subagents`) appear only in a secondary article in the research notes, and are not cited in this module.
- The exact `multitask_strategy` parameter name on `runs.create` was not confirmed against an API reference page. The module refers to it generically.
