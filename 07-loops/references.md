# 07: References

Sources by topic, each with what to take from it. Claude Code documentation pages were read on 2026-10-19. Re-check them before relying on specific limits, because they change often.

## The agent loop
- **Thorsten Ball, "How to Build an Agent"**: https://ampcode.com/how-to-build-an-agent (2025-04-15). The canonical from-scratch build: three tools, under 400 lines of Go. Take: "an LLM, a loop, and enough tokens", and the five-step loop.
- **Geoffrey Huntley, "how to build a coding agent: free workshop"**: https://ghuntley.com/agent/ (2025-08-24). Building up tool by tool; the context window as scarce memory. Take: one context window per activity.
- **Michael Bolin (OpenAI), "Unrolling the Codex agent loop"**: https://openai.com/index/unrolling-the-codex-agent-loop/ (2026-01). Turn vs thread, prompt order, append-only history for cache hits, quadratic payloads, compaction. Take: treat the prompt as an event log.
- **OpenAI Agents SDK, running agents**: https://openai.github.io/openai-agents-python/running_agents/. The three-way result classification and `MaxTurnsExceeded`. Take: a framework's loop is the one you just wrote.
- **Anthropic, "How Claude Code works"**: https://code.claude.com/docs/en/how-claude-code-works. Gather context → act → verify; the compaction thrash guard.
- **Anthropic, "Building effective agents"**: https://www.anthropic.com/engineering/building-effective-agents (2024-12-19). Agents as "LLMs using tools based on environmental feedback in a loop"; stopping conditions; the evaluator-optimizer pattern.

## Oracles, backpressure, governors
- **Steve Kinney, "The Ralph Loop"** (AI Development Setup course): https://stevekinney.com/courses/ai-development-setup/the-ralph-loop. The `measure → pick → run → accept → governor` decomposition, the oracle-quality ranking, typed exit codes, and "write the oracle first". Take: almost the whole structure of files 02 and 03.
- **Nicholas Carlini (Anthropic), "Building a C compiler with a team of parallel Claudes"**: https://www.anthropic.com/engineering/building-c-compiler (2026-02-05). Near-perfect tests, agent-legible harness output, `--fast` sampling, GCC as a bisection oracle, lock-file task claims, the bash loop, $20k for about 2,000 sessions.
- **HumanLayer, "12-Factor Agents"**: https://github.com/humanlayer/12-factor-agents. Factor 8 (own your control flow) and factor 9 (compact errors into context; break after about 3 consecutive errors).
- **Spotify, "Feedback loops" (Honk part 3)**: https://engineering.atspotify.com/2025/12/feedback-loops-background-coding-agents-part-3 (2025-12-09). Verifiers chosen by repo contents, a Stop hook that runs every verifier, and an LLM judge on diff-vs-prompt that vetoes about 25% of sessions.
- **Stripe, "Minions"**: https://stripe.dev/blog/minions-stripes-one-shot-end-to-end-coding-agents (2026-02-09). Shift-left lint in under 5 s; at most two CI rounds.
- **Kent Beck, "Augmented Coding: Beyond the Vibes"**: https://newsletter.kentbeck.com/p/augmented-coding-beyond-the-vibes (2025-06-25). Three warning signs (loops, unrequested features, cheating), as a stuck-loop rubric.
- **Vivek Trivedy (LangChain), "Improving Deep Agents with harness engineering"**: https://www.langchain.com/blog/improving-deep-agents-with-harness-engineering (2026-02-17). `LoopDetectionMiddleware`, `PreCompletionChecklistMiddleware`, and the reasoning-sandwich result (xhigh everywhere scored worse because of timeouts).
- **Andrej Karpathy, autoresearch**: https://github.com/karpathy/autoresearch. A frozen evaluator, one editable file, a fixed 5-minute budget per experiment, keep or discard.

## Self-correcting loops
- **Anthropic, "Harness design for long-running application development"**: https://www.anthropic.com/engineering/harness-design-long-running-apps (2026-03-24). Agents grade their own work too generously; generator/evaluator split; sprint contracts; $9 vs $200 vs $124.70.
- **Anthropic, Prompting Claude Opus 5**: https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5. Verification instructions cause over-verification. Take: put the check in the environment.
- **Anthropic, Claude Code best practices**: https://code.claude.com/docs/en/best-practices. The verification ladder (prompt → `/goal` → Stop hook → refuting subagent); `/clear` after two failed corrections; adversarial reviewers always find gaps.
- **DeepLearning.AI, Agentic AI (Andrew Ng)**: https://www.deeplearning.ai/courses/agentic-ai/. Module 2: reflection with external feedback, and evaluating whether reflection helps.

