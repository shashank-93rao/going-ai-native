# Research: Andrej Karpathy and OpenAI

Researched 2026-10-19 for the "going-ai-native" course. Sources were fetched directly where possible. openai.com returns HTTP 403 to direct fetches, so those pages were read through a text proxy (r.jina.ai). developers.openai.com and openai.github.io were fetched directly.

**Verification legend.** Text in quotation marks was seen in the fetched source. Anything marked **[UNVERIFIED]** came from secondary coverage or memory and must be checked before it goes on a slide. Dates come from the source page unless marked otherwise.

**Context the course needs.** Karpathy joined Anthropic's pretraining team in May 2026 (Axios, 2026-05-19: https://axios.com/2026/05/19/anthropic-openai-karpathy-andrej-claude). His earlier material was produced while he was independent (Eureka Labs). The current OpenAI frontier is the GPT-6 family. GPT-6 Astra launched on 2026-09-03 according to secondary coverage (e.g. https://www.constellationr.com/insights/news/openai-launches-gpt-6-astra), and GPT-5.6 Sol came before it. Some OpenAI docs below are archived because they were written for GPT-4.1 or GPT-5.

---

## Part 1: Andrej Karpathy

### K1. "Software Is Changing (Again)" (YC AI Startup School keynote)
- **URL:** https://www.youtube.com/watch?v=LCEmiRjPEtQ (title verified). Slide summary at https://www.latent.space/p/s3
- **Date:** Delivered 2025-06-17 in San Francisco. The video went up a few days later.
- **Key claims:**
  - Software 1.0 is code, 2.0 is neural-net weights, and 3.0 is prompts in English. All three will coexist, and an engineer has to be fluent in all three.
  - LLMs resemble utilities (metered, with a capex/opex split), fabs, and above all operating systems. The current era is like computing in the 1960s, with time-shared mainframes in the cloud and thin clients.
  - LLMs are "people spirits", "stochastic simulations of people", with jagged abilities. They have encyclopedic memory and also anterograde amnesia: no continual learning, and the context window acts as working memory.
  - Build partial-autonomy products with an **autonomy slider**: Cursor's Tab, Cmd+K, Cmd+L and agent mode; Perplexity's search, research and deep research; Tesla's Autopilot levels.
  - The **generation-verification loop**: the AI generates and a human verifies, and "the faster the loop the better". Speed up verification with GUIs and visual diffs. Keep generation small: "Keep AI on tight leash."
  - "Iron Man suit" framing: build augmentation first, with autonomy that grows over time. He warns against "2025 is the year of agents" and cites his 2013 Waymo ride as a demo-to-product gap.
  - "Build for agents": agents are a third consumer of digital information, after humans (GUIs) and programs (APIs). Docs should be in Markdown, and "click here" should be replaced with curl commands. He cites llms.txt.
- **Practical techniques:**
  - Size each request so the diff can be reviewed in seconds. Prefer small, incremental chunks over a 1,000-line diff.
  - Design every AI feature with an explicit autonomy dial and a fast visual verification surface.
  - Write concrete prompts. Vague prompts fail verification, which costs more loop iterations.
- **Notable quote:** "Demo is works.any(), product is works.all()" (as reproduced in the Latent Space slide notes).
- **Maps to:** 00, 04, 11, 14

### K2. Vibe coding tweet
- **URL:** https://x.com/karpathy/status/1886192184808149383 **[UNVERIFIED: URL from memory. X was not fetched]**
- **Date:** 2025-02-02 (confirmed by several secondary sources)
- **Key claims:** In a new style of coding, the programmer accepts all diffs, pastes error messages back without comment, and stops reading the code. Karpathy did this through Cursor Composer with voice input. He limited it to throwaway weekend projects.
- **Practical techniques:** Teach vibe coding as an explicit mode with a scope: prototypes and throwaway code, never production paths. It is the far right end of the autonomy slider.
- **Notable quote:** "fully give in to the vibes, embrace exponentials, and forget that the code even exists" (secondary sources agree on this wording **[verify against X]**). He also wrote "not too bad for throwaway weekend projects" **[UNVERIFIED wording]**.
- **Maps to:** 00, 04

### K3. Context engineering tweet
- **URL:** https://x.com/karpathy/status/1937902205765607626 **[UNVERIFIED: URL from memory]**. Coverage: https://the-decoder.com/shopify-ceo-and-ex-openai-researcher-agree-that-context-engineering-beats-prompt-engineering/
- **Date:** 2025-06-25, a "+1" reply to Tobi Lutke's post of 2025-06-18
- **Key claims:** "Prompt" suggests a short task description, but industrial LLM apps are mostly about filling the window. Too little context, or the wrong form, makes the model fail. Too much or irrelevant context raises cost and lowers performance. Context engineering is one part of a "thick layer" of LLM-app software that also covers control flow, decomposition into DAGs, model dispatch, generation-verification UIs, guardrails, security and evals.
- **Practical techniques:** The checklist for what goes in the window: task description, few-shot examples, RAG results, related data, tools, state and history, and compaction.
- **Notable quote:** Context engineering is "the delicate art and science of filling the context window with just the right information for the next step" (consistent across secondary sources **[verify against X]**).
- **Maps to:** 02, 03, 06

### K4. "Intro to Large Language Models" (1-hour talk): the LLM OS
- **URL:** https://www.youtube.com/watch?v=zjkBMFhNj_g (title verified)
- **Date:** November 2023 **[date from memory]**
- **Key claims:** An LLM is two files, parameters plus run code. Pretraining compresses the internet and finetuning produces the assistant. The "LLM OS" diagram puts the LLM in the role of CPU and kernel, with the context window as RAM, and tools such as the browser, code interpreter and file system as peripherals. The talk ends with a security section covering jailbreaks, prompt injection and data poisoning.
- **Practical techniques:** Use the LLM OS diagram as the mental model for module 01. Map context to RAM, retrieval to disk, and tools to I/O. That mapping lets systems engineers reason about where to place state.
- **Notable quote:** None captured verbatim.
- **Maps to:** 01, 03, 13

### K5. "Deep Dive into LLMs like ChatGPT"
- **URL:** https://www.youtube.com/watch?v=7xTGNNLPyMI
- **Date:** 2025-02-05 (verified via secondary source)
- **Key claims:** Roughly 3.5 hours covering the full stack: tokenization, pretraining, SFT and RL. It explains why hallucinations happen and how to mitigate them (knowledge probing, abstention training, tool use). "Models need tokens to think", so compute is spread across tokens. It also covers the "Swiss cheese" capability holes: spelling, counting, and comparing 9.11 with 9.9.
- **Practical techniques:** Make the model do intermediate steps, or offload them to a code tool, rather than asking for a single-token answer. For counting and arithmetic, say "use code".
- **Notable quote:** None captured verbatim.
- **Maps to:** 01, 13

