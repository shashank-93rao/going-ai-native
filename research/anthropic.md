# Research: what Anthropic says (as of 2026-10-19)

Scope: anthropic.com/engineering (full index read on 2026-10-19), anthropic.com/research and /news, platform.claude.com docs (formerly docs.claude.com), code.claude.com docs, claude.com/blog and claude.dev/blog, plus a few secondary sources for Claude Code team talks. 49 entries.

**How to read this file**
- Quotes were pulled from pages through a fetch tool. They are short and were requested verbatim, but check each one against the live page before it goes on a slide. Anything I could not confirm on an Anthropic page is marked **[UNVERIFIED]** or **[SECONDARY]**.
- Several older URLs now redirect, and the redirect target is the URL listed. For example, `anthropic.com/engineering/claude-code-best-practices` goes to `code.claude.com/docs/en/best-practices`, and `docs.claude.com/...` goes to `platform.claude.com/docs/...`.
- Module numbers refer to `00-draft-topics.md` (00 to 14, 06b, 06c, 99).
- Model names in this file (Opus 4.x, 5, 5.5, Sonnet 5.5, Haiku 5.5, Fable, Mythos) are the ones the sources use.

---

## A. Agent architecture and loops

### 1. Building effective agents
- **URL:** https://www.anthropic.com/engineering/building-effective-agents
- **Date:** 2024-12-19 (Erik Schluntz, Barry Zhang). The page now carries a note that tooling has changed and points to Managed Agents. Its model examples were updated to Haiku 4.5 and Sonnet 4.5.
- **Key claims**
  - Successful teams use simple, composable patterns, not complex frameworks.
  - Taxonomy:
    - **Workflows** are LLMs and tools orchestrated through predefined code paths.
    - **Agents** are LLMs that direct their own process and tool use.
  - The building block is the **augmented LLM**: retrieval, tools and memory.
  - Agentic systems trade latency and cost for task performance. Start with a single call plus retrieval and examples, and add complexity only when it measurably helps.
  - Frameworks add abstraction layers that hide prompts and responses and make debugging harder.
- **Practical techniques**
  - Five workflow patterns, each with a "when to use":
    - prompt chaining, with programmatic gates between steps
    - routing, e.g. easy queries go to a cheap model
    - parallelization: sectioning, or voting
    - orchestrator-workers, where subtasks are not predefined
    - evaluator-optimizer, used when clear criteria exist and iteration measurably helps
  - Autonomous agents are "LLMs using tools based on environmental feedback in a loop". Pair them with stopping conditions such as max iterations and with human checkpoints.
  - Three principles: simplicity, transparency (show the plan), and the agent-computer interface (ACI).
  - Appendix 2 on tool design:
    - Give the model room to think before it commits.
    - Use formats common in internet text.
    - Avoid formats that force line-counting or string escaping.
    - Write tool docs like docstrings for a junior developer.
    - **Poka-yoke** the tools.
- **Notable quote/anecdote:**
  - "add multi-step agentic systems only when simpler solutions fall short."
  - "Poka-yoke your tools."
  - Anecdote: in the SWE-bench agent, relative paths broke after the agent changed directory. Requiring absolute paths fixed it. They "spent more time optimizing our tools than the overall prompt."
- **Maps to:** 06, 06b, 05, 06c (the argument against frameworks)

### 2. How Claude Code works (the agentic loop)
- **URL:** https://code.claude.com/docs/en/how-claude-code-works
- **Date:** living doc (read 2026-10-19)
- **Key claims**
  - The loop has three phases that blend together: **gather context, take action, verify results**, repeated until done. The user can interrupt at any point.
  - The "agentic harness" is the layer around the model that supplies tools and manages context.
  - Tools fall into five categories: file ops, search, execution, web, code intelligence.
  - Sessions are stored as JSONL under `~/.claude/projects/`. Edits are checkpointed before they are applied. Remote side effects cannot be checkpointed.
- **Practical techniques**
  - When context fills, Claude Code clears old tool outputs first, then summarizes. Persistent rules belong in CLAUDE.md, because early instructions can be lost to compaction.
  - Steer a session by queuing a message mid-turn. Claude reads it after the current tool calls finish.
  - Auto-compaction stops after a few attempts and shows a "thrashing" error, rather than looping forever. This is a runaway-loop guard worth showing in 06b.
  - MCP tool definitions are deferred by default and loaded through tool search.
- **Notable quote:** "Claude Code is the layer around the model that provides the tools and manages the context the model sees."
- **Maps to:** 06b, 03, 04

### 3. Building agents with the Claude Agent SDK
- **URL:** https://claude.com/blog/building-agents-with-the-claude-agent-sdk (redirected from anthropic.com/engineering)
- **Date:** 2025-09-29 (Thariq Shihipar)
- **Key claims**
  - The Claude Code SDK was renamed the Agent SDK because the same harness now runs most of Anthropic's agent loops, including non-coding ones.
  - Design principle: "give your agents a computer".
- **Practical techniques**
  - **Gather context**
    - Agentic search (grep/tail over a folder structure) comes first. The folder layout is itself context engineering.
    - Add semantic search only when speed or query variety demands it.
    - Use subagents for parallel work and clean context.
    - Rely on compaction for long runs.
  - **Take action**
    - Design tools as the primary actions.
    - Use bash for general work.
    - Generate code when you need precise, reusable operations.
    - Use MCP for integrations.
  - **Verify work**
    - Rules and linting give the best feedback. TypeScript gives richer lint feedback than JS.
    - Use visual feedback (Playwright screenshots).
    - Use LLM-as-judge only when the gain is worth it, because it is "not very robust" and adds latency.
  - **Improving the agent**
    - Read failures and ask whether the agent has the right tools.
    - Ask whether search APIs could be restructured, and whether a formal rule could catch a repeated failure.
    - Build a representative test set from real usage.
- **Notable quote:** "Agents often operate in a specific feedback loop: gather context -> take action -> verify work -> repeat."
- **Maps to:** 06, 06b, 11, 06c (the raw-SDK side of the comparison)

### 4. Effective harnesses for long-running agents
- **URL:** https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents
- **Date:** 2025-11-26 (Justin Young)
- **Key claims**
  - Long tasks span many context windows, and each new session starts with amnesia. Compaction alone is not enough.
  - Even Opus 4.5 on the Agent SDK fell short of a production-quality claude.ai clone from a high-level prompt alone.
  - Two failure modes:
    - **Overreach:** builds everything at once, runs out of context mid-feature, leaves work undocumented.
    - **Premature completion:** sees existing progress and declares the project done.
- **Practical techniques**
  - **Initializer agent.** The first session uses a different user prompt. Same system prompt, tools and harness. It writes:
    - `init.sh`
    - `claude-progress.txt`
    - a JSON **feature list** with more than 200 features, all initially failing
    - an initial git commit
  - **Coding agent.** Each later session does one feature at a time, tests it end to end, commits, and updates progress.
  - Use a JSON feature list rather than Markdown, because the model is less likely to rewrite JSON inappropriately. Agents may only flip `passes`.
  - Startup ritual for every session:
    1. `pwd`
    2. read the git log and progress notes
    3. pick the highest-priority failing feature
    4. run `init.sh` and a smoke e2e test before starting new work
  - Browser automation (Puppeteer MCP) for testing as a user. Claude had been marking features done after unit tests or curl, even when they failed end to end. Known blind spot: native alert modals.
  - The article includes a failure-mode-to-fix table that can be reused in the course.
- **Notable quote:** "It is unacceptable to remove or edit tests because this could lead to missing or buggy functionality."
- **Maps to:** 06b (core), 03, 10, 11

### 5. Harness design for long-running application development
- **URL:** https://www.anthropic.com/engineering/harness-design-long-running-apps
- **Date:** 2026-03-24 (Prithvi Rajasekaran, Labs)
- **Key claims**
  - Two problems:
    - Coherence degrades as context fills. Sonnet 4.5 showed "context anxiety", wrapping up early.
    - Agents grade their own work too generously.
  - Splitting generator from evaluator, loosely inspired by GANs, fixes the second.
  - Every harness component encodes an assumption about what the model can't do alone. Re-test those assumptions with each new model.
- **Practical techniques**
  - **Frontend loop.** Make taste gradable with four criteria: design quality, originality, craft, functionality. Weight the first two more heavily.
    - Calibrate the evaluator with few-shot examples.
    - The evaluator uses Playwright on the live page.
    - Runs took 5 to 15 iterations and up to 4 hours.
  - **Three agents**
    - Planner: turns a 1 to 4 sentence prompt into a spec and stays high-level so spec errors don't cascade.
    - Generator: works in sprints, one feature at a time, using git.
    - Evaluator: clicks through the app, API and DB. Each criterion has a hard threshold.
  - **Sprint contracts.** Before each sprint the generator proposes what it will build and how success will be checked. The evaluator negotiates until they agree. They communicate through files. Sprint 3 had 27 criteria.
  - Tune the evaluator prompt over several rounds by reading its logs. It started out lenient and superficial.
  - Context resets with a handoff artifact were essential on Sonnet 4.5. On Opus 4.5 they were dropped in favor of auto-compaction.
  - On Opus 4.6 the sprints were removed and the evaluator became one pass at the end.
- **Numbers**
  - Solo run: 20 min, $9, and the core feature was broken.
  - Full harness: 6 hr, $200 (more than 20x the cost), much more functional.
  - Opus 4.6 DAW build: 3 hr 50 min, $124.70, with three build/QA rounds.
- **Notable quotes:**
  - "agents reliably skew positive when grading their own work."
  - "Out of the box, Claude is a poor QA agent."
  - "every component in a harness encodes an assumption about what the model can't do on its own"
- **Maps to:** 06b, 06 (evaluator-optimizer), 08, 11, 10

### 6. Building a C compiler with a team of parallel Claudes
- **URL:** https://www.anthropic.com/engineering/building-c-compiler
- **Date:** 2026-02-05 (Nicholas Carlini, Safeguards)
- **Key claims**
  - With no orchestrator and no human online, 16 agents built a 100k-line Rust C compiler that builds Linux 6.9 on x86, ARM and RISC-V.
  - Most of the effort went into the environment: tests, oracles and the harness.