## Ralph
- **Geoffrey Huntley, "Ralph Wiggum as a 'software engineer'"**: https://ghuntley.com/ralph/ (2025-07-14). The original: specs, fix_plan, one item per loop, backpressure, subagents as context firewall, failure modes. The $50k/$297 anecdote is a client's claim.
- **Geoffrey Huntley, "nobody should type code by hand anymore"**: https://ghuntley.com/agency/ (2026-10-13). Automated verification (pre-commit diff checks, property tests) over human eyeballing; stuck-loop recovery by trace introspection.
- **Anthropic, ralph-wiggum Claude Code plugin**: https://github.com/anthropics/claude-code/tree/main/plugins/ralph-wiggum. Stop-hook same-session variant; `/ralph-loop --max-iterations --completion-promise`; good and poor fits.
- **Dex Horthy (HumanLayer), "A Brief History of Ralph"**: https://humanlayer.dev/blog/brief-history-of-ralph (2026-01-06). The fresh-context critique of the plugin; know the end state before looping; small changes per night.
- **repomirror, "We Put a Coding Agent in a While Loop and It Shipped 6 Repos Overnight"**: https://github.com/repomirrorhq/repomirror/blob/main/repomirror.md (about 2025-08). About 1,100 commits for under $800; 1,500 → 103-word prompt; the self-`pkill`.
- **Jarred Sumner, "Rewriting Bun in Rust"**: https://bun.com/blog/bun-in-rust, with commentary by **Simon Willison**: https://simonwillison.net/2026/Jul/8/rewriting-bun-in-rust/. 11 days, more than 1M lines, about $165k; the test suite as conformance oracle; fix the process, not the output. Token figures quoted from Sumner via Willison.
- **Armin Ronacher, "The Coming Loop"**: https://lucumr.pocoo.org/2026/6/23/the-coming-loop/ (2026-06-23). Outer harness loops; when loops hurt (code you care about) and when they shine (ports, perf, security scans, research).
- **Simon Willison, "Designing agentic loops"**: https://simonwillison.net/2025/Sep/30/designing-agentic-loops/ (2025-09-30). Good loop problems, sandboxing YOLO mode, budget-capped credentials.

## Long-running harnesses and external state
- **Anthropic, "Effective harnesses for long-running agents"**: https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents (2025-11-26). Initializer + coding agent; `feature_list.json`, `claude-progress.txt`, `init.sh`; startup ritual; overreach and premature completion.
- **OpenAI, "Run long horizon tasks with Codex"**: https://developers.openai.com/blog/run-long-horizon-tasks-with-codex (about 2026-02). The 25-hour run; Prompt.md / Plans.md / Implement.md / Documentation.md; decision notes against oscillation.
- **Anthropic, "Scaling Managed Agents"**: https://www.anthropic.com/engineering/managed-agents (2026-04-08). Session as event log, stateless harness, cattle sandboxes, `wake(sessionId)`.
- **Anthropic, prompting best practices (multi-window section)**: https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices. Startup prompts; fresh window over compaction.
- **Steve Yegge, Beads**: https://github.com/steveyegge/beads. A git-backed issue graph as agent memory, with atomic claims. (Gas Town details in the research notes are secondary and are not used here.)

## Scheduled, ambient and event-driven loops
- **Claude Code, `/goal`**: https://code.claude.com/docs/en/goal. Evaluator model, condition writing, stall guard, error handling, `-p` usage.
- **Claude Code, scheduled tasks and `/loop`**: https://code.claude.com/docs/en/scheduled-tasks. Three forms, `loop.md`, 7-day expiry, 50-task limit, jitter, no catch-up.
- **Claude Code, hooks guide**: https://code.claude.com/docs/en/hooks-guide, and reference https://code.claude.com/docs/en/hooks. Command, prompt and agent hooks; the 8-block cap; `stop_hook_active`; `CLAUDE_CODE_STOP_HOOK_BLOCK_CAP`.
- **Claude Code, routines**: https://code.claude.com/docs/en/routines. Schedule, API and GitHub triggers; untrusted fire payloads; "green status ≠ success".
- **Claude Code, CLI reference**: https://code.claude.com/docs/en/cli-reference. `--max-turns`, `--max-budget-usd`, `--output-format`, `--permission-mode`.
- **Anthropic, "Building effective agent automations"**: https://claude.dev/blog/building-effective-agent-automations/ (2026-10-08). Bookmarks, ledger, idempotent posting, unreadable-is-not-quiet, re-verify before posting, budget 3–5x.
- **Harrison Chase (LangChain), "Introducing ambient agents"**: https://www.langchain.com/blog/introducing-ambient-agents (2025-01-14). Notify / question / review; the Agent Inbox.
- **Mitchell Hashimoto, "My AI Adoption Journey"**: https://mitchellh.com/writing/my-ai-adoption-journey, and "Vibing a Non-Trivial Ghostty Feature": https://mitchellh.com/writing/non-trivial-vibing. End-of-day report-only agents; a feature for $15.98 across 16 sessions.
- **Anthropic, "How the Claude Code team does code review"**: https://claude.dev/blog/solving-code-review-at-anthropic/. The PR with more than 50 overnight review rounds, and round caps.

## Not used, or used with hedges
- Huntley's "$50k contract for $297" is presented as the client's claim, as Huntley presents it.
- Gas Town's "Witness" stuck-agent detector appears only in secondary sources, so it's not described here.
- The number of agents in the Bun port isn't stated in the source, so this module doesn't give one.
- Model prices in `code/governor.py` are placeholders. Check the pricing page.