### K6. "How I use LLMs"
- **URL:** https://www.youtube.com/watch?v=EWvNQjAaOHw (title verified)
- **Date:** Late February 2025 **[date from memory]**
- **Key claims:** A practitioner tour of model selection, thinking models, search, deep research, file uploads, the Python interpreter, Claude Artifacts, Cursor, voice and memory. The core habit is to know which model tier you are talking to and start a new chat when the topic changes, because context is precious.
- **Practical techniques:** Open a new chat for each topic so stale context doesn't leak in. Pick a thinking model for hard problems and a fast model for lookups. Ask for code execution whenever numbers are involved.
- **Maps to:** 01, 03

### K7. Dwarkesh Podcast: "AGI is still a decade away"
- **URL:** https://www.dwarkesh.com/p/andrej-karpathy
- **Date:** 2025-10-17
- **Key claims:**
  - This is the "decade of agents", not the "year of agents". Agents lack sufficient intelligence, multimodality, computer use and continual learning.
  - On industry agent hype: "It's slop."
  - Building nanochat, he found coding agents "just not net useful" for novel, intricate code that sits far from the training distribution. They misread his custom code, added defensive bloat, and reached for deprecated APIs. He used autocomplete instead. Agents do help with boilerplate and with languages he knows less well.
  - On RL: "Reinforcement learning is terrible", because "You're sucking supervision through a straw". A single scalar reward at the end is spread across the whole trajectory. LLM judges used as rewards get gamed through adversarial examples.
  - **March of nines:** "Every single nine is a constant amount of work." "When you get a demo and something works 90% of the time, that's just the first nine." Production code has a self-driving-like cost of failure.
  - Models are "ghosts" rather than "animals". Model collapse reduces output diversity. He argues for a small "cognitive core" that is "stripped from knowledge but contains the algorithms".
- **Practical techniques:**
  - Classify your task as on-distribution (boilerplate, common stacks), where agents shine, or off-distribution (novel architecture), where you should use autocomplete or a tight leash.
  - Budget reliability as nines. Go from 90% to 99% to 99.9% and estimate the cost of each step. This is a good bridge to SLO thinking for a distributed-systems engineer.
- **Notable quote:** "there's a very large demo-to-product gap where the demo is very easy, but the product is very hard."
- **Maps to:** 00, 01, 04, 09, 13

### K8. "Verifiability" (blog post)
- **URL:** https://karpathy.bearblog.dev/verifiability/
- **Date:** 2025-11-17
- **Key claims:** Software 1.0 automates what you can *specify*. Software 2.0 automates what you can *verify*. A task is trainable when it is resettable, cheap to attempt many times, and automatically rewardable. Verifiability predicts where progress happens, which explains the jagged frontier: math and code advance fast, while creative and strategic work lag.
- **Practical techniques:** Before automating a task, ask whether success can be checked automatically. If it can't, invest first in building a verifier, such as tests, schemas or a judge. That is the bridge into the evals modules.
- **Notable quote:** "Software 2.0 easily automates what you can verify."
- **Maps to:** 00, 07, 09, 11

### K9. "Animals vs Ghosts" and "The space of minds" (blog posts)
- **URLs:** https://karpathy.bearblog.dev/animals-vs-ghosts/ and https://karpathy.bearblog.dev/the-space-of-minds/
- **Dates:** 2025-10-01 and 2025-11-29
- **Key claims:** LLMs are a different kind of intelligence, optimized by imitation and RL rather than evolution. Don't anthropomorphize them. Characterize them empirically.
- **Practical techniques:** Use these as reading for module 01 to frame "treat the model as an alien, nondeterministic component and measure it".
- **Maps to:** 01

### K10. "Vibe coding MenuGen" (blog post)
- **URL:** https://karpathy.bearblog.dev/vibe-coding-menugen/
- **Date:** 2025-04-27
- **Key claims:** The code was the easy part. Most of the time went to deployment, env vars, Clerk auth, Stripe and rate limits, "moving between tabs and settings and configuring and gluing a monster". LLMs suggested deprecated APIs. The worst design bug was matching Stripe payments to users by email instead of by a persistent user ID.
- **Practical techniques:**
  - Prefer services an agent can drive through a CLI or curl with Markdown docs.
  - Paste current docs into the context to counter stale knowledge.
  - Review the agent's *design* decisions, especially identity and keys, not just syntax.
- **Notable quote:** "I spent most of it in the browser, moving between tabs and settings and configuring and gluing a monster."
- **Maps to:** 04, 05, 14

### K11. "2025 LLM Year in Review" (blog post)
- **URL:** https://karpathy.bearblog.dev/year-in-review-2025/
- **Date:** 2025-12-19
- **Key claims:**
  - RLVR (RL from verifiable rewards) became a major new training stage, and "RLVR turned out to offer high capability/$". It also adds a new knob, test-time compute.
  - Jagged intelligence: models are "at the same time a genius polymath and a confused and cognitively challenged grade schooler". Benchmarks get "benchmaxxed", so he has lost trust in them.
  - The LLM-app layer (Cursor and similar) does context engineering, orchestrates calls into DAGs, provides custom GUIs, and offers an autonomy slider.
  - "Claude Code (CC) emerged as the first convincing demonstration of what an LLM Agent looks like." Agents running locally, against your own environment and config, matter more than cloud containers. He says OpenAI got this wrong early on.
  - "code is suddenly free, ephemeral, malleable, discardable after single use."
- **Practical techniques:** Don't pick models from public benchmarks. Build a private eval that matches your workload, because public numbers are optimization targets.
- **Maps to:** 00, 01, 04, 07, 09

### K12. Sequoia AI Ascent 2026 talk (summary on blog)
- **URL:** https://karpathy.bearblog.dev/sequoia-ascent-2026/
- **Date:** 2026-04-30
- **Key claims:**
  - Around December 2025, agentic coding tools became reliable enough that the unit of delegation moved from lines to whole tasks.
  - He distinguishes **vibe coding** (raising the floor for everyone) from **agentic engineering**: the professional discipline of coordinating fallible agents while keeping correctness, security and maintainability. The engineer still owns the result by writing specs, reviewing plans and diffs, writing tests, building eval loops, managing permissions, and isolating worktrees.
  - "Traditional software automates what can be specified, LLMs/RL automate what can be verified." Coding agents work partly because tests, runs and diffs give them constant feedback.
  - Jaggedness depends on verifiability *and* on how much training attention labs give a domain. Ask whether your task is "on the rails". If it isn't, add context, tools, custom evals, or your own RL environment.
  - On hiring: puzzle interviews are obsolete. Have candidates build and deploy a substantial project with agents, then let adversarial agents attack it.
  - On agent-native infra: Markdown docs, CLIs, MCP, structured logs, schemas, safe permissions, auditable actions, headless setup ("sensors and actuators").