- **Practical techniques**
  - **Ralph-style loop.** A bash `while true` restarts `claude -p "$(cat AGENT_PROMPT.md)"` each time a session ends, with logs named by commit. Run it in a container. The script is reproduced in section G.
  - **Coordination through git**
    - A bare repo is mounted at `/upstream`. Each agent clones it to `/workspace`.
    - **Lock files** in `current_tasks/` claim tasks. Git conflicts make a second claimant pick another task.
  - **Tests must be near-perfect,** because agents solve whatever the verifier checks. Add CI once regressions appear.
  - **Oracle-based bisection.** Compile most kernel files with GCC and a random subset with Claude's compiler, so parallel agents can each fix different bugs. Add delta debugging for pairs of files that fail together.
  - **Make the harness agent-friendly**
    - Print only a few lines and send the rest to log files.
    - Put `ERROR` on the same line so grep finds it.
    - Precompute summary stats.
    - Offer a `--fast` mode that runs a random 1% or 10% sample, deterministic per agent, to handle "time blindness".
  - Keep READMEs and progress files current, because each agent starts in a fresh container.
  - Use specialized roles: dedup, performance, codegen quality, Rust-idiom critic, docs.
- **Numbers**
  - About 2,000 sessions over 2 weeks.
  - About 2B input and 140M output tokens.
  - Just under $20k.
  - About 99% on the GCC torture suite.
- **Notable quotes:**
  - "For autonomous systems, it is easy to see tests pass and assume the job is done, when this is rarely the case."
  - "The resulting compiler has nearly reached the limits of Opus's abilities."
- **Maps to:** 06b (core), 04 (parallel agents), 10, 14

### 7. Ralph Wiggum plugin (official Claude Code plugin)
- **URL:** https://github.com/anthropics/claude-code/tree/main/plugins/ralph-wiggum (README read through raw.githubusercontent.com)
- **Date:** undated README in Anthropic's claude-code repo. The technique comes from Geoffrey Huntley (ghuntley.com/ralph).
- **Key claims**
  - "Ralph is a Bash loop." The plugin moves the loop inside one session.
  - A **Stop hook** intercepts exit and feeds back *the same prompt*. Each pass sees the previous pass's files and git history.
- **Practical techniques**
  - Usage: `/ralph-loop "<prompt>" --max-iterations N --completion-promise "DONE"`, and `/cancel-ralph` to stop.
  - Prompt guidance:
    - concrete completion criteria
    - incremental phases
    - built-in self-correction (TDD: run tests, fix)
    - escape hatches: **always** set `--max-iterations`, and tell the agent what to output if it is stuck
  - Caveat: the completion promise is an exact string match, so it can't tell "success" from "blocked".
  - Good fit: work with automatic checks, greenfield work, refinement. Poor fit: judgment-heavy work, unclear criteria, production debugging.
- **Notable anecdote (as cited in the README, not verified by Anthropic):** a "$50k contract completed for $297 in API costs", and six repos generated overnight at a YC hackathon.
- **Maps to:** 06b (core), 11

### 8. `/goal`: keep Claude working toward a condition
- **URL:** https://code.claude.com/docs/en/goal
- **Date:** living doc (read 2026-10-19)
- **Key claims**
  - `/goal <condition>` keeps the session taking turns until a **separate evaluator model** judges the condition met or impossible, or until an unrecoverable error occurs.
  - The evaluator is a session-scoped prompt-based Stop hook running on the small fast model.
  - Completion is decided by a fresh model, not the worker.
- **Practical techniques**
  - Comparison table:
    - `/goal`: the next turn starts after the previous one, and stops when the condition holds.
    - `/loop`: the next turn starts when a time interval elapses.
    - Stop hook: your own script decides.
  - Writing a good condition:
    - one measurable end state
    - a stated check (`npm test` exits 0)
    - invariants (no other test file modified)
    - a budget clause ("or stop after 20 turns")
  - The evaluator does not run tools. It judges only what is in the transcript, so the worker has to *surface* the evidence.
  - Stall guard: several turns in a row with no tool use stop the loop and hand control back.
  - Runaway and failure handling:
    - Auth, credit and context-overflow errors clear the goal.
    - Transient errors retry up to 3 times, then pause.
    - Background work defers evaluation, with check-ins at 30 min that back off.
  - Non-interactive use: `claude -p "/goal ..."` together with `--output-format stream-json`.
- **Notable quote:** "completion is decided by a fresh model rather than the one doing the work."
- **Maps to:** 06b (core), 11

### 9. `/loop`, cron tools and scheduled agents (routines, desktop tasks)
- **URL:** https://code.claude.com/docs/en/scheduled-tasks (also /routines, /desktop-scheduled-tasks)
- **Date:** living doc (read 2026-10-19)
- **Key claims**
  - There are three scheduling surfaces:
    - **Cloud routines:** no machine needed, fresh clone, minimum interval 1 h.
    - **Desktop tasks:** local, minimum 1 min.
    - **`/loop`:** session-scoped, minimum 1 min.
  - `/loop` comes in three forms:
    - fixed interval (`/loop 5m check the deploy`)
    - self-paced (no interval, so Claude picks 1 min to 1 h based on what it saw)
    - bare `/loop`, which runs a built-in maintenance prompt or your `loop.md`
- **Practical techniques**
  - The maintenance prompt runs in order:
    1. continue unfinished work
    2. tend the branch's PR (comments, CI, conflicts)
    3. cleanup passes
    It takes irreversible actions only when the transcript already authorized them.
  - `.claude/loop.md` customizes it. Edits take effect on the next iteration, so the instructions can be tuned while the loop runs.
  - **Bounds**
    - Recurring tasks expire after 7 days ("bounds how long a forgotten loop can run").
    - A session holds at most 50 tasks.
    - Missed fires are not caught up.
    - Self-paced loops end with `ScheduleWakeup stop:true`, or after a fallback wakeup about 20 min later that doesn't reschedule.
  - Use the Monitor tool or Channels instead of polling when events can be streamed or pushed.
  - Jitter: recurring tasks run late, up to half the interval and at most 30 min. `*/5` runs 15 s early to stay inside the 5-minute prompt-cache TTL.
- **Notable quote:** "Recurring tasks automatically expire 7 days after creation... This bounds how long a forgotten loop can run."
- **Maps to:** 06b (core), 12

### 10. Hooks guide (Stop hooks, prompt and agent hooks, loop guards)
- **URL:** https://code.claude.com/docs/en/hooks-guide (reference: /docs/en/hooks)
- **Date:** living doc
- **Key claims**
  - Hooks give deterministic control. CLAUDE.md instructions are advisory; hooks are guaranteed.
  - There are three kinds beyond plain commands: command, **prompt** (a single LLM call returning `{"ok": bool, "reason"}`), and **agent** (an experimental subagent with tools, up to 50 turns).
- **Practical techniques**
  - Exit codes: `exit 2` blocks, and stderr goes back to Claude as feedback.
  - Example: a `PreToolUse` hook on `Edit|Write` that blocks `.env`, `package-lock.json` and `.git/`.
  - Stop hook as a completion gate:
    - A prompt Stop hook: "Check if all tasks are complete. If not, respond with {"ok": false, "reason": ...}".
    - An agent Stop hook: "Verify that all unit tests pass. Run the test suite..."
  - `"impossible": true` lets a prompt hook end a goal that can never be met.
  - **Loop guard**
    - Claude Code overrides a Stop hook after **8 consecutive blocks** with no tool call in between.
    - Scripts should check `stop_hook_active` and exit 0 when it is set.
    - The cap is tunable through `CLAUDE_CODE_STOP_HOOK_BLOCK_CAP`.
  - Other hook uses: re-inject context after compaction (`SessionStart` with the compact matcher), audit config changes, auto-format on `PostToolUse`.
- **Notable quote:** "Claude Code overrides a Stop hook after it blocks eight times in a row with no tool call from Claude in between."
- **Maps to:** 05, 06b, 11

### 11. Dynamic workflows (orchestration as a script)
- **URL:** https://code.claude.com/docs/en/workflows
- **Date:** living doc (read 2026-10-19)
- **Key claims**
  - A workflow is a JavaScript script, written by Claude, that orchestrates many subagents. The *plan moves into code*, intermediate results live in script variables rather than in context, and the script can be rerun.
  - A comparison table shows who holds the plan in each option: subagents, skills, agent teams, workflows.
- **Practical techniques**
  - Primitives: `agent(prompt, {schema})`, `pipeline(items, fn)`, `parallel()`, `phase()`, `log()`.
  - Determinism: `Date.now()` and `Math.random()` throw, so a resumed run replays the same calls.
  - Schema-validated outputs retry up to 5 times.
  - Example prompt shapes:
    - "keep fixing until tsc passes or **two rounds in a row make no progress**"
    - "find flaky tests... stop once **two rounds in a row find nothing new**"
    - "**adversarially verify each finding** before reporting"
  - Runaway bounds:
    - 1,000 agents per run
    - 16 concurrent agents
    - 4,096 items per `parallel` call
    - a "Large workflow" warning above 25 agents or 1.5M projected tokens
    - stalled agents restart up to 5 times
  - `/deep-research` is a bundled workflow. It fans out, cross-checks sources, votes on claims, and marks claims as unverified rather than refuted when the checker failed.
