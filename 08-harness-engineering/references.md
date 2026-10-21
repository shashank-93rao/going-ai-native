# References

Primary sources first. "Take" says what to use from each.

## Harness engineering, directly
- **OpenAI (Ryan Lopopolo), "Harness engineering: leveraging Codex in an agent-first world"**, February 2026. https://openai.com/index/harness-engineering/
  Take: AGENTS.md as a ~100-line map into a versioned `docs/` system of record; custom lints with remediation text; layered architecture enforced mechanically; per-worktree app instances plus a LogQL/PromQL-queryable observability stack; golden principles plus background cleanup agents instead of "slop Fridays". The reported scale (about 1M LOC, about 1,500 PRs, 3 growing to 7 engineers, about five months) comes from the post. The page returned 403 to automated fetches when this module was written; details here come from the course's research notes and a search snippet, so re-read the post before quoting it.
- **LangChain (Vivek Trivedy), "Improving Deep Agents with harness engineering"**, 2026-02-17. https://www.langchain.com/blog/improving-deep-agents-with-harness-engineering
  Take: 52.8% → 66.5% on Terminal-Bench 2.0 with the model fixed (verified). Middleware: PreCompletionChecklist, LocalContext, LoopDetection. The reasoning sandwich, and the result that xhigh everywhere scored 53.9% because of timeouts. The overfitting warning.
- **Mitchell Hashimoto, "My AI Adoption Journey"**, 2026-02-05. https://mitchellh.com/writing/my-ai-adoption-journey
  Take: "Engineer the harness": every agent mistake becomes an AGENTS.md line or a purpose-built tool. "Each line in that file is based on a bad agent behavior" (verified). Also: reproduce your own past commits with an agent, which is the seed for a task suite.

## Anthropic engineering
- **"Effective harnesses for long-running agents"**, 2025-11-26. https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents
  Take: sessions start with amnesia, so use durable state files. Claude marked features done after unit tests or curl when they failed end to end. "It is unacceptable to remove or edit tests..."
- **"Harness design for long-running application development"**, 2026-03-24. https://www.anthropic.com/engineering/harness-design-long-running-apps
  Take: "every component in a harness encodes an assumption about what the model can't do on its own" (verified). "agents reliably skew positive when grading their own work" (verified). Strip pieces that are no longer load-bearing on new models.
- **"Scaling Managed Agents: decoupling the brain from the hands"**, 2026-04-08. https://www.anthropic.com/engineering/managed-agents
  Take: "Harnesses encode assumptions that go stale as models improve." Containers as cattle.
- **"Building a C compiler with a team of parallel Claudes"**, 2026-02-05. https://www.anthropic.com/engineering/building-c-compiler
  Take: most effort goes into tests and oracles, because agents solve whatever is checked. Agent-friendly test output: few lines, `ERROR` on the same line, `--fast` sampling.
- **"Demystifying evals for AI agents"**, 2026-01-09. https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents
  Take: start with 20–50 tasks from real failures; grade outcomes; a clean environment per trial (git-history leakage happened); "0% pass@100 is most often a signal of a broken task".
- **"Automating eval design and hillclimbing with Claude"**, about 2026-09/10. https://claude.dev/blog/automating-eval-design-and-hillclimbing/
  Take: train/test split, noise check before round 1, revert rules, "never paste failures into the prompt".
- **"Quantifying infrastructure noise in agentic coding evals"**, 2026-02-05. https://www.anthropic.com/engineering/infrastructure-noise
  Take: about 6 points of Terminal-Bench 2.0 swing from infrastructure configuration alone; distrust gaps under about 3 points.
- **"Prompting Claude Opus 5"** (living doc). https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5
  Take: explicit verification instructions "cause over-verification"; remove them and legacy harness verification steps (verified). This is the canonical harness-decay example.
- **"From shortcuts to sabotage: natural emergent misalignment from reward hacking"**, 2025-11-21. https://www.anthropic.com/research/emergent-misalignment-reward-hacking
  Take: test-gaming (for example `sys.exit(0)`) is a real behavior to design graders against.
- **"Equipping agents for the real world with Agent Skills"**. https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills
  Take: skills as progressive disclosure; the description loads first and the body on demand. Runbooks fit this shape.
- **Claude Code hooks reference**. https://code.claude.com/docs/en/hooks
  Take (verified October 2026): Stop and PreToolUse hooks block on exit code 2 with stderr as the reason; Stop input has `stop_hook_active`; there is an 8-consecutive-continuation cap (`CLAUDE_CODE_STOP_HOOK_BLOCK_CAP`).

## OpenAI, other
- **"Unrolling the Codex agent loop"**, about 2026-01-23. https://openai.com/index/unrolling-the-codex-agent-loop/
  Take: AGENTS.md aggregation order (more specific files later) and the default 32 KiB cap.

## Practitioners and companies
- **Stripe, "Minions: Stripe's one-shot, end-to-end coding agents"**, 2026-02-09. https://stripe.dev/blog/minions-stripes-one-shot-end-to-end-coding-agents
  Take: isolated pre-warmed devboxes (about 10 s); a local lint subset in under 5 s; at most two CI rounds; curated tool subsets.
- **Spotify, "Honk" background coding agent, parts 1–3**, Nov–Dec 2025. https://engineering.atspotify.com/2025/11/spotifys-background-coding-agent-part-1 , https://engineering.atspotify.com/2025/12/feedback-loops-background-coding-agents-part-3
  Take: three failure modes, of which "passes CI but wrong" is the most serious (part 3); verifiers exposed as one tool; a Stop hook gating PR creation; an LLM judge on diff vs prompt (about 25% veto, about half recover).
- **Geoffrey Huntley, "nobody should type code by hand anymore. here's what's left."**, 2026-10-13. https://ghuntley.com/agency/
  Take: pre-commit diff checks for architectural violations; property-based tests for invariants under fault injection; delete AGENTS.md and skills periodically and re-test.
- **Simon Willison, "Designing agentic loops"**, 2025-09-30. https://simonwillison.net/2025/Sep/30/designing-agentic-loops/
  Take: document shell commands in AGENTS.md with one example each; sandbox YOLO mode; scoped credentials.

## Course cross-references
- [03-context-engineering](../03-context-engineering/README.md): context budgets, pruning, and agentic search vs RAG.
- [07-loops](../07-loops/README.md): oracles, "prove it can fail", governors, and event-driven agents.
- [10-evals-fundamentals](../10-evals-fundamentals/README.md) and [12-hill-climbing](../12-hill-climbing/README.md): pass^k, clustered errors, and the revert rules used in 05.
- [16-security-and-containment](../16-security-and-containment/README.md): sandboxing the agent under eval, and read-only observability credentials.

## Not verified
- The exact wording and byline of the OpenAI harness post, which could not be fetched directly. The numbers are presented as "reported".
- Claude Code's subdirectory CLAUDE.md loading behavior and the `@path` import, described from the course research notes and general docs knowledge as of 2026. Check current memory docs.
- The Claude Code CLI flags in the eval command template (`-p`, `--dangerously-skip-permissions`). Check `claude --help` for your version.