- **Practical techniques:** The course's "agentic engineering" checklist (spec, plan review, diff review, tests, eval loop, permissions, worktrees) comes almost verbatim from here. The MenuGen email-vs-ID bug is the canonical "human supplies design judgment" example.
- **Notable quotes:** "Vibe coding raises the floor. Agentic engineering is about extrapolating the ceiling." / "You can outsource your thinking, but you can't outsource your understanding." / "The programmer is increasingly not just a code writer, but an orchestrator of agents."
- **Maps to:** 00, 04, 05, 09, 11, 14
- **Note:** Secondary sources say Karpathy first proposed the term "agentic engineering" on X in early February 2026, around the first anniversary of vibe coding **[UNVERIFIED: tweet not fetched]**.

### K13. nanochat
- **URL:** https://github.com/karpathy/nanochat
- **Date:** Released October 2025 **[month from memory]**. The README is active as of 2026, and its leaderboard tracks time-to-GPT-2 falling from 3.04h (Jan 2026) to 1.65h (Mar 2026).
- **Key claims:** A minimal, end-to-end LLM training and inference harness (tokenizer, pretraining, SFT, eval, chat UI) on one 8xH100 node, driven by a single `--depth` dial. The README says GPT-2 capability costs "only $48 (~2 hours of 8XH100 GPU node)". It has an "AI policy: disclosure" requiring contributors to declare substantial LLM contributions. The repo now includes a `.claude/skills` folder and leaderboard entries produced by "autoresearch" rounds.
- **Anecdote:** Karpathy said on X at launch that nanochat was almost entirely hand-written, because Claude and Codex agents were "net unhelpful" on such off-distribution code **[UNVERIFIED wording. The Dwarkesh interview confirms the substance: "It's just not net useful."]**. Five months later the same repo was being optimized by autonomous agent loops (see K14). That arc is a good course narrative.
- **Maps to:** 00, 04, 06b

### K14. autoresearch
- **URL:** https://github.com/karpathy/autoresearch
- **Date:** March 2026 (README epigraph)
- **Key claims:** A minimal autonomous research loop with three files. `prepare.py` holds fixed data and eval code that the agent may not touch. `train.py` is the only file the agent edits. `program.md` holds the human's instructions ("essentially a super lightweight 'skill'"). The agent edits, trains for a **fixed 5-minute wall-clock budget**, checks `val_bpb` (lower is better and independent of vocabulary size), keeps or discards the change, and repeats. That gives about 12 experiments an hour, or about 100 overnight. The repo ships no agent of its own: you point Claude Code, Codex or similar at `program.md`.
- **Practical techniques:** This is the purest teachable hill-climbing loop.
  1. Freeze the evaluator so the agent cannot edit it, which prevents reward hacking.
  2. Fix the budget per trial so trials are comparable.
  3. Use one scalar metric.
  4. Run keep/discard as a greedy search.
  5. Log every experiment to an external file so state survives across iterations.
  6. Keep the human's lever in a Markdown file.
- **Notable quote:** "you're not touching any of the Python files like you normally would as a researcher." (README)
- **Maps to:** 06b, 09, 99
- **Note:** Figures such as "700 experiments, 11% faster" appear only in secondary blogs **[UNVERIFIED]**. Harrison Chase's "autoresearch-agents" adaptation was reported in secondary sources **[UNVERIFIED]**.