- **Notable quote:** "A workflow moves the plan into code."
- **Maps to:** 06, 06b, 06c (Anthropic's built-in alternative to a LangGraph-style graph), 04

### 12. Subagents and agent teams (Claude Code docs)
- **URLs:** https://code.claude.com/docs/en/sub-agents and https://code.claude.com/docs/en/agent-teams
- **Date:** living docs
- **Key claims**
  - A subagent runs in its own context and returns a summary. Agent teams (experimental) are a lead plus peer sessions with a shared task list and mailboxes.
  - Teams cost more tokens. Use them when peers need to challenge each other.
- **Practical techniques**
  - Subagent frontmatter:
    - `tools`
    - `model` (route cheap work to haiku)
    - `isolation: worktree`
    - `maxTurns` (a budget)
    - `permissionMode`
    - `memory: project`
    - `hooks`
  - Nesting goes 3 layers deep by default, with 20 concurrent subagents.
  - Restate CLAUDE.md rules in the delegation prompt, because non-fork subagents don't see conversation history.
  - Team guidance:
    - Start with 3 to 5 teammates and 5 to 6 tasks each.
    - Give each teammate its own files to avoid overwrites.
    - Quality gates: `TeammateIdle`, `TaskCompleted`, `TaskCreated` hooks, where exit 2 keeps the agent working.
  - Competing-hypotheses debugging: "Spawn 5 agent teammates to investigate different hypotheses. Have them talk to each other to try to disprove each other's theories, like a scientific debate." The rationale is that this beats anchoring.
  - Security: a message from another agent is marked as non-user. A teammate can't approve on your behalf.
- **Notable quote:** "Three focused teammates often outperform five scattered ones."
- **Maps to:** 04, 06, 05

### 13. Scaling Managed Agents: decoupling the brain from the hands
- **URL:** https://www.anthropic.com/engineering/managed-agents
- **Date:** 2026-04-08 (Lance Martin, Gabe Cemaj, Michael Cohen)
- **Key claims**
  - Harnesses encode assumptions that go stale. Context resets helped Sonnet 4.5 and were dead weight on Opus 4.5.
  - Virtualize three things:
    - **session:** an append-only event log
    - **harness:** the loop
    - **sandbox:** execution
- **Practical techniques**
  - Treat containers as **cattle, not pets.** A sandbox failure becomes a tool-call error that Claude can retry on a fresh container.
  - A harness crash is recoverable: `wake(sessionId)` and replay the log.
  - Keep loop state *outside* the context. The session log is a queryable object (`getEvents()`), so compaction does not have to make irreversible choices.
  - Interfaces: `execute(name,input)->string`, `provision`, `emitEvent`.
  - Keep credentials structurally out of reach of generated code:
    - Git tokens are used only at clone time.
    - OAuth tokens sit in a vault behind an MCP proxy.
- **Numbers:** p50 TTFT about 60% lower, p95 more than 90% lower.
- **Notable quotes:**
  - "Harnesses encode assumptions that go stale as models improve."
  - "The container became cattle."
- **Maps to:** 06b (durable loops, as reconcilers), 12, 13, 06c (compare with LangGraph checkpointing)

### 14. Building effective agent automations (scheduled Managed Agent)
- **URL:** https://claude.dev/blog/building-effective-agent-automations/
- **Date:** 2026-10-08 (Lance Martin, CJ Avilla). The reference implementation is in `anthropics/claude-quickstarts`.
- **Key claims**
  - Scheduled agents fail quietly. They lose access to a source, or drift from your preferences, and nobody notices.
  - Six components: Sources, Destination, Agent, Schedule, Memory, Guardrails.
- **Practical techniques**
  - Config as files: `agent.md`, `deployment.md` (cron `32 7 * * 1-5`, budget 500 cents), `environment.yaml` (network allowlist), memory stores, `vault.yaml`.
  - **Bookmarks rather than time windows.** "A late run leaves a gap and an early run repeats items."
  - A **ledger** with stable IDs.
  - **Idempotency**
    - Check whether today's post exists before posting.
    - Count a post as sent only on `"ok": true` plus a ts.
    - Otherwise record "maybe posted".
  - A failed read is reported as unreadable, never as a quiet day.
  - Re-verify every item against its live source just before posting.
  - Preferences live in a read-only store that the agent re-reads every run.
  - Budget: start at 3 to 5x the cost of a normal run. A capped run pauses with `budget_reached`.
- **Notable quote:** "One stale "still waiting on you" costs more trust than ten missing items, so never hedge an item's status: assert it or drop it."
- **Maps to:** 06b (scheduled loops), 12, 11

---

## B. Context engineering, tools and MCP

### 15. Effective context engineering for AI agents
- **URL:** https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- **Date:** 2025-09-29 (Rajasekaran, Dixon, Ryan, Hadfield)
- **Key claims**
  - Context is a finite "attention budget" with diminishing returns.
  - **Context rot:** recall degrades as the token count grows. It is a gradient, not a cliff. One cause is n² attention.
  - System prompts should sit at the "right altitude", between brittle if-else rules and vague guidance.
- **Practical techniques**
  - Start with a minimal prompt and add instructions only in response to observed failures.
  - Prefer a few canonical, diverse examples over a list of edge cases.
  - Avoid bloated, overlapping toolsets. "If a human engineer can't definitively say which tool should be used... an AI agent can't be expected to do better" (paraphrase; check wording).
  - **Just-in-time retrieval:** pass references (paths, queries) and load the content with tools.
  - Hybrid: preload CLAUDE.md and explore the rest.
  - **Compaction:** keep decisions, open bugs and implementation details; drop redundant tool output. Tune for recall first, then precision. Clearing tool results is the lightest form.
  - **Structured notes:** NOTES.md or to-do lists outside the window, plus the memory tool.
  - **Subagents** return condensed results of 1k to 2k tokens after using tens of thousands.
  - Which to use when:
    - compaction for long back-and-forth
    - notes for milestone-based work
    - multi-agent for parallel research
- **Notable quote:** "find the smallest set of high-signal tokens that maximize the likelihood of your desired outcome."
- **Maps to:** 03 (core), 01, 06

### 16. Writing effective tools for agents, with agents
- **URL:** https://www.anthropic.com/engineering/writing-tools-for-agents
- **Date:** 2025-09-11 (Ken Aizawa)
- **Key claims**
  - Tools are a contract between deterministic systems and non-deterministic agents.
  - More tools do not mean better results.
  - Improve tools with an eval-driven loop in which agents help optimize the tools.
- **Practical techniques**
  - **Generate eval tasks with Claude Code** from real data. Good tasks need many tool calls. Use verifiers that are not overly strict.
  - Run each task in a simple agent loop and have the agent output reasoning and feedback before tool calls.
  - Metrics to collect:
    - accuracy
    - runtime
    - number of tool calls
    - tokens
    - tool errors
  - **Held-out test set** to avoid overfitting.
  - Paste the concatenated transcripts into Claude Code and have it refactor the tools.
  - Design rules:
    - Consolidate operations: `schedule_event` instead of list plus create, `search_logs` instead of `read_logs`.
    - Namespace tools (`asana_projects_search`).
    - Return semantic names instead of UUIDs.
    - Offer a `response_format` enum of concise or detailed (72 vs 206 tokens).
    - Paginate and truncate. Claude Code's default cap is 25k tokens per tool response.
    - Write actionable error messages.
    - Use unambiguous parameter names (`user_id`).
- **Notable anecdote:** Claude's web search tool kept appending "2025" to queries. Changing the tool description fixed it.
- **Notable quote:** "Avoid overly strict verifiers that reject correct responses due to spurious differences like formatting, punctuation, or valid alternative phrasings."
- **Maps to:** 05 (core), 09 (hill-climbing tools), 07

### 17. Code execution with MCP
- **URL:** https://www.anthropic.com/engineering/code-execution-with-mcp
- **Date:** 2025-11-04 (Adam Jones, Conor Kelly)
- **Key claims**
  - Direct tool calling breaks down at scale for two reasons. Every tool definition is loaded up front, and every intermediate result passes through the model.
  - Present MCP servers as a code API on a filesystem instead.
- **Practical techniques**
  - Tree layout: `servers/google-drive/getDocument.ts`. The agent lists directories and reads only the definitions it needs (progressive disclosure), or calls `search_tools` with a detail level.
  - Filter and aggregate in code. Example: 10k spreadsheet rows, of which only 5 are logged to the model.
  - Run loops and polling in code.
  - PII tokenization in the MCP client.
  - Save working code as functions, plus a SKILL.md, so it becomes a skill.
  - Tradeoff: you now need a sandbox, resource limits and monitoring.
- **Numbers:** 150,000 to 2,000 tokens, a 98.7% reduction. Cloudflare reports similar results with "Code Mode".
- **Notable quote:** "Agents scale better by writing code to call tools instead."
- **Maps to:** 05, 03, 13

### 18. Introducing advanced tool use (Tool Search, Programmatic Tool Calling, Tool Use Examples)
- **URL:** https://www.anthropic.com/engineering/advanced-tool-use
- **Date:** 2025-11-24 (Bin Wu et al.)
- **Key claims**
  - Tool definitions can consume 55k to 134k tokens before the conversation starts.
  - Three beta features address this: tool search, programmatic tool calling, and tool use examples.
- **Practical techniques**
  - **Tool Search:** mark tools `defer_loading: true` and keep 3 to 5 hot tools loaded. Use it when definitions exceed 10k tokens or there are more than 10 tools.
  - **Programmatic Tool Calling:** Claude writes Python that calls tools in a sandbox. Use it for 3 or more dependent calls or for large data.
  - **Tool Use Examples:** 1 to 5 realistic examples per tool, focused on ambiguous cases.
- **Numbers**
  - Tool search:
    - context about 77k to 8.7k tokens
    - MCP eval accuracy on Opus 4: 49% to 74%
    - MCP eval accuracy on Opus 4.5: 79.5% to 88.1%
  - Programmatic tool calling:
    - tokens 43,588 to 27,297 (-37%)
    - GIA 46.5% to 51.2%
  - Tool use examples: complex-parameter accuracy 72% to 90%.
- **Notable quote:** "Code is a natural fit for orchestration logic, such as loops, conditionals, and data transformations."
- **Maps to:** 05, 03

### 19. Equipping agents for the real world with Agent Skills
- **URL:** https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills
- **Date:** 2025-10-16, updated 2025-12-18 when Skills became an open standard (Barry Zhang, Keith Lazuka, Mahesh Murag)
- **Key claims**
  - A skill is a folder of instructions, scripts and resources.
  - **Progressive disclosure** happens at three levels:
    1. name and description, in the system prompt
    2. the SKILL.md body
    3. linked files, read only when needed
- **Practical techniques**
  - Evaluate first: run representative tasks, find the gaps, and build skills for those gaps.
  - Split large SKILL.md files.
  - Say explicitly whether a script is meant to be *executed* or *read*.
  - Tune the name and description, because they decide when the skill triggers.
  - Have Claude write its successes and mistakes back into the skill.
  - Security: install only trusted skills. Audit scripts, dependencies and network calls.
- **Notable quote:** "Progressive disclosure is the core design principle that makes Agent Skills flexible and scalable."
- **Maps to:** 05, 03

### 20. The "think" tool
- **URL:** https://www.anthropic.com/engineering/claude-think-tool
- **Date:** 2025-03-20. An update on 2025-12-15 says extended thinking is now recommended instead in most cases.
- **Key claims**
  - A no-op `think(thought)` tool gives Claude a scratchpad *between* tool calls. It helps most in policy-heavy, sequential tool use.
- **Practical techniques**
  - Pair the tool with a domain prompt that says when to think and gives worked examples, such as listing the applicable rules and checking that all required info is collected.
  - Skip it for single or parallel calls.
- **Numbers**
  - τ-bench airline pass^1: 0.584 with the think tool plus an optimized prompt, vs 0.332 baseline.
  - pass^5: 0.340 vs 0.100.
  - SWE-bench: +1.6%.
  - The page's prose and its table disagree, so cite the table.
- **Notable quote:** "we recommend using that feature instead of a dedicated think tool in most cases" (the 2025-12 update)
- **Maps to:** 02, 05, 07 (an example of pass^k reporting)

### 21. Introducing Contextual Retrieval
- **URL:** https://www.anthropic.com/engineering/contextual-retrieval
- **Date:** 2024-09-19
- **Key claims**
  - Chunks lose their context. Prepend a short, LLM-generated context to each chunk before embedding it and before BM25 indexing.
- **Practical techniques**
  - Use Haiku with the full document cached and a prompt that ends "Answer only with the succinct context and nothing else."
  - Hybrid retrieval: BM25 plus embeddings, rank fusion, retrieve the top 150, rerank to the top 20.
  - Pass 20 chunks rather than 5 or 10.
  - **If the knowledge base is under 200k tokens, skip RAG and put it all in the prompt with caching.**
- **Numbers**
  - Top-20 retrieval failure falls by 35% with contextual embeddings, by 49% when BM25 is added, and by 67% with reranking (5.7% to 1.9%).
  - The one-time contextualization cost is about $1.02 per million doc tokens.
- **Maps to:** 03

### 22. Raising the bar on SWE-bench Verified with Claude 3.5 Sonnet
- **URL:** https://www.anthropic.com/engineering/swe-bench-sonnet
- **Date:** 2025-01-06
- **Key claims**
  - A minimal scaffold (prompt, bash tool, edit tool) that lets the model decide its own steps scored 49%, beating the previous state of the art of 45%.
- **Practical techniques**
  - Absolute paths only.
  - `str_replace` edits that must match exactly once, and return an error otherwise.
  - The prompt suggests: explore, write a repro script, fix, rerun the repro, check edge cases.
  - The stop condition is "the model decides it's finished, or exceeds its 200k context length".
- **Notable quote:** "many successful runs took hundreds of turns for the model to resolve, and >100k tokens."
- **Lessons on grading:** hidden tests mean the model can believe it succeeded when it hasn't. Some failures were environment bugs, such as patches applied twice.
- **Maps to:** 05, 06b, 10

---

## C. Evals and hill-climbing

### 23. Demystifying evals for AI agents
- **URL:** https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents
- **Date:** 2026-01-09 (Mikaela Grace, Jeremy Hadfield, Rodrigo Olivares, Jiri De Jonghe)
- **Key claims**
  - Vocabulary:
    - task
    - trial
    - grader (made of assertions)
    - transcript/trace
    - **outcome**, meaning the environment's final state, e.g. "is there a reservation in the DB", not "did the agent say it booked"
    - eval harness vs agent harness
    - suite
  - Evaluating an agent means evaluating harness plus model.
  - Three grader types:
    - code: fast, objective, brittle
    - model: flexible, needs calibration
    - human: gold standard, slow
  - **pass@k vs pass^k.** At 75% per-trial success, pass^3 ≈ 42%. Use pass^k for customer-facing consistency.
  - **Capability evals** start low (a hill to climb). **Regression evals** sit near 100%. Graduate capability evals into the regression suite.
- **Practical techniques (8-step roadmap)**
  0. Start early with **20 to 50 tasks drawn from real failures.**
  1. Convert manual checks and bug-tracker items into tasks.
  2. Write unambiguous tasks with reference solutions. "0% pass@100 is most often a signal of a broken task."
  3. Balance sets so they test both when a behavior should happen and when it shouldn't. Example: web search over-triggering and under-triggering.
  4. Keep a stable, isolated harness: a clean environment per trial. Claude once used git history from earlier trials, and shared memory limits caused correlated failures.
  5. Grade outcomes, not paths. Give partial credit. Give the LLM judge an "Unknown" option. Use one judge per dimension. Make graders hack-resistant.
  6. **Read the transcripts.**
  7. Watch for saturation.
  8. A dedicated evals team owns the infrastructure; domain experts and PMs contribute tasks, even as PRs written with Claude Code.
- **Other techniques**
  - Per-agent recipes:
    - **Coding:** fail-to-pass tests plus an LLM rubric.
    - **Conversational:** state check, turn limit, tone rubric, simulated user.
    - **Research:** groundedness, coverage, source quality.
    - **Computer use:** backend state checks.
  - The Swiss-cheese model: layer automated evals, production monitoring, A/B tests, user feedback, transcript review and human studies.
  - Frameworks listed: Harbor, Braintrust, LangSmith, Langfuse, Arize.
- **Notable anecdote:** Opus 4.5 scored 42% on CORE-Bench and 95% after grader and scaffold bugs were fixed, e.g. rigid numeric matching rejected "96.12". Qodo's one-shot evals missed Opus 4.5's gains on long tasks.
- **Notable quote:** "it's often better to grade what the agent produced, not the path it took."
- **Maps to:** 07 (core), 08, 09, 10

### 24. A statistical approach to model evaluations ("Adding Error Bars to Evals")
- **URL:** https://www.anthropic.com/research/statistical-approach-to-model-evals (paper: arXiv 2411.00640, Evan Miller)
- **Date:** 2024-11-19
- **Key claims**
  - An eval is a sample from a "question universe". Report a standard error and a 95% CI (mean ± 1.96·SEM).
- **Practical techniques (5 recommendations)**
  1. Use the CLT and report SEM.
  2. **Cluster standard errors** when questions share a passage. Clustered SEs came out more than 3x naive on popular evals.
  3. Reduce within-question variance by resampling and averaging per question, or by using token probabilities.
  4. **Paired-difference tests** when comparing models on the same questions. Question-level correlation between frontier models is 0.3 to 0.7.
  5. **Power analysis** to choose the number of questions for a target effect size.
- **Notable quote:** "Statistics is the science of measurement in the presence of noise."
- **Maps to:** 09 (core), 07

### 25. Define success criteria / Create strong empirical evaluations (docs)
- **URLs:** https://platform.claude.com/docs/en/test-and-evaluate/define-success and https://platform.claude.com/docs/en/test-and-evaluate/develop-tests
- **Date:** living docs
- **Key claims**
  - Success criteria should be Specific, Measurable, Achievable and Relevant, and most apps need several at once.
  - Eval design: make it task-specific, automate where possible, and **"prioritize volume over quality"**.
- **Practical techniques**
  - Bad criterion: "classify sentiment well". Good: F1 ≥ 0.85 on a held-out set of 10k tweets.
  - A multidimensional example:
    - F1 ≥ 0.85
    - 99.5% non-toxic
    - 90% of errors are inconveniences, not egregious
    - 95% of responses under 200 ms
  - Worked graders: exact match, cosine similarity (consistency across paraphrases), ROUGE-L, LLM Likert (tone), LLM binary (PHI).
  - Use a different model to grade than to generate.
  - Likert grader prompt (verbatim from the doc): "Rate this customer service response on a scale of 1-5 for being {target_tone}: <response>{model_output}</response> 1: Not at all {target_tone} 5: Perfectly {target_tone} Output only the number."
- **Notable quote:** "More questions with slightly lower signal automated grading is better than fewer questions with high-quality human hand-graded evals."
- **Maps to:** 07, 08, 02

### 26. Automating eval design and hillclimbing with Claude (`/claude-api build-eval`, `/claude-api hillclimb`)
- **URL:** https://claude.dev/blog/automating-eval-design-and-hillclimbing/
- **Date:** the article page says 2026-09-28; the claude.com/blog listing shows 2026-10-07 (Lance Martin)
- **Key claims**
  - Four properties of a good eval:
    - tasks mirror production
    - score scales with capability and effort
    - **headroom:** the best model at max effort is well below 100%
    - low run-to-run variance
  - **Adversarial sampling trap.** Picking only cases the current model fails measures that model's "failure fingerprint". Pick cases a *human* judged hard.
- **Practical techniques**
  - **build-eval**
    - Example sources, in priority order: production transcripts, bug reports, 5 to 10 handwritten cases, synthesized cases.
    - Choose the cheapest grader that fits. Judge rubrics are written as *checkable claims, not a 1 to 5 scale*.
    - Pairwise comparison against the baseline, in blind random order.
    - The judge must not be the model under test.
    - Diagnostics: run the grader twice and compare verdicts, check the plumbing (timeouts, truncation), check headroom (≥95% means optimize cost instead).
  - **hillclimb**
    - Choose the surfaces it may change: prompt, skills, tool descriptions, model, effort, harness.
    - Random **train/test split.**
    - **Noise check before round 1.** Noise must be smaller than the smallest change you'd act on.
    - One root-cause patch per round.
    - Rules:
      - **train up but test flat: revert (overfit)**
      - any regression: revert
      - both up: keep
    - After 2 to 3 flat rounds, bucket the remaining failures by cause to find bad tasks or harness bugs.
    - Finish at the best test version and report CIs. If the gain is within noise, don't merge.
    - "Never paste failures into the prompt."
- **Numbers**
  - **Support bot**
    - Opus 4.8 high: 74.4% at 4.6¢.
    - After a prompt audit, moving to Sonnet 5 low, and adding routing rules: 98.9% on train at about 1¢.
    - Held-out: 90.5% vs 78.6% originally, at about 1/5 the cost.
  - **claude-api skill eval:** 66.1% to 77% to 80% to 87.9%. The last step came from fixing *broken graders*.
  - **Inbox router:** 0.681 to 0.875. Variant v2 (added worked examples) was reverted because train rose while test stayed flat.
- **Notable quotes:**
  - "A good task is one where two domain experts would reach the same verdict and everything the grader checks is stated in the task."
  - "If the hillclimber reads the failing transcripts, it should never paste the failure content into the prompt."
- **Maps to:** 09 (core), 07, 08, 99

### 27. Quantifying infrastructure noise in agentic coding evals
- **URL:** https://www.anthropic.com/engineering/infrastructure-noise
- **Date:** 2026-02-05 (Gian Segato)
- **Key claims**
  - In agentic evals, the resource budget is part of the task.
  - On Terminal-Bench 2.0, infrastructure configuration alone moved scores by **6 points** (p<0.01), which is more than many leaderboard gaps.
- **Practical techniques**
  - Infra errors fell from 5.8% at strict 1x to 0.5% uncapped.
  - Up to about 3x headroom fixes reliability without making the eval easier. Above 3x the eval measures something different, because agents can install big stacks.
  - Specify a guaranteed allocation *and* a separate kill threshold. Calibrate the band empirically and report it.
  - Run evals at different times of day and on different days.
  - Distrust leaderboard gaps under about 3 points without matched configurations. Naive binomial CIs already span 1 to 2 points.
  - SWE-bench was less sensitive: +1.54 points at 5x RAM.
- **Maps to:** 09, 10, 12

### 28. Eval awareness in Claude Opus 4.6's BrowseComp performance
- **URL:** https://www.anthropic.com/engineering/eval-awareness-browsecomp
- **Date:** 2026-03-06 (Russell Coleman)
- **Key claims**
  - In 2 of 1,266 problems, the model inferred it was in an eval, identified BrowseComp, found the decryption code on GitHub and a JSON mirror on HuggingFace, and decrypted the answer key.
  - 9 more problems were ordinary contamination. 16 other attempts failed.
  - Multi-agent setups had 3.7x the rate of unintended solutions (0.87% vs 0.24%).
- **Practical techniques**
  - URL blocklists weren't enough. Blocking search results that contain the benchmark's *name* worked.
  - Evals leave traces on the web: e-commerce sites cache agents' queries as indexed pages.
  - Treat eval integrity as adversarial and ongoing.
- **Numbers:** the eval-aware run used 40.5M tokens, 38x the median. Score adjusted from 86.81% to 86.57%.
- **Notable quote:** "treat eval integrity as an ongoing adversarial problem rather than a design-time concern."
- **Maps to:** 10, 13, 09

### 29. Designing AI-resistant technical evaluations
- **URL:** https://www.anthropic.com/engineering/AI-resistant-technical-evaluations
- **Date:** 2026-01-21 (Tristan Hume)
- **Key claims**
  - Anthropic's performance-engineering take-home (more than 1,000 candidates) was saturated in turn by Opus 4 and then Opus 4.5.
  - Problems that resemble well-documented work fall to AI. Novel, out-of-distribution puzzles hold up.
- **Numbers (cycles, lower is better):** Opus 4.5 in a casual Claude Code session scored 1790, about the best human in 2 hours. With the improved harness it reached 1363.
- **Notable quote:** "The original worked because it resembled real work. The replacement works because it simulates novel work."
- **Maps to:** 14 (hiring and skills), 09 (saturation)

---

## D. Claude Code practice and team workflows

### 30. Best practices for Claude Code (formerly the "Claude Code: Best practices for agentic coding" blog, 2025-04-18, Boris Cherny)
- **URL:** https://code.claude.com/docs/en/best-practices (308 redirect from anthropic.com/engineering/claude-code-best-practices)
- **Date:** living doc (read 2026-10-19); the original blog post is from 2025-04-18
- **Key claims**
  - Most advice follows from one constraint: the context window fills fast and performance degrades as it fills.
  - **Give Claude a way to verify its work.** Without a check, "looks done" is the only signal and *you* become the verification loop.
- **Practical techniques**
  - A ladder of verification strength:
    1. "run the check and iterate" in the prompt
    2. a `/goal` condition
    3. a **Stop hook** as a deterministic gate
    4. a verification subagent or workflow that tries to refute the result
  - Ask for evidence (test output, command run, screenshot), not assertions.
  - Explore, plan, implement, commit, with plan mode and Ctrl+G to edit the plan. "If you could describe the diff in one sentence, skip the plan."
  - Before and after prompts, e.g. "write a failing test that reproduces the issue, then fix it". "Address the root cause, don't suppress the error."
  - **CLAUDE.md**
    - For each line ask "Would removing this cause Claude to make mistakes?"
    - Use emphasis like IMPORTANT sparingly.
    - Treat it like code and prune it.
  - **Interview pattern.** "Interview me in detail using the AskUserQuestion tool... then write a complete spec to SPEC.md", then start a fresh session to implement. A good spec names files and interfaces, states what is out of scope, and ends with an e2e verification step.
  - **After 2 failed corrections, `/clear`** and write a better prompt. "A clean session with a better prompt almost always outperforms a long session with accumulated corrections."
  - Writer/Reviewer split across two sessions. One Claude writes the tests and another writes the code.
  - **Fan-out:** `for file in $(cat files.txt); do claude -p "Migrate $file ... Return OK or FAIL." --allowedTools ... --permission-mode dontAsk; done`. Test on 2 to 3 files first. `/batch` spreads the work over 5 to 30 worktree subagents.
  - Adversarial review subagent: "Report gaps, not style preferences." Warning: reviewers asked to find gaps will always find some, and chasing every one leads to over-engineering.
  - Named failure patterns:
    - kitchen-sink session
    - correcting over and over
    - over-specified CLAUDE.md
    - trust-then-verify gap
    - infinite exploration
- **Notable quote:** "Give Claude a check it can run: tests, a build, a screenshot to compare. It's the difference between a session you watch and one you walk away from."
- **Maps to:** 04 (core), 11, 03, 02

### 31. How Anthropic teams use Claude Code
- **URL:** https://claude.com/blog/how-anthropic-teams-use-claude-code (redirected from anthropic.com/news; a PDF version also exists)
- **Date:** 2025-07-24
- **Key claims**
  - Teams across Anthropic, including non-engineers, use Claude Code for onboarding, incident debugging and automation. The best teams treat it as a thought partner.
- **Practical techniques (by team)**
  - **Data Infra:** feed it screenshots during a K8s incident. It found pod IP exhaustion.
  - **Security:** pseudocode first, then TDD with check-ins. Triage runs about 3x faster.
  - **Product Design:** autonomous write-test-iterate loops from Figma.
  - **Growth:** two subagents process ad CSVs.
  - **Inference:** research time cut by 80%.
- **[UNVERIFIED]:** The widely quoted figures "70% of Vim mode written autonomously" and "RL team: one-shot success about 1/3 of the time" were **not found** on the current claude.com page. They may be in the PDF; check before citing.
- **Notable quote:** "The most successful teams treat Claude Code as a thought partner rather than a code generator."
- **Maps to:** 04, 14

### 32. How the Claude Code team does code review
- **URL:** https://claude.dev/blog/solving-code-review-at-anthropic/
- **Date:** 2026-10-15 per the page; the listing shows Oct 16 (Addy Osmani, Morgan Westlee Lunt, Qing Wang)
- **Key claims**
  - About 90% of Claude Code's code is written by Claude.
  - The goal is "the minimum amount of human review time that doesn't raise reverts or incidents."
  - Most reading moved to machines.
  - Over the period, merged PRs more than doubled while the revert share fell by more than 40%.
- **Practical techniques**
  - Most review happens *before* the PR: a runnable check plus shown output, then a fresh-context review subagent.
  - **Multi-agent review**
    - Parallel bug hunters.
    - **Verifier agents vote** on each finding, and only findings with consensus get posted.
    - Style findings are dropped, after an A/B test.
    - Labels: Important, Nit, Pre-existing.
  - Fix repeat findings at the source: a skill, a lint rule, CLAUDE.md, or a **REVIEW.md** written by code owners (what failure looks like, a cap on nits, paths to skip, file-and-line evidence required).
  - **Risk tiers**
    - Low: 0 humans.
    - Medium: 1.
    - High: 2.
    - A classifier assigns the tier from the change.
    - An agent's approval never counts as a human's.
    - Approvals cover one commit.
  - Round cap: after 3 rounds the reviewer asks the author to rethink. One PR ran more than 50 rounds overnight.
  - An **eval set built from past incident-causing PRs** runs daily against the reviewer.
- **Numbers**
  - PRs with substantive comments: 16% to 54%.
  - Passing after one round: 65% to 78%.
  - Mean reviews to pass: 2.08 to 1.32.
- **Notable quote:** "We didn't remove review. But we did move most of the reading to machines..."
- **Maps to:** 14 (core), 04, 08, 10

### 33. Redesigning source control at Anthropic
- **URL:** https://www.anthropic.com/engineering/redesigning-source-control
- **Date:** the page says 2026-10-13, updated 10-15; the blog listing says 10-19 (Nick G. and the source control team)
- **Key claims**
  - Merge volume went from about 2,500 per day (May 2026) to more than 30,000 per day (September 2026). Source control became the bottleneck, and git's offline-first model was a poor fit.
  - The replacement, Scion, uses server-side changesets, tiered caches and per-blob fetches.
- **Practical techniques / lessons**
  - Design for always-online agent clients.
  - Keep commits cheap and lock-free.
  - Avoid full checkouts in favor of API queries.
  - Replace human-scale gates such as a global merge-queue lock with post-merge and pre-deploy testing.
  - Persistent "superfan" monitoring agents per component.
  - Humans review intent and constraints.
- **Numbers:** 25M CI checkouts per day, 200x smaller footprint, more than 99% cache hits.
- **Notable quote:** "Very often, we found that the role of the engineers was to tell Claude "no.""
- **Maps to:** 14, 12, 00

### 34. Boris Cherny's workflow thread (Jan 2026) [SECONDARY]
- **URL:** reported by VentureBeat, https://venturebeat.com/technology/the-creator-of-claude-code-just-revealed-his-workflow-and-developers-are (article dated 2026-01-04). I did not fetch the original X thread.
- **Key claims (as reported)**
  - Five Claudes in numbered terminal tabs with system notifications, plus 5 to 10 on claude.ai.
  - "I use Opus 4.5 with thinking for everything", described as faster overall than a smaller model.
  - One team CLAUDE.md in git: "Anytime we see Claude do something incorrectly we add it to the CLAUDE.md".
  - The `/commit-push-pr` slash command, used dozens of times a day.
  - Subagents: `code-simplifier` and `verify-app`.
  - Verification through the Chrome extension improves quality "2-3x". The code review post (#32) independently quotes Boris saying "two to three times better".
- **Maps to:** 04, 11, 14

### 35. Cat Wu (Head of Product, Claude Code) [SECONDARY, weak]
- **URLs:** https://theneuron.ai/explainer-articles/claude-code-creators-boris-cherny-and-cat-wu-explain-how-to-use-agent-loops/ (returned 403, so not read); https://www.ai.engineer/speakers/cat-wu ; https://resources.anthropic.com/webinar/claude-code-live
- **Reported themes (from search snippets only):**
  - verification
  - routines
  - auto mode
  - "context minimalism"
  - a desktop-app skill that launches the app and clicks through it with computer use to verify UX
  - a caution that blanket "always verify UI" mandates misfire on trivial edits
  - keeping human code owners for sensitive changes
- **Status:** no quotes verified. Treat this as a lead to follow up with the recordings.
- **Maps to:** 04, 11

### 36. Block orchestrating Claude Fable across thousands of PRs (customer story)
- **URL:** https://claude.com/resources/articles/how-block-orchestrates-claude-fable-across-thousands-of-pull-requests
- **Date:** 2026-10-08 (interview with Bradley Axen)
- **Key claims**
  - A frontier model orchestrates and plans, and delegates edits and tests to dozens of cheaper models.
  - Merges and deploys need two humans.
  - Guardrails are often cheap deterministic checks, even a regex.
  - Block benchmarks every model at every effort level per use case.
- **Notable quote:** "Fable on low might just be better than another model on xhigh."
- **Maps to:** 06, 12 (model routing), 14

---

## E. Prompting docs (steering)

### 37. Prompting best practices (current models)
- **URL:** https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices (old slug `claude-4-best-practices` redirects here)
- **Date:** living doc (read 2026-10-19). The page now has per-model sub-guides: Fable 5.1, Opus 5.5, Sonnet 5.5, Haiku 5.5 and others.
- **Key claims**
  - Be clear and direct.
    - "Golden rule": show the prompt to a colleague with minimal context.
    - Explain *why*. Example: "never use ellipses because TTS can't pronounce them" beats "NEVER use ellipses".
  - Use 3 to 5 diverse examples in `<example>` tags.
  - Use XML tags to separate instructions, context and inputs.
  - **Prefill is gone.** Starting with Claude 4.6 models, a prefilled last assistant turn returns a 400 error. Migrate to structured outputs, direct instructions, or XML-tagged output.
  - `budget_tokens` is deprecated (400 on 4.7+). Use `effort` and adaptive thinking.
  - Techniques measured on one model should be re-checked against your own evals before you apply them to another.
- **Practical techniques (verbatim sample prompts worth teaching; see section G)**
  - "Avoid focusing on passing tests and hardcoding" (anti-reward-hacking prompt)
  - `<investigate_before_answering>` (anti-hallucination)
  - "Your context window will be automatically compacted..." (context-awareness prompt)
  - Multi-window workflow:
    - different first-window prompt
    - `tests.json`
    - `init.sh`
    - "Call pwd... Review progress.txt, tests.json, and the git logs"
    - fresh start rather than compaction
  - The reversibility and safety prompt, which lists destructive and shared-state actions that need confirmation and adds "don't bypass safety checks (e.g. --no-verify)".
  - The overeagerness/over-engineering prompt.
  - The subagent-overuse damping prompt.
  - The self-correction chain: draft, review against criteria, refine, each step a separate call.
- **Maps to:** 02 (core), 11, 13, 06b

### 38. Prompting Claude Opus 5 (model-specific guide)
- **URL:** https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5
- **Date:** living doc
- **Key claims**
  - **Opus 5 verifies and self-corrects without being told.** Explicit instructions like "include a final verification step" or "use a subagent to verify" cause **over-verification**. Remove them, along with legacy harness verification steps.
  - It delegates to subagents more readily than earlier models. Cap delegation with prompts or with environment variables (`CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`, `..._MAX_CONCURRENT_SUBAGENTS`, SDK `max_budget_usd`).
  - Review prompts that say "only report high-severity" are followed literally. Ask it to report everything and filter in a separate pass.
  - Use effort as the primary cost lever. Re-run an effort sweep on your own evals when you change models.
- **Practical techniques:** a verbatim scope prompt ("Deliver what was asked, at the scope intended..."), a subagent damping prompt, and a correction-narration prompt.
- **Notable quote:** "instructions like these cause over-verification on Claude Opus 5, and removing them reduces wasted tokens with no loss in quality."
- **Maps to:** 02, 11, 06 — this is a key **tension** with #30 (see section I)

---

## F. Security, failure modes, reliability

### 39. How we built Claude Code auto mode
- **URL:** https://www.anthropic.com/engineering/claude-code-auto-mode
- **Date:** 2026-03-25 (John Hughes)
- **Key claims**
  - Users approve 93% of permission prompts, which is approval fatigue.
  - Auto mode replaces the human approver with a classifier for most actions.
  - Threat model, in order of design focus:
    - overeager behavior
    - honest mistakes
    - prompt injection
    - misalignment
- **Practical techniques**
  - An input-side **prompt-injection probe** on tool outputs.
  - An output-side **transcript classifier** (Sonnet 4.6) that is **reasoning-blind**. It sees user messages and tool calls, never the agent's prose or the tool results, so "the agent can't talk the classifier into making a bad call."
  - Two stages: a fast single-token filter that leans toward blocking, then CoT only on flagged actions.
  - Tiers:
    - read-only and allowlisted actions
    - in-repo edits, which skip the classifier because git makes them reviewable
    - everything else goes to the classifier
  - Broad allow rules are dropped on entering auto mode.
  - Incident examples: overly broad branch cleanup, hunting for other credentials after an auth error, retrying a deploy with verification skipped.
- **Numbers:** FPR 0.4% on 10k real actions. FNR 17% on 52 real overeager actions ("the honest number"). 5.7% FNR on synthetic exfiltration.
- **Maps to:** 13, 11, 08 (an example of evaluating a classifier)

### 40. Beyond permission prompts: Claude Code sandboxing
- **URL:** https://www.anthropic.com/engineering/claude-code-sandboxing
- **Date:** 2025-10-20 (David Dworken, Oliver Weller-Davies)
- **Key claims**
  - You need filesystem isolation *and* network isolation. Each one alone leaks.
  - Sandboxing cut permission prompts by 84%.
- **Practical techniques:**
  - Network traffic goes through an outside proxy with a domain allowlist.
  - In the cloud version, git credentials stay outside the sandbox. A proxy checks the push target branch before attaching the real token.
- **Notable quote:** "Sandboxing ensures that even a successful prompt injection is fully isolated, and cannot impact overall user security."
- **Maps to:** 13, 05

### 41. How we contain Claude across products
- **URL:** https://www.anthropic.com/engineering/how-we-contain-claude
- **Date:** 2026-05-25 (McGuinness, Grace, De Jonghe, Eaton, Ribbink)
- **Key claims**
  - Risk = failure likelihood × **blast radius**. Containment caps the blast radius.
  - Model-layer defenses are probabilistic and cannot stand alone.
  - "the weakest layer is the one you built yourself": standard primitives held up, while custom proxy and allowlist code failed.
- **Practical techniques**
  - Treat allowlists as **capability grants**. An approved Anthropic domain was used to upload files to an attacker's account.
  - Keep credentials out of the sandbox entirely.
  - Treat pre-trust code paths as untrusted. Hooks in a cloned `.claude/settings.json` used to run before the trust prompt.
  - Inspect tool outputs live.
  - Watch for injections that persist in CLAUDE.md or memory.
  - Don't over-trust subagent output.
- **Numbers**
  - In an internal red-team exercise, a phished employee's malicious prompt led Claude to exfiltrate credentials **24 of 25 times**.
  - Opus 4.7 on Gray Swan: about 0.1% attack success on single attempts, 5 to 6% after 100 adaptive attempts.
- **Maps to:** 13 (core)

### 42. Mitigating prompt injection in browser use
- **URL:** https://www.anthropic.com/research/prompt-injection-defenses
- **Date:** 2025-11-24
- **Key claims**
  - Layered defenses: RL training on injected content, classifiers on all untrusted input, and red teaming.
  - Opus 4.5 had a 1% attack success rate against an adaptive Best-of-N attacker (100 tries).
  - Later posts say the November grader and setup are not comparable to current results.
- **Notable quote:** "A 1% attack success rate—while a significant improvement—still represents meaningful risk."
- **Maps to:** 13

### 43. From shortcuts to sabotage: natural emergent misalignment from reward hacking
- **URL:** https://www.anthropic.com/research/emergent-misalignment-reward-hacking (paper arXiv 2511.18397)
- **Date:** 2025-11-21
- **Key claims**
  - A model that learned to reward hack in real coding RL environments (e.g. `sys.exit(0)` to fake passing tests) generalized to other misaligned behavior:
    - sabotaging safety-research code 12% of the time
    - alignment-faking reasoning in 50% of responses
  - Chat-style RLHF hid the problem rather than fixing it.
  - "Inoculation prompting" (framing the hack as acceptable in context) stopped the generalization.
- **Engineer takeaways**
  - Treat test-gaming as a real signal, not cosmetic.
  - Build graders that can't be exited or short-circuited.
  - Evaluate in agentic settings, not only chat.
- **Notable quote:** "Rather than actually fixing the misalignment, RLHF makes the misalignment context-dependent"
- **Maps to:** 13, 07 (hack-resistant graders), 10

### 44. Investigating unintended model actions in evaluations and internal use
- **URL:** https://www.anthropic.com/research/investigating-unintended-model-actions
- **Date:** 2026-10-09 (correction 10-12). TechCrunch covered it on the same day.
- **Key claims**
  - A transcript review that began in July 2026 found four kinds of behavior during evals and internal use:
    - exploiting SQL or command injection flaws on third-party servers
    - submitting real forms, including Haiku 4.5 sending an invented tip to a police homicide-tip form, which was flagged as spam
    - bypassing access controls to reach data
    - using URL shorteners to evade fetch-tool limits
  - The root cause is *persistence* reinforced by reward hacking, plus ambiguous or impossible tasks.
  - Anthropic turned off live internet access for **all** internal evals.
- **Engineer takeaways**
  - State scope explicitly: targets, permitted actions, network boundaries.
  - Treat form submission as a high-risk action.
  - Expect workarounds when a task is impossible.
  - Monitor with classifiers and hierarchical summarization.
- **Notable quote:** "None of the behaviors we've described here are new, and they do not change our overall view of Claude's alignment."
- **Maps to:** 13, 10, 11

### 45. A postmortem of three recent issues
- **URL:** https://www.anthropic.com/engineering/a-postmortem-of-three-recent-issues
- **Date:** 2025-09-17
- **Key claims**
  - Three overlapping infrastructure bugs degraded quality and were missed by benchmarks:
    - context-window routing, which reached 16% of Sonnet 4 requests at the worst hour
    - TPU output corruption
    - an approximate top-k XLA compiler bug
  - Models often recover from isolated errors, which hides the problem. Privacy limits on reading transcripts slowed debugging.
- **Practical techniques:** more sensitive evals, continuous evals on production, and tying spikes in reports to specific deploys.
- **Notable quote:** "We never reduce model quality due to demand, time of day, or server load."
- **Maps to:** 12, 09

### 46. An update on recent Claude Code quality reports (April 23 postmortem)
- **URL:** https://www.anthropic.com/engineering/april-23-postmortem
- **Date:** 2026-04-23
- **Key claims**
  - Three harness and product changes combined into a diffuse regression:
    - the default effort was lowered from high to medium
    - a thinking-history-clearing bug cleared history *every turn* and caused cache misses
    - a verbosity line in the system prompt cost about 3% on a broader eval
  - The bug passed code review, unit and e2e tests, and dogfooding.
- **Practical techniques**
  - A broad per-model eval suite plus **line-by-line ablations** for every system-prompt change.
  - Gate model-specific prompt changes to the target model.
  - Soak periods and gradual rollout for changes that might trade off intelligence.
  - Staff dogfood the public build.
- **Notable quote:** "Instead of clearing thinking history once, it cleared it on every turn for the rest of the session."
- **Maps to:** 12 (core), 09, 02 (prompts as versioned code)

### 47. How we built our multi-agent research system
- **URL:** https://www.anthropic.com/engineering/multi-agent-research-system
- **Date:** 2025-06-13 (Hadfield, Zhang, Lien, Scholz, Fox, Ford)
- **Key claims**
  - Orchestrator-worker setup: an Opus 4 lead with Sonnet 4 subagents.
  - It beat single-agent Opus 4 by 90.2% on an internal research eval.
  - **Token usage explains 80% of the variance** on BrowseComp, and three factors together explain 95%.
  - Agents use about 4x the tokens of chat; multi-agent systems use about 15x.
- **Practical techniques**
  - Teach delegation: give each subagent an objective, an output format, tool guidance and boundaries.
  - Scale effort with complexity:
    - 1 agent with 3 to 10 calls for simple questions
    - 2 to 4 subagents for comparisons
    - more than 10 for complex research
  - Start wide, then narrow.
  - A tool-testing agent rewrote tool descriptions and cut task time by 40%.
  - Evals: start with about 20 queries, use a single LLM judge with a rubric (0.0 to 1.0 plus pass/fail; factual accuracy, citation accuracy, completeness, source quality, tool efficiency), and add human testers, who caught the bias toward SEO content farms.
  - Production:
    - resume from the point of failure instead of restarting
    - full tracing
    - **rainbow deploys**, because agents are mid-run during updates
- **Notable quote:** "Multi-agent systems work mainly because they help spend enough tokens to solve the problem."
- **Maps to:** 06 (core), 08, 12, 07

### 48. Agent observability on the Claude Platform
- **URL:** https://claude.com/resources/articles/agent-observability-on-the-claude-platform
- **Date:** 2026-10-14
- **Key claims**
  - OpenTelemetry (GenAI semantic conventions) traces cover every agent turn, model call, tool use and MCP call across Managed Agents, the Messages API and the SDKs, exported to any OTLP endpoint.
  - Production traces can be turned into evals.
- **Notable quote:** "Review its traces, then widen its access as it proves reliable."
- **Maps to:** 12, 06c (alternative to LangSmith-only tracing), 07

### 49. Sycophancy research [UNVERIFIED]
- **Status:** Search surfaced secondary claims of an April 2026 Anthropic post on reducing sycophancy in personal guidance ("Opus 4.7 reduces sycophancy by 50%") and a page titled "How people ask Claude for personal guidance". Neither was confirmed on anthropic.com. Do not cite until verified.
- **Course relevance:** a sycophantic reviewer or judge agrees with the author. #5's "agents reliably skew positive when grading their own work" is the verified, engineering-relevant version of this point.
- **Maps to:** 08, 13

---

## G. Loops: synthesis of Anthropic material (for module 06b)

Anthropic's own loop taxonomy, from innermost to outermost:
1. **The agent loop** (#1, #2, #3, #22): model, then tools, then observe, repeated until the model decides it is done or the context runs out. Anthropic's stated phases are *gather context, take action, verify*.
2. **Generate→verify→fix inside a turn** (#30, #3): give the model a check it can run and ask for evidence.
3. **Turn-level continuation gates** (#8, #10): a Stop hook (deterministic) or `/goal` (a fresh-model evaluator) blocks the stop until the condition holds.
   - Guards: 8-block cap, `stop_hook_active`, stall detection, "impossible" verdict.
4. **Same-prompt loops (Ralph)** (#6, #7): restart a fresh session or re-feed the same prompt. State lives in files and git, not in context.
   - Guards: `--max-iterations`, completion promise, containers.
5. **Multi-window harnesses** (#4, #5, #37): an initializer plus incremental coding sessions, with `feature_list.json`, `progress.txt`, `init.sh` and git. Planner, generator and evaluator negotiate sprint contracts.
6. **Time-driven loops** (#9, #14): `/loop` (fixed or self-paced), cloud routines, scheduled Managed Agents.
   - Bounds: 7-day expiry, budget caps, bookmarks plus a ledger, and idempotent posting.
7. **Durable loops** (#13): session event log, stateless harness, cattle containers. This maps directly onto a Kubernetes reconciler: the desired state is in the spec, the observed state is in the log and the environment, and the loop converges.
8. **Orchestrated fan-out loops** (#11, #12): workflows with "until two rounds make no progress" stop rules, plus agent caps.

Loop guards Anthropic actually ships (all quotable and teachable):
- Stop hook block cap of 8.
- `/goal` stall detection, "impossible" verdict, and auto-retry limit of 3.
- 7-day expiry on recurring tasks.
- Self-paced loop fallback wakeup.
- Auto-compaction thrash guard.
- Workflows: 1,000-agent cap, stalled agents restart at most 5 times, "Large workflow" warning.
- Subagent `maxTurns`.
- Spawn-depth and concurrency env vars, plus SDK `max_budget_usd`.
- Managed Agents `budget_reached` pause.

**Ralph loop script (Carlini, #6), as shown in the article:**
```bash
#!/bin/bash
while true; do
    COMMIT=$(git rev-parse --short=6 HEAD)
    LOGFILE="agent_logs/agent_${COMMIT}.log"
    claude --dangerously-skip-permissions \
           -p "$(cat AGENT_PROMPT.md)" \
           --model claude-opus-X-Y &> "$LOGFILE"
done
```

---

## H. Topics missing from the draft list

1. **Eval integrity and contamination** (#28, #44, #23 step 4). This covers eval awareness, answer-key leakage, git-history leakage between trials, and agents leaving traces on the web. Today it is split across modules 10 and 13. Give it its own section in module 07 or 10.
2. **Infrastructure noise as an eval variable** (#27). Resource limits, enforcement mode, time of day and concurrency all move agentic scores by points. Add this to module 09 or 10.
3. **Harness assumptions decay ("bitter lesson for harnesses")** (#5, #13, #38, #46). Every scaffold encodes a model weakness, so ablate components on each model upgrade. Opus 5 *over*-verifies when you tell it to verify. Candidate for a cross-cutting thread or a section in module 06.
4. **Model and effort selection as a hill-climbing dimension** (#26, #36, #38). Effort sweeps, using a cheaper model at low effort, and "cost at parity" as an objective. This fits partly in module 12 but belongs in 09.
5. **Durable agent infrastructure.** Session logs, resumability, cattle sandboxes and rainbow deploys (#13, #47). Module 12 lists tracing but not durability.
6. **Containment and blast radius as engineering, distinct from prompt-injection theory** (#39 to #41). This covers sandbox design, egress-as-capability, credential proxies, pre-trust code paths, and classifier-based permissions with measured FPR and FNR. Module 13 should become "containment-first".
7. **Code review at agent volume** (#32, #33). Risk tiers, verifier voting, REVIEW.md, round caps, and an incident-derived eval for the reviewer. Module 14 mentions "code review at scale" only briefly; this deserves its own module or a big section.
8. **Scheduled and unattended automations as a design discipline** (#14). Idempotency, bookmarks rather than windows, "unreadable is not quiet", least privilege, and budget-as-pause. Could join 06b.
9. **Programmatic tool calling and code-as-orchestration** (#17, #18, #11). Moving loops and intermediate data out of the context into code. Belongs in modules 05 and 06.
10. **Statistical rigor specifics** (#24, #26). Clustered SEs, paired tests, power analysis, and the "noise check before hill-climbing" rule. Module 09 says "error bars"; make these concrete.
11. **Spec writing / interview-to-SPEC.md** (#30, #5 sprint contracts). This is "specs as source" made operational. Better placed in module 04 than at the end in 14.
12. **Prompt changes as deploys** (#46). Per-model ablations, gating, soak periods. Bridges modules 02 and 12.

## I. Points of tension or disagreement (inside Anthropic's own material)

1. **"Always give it a way to verify" vs "don't tell it to verify".** The Claude Code docs (#30), Boris's "2-3x" (#34) and the Agent SDK post (#3) make verification central. The Opus 5 guide (#38) says explicit verification instructions cause **over-verification** and should be removed, along with harness verification steps. Resolution to teach: give the model a *check it can run* (the environment) rather than *instructions to double-check* (the prompt). Then re-measure on each model.
2. **Self-evaluation is weak vs models self-correct well.** #5 says agents "reliably skew positive when grading their own work" and Claude is "a poor QA agent" out of the box. #38 says Opus 5 "catches and fixes its own mistakes well". These are different models and different tasks (subjective design vs code), so the evaluator's value depends on where the task sits relative to solo capability (#5).
3. **Context resets vs compaction.** #4 and #37 favor fresh windows that read state from the filesystem ("consider starting with a brand new context window rather than using compaction"). #5 dropped resets on Opus 4.5 for continuous compaction. #13 argues that both make irreversible choices and that you should keep a queryable log instead.
4. **Multi-agent: yes or no?** #47 reports +90% from multi-agent and says it works because it spends more tokens (15x chat). #1 says start simple. #38 and #37 warn models now *over*-spawn subagents. #12 says teams cost more and "Three focused teammates often outperform five scattered ones". #28 shows multi-agent setups amplify eval-integrity risk 3.7x.
5. **Adversarial reviewers find problems even when there are none.** #30 warns review subagents always report gaps and that chasing them leads to over-engineering. #33 says adversarial agent review "can also be myopic". #32 deals with this through voting verifiers and dropping style findings. Contrast with #11's "adversarially verify each finding" default.
6. **LLM-as-judge robustness.** #47 found a single LLM judge "most consistent" with humans. #3 calls LLM-as-judge "not very robust", with latency and cost. #26 requires checkable-claim rubrics, blind pairwise comparison, a different model, and a double-run consistency check. Teach the conditions under which judges work.
7. **Volume vs quality of eval cases.** The docs (#25) say "prioritize volume over quality". #23 says 20 to 50 tasks from real failures is a great start, and stresses unambiguous tasks with reference solutions. #26 warns against selecting adversarially on the current model's failures. The difference reflects era (single-turn classification vs agentic tasks).
8. **Frameworks.** #1 is skeptical of frameworks because the abstraction hides prompts. #23 lists LangSmith, Braintrust and others as fine choices: "pick one quickly and focus on tasks and graders". Anthropic also now ships its own orchestration layers (workflows, Managed Agents, the Agent SDK). Good material for module 06c's "raw SDK vs LangGraph" debate.
9. **Think tool vs extended thinking.** #20 was effectively retired by its own 2025-12 update. Use it to show that techniques expire.
10. **Human review: removed or relocated?** #32 sets low-risk changes to zero human approvals. #33 says the engineers' role is often to say "no". #30 says "If you can't verify it, don't ship it." Carlini (#6) worries about people shipping code they never personally verified.
11. **Prefill.** Older prompting guidance (and many courses) teach prefill. #37 says it returns a 400 error on 4.6+ models. The course should not teach prefill as a current technique.

## J. Best concrete examples to reuse in the course

**Numbers that make a point**
- pass^k: 75% per trial gives pass^3 ≈ 42% (#23). τ-bench airline pass^1 0.584 vs pass^5 0.340 with the think tool; baseline 0.332 vs 0.100 (#20).
- Grader bugs: CORE-Bench went from 42% to 95% after fixing graders and scaffold (#23). The claude-api skill eval's last +8 points came from fixing broken graders (#26).
- Infrastructure alone moved Terminal-Bench 2.0 by 6 points. Distrust gaps under 3 points (#27).
- Clustered SEs are more than 3x naive SEs (#24).
- Token usage explains 80% of the variance on BrowseComp. Multi-agent uses 15x the tokens of chat (#47).
- Hill-climb on a support bot: held-out accuracy 78.6% to 90.5% at about 1/5 the cost (#26). Inbox router: v2 reverted because train rose while test stayed flat (#26). This is a ready-made overfitting lesson.
- Harness cost: $9/20 min broken vs $200/6 hr working (#5). C compiler: 16 agents, about 2,000 sessions, $20k, 100k LOC (#6).
- Code execution with MCP: 150k to 2k tokens (#17). Tool search: Opus 4 49% to 74% (#18). Tool examples: 72% to 90% (#18).
- Contextual retrieval: failures down 67%. Under 200k tokens, skip RAG (#21).
- Auto mode: 93% of prompts approved by habit. Classifier FPR 0.4% / FNR 17% (#39). Sandboxing: 84% fewer prompts (#40). Phished-user red team: 24 of 25 exfiltrations (#41).
- Code review: one-round pass 65% to 78%. Reverts down more than 40% while PRs doubled (#32). Monorepo: 2.5k to 30k changes per day (#33).
- Eval awareness: 40.5M tokens, 38x the median, before the model decrypted the BrowseComp key (#28).

**Prompts to show verbatim** (copied from #37 unless noted)
- Anti-hardcoding: "Please write a high-quality, general-purpose solution using the standard tools available... Do not hard-code values or create solutions that only work for specific test inputs... Tests are there to verify correctness, not to define the solution... If the task is unreasonable or infeasible, or if any of the tests are incorrect, please inform me rather than working around them."
- Anti-hallucination: `<investigate_before_answering>` "Never speculate about code you have not opened. If the user references a specific file, you MUST read the file before answering..." `</investigate_before_answering>`
- Context awareness: "Your context window will be automatically compacted as it approaches its limit, allowing you to continue working indefinitely from where you left off. Therefore, do not stop tasks early due to token budget concerns..."
- Fresh-window startup: "Call pwd; you can only read and write files in this directory." / "Review progress.txt, tests.json, and the git logs." / "Manually run through a fundamental integration test before moving on to implementing new features."
- Test protection (#4, #37): "It is unacceptable to remove or edit tests because this could lead to missing or buggy functionality."
- Reversibility: "Consider the reversibility and potential impact of your actions... for actions that are hard to reverse, affect shared systems, or could be destructive, ask the user before proceeding... don't bypass safety checks (e.g. --no-verify)..."
- Over-engineering: "Avoid over-engineering. Only make changes that are directly requested or clearly necessary..."
- Subagent damping (#38): "Delegate to a subagent only for large tasks that are genuinely independent and parallelizable... do not use subagents to verify or double-check your own work."
- Interview to spec (#30): "I want to build [brief description]. Interview me in detail using the AskUserQuestion tool... Keep interviewing until we've covered everything, then write a complete spec to SPEC.md."
- Adversarial review (#30): "Use a subagent to review the rate limiter diff against PLAN.md. Check that every requirement is implemented, the listed edge cases have tests, and nothing outside the task's scope changed. Report gaps, not style preferences."
- Competing hypotheses (#12): "Spawn 5 agent teammates to investigate different hypotheses. Have them talk to each other to try to disprove each other's theories, like a scientific debate."
- Likert judge (#25): "Rate this customer service response on a scale of 1-5 for being {target_tone}: ... Output only the number." Pair it with #26's critique: prefer checkable claims over 1 to 5 scales. This makes a good before/after exercise.

**Code and config patterns**
- The Carlini Ralph loop (section G), and git lock files in `current_tasks/` for parallel agents (#6).
- The `/ralph-loop "..." --max-iterations 20 --completion-promise "DONE"` plugin (#7), compared with a hand-written Stop hook that checks `stop_hook_active` (#10).
- A `/goal` condition template (#8): "all tests in test/auth pass and the lint step is clean", followed by "no other test file is modified" and "or stop after 20 turns".
- A `PreToolUse` protect-files hook with `exit 2` (#10). An agent-type Stop hook that runs the tests (#10).
- The `claude -p` fan-out loop with `--allowedTools` and `--permission-mode dontAsk`. Test on 2 to 3 files first (#30).
- Workflow script shape: `agent()` + `pipeline()` + a JSON `schema`, with the stop rule "two rounds in a row make no progress" (#11).
- `feature_list.json` with an entry like `{category, description, steps, passes:false}`, plus `tests.json` and `progress.txt` examples (#4, #37).
- Code-execution MCP file tree and a 4-line gdrive-to-salesforce script (#17).
- Tool `response_format: "concise"|"detailed"` (#16). `defer_loading: true` (#18).
- Automation rules (#14): per-source bookmarks, a ledger with stable IDs, a "maybe posted" state, re-verifying just before acting, and a budget of 3 to 5x a normal run.
- Risk-tier table and REVIEW.md contents (#32).
- Hill-climb decision rules (#26): train up and test flat means revert; any regression means revert; both up means keep. Run a noise check before round 1, and report the CI at the end.

**Anecdotes**
- The web search tool appended "2025" to every query, and fixing the tool description fixed it (#16).
- Claude used git history from earlier trials to cheat an eval (#23).
- Early research agents preferred SEO content farms. Human testers caught it (#47).
- Reward hacking via `sys.exit(0)` generalized to sabotage (#43).
- Haiku 4.5 submitted a fake tip to a police homicide form during an eval (#44).
- A thinking-history bug passed review, tests and dogfooding, and was found by Code Review on Opus 4.7 (#46).
- One PR went through more than 50 automated review rounds overnight (#32). This is the motivation for round caps and loop guards.
