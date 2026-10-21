# Gap Analysis

This compares the draft topic list (`00-draft-topics.md`) with four research passes:

| File | Scope |
|---|---|
| `anthropic.md` | 49 sources: the Anthropic engineering blog, docs, and Claude Code material through Oct 2026 |
| `openai-karpathy.md` | 33 sources: Karpathy talks and posts, OpenAI guides, Codex and harness posts |
| `practitioners.md` | 46 sources: Hamel/Shreya, Willison, Cognition, Huntley, METR, Stripe, Spotify, and others |
| `curricula.md` | Udacity nd900, the top Udemy courses, all 19 LangChain Academy items, DeepLearning.AI, Hugging Face, Maven AI Evals, and Steve Kinney |

## 1. Gaps found, and what we do with each

| # | Gap | Raised by | Disposition |
|---|---|---|---|
| 1 | **Verifiability as the organizing principle**: ask "can this be checked automatically?" before you automate, give autonomy, or hill-climb | Karpathy (Verifiability, Software 3.0), Anthropic, Huntley | Becomes the **course thesis** in module 00 and recurs in every module |
| 2 | **Harness engineering**: make the codebase and runtime legible and checkable for agents (AGENTS.md as a map, lints whose errors say how to fix them, observability per worktree, docs as the system of record) | OpenAI Harness engineering, LangChain (+13.7 pts on Terminal Bench with the model held fixed), Mitchell Hashimoto | **New module 08** |
| 3 | **Backpressure and oracle design**: build verifiers the loop can consume. "Write the oracle first and prove it can fail." | Huntley, Kinney, Spotify, Stripe | Core of the Loops module (07), reused in 08 and 14 |
| 4 | **Loop economics and governors**: budgets, iteration caps, stall and repetition detection, cost per iteration | Stripe (2 CI rounds), repomirror (~$10.50/hr), Bun port (~$165k), 12-factor #9, Stop-hook 8-block cap | Loops module (07) |
| 5 | **Scheduled, ambient, event-driven, and headless agents**, plus the "agent inbox" way of supervising them | LangChain Ambient Agents, Anthropic routines/`/loop`/scheduled agents, Mitchell's end-of-day agents | Loops module (07) |
| 6 | **Durable external memory for long runs**: Plans.md, progress files, feature_list.json, Beads, git as the state store | OpenAI long-horizon Codex, Anthropic long-running harnesses, Yegge | Loops (07); context management in 03 |
| 7 | **Design for evaluability early**: tracing and the trace data model come *before* error analysis | Hamel L2, LangChain ADLC, DL.AI Evaluating Agents | Tracing moves into **Evals fundamentals (10)**; production observability (15) builds on it |
| 8 | **Synthetic data and simulated worlds** to solve the eval cold-start problem | Hamel L3, Anthropic test-case docs | Evals (10) and Testing agents (13) |
| 9 | **Statistical rigor**: clustered SEs (3x naive), paired tests, power, a noise check before hill-climbing, infra noise (6-pt swings) | Anthropic error-bars paper and infra-noise post, Eugene Yan | Hill-climbing (12), with concrete worked numbers |
| 10 | **Eval integrity**: contamination, eval awareness, answer-key and git-history leakage, benchmark literacy (SWE-bench Verified retired) | Anthropic, practitioners | Evals (10) and Hill-climbing (12) |
| 11 | **Abstention-aware scoring**: score correct, abstain, and wrong separately | OpenAI "Why LMs hallucinate" (SimpleQA 52/22/26 vs 1/24/75) | Evals (10) |
| 12 | **Automated prompt and harness optimization** (DSPy/GEPA, bounded improve-loops), taught *after* manual hill-climbing | Hamel, LangSmith, Karpathy autoresearch | Hill-climbing (12) |
| 13 | **Model, effort, and cost as hill-climbing dimensions**: the accuracy-vs-cost frontier, fixing at the cheapest layer, the model-upgrade drill | Hamel L8/L9, Anthropic, OpenAI | Hill-climbing (12) and Production (15) |
| 14 | **Harness assumptions decay**: every scaffold encodes some model weakness, so ablate on each model upgrade. Prompt advice expires. | Anthropic (Opus 5 over-verifies), OpenAI (GPT-6 literalness), Thorsten Ball | Cross-cutting thread: Harness (08), Prompting (02), Hill-climbing (12) |
| 15 | **Prompt changes are deploys**: version, gate, soak, roll back | Anthropic | Prompting (02) and Production (15) |
| 16 | **Instruction hierarchy conflicts** across system prompt, AGENTS.md, skills, and the user | OpenAI GPT-6 guide | Prompting (02) and Context (03) |
| 17 | **Prompt caching and append-only prompt discipline** | OpenAI "Unrolling the Codex loop", Anthropic | LLMs (01) and Context (03) |
| 18 | **Code-as-action and programmatic tool calling**; MCP vs shell/CLI; degradation as tool count grows | Anthropic code-execution-with-MCP, Willison, Ronacher, HF smolagents, Breunig | Tools (05) |
| 19 | **Execution environments and sandboxes** as both capability boundary and security boundary | Deep Agents, Anthropic containment posts | Tools (05) and Security (16) |
| 20 | **Concurrency and durability of stateful agents**: checkpointers, time travel, double texting, resumability | LangGraph Academy, Anthropic Managed Agents | Architectures (06) and Frameworks (09), framed through idempotency, event sourcing, and OCC |
| 21 | **Single-writer multi-agent**: helpers read, review, or research while one agent writes | Cognition 2026 update, Anthropic | Architectures (06) |
| 22 | **Clean-context review agents** ("models watching models") | Cognition, Anthropic verifier voting | Architectures (06) and Team (17) |
| 23 | **RAG and memory in full**: agentic search vs embeddings for code; semantic, episodic, and procedural memory; grounding evals | Every curriculum, Jason Liu | Context (03), expanded |
| 24 | **Spec-driven development**: interview → SPEC.md → plan → implement → validate | DL.AI SDD course, Anthropic, Dex Horthy research-plan-implement | Agentic coding workflows (04) |
| 25 | **Mid-run steering primitives** (steer and continue APIs, `/goal`) and agent UX | OpenAI GPT-6 API, Anthropic, FSDL | Steering (14) |
| 26 | **Containment-first security**: egress-as-capability, credential proxies, permission classifiers with measured FPR/FNR; turning red-team findings into regression tests | Anthropic, Willison, Hamel L7 | Security (16) |
| 27 | **Code review at agent volume**: risk tiers, verifier voting, REVIEW.md, round caps | Anthropic (~90% of code Claude-written), Stripe, Spotify | Team (17) |
| 28 | **Entropy management**: background cleanup agents and paying down agent-written drift | OpenAI Harness engineering | Harness (08) |
| 29 | **Cognitive debt**, and **measuring your own productivity** (METR: 19% slower, perceived 20% faster) | METR, Ronacher, Beck | Orientation (00) and Team (17) |
| 30 | **Framework landscape beyond LangChain**: OpenAI Agents SDK, Claude Agent SDK, CrewAI, ADK/A2A, Pydantic AI | Ed Donner, Anthropic, OpenAI | Frameworks (09) |
| 31 | **Agent-native product surfaces** (llms.txt, CLIs, headless setup) | Karpathy | Tools (05), short section |
| 32 | Governance (NIST AI RMF, EU AI Act) | Curricula | Security (16), short section |
| 33 | Hill-climbing an LLM data pipeline (DocETL) | Shreya Shankar | **Capstone variant B**: relevant to a data-pipeline background |