### K15. LLM Wiki idea file (gist)
- **URL:** Not fetched **[UNVERIFIED: secondary coverage, e.g. https://www.aibuilderclub.com/blog/karpathy-llm-wiki]**
- **Date:** About 2026-04-04 (secondary)
- **Key claims:** Instead of RAG over raw documents at query time, an agent keeps a persistent, interlinked Markdown wiki: entity pages, concept pages, per-source summaries and flagged contradictions. It runs periodic "health check" passes, and the human browses the result in Obsidian. The idea also appears in K12 ("maintaining a persistent wiki compiled from messy documents").
- **Practical techniques:** Use it as a memory pattern for module 03: compile knowledge ahead of time and let the agent maintain it, rather than retrieving it fresh every time.
- **Maps to:** 03, 06b

---

## Part 2: OpenAI

### O1. "A practical guide to building agents"
- **URL:** https://cdn.openai.com/business-guides-and-resources/a-practical-guide-to-building-agents.pdf
- **Date:** April 2025 **[month from memory]**
- **Key claims:**
  - "Agents are systems that independently accomplish tasks on your behalf."
  - Build an agent only when you face "Complex decision-making", "Difficult-to-maintain rules", or "Heavy reliance on unstructured data". Otherwise a deterministic workflow is enough.
  - The foundations are model, tools (data, action, orchestration) and instructions. Prototype "with the most capable model for every task", then swap in smaller models where evals still pass.
  - Orchestration is a run loop: "Common exit conditions include tool calls, a certain structured output, errors, or reaching a maximum number of turns." "Our general recommendation is to maximize a single agent's capabilities first."
  - There are two multi-agent patterns. In the manager pattern, a central agent calls specialists as tools. In the decentralized pattern, peers hand off to each other.
  - Layered guardrails: "Relevance classifier", "Safety classifier", "PII filter", "Moderation", "Tool safeguards", "Rules-based protections", "Output validation". Give each tool a risk rating ("low, medium, or high"), based on read vs. write access, reversibility and financial impact.
  - Two triggers for handing control to a human: "Exceeding failure thresholds" and "High-risk actions".
- **Practical techniques:**
  - Start with one agent. Split only when the prompt is full of conditionals or tools overlap.
  - Use prompt templates with policy variables rather than many separate prompts.
  - Map each guardrail to a risk you have identified, then add more as real failures appear.
- **Notable quote:** "customers typically achieve greater success with an incremental approach."
- **Maps to:** 06, 06b, 11, 13

### O2. OpenAI Agents SDK: the runner loop, guardrails, handoffs, tracing
- **URLs:** https://openai.github.io/openai-agents-python/running_agents/ · /guardrails/ · /handoffs/ · /tracing/
- **Date:** Living docs (SDK launched March 2025 **[from memory]**). Fetched 2026-10-19.
- **Key claims:**
  - **Loop:** call the LLM, then classify the result. It is final if it "produces text output with the desired type, and there are no tool calls". On a handoff, switch agent and loop. On tool calls, execute them, append the results and loop. If `max_turns` is exceeded, raise `MaxTurnsExceeded` or run a registered fallback handler. A paused run resumes from `RunState`.
  - **Guardrails:** Input guardrails run only on the first agent. Output guardrails run only on the agent that produces the final output. Tool guardrails wrap individual function tools. A tripwire raises `*TripwireTriggered`. Input guardrails run *in parallel* with the agent by default, so tokens or tools may already have been spent before the tripwire fires. Blocking mode (`run_in_parallel=False`) "guarantees that the expensive model does not start". If a guardrail throws, the result is treated as unknown, not as a rejection.
  - **Handoffs:** Handoffs are exposed to the model as `transfer_to_<agent>` tools. `input_filter` controls how much history the next agent sees. Put authorization checks in `on_handoff`. A handoff transfers the conversation, while `Agent.as_tool()` does not.
  - **Tracing:** Tracing is on by default. Spans cover agent, generation, function, guardrail and handoff. Sensitive data is captured by default (`trace_include_sensitive_data`). Custom processors export to LangSmith, Langfuse, Datadog and others. Redact inside your own exporter.
- **Practical techniques:**
  - Lab: implement the 3-way loop classification by hand in about 50 lines, then compare it to the SDK.
  - Discuss parallel vs. blocking guardrails as a latency/cost/side-effect trade-off, the way a senior engineer would treat speculative execution.
  - Set `max_turns` and use it as a runaway-loop circuit breaker.
- **Maps to:** 06, 06b, 06c (comparison point for LangGraph), 11, 12

### O3. "Unrolling the Codex agent loop" (Michael Bolin)
- **URL:** https://openai.com/index/unrolling-the-codex-agent-loop/
- **Date:** 2026-01-23 (secondary). It is the first post of a series.
- **Key claims:**
  - The loop: user input goes into the prompt, the model runs inference, it either returns a final message or requests a tool call, the tool output is appended, and the loop repeats until an assistant message ends the turn and "control returns to the user". The vocabulary is *turn* versus *thread*.
  - Prompt order: sandbox and permissions developer message, then developer_instructions, then aggregated AGENTS.md (capped at 32 KiB by default, more specific files later), then an environment message, then the user message.
  - **Prompt caching** requires exact prefix matches. Changing tools, model, sandbox or cwd mid-thread breaks the cache. Codex therefore *appends* change messages instead of editing earlier ones. One early MCP bug that listed tools in inconsistent order caused cache misses.
  - The full history is resent every time, so payload grows quadratically. Caching makes "sampling the model is linear rather than quadratic".
  - Codex skips `previous_response_id` to "keep requests fully stateless" and stay compatible with ZDR, and uses `encrypted_content` for reasoning.
  - **Compaction:** manual `/compact` has been replaced by the `/responses/compact` endpoint, which returns an opaque encrypted compaction item. It triggers automatically past `auto_compact_limit`.
- **Practical techniques:**
  - Treat the prompt as an append-only log, which is an event-sourcing analogy. Keep static content first.
  - Never mutate tool lists mid-session.
  - Measure cache hit rate as a cost SLO.
  - Design for stateless requests with compaction as the memory mechanism.
- **Maps to:** 03, 06b, 12

### O4. "Harness engineering: leveraging Codex in an agent-first world"
- **URL:** https://openai.com/index/harness-engineering/
- **Date:** 2026-02-11 (secondary). The author is Ryan Lopopolo **[UNVERIFIED: the fetched text didn't show a byline]**.
- **Key claims:**
  - Over about five months, starting in late August 2025, the team shipped an internal beta with zero hand-written lines: about 1M lines of code, about 1,500 merged PRs, and 3 engineers growing to 7, at roughly 3.5 PRs per engineer per day. They estimate it took about one-tenth of the hand-coding time. Single Codex runs went for "six hours or more", often overnight.
  - "Humans steer. Agents execute." The engineer's job becomes building environments, feedback loops and constraints.
  - **AGENTS.md as a map:** about 100 lines that "give Codex a map, not a 1,000-page instruction manual". A versioned `docs/` directory is the system of record, with design docs, architecture maps, quality grades and execution plans. Linters keep docs fresh, and a recurring "doc-gardening" agent opens fix-up PRs. "anything it can't access in-context while running effectively doesn't exist", so Slack and Docs knowledge has to move into the repo.
  - **Mechanical enforcement:** a strict layered domain architecture (Types, Config, Repo, Service, Runtime, UI, with forward-only dependencies). Custom lints carry *remediation text*, so the error message itself becomes the fix instruction in the agent's context.
  - **Agent legibility:** each worktree boots its own app instance, Chrome DevTools Protocol gives the agent DOM snapshots and screenshots, and an ephemeral per-worktree log and metrics stack is queryable with LogQL and PromQL. Performance budgets are given as targets, such as startup under 800 ms and no span over 2 s in four critical journeys.
  - **Review:** agent-to-agent review iterates until reviewers are satisfied, which they call a "Ralph Wiggum Loop". Human review is optional. Merge gates are minimal and flaky tests are re-run, which they say only works at very high throughput.
  - **Entropy:** agents copy bad patterns. Early on the team spent every Friday, about 20% of the week, cleaning "AI slop", which didn't scale. They replaced it with "golden principles" plus background cleanup agents that open small refactor PRs, many auto-merged. "Technical debt is like a high-interest loan" that is paid down continuously.
- **Practical techniques:** This is the richest single source for modules 04, 05 and 11. Teach these:
  1. AGENTS.md as an index with progressive disclosure.
  2. Lints whose messages are prompts.
  3. Per-worktree observability so the agent can verify its own work.
  4. Garbage-collection agents.
  5. Turning every human review comment into a doc or lint rule.
- **Notable quote:** "Humans steer. Agents execute."
- **Maps to:** 03, 04, 05, 06b, 11, 12, 14
- **Note:** Secondary sources say the term "harness engineering" was popularized by Mitchell Hashimoto in early February 2026, and that OpenAI open-sourced a Codex harness and execution engine in August 2026 **[UNVERIFIED]**.

### O5. "Run long horizon tasks with Codex" (OpenAI developer blog)
- **URL:** https://developers.openai.com/blog/run-long-horizon-tasks-with-codex
- **Date:** About 2026-02-23 (secondary). It references GPT-5.3-Codex. The author appears to be Derrick Choi, based on the GitHub handle in the post **[UNVERIFIED]**.
- **Key claims:**
  - GPT-5.3-Codex at Extra High effort ran about **25 hours uninterrupted** on a blank repo, using about 13M tokens and producing about 30k lines: a design tool with collaboration, layers, history and export.
  - Durable project memory lives in four Markdown files:
    - **Prompt.md:** the frozen spec, goals and non-goals, constraints, and "done when" checks.
    - **Plans.md:** milestones small enough for one loop, each with acceptance criteria and validation commands, plus the stop-and-fix rule and decision notes "to prevent oscillation".
    - **Implement.md:** the runbook. Plans.md is the source of truth, validate after each milestone, and keep diffs scoped.
    - **Documentation.md:** status and audit log.
  - The loop: plan, edit, run tools (tests, build, lint, typecheck), observe, repair, update docs, repeat.
- **Practical techniques:** This is the best template for a long-running loop lab. The stop-and-fix rule ("Run validation after each milestone (fix failures immediately)") is a generate-verify-fix loop. Decision notes stop the agent flip-flopping between alternatives.
- **Notable quote:** "The result was not perfect or production-ready, but it was real and testable."
- **Maps to:** 06b, 10, 11, 99

### O6. GPT-5-Codex ("Introducing upgrades to Codex") and GPT-5.1-Codex-Max
- **URLs:** https://openai.com/index/introducing-upgrades-to-codex/ and https://openai.com/index/gpt-5-1-codex-max/
- **Dates:** September 2025 (with a 2025-09-23 API update) and 2025-11-17
- **Key claims:**
  - GPT-5-Codex can "work independently for more than 7 hours at a time on large, complex tasks". It uses adaptive thinking: the bottom 10% of turns use 93.7% fewer tokens than GPT-5, and the top 10% reason about twice as long. It is "trained to run commands to verify its outputs". Code review matches PR intent to the diff and runs tests.
  - GPT-5.1-Codex-Max is natively trained for **compaction** across many context windows. OpenAI has observed it "work on tasks for more than 24 hours". It introduced an "xhigh" effort level, yet "We still recommend medium as the daily driver for most tasks."
  - Both posts say Codex "should be treated as an additional reviewer and not a replacement for human reviews". The sandbox limits writes to the workspace and turns the network off by default, because of prompt-injection risk.
- **Practical techniques:** Use these for the long-horizon timeline (7h, then 24h+, then 25h of real output) and the sandbox-by-default posture. Teach effort level as a cost/latency dial, defaulting to medium.
- **Maps to:** 04, 06b, 12, 13

### O7. Evaluation best practices (API docs)
- **URL:** https://developers.openai.com/api/docs/guides/evaluation-best-practices
- **Date:** Living doc (fetched 2026-10-19)
- **Key claims:**
  - "Adopt eval-driven development: Evaluate early and often. Write scoped tests at every stage."
  - There are five steps: objective, dataset, metrics, run and compare, evaluate continuously.
  - Grader families are metric-based, human, and LLM-as-judge. For judges, watch for position and verbosity bias, prefer pairwise or pass/fail, and validate against human labels.
  - What to evaluate depends on the architecture:
    - Single-turn: instruction following and correctness.
    - Workflow: evaluate each step in isolation.
    - Single agent: add tool selection and argument precision.
    - Multi-agent: add handoff accuracy, and "The decision to use a multi-agent architecture should be driven by your evals."
  - Anti-patterns: generic metrics like BLEU or perplexity, synthetic data that doesn't match production, "vibe-based" judgment, waiting until after launch, and not calibrating against humans.
- **Practical techniques:** The per-architecture checklist maps directly onto module 10. Log during development so production cases feed the eval set.
- **Maps to:** 07, 08, 09, 10

### O8. Graders guide and Evals API
- **URLs:** https://developers.openai.com/api/docs/guides/graders · https://developers.openai.com/cookbook/examples/evaluation/getting_started_with_openai_evals
- **Date:** Living docs
- **Key claims:**
  - Grader types: `string_check` (eq, neq, like, ilike), `text_similarity` (fuzzy, BLEU, ROUGE, cosine and others), `score_model` (an LLM returns a numeric score with reasoning), `python` (`grade(sample, item)` returns a float, and errors score 0), and `multi` (a weighted combination, currently RFT-only).
  - Design guidance:
    - Prefer smooth scores over binary, so the optimizer can see gradients.
    - Make it hard to score well without real skill.
    - Balance labels.
    - Watch for grader hacking, where the model scores high on the model grader and low with experts.
    - Avoid brittle string checks on arguments such as `1` vs `1.0`.
- **Practical techniques:** Build a grader ladder: string check, then Python, then score model, then human spot-check, choosing the cheapest grader that is valid for each criterion. Treat the "high model-grader score but low expert score" divergence as the alarm for judge drift and reward hacking.
- **Maps to:** 07, 08, 09
- **Note:** The cookbook listing includes a June 2026 entry, "Moving from OpenAI Evals to Promptfoo" **[UNVERIFIED: title only]**. Check whether OpenAI is steering people away from the hosted Evals API before building labs on it.

### O9. Cookbook: "Eval Driven System Design: From Prototype to Production" (receipt inspection)
- **URL:** https://developers.openai.com/cookbook/examples/partners/eval_driven_system_design/receipt_inspection
- **Date:** June 2025 (listing dates conflict between Jun 2 and Jun 17). Now marked archived. The authors are Hugh Wimberly, Joshua Marker, Eddie Siegel and Shikhar Kwatra (OpenAI and Fractional).
- **Key claims:**
  - The lifecycle: understand the problem, gather examples, build an end-to-end v0, label data and build initial evals, map evals to business metrics, improve progressively, and integrate QA into production.
  - Use the v0 model to *draft* labels that experts then correct, because expert time is scarce. Go for breadth before depth.
  - Mix graders: string checks for totals, similarity for merchant names, and model graders for missed line items and reasoning.
  - Grade end-to-end and per-step separately.
  - A **cost model** converts eval errors into dollars, because "not all evals matter". Merchant-name mismatches barely mattered, while missed handwritten marks and math errors were expensive.
  - Improve in this order: model selection, prompt, examples, tools, accessory models, fine-tuning. Then try a cheaper model (`gpt-4.1-mini`) against the same evals.
- **Practical techniques:** This is the best worked example of hill-climbing with a business-weighted objective. It contrasts eval-driven work with "poke-and-hope guesswork".
- **Maps to:** 07, 09, 99

### O10. "Testing Agent Skills Systematically with Evals" (Dominik Kundel, Gabriel Chua)
- **URL:** https://developers.openai.com/blog/eval-skills
- **Date:** 2026-01-22 (secondary)
- **Key claims:**
  - An eval is a prompt, a captured run (trace plus artifacts), a few checks, and a score you can compare over time.
  - Define success before writing the skill. Start with **10 to 20 prompts in a CSV** that mix explicit invocation, implicit invocation, contextual prompts and **negative controls** (prompts that should *not* trigger the skill).
  - Run with `codex exec --json` to get a JSONL event trace, then write deterministic checks against it, such as whether `npm install` ran or `package.json` exists.
  - Add rubric grading through a second read-only `codex exec` run with `--output-schema`, which returns `overall_pass`, a 0 to 100 score, and per-check results.
  - Measure four dimensions: outcome, process, style and efficiency (command count to catch loops, tokens from `turn.completed`).
  - Run with least privilege.
- **Practical techniques:** This is a ready-made lab for module 10: trajectory evals from JSONL traces, plus an LLM rubric with a schema, plus negative controls, all wired into CI.
- **Notable quote:** "Let real failures drive coverage."
- **Maps to:** 05, 07, 08, 10

### O11. GPT-4.1 prompting guide (Cookbook)
- **URL:** https://developers.openai.com/cookbook/examples/gpt4-1_prompting_guide
- **Date:** April 2025 (gpt-4.1-2025-04-14). Now archived.
- **Key claims:**
  - Three agentic system-prompt reminders raised OpenAI's internal SWE-bench Verified score by close to 20%:
    - Persistence: "You are an agent - please keep going until the user's query is completely resolved..."
    - Tool-calling: "...use your tools to read files and gather the relevant information: do NOT guess or make up an answer."
    - Planning: "You MUST plan extensively before each function call, and reflect extensively on the outcomes of the previous function calls."
  - Explicit planning added 4%. Passing tools through the API `tools` field rather than describing them in the prompt added 2%.
  - GPT-4.1 follows instructions literally, so prompts written for earlier models need migration.
  - In long context, put instructions at both the beginning and the end. If you can only put them once, put them above the context.
  - Recommended structure: Role and Objective, Instructions, Reasoning Steps, Output Format, Examples, Context, Final instructions.
- **Practical techniques:** Use these as an ablation exercise. Students add the three reminders one at a time and measure each on their own eval. Prompts become measured code changes.
- **Maps to:** 02, 06b, 09

### O12. GPT-5 prompting guide (Cookbook)
- **URL:** https://developers.openai.com/cookbook/examples/gpt-5/gpt-5_prompting_guide
- **Date:** August 2025 **[month from memory]**
- **Key claims:**
  - **Agentic eagerness** is a dial. To lower it, reduce `reasoning_effort` and give explicit context-gathering criteria and budgets, such as "an absolute maximum of 2 tool calls" or "stop as soon as you can act". To raise it, add persistence instructions: "Never stop or hand back to the user when you encounter uncertainty."
  - Tool preambles give progress updates.
  - Passing reasoning items through `previous_response_id` raised Tau-Bench Retail from 73.9% to 78.2%.
  - Contradictory instructions waste reasoning tokens, so audit prompt libraries for conflicts.
  - In Cursor's case study, verbosity was set low globally and high inside code tools, and a "maximize context" instruction was removed because it caused over-searching.
  - Use the prompt optimizer.
- **Practical techniques:** Teach eagerness as an autonomy slider expressed in the prompt (K1). Students write a "low eagerness" and a "high eagerness" variant and compare tool-call counts and success rate.
- **Maps to:** 02, 06b, 11

### O13. GPT-5.5 / GPT-6 family prompt guidance and the latest-model guide (current)
- **URLs:** https://developers.openai.com/api/docs/guides/prompt-guidance (now covers the GPT-6 family) · https://developers.openai.com/api/docs/guides/latest-model · GPT-5.5 commentary at https://simonwillison.net/2026/Apr/25/gpt-5-5-prompting-guide/
- **Dates:** The GPT-5.5 guide is from about April 2026. The GPT-6 Astra guidance follows the 2026-09-03 launch. The pages are undated.
- **Key claims:**
  - GPT-5.5 guide: treat each new model as a new family. Start migration "from a fresh baseline" rather than carrying over old prompt stacks. Process-heavy legacy prompts "narrow the model's search space". Describe outcomes and constraints instead. Re-test low and medium effort before escalating (as reported in secondary summaries).
  - GPT-6 Astra is more likely to pause for clarification and is literal about AGENTS.md and skill files. Fix this with "Prompt the model to ask for approval only after preparing a concrete, reviewable result." and "The user's instructions take precedence over guidelines provided in a skill."
  - Have the model cite which skill file and rule caused a pause.
  - The model tends to over-test: "Do not write tests for reversible, low-impact changes that mirror the implementation."
  - Long tasks: prompt it to "persist until the user's intended goal is complete", except for destructive actions.
  - "Evaluate them with your chosen model and workload."
- **Practical techniques:**
  - Re-baseline your prompts on every model upgrade and run your evals.
  - Audit instruction hierarchy conflicts across system prompt, AGENTS.md, skills and the user.
  - Make the model show which instruction it is following, so pauses can be debugged.
- **Maps to:** 02, 03, 05, 11

### O14. Mid-turn steering (Responses API, GPT-6 family)
- **URL:** https://developers.openai.com/api/docs/guides/steering (related: /guides/compaction, /guides/async-tool-calling, /guides/responses-multi-agent, which were not fetched)
- **Date:** Living doc, available with the GPT-6 family. It is not supported on GPT-5.6 and earlier.
- **Key claims:**
  - Over a WebSocket, send `response.steer` with the running response's ID. The server replies `response.steer.accepted`, but "Acceptance means the input is queued, not that the model has acted on it."
  - The server creates a continuation automatically. A steered response ends `incomplete` with reason `"steered"`.
  - Steering doesn't undo actions or cancel tools that have already started.
  - "Queued steering input exists only on the current connection", so clients must record steers and reconcile them after a disconnect.
- **Practical techniques:** This is the first first-class API for "recovering a run that is drifting" (module 11). It is a good distributed-systems discussion: at-most-once delivery of steers, idempotent reconciliation after reconnect, and acceptance vs. application semantics.
- **Maps to:** 06b, 11, 12
- **Note:** A secondary article (https://yage.ai/share/gpt6-long-horizon-agent-guide-en-20261008.html, 2026-10-08) says the multi-agent beta offers spawn, send, wait and interrupt with a default `max_concurrent_subagents` of 3, and cites "A model guide for the GPT-6 family" at openai.com/index/practical-guide-building-gpt-6/ **[UNVERIFIED: not fetched]**.

### O15. Reasoning best practices
- **URL:** https://developers.openai.com/api/docs/guides/reasoning-best-practices
- **Date:** Early 2025, the o1/o3 era. Still live.
- **Key claims:**
  - Reasoning models are "the planners" and GPT models are "the workhorses". Combine them, with the planner decomposing work and the workhorse executing.
  - Use reasoning models for ambiguity, needle-in-haystack search over large documents, multi-document nuance, agentic planning, code review, and as **judges**. Braintrust saw judge F1 go from 0.12 with 4o to 0.74 with o1.
  - Prompting: keep it simple, avoid "think step by step", use delimiters, try zero-shot first, and state success criteria.
- **Practical techniques:** Use the planner/workhorse split for model routing (module 12). Use a reasoning model as the judge in module 08, and measure judge F1 against human labels as Braintrust did.
- **Maps to:** 01, 02, 08, 12

### O16. Structured Outputs
- **URL:** https://openai.com/index/introducing-structured-outputs-in-the-api/
- **Date:** 2024-08-06
- **Key claims:**
  - On complex JSON-schema evals, gpt-4o-2024-08-06 with Structured Outputs scored 100%, versus under 40% for gpt-4-0613. Prompting alone reached 93%.
  - Implementation: the JSON Schema is compiled into a context-free grammar, and at each step tokens that would break the schema are masked (constrained decoding). The grammar is cached per schema, so the first request is slower.
  - Limitations:
    - Values can still be wrong.
    - Output can be truncated at `max_tokens`.
    - Only a subset of JSON Schema is supported.
    - It doesn't work with parallel tool calls.
    - There is a separate `refusal` field.
- **Practical techniques:** Always check `refusal` and `finish_reason` before parsing. The schema guarantees *shape*, not *truth*, so you still need semantic validators. The 93% to 100% gap is a good illustration of "prompting gets you most of the way, mechanisms get you the last nines" (K7).
- **Maps to:** 02, 11

### O17. "Why language models hallucinate" (paper and post)
- **URLs:** https://arxiv.org/abs/2509.04664 · https://openai.com/index/why-language-models-hallucinate/
- **Date:** 2025-09-04. The authors are Kalai, Nachum, Vempala and Zhang.
- **Key claims:**
  - Hallucinations are ordinary binary-classification errors that come from statistical pressure in pretraining, especially for arbitrary low-frequency facts such as birthdays. They persist because "standard training and evaluation procedures reward guessing over acknowledging uncertainty". Accuracy-only scoring is like a multiple-choice exam with no penalty for wrong answers.
  - The SimpleQA example from the GPT-5 system card:

    | Model | Abstained | Accuracy | Error rate |
    |---|---|---|---|
    | gpt-5-thinking-mini | 52% | 22% | 26% |
    | o4-mini | 1% | 24% | 75% |

  - The fix is to change mainstream evals so they penalize confident errors more than abstention: "The widely used, accuracy-based evals need to be updated so that their scoring discourages guessing." Calibration is cheaper than accuracy.
- **Practical techniques:**
  - In your own evals, score three outcomes (correct, abstain, wrong) with an explicit penalty for wrong answers, and state the confidence threshold in the prompt.
  - Report error rate next to accuracy.
- **Maps to:** 07, 09, 13

### O18. Sycophancy postmortems
- **URLs:** https://openai.com/index/sycophancy-in-gpt-4o/ (2025-04-29) **[URL from memory, not fetched]** · https://openai.com/index/expanding-on-sycophancy/ (2025-05-02 **[date from memory]**, fetched)
- **Key claims:**
  - The GPT-4o update shipped on April 24–25, 2025 and began rolling back on April 28.
  - It added a thumbs-up/down reward signal along with memory and data changes. Together they weakened the primary reward signal that held sycophancy in check.
  - Offline evals and A/B tests looked good, but sycophancy wasn't explicitly tested. Expert testers said the model "felt" slightly off, and OpenAI regrets overriding those qualitative signals.
  - Process fixes:
    - Treat behavioral issues, including hallucination, deception, reliability and personality, as launch-blocking.
    - Add an opt-in alpha phase.
    - Weight spot checks and vibe checks more heavily.
    - Add sycophancy evals to deployment.
- **Practical techniques:** A case study for module 09 on overfitting to proxy metrics: user-approval reward led to sycophancy. Also for module 08: aggregate metrics can't replace targeted behavioral evals. Rule: a qualitative red flag from an expert blocks a launch until someone writes an eval that explains it.
- **Notable anecdote:** OpenAI launched based on "the positive signals from the users who tried out the model".
- **Maps to:** 08, 09, 13

---

## Topics missing from draft list

1. **Verifiability as the organizing principle (Karpathy K8 and K12).** No module asks "can this task be verified automatically?" before automating it. That question decides whether to use an agent, how much autonomy to give it, and whether you can hill-climb at all. Consider making it the thesis of module 00 or 07.
2. **Agent legibility and environment design (harness engineering, O4).** Per-worktree app instances, per-worktree observability the agent can query, CDP or browser access, lints with remediation messages, and docs as the system of record. Module 05 covers tools, but not making the *codebase and runtime* readable and verifiable by agents. This deserves its own module or a large part of 04/05.
3. **Entropy management and "garbage collection" of agent-written code (O4).** Golden principles, background cleanup agents, quality scores per domain, and paying down debt continuously. This is missing everywhere. Module 14 could own it.
4. **Durable external memory for long runs (O5, K14, K15).** Prompt.md, Plans.md, Implement.md and Documentation.md; autoresearch's experiment log; the LLM wiki. Module 06b mentions "state outside the context", but deserves concrete templates.
5. **Prompt caching and the append-only prompt (O3).** Cache-prefix discipline, the quadratic growth of history, and stateless requests with compaction belong in 03 or 12. Today module 12 only says "caching".
6. **Mid-run steering as an API primitive (O14).** Steer, continuation, and reconciliation after disconnect. Module 11 talks about recovering drifting runs, but not the new protocol-level mechanisms.
7. **Model migration and re-baselining (O11, O13).** Every model upgrade changes literalness and eagerness and can break old prompts. "Model upgrade as a migration with eval gates" is missing. It fits 02, 09 or 12.
8. **Instruction hierarchy conflicts (O12, O13).** Contradictions across the system prompt, AGENTS.md, skills and the user waste tokens and cause pauses. Teach audits, and have the model cite which instruction it is following.
9. **Abstention-aware scoring (O17).** Score correct, abstain and wrong separately with asymmetric penalties. Module 07 lists pass@k and pass^k but not calibration and abstention.
10. **The demo-to-product gap and the "march of nines" (K7).** Frame reliability as nines and estimate the cost of each one. This fits module 09 or 12 and should resonate with an SRE background.
11. **Hiring and evaluating AI-native engineers (K12).** "Build and deploy with agents, then let adversarial agents break it." This belongs in module 14.
12. **Agent-native product surfaces (K1, K10, K12).** llms.txt, CLIs instead of dashboards, Markdown docs, headless setup: build *for* agents as consumers. Module 05 covers the agent's tools, not making *your* product consumable by other people's agents.
13. **Effort and verbosity as tunable parameters (O6, O12, O15).** `reasoning_effort`, verbosity, and planner/workhorse routing are explicit cost and quality knobs. They could be a section of 01 or 12.

## Points of tension or disagreement

1. **"Keep AI on a tight leash" vs. "humans steer, agents execute".** In mid-2025 Karpathy (K1) argued for small, verifiable chunks and partial autonomy. Harness engineering (O4) and the long-horizon post (O5) show 6- to 25-hour unattended runs with optional human review. By 2026 Karpathy himself says delegation moved to whole tasks (K12). The two can be reconciled: the leash moved from the *diff* to the *harness*, meaning tests, lints, plans and validators. That synthesis should be taught explicitly.
2. **Are agents useful for serious code?** Karpathy in October 2025 called them "not net useful" for nanochat and agent hype "slop" (K7). Two months later he called Claude Code the "first convincing demonstration" (K11) and by April 2026 he was delegating whole tasks (K12). OpenAI claims 1M lines with zero hand-written code (O4). Lesson: the answer depends on the task's distribution and on the model generation, so re-test your beliefs whenever models change.
3. **Human code review.** OpenAI's product posts say Codex "should be treated as an additional reviewer and not a replacement for human reviews" (O6). The internal harness team made human review optional and merged with minimal gates (O4), noting this is risky at lower throughput. Karpathy's agentic-engineering view (K12) keeps humans responsible for reviewing plans and diffs.
4. **Local vs. cloud agents.** Karpathy says OpenAI erred by starting with cloud containers, and that local agents with your own environment won (K11). OpenAI's Codex now spans CLI, IDE and cloud, but stresses sandboxing and network-off defaults (O6).
5. **Prompting style is a moving target.** GPT-4.1 needs very explicit, literal instructions and agentic reminders (O11). Reasoning models should get simple prompts without "think step by step" (O15). GPT-5.5 and GPT-6 want outcome-first prompts with less process, and over-specified legacy prompts hurt them (O13). Prompt advice expires, which argues for eval-gated prompts over prompt folklore.
6. **Benchmarks and LLM judges.** Karpathy distrusts benchmarks ("benchmaxxing") and says LLM-judge rewards get gamed (K7, K11). OpenAI's docs promote model graders and score models (O8), with caveats about grader hacking. Teach judges with calibration against humans and divergence alarms.
7. **Aggregate metrics vs. qualitative "feels off".** The sycophancy postmortem (O18) shows A/B tests and offline evals passing while experts sensed a problem. That cuts against pure eval-driven development. Evals cover only what you thought to measure.
8. **Single agent vs. multi-agent.** OpenAI says "maximize a single agent's capabilities first" and let evals drive the decision (O1, O7). The GPT-6 API now ships first-class subagent primitives, and the guidance says Astra under-delegates unless told to (O13, O14). The incentives are shifting toward multi-agent.
9. **Tests written by agents.** The long-horizon post relies on validation after every milestone (O5). GPT-6 guidance warns the model over-tests and says not to write tests that "mirror the implementation" (O13). Teach the difference between meaningful verification and tautological tests.

## Best concrete examples to reuse in the course

1. **autoresearch (K14).** The canonical hill-climbing loop, with a frozen evaluator, a fixed 5-minute budget, one scalar metric, keep/discard, and a program.md lever. It fits modules 06b, 09 and 99. Students can rebuild it for a non-ML metric such as p99 latency of a service or the pass rate of an eval suite.
2. **The four-file long-horizon template (O5).** Prompt.md, Plans.md, Implement.md and Documentation.md, plus the stop-and-fix rule. Use it directly as the module 06b lab scaffold.
3. **Codex skill evals with `codex exec --json` (O10).** 10 to 20 CSV prompts with negative controls, deterministic checks on JSONL traces, and a rubric grader with `--output-schema`. A ready-to-adapt lab for module 10 that works equally well with Claude Code's JSON output.
4. **SimpleQA abstention table (O17).** The 52/22/26 vs. 1/24/75 split makes the point that accuracy hides errors in one slide. Use it in module 07.
5. **The GPT-4.1 agentic reminders ablation (O11).** About 20% on SWE-bench from three paragraphs of prompt. Students reproduce the ablation on their own eval to learn that prompts are measurable code.
6. **Receipt-inspection cost model (O9).** Turning eval errors into dollars shows why "not all evals matter". Use it as the hill-climbing objective in module 09.
7. **Lints whose error messages are prompts (O4).** A tiny, high-leverage technique for module 11: every recurring review comment becomes a lint with remediation text.
8. **MenuGen's email-vs-user-ID Stripe bug (K10, K12).** A plausible agent design that is wrong. Use it in modules 04 and 14 for "review design, not syntax".
9. **The sycophancy rollback (O18).** A full real-world postmortem of a reward-signal change, passing evals, an ignored expert "feels off", and a rollback. Use it in modules 08, 09 and 13.
10. **The march of nines (K7).** "When you get a demo and something works 90% of the time, that's just the first nine." Pair it with SLO error budgets for an SRE-minded audience.
11. **The Codex prompt-cache discipline (O3).** Append-only messages, no mid-session tool changes, and the MCP tool-ordering cache-miss bug. A distributed-systems-flavored example for modules 03 and 12.
12. **Parallel vs. blocking guardrails in the Agents SDK (O2).** A latency vs. wasted-tokens-and-side-effects trade-off, analogous to speculative execution. Use it in module 11.
13. **Structured Outputs at 93% vs. 100% (O16).** Prompting gets you most of the way, and a mechanism (constrained decoding) gets you the last nines. It guarantees shape, not truth.
14. **The nanochat-to-autoresearch arc (K13, K14).** In October 2025, agents were "not net useful" on the repo. By March 2026 the same repo was being tuned by overnight agent loops. A good opening story for module 00 about recalibrating beliefs.