Cut or de-emphasized:
- **Prefill.** It returns a 400 error on Claude 4.6+, so it appears only as a "techniques expire" example.
- **The "think" tool.** Its own update retired it.
- **Fine-tuning.** Out of scope; one paragraph on when you'd consider it.
- **Prompt-engineering "tricks" catalogs.** The Udemy courses lean on these heavily. The course replaces them with eval-gated prompting.

## 2. Tensions, and the stance the course takes

| Tension | Course stance (synthesis) |
|---|---|
| "Keep AI on a tight leash" (Karpathy 2025) vs 25-hour unattended runs (OpenAI 2026) | **The leash moved from the diff to the harness.** Autonomy should scale with how strong your verification is. |
| "Always give it a way to verify" vs "telling Opus 5 to verify causes over-verification" | **Put the check in the environment (a test it can run), not in the prompt.** Re-measure on every model. |
| Multi-agent: Cognition 2025 "don't" vs Yegge 20–30 agents / Anthropic +90% | **Single-writer principle.** Parallelize reads and isolated tasks with verifiable criteria. Never let parallel writers share state. |
| Ralph as a Stop-hook in the same session vs fresh context each iteration (Dex Horthy) | Fresh context plus durable state files is the default. Same-session Stop hooks are for short gates. |
| Loops for everything (Huntley) vs loops only for ports and experiments (Ronacher) | Choose based on **oracle quality**: loop hard where a strong oracle exists (ports, migrations, perf targets), stay interactive where it doesn't. |
| Eval-driven development first (Eugene) vs evals for observed failures (Hamel/Shreya) | Write **constraint evals** up front. **Failure-mode evals** come from error analysis. |
| METR slowdown vs company speedup claims | Both are true. Gains concentrate in narrow, verifiable task classes. **Measure your own productivity.** |
| Human review required vs automated verification replaces review | **Risk-tiered review policy.** |
| MCP with many tools vs shell/code tools | Use few, curated tools. Prefer code-as-action for data-heavy work. Measure the effect of adding a tool. |
| Hooks are useless for steering vs hooks are central | **Blocking verification gates work. Hooks that try to steer behavior mostly don't.** |
| Grep vs embeddings | Agentic search for code; vector RAG for document Q&A, each with its own evals. |
| AGENTS.md is core vs "delete it every few months" | Treat context files as code. Test with and without them, and prune them on model upgrades. |
| LLM judges are robust vs gameable | Use judges only with binary rubrics, calibration against 100–200 human labels, and drift alarms. |
| Frameworks hide prompts vs "pick one quickly" | Build it raw once to understand it, then adopt a framework for durability and tracing. |

## 3. Verification debt carried into Phase C
These items are marked [UNVERIFIED] or [secondary] in the research files and must be checked, or dropped, before they appear in course text:
- Exact Karpathy tweet wording and URLs
- Boris Cherny's "2–3x" claim (seen only via VentureBeat)
- Cat Wu material (403 errors)
- The SWE-bench Verified retirement post (blocked)
- The Shopify memo text
- Yegge's Medium posts
- Eden Marco's syllabus
- Dates that conflict between Anthropic listings and article pages
- Newer model facts (GPT-6 Astra, Karpathy joining Anthropic)

The course will cite sources by link and avoid quoting anything we couldn't verify.
