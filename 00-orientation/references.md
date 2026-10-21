# References

Primary sources were fetched and checked on 2026-10-19 unless marked otherwise.

## The thesis

- **Karpathy, "Verifiability"** (2025-11-17). https://karpathy.bearblog.dev/verifiability/
  *Take:* "Software 1.0 easily automates what you can specify. Software 2.0 easily automates what you can verify." Also the three conditions: resettable, efficient, rewardable. The course adds "faithful" for delegation.
- **Karpathy, Sequoia AI Ascent 2026 summary** (2026-04-30). https://karpathy.bearblog.dev/sequoia-ascent-2026/
  *Take:* vibe coding vs agentic engineering ("raises the floor" / "extrapolating the ceiling"), the December 2025 step change to delegating "macro actions", "LLMs and reinforcement learning automate what you can verify", and "You can outsource your thinking, but you can't outsource your understanding."
- **Karpathy, "Software Is Changing (Again)"**, YC AI Startup School (June 2025). Talk: https://www.youtube.com/watch?v=LCEmiRjPEtQ · Slide notes: https://www.latent.space/p/s3
  *Take:* "Software 3.0 - Prompts are now Programs", the autonomy slider, the generation-verification loop, and "Keep AI on tight leash". The quotes come from the Latent Space notes, not a transcript.
- **Karpathy, "Vibe coding MenuGen"** (2025-04-27). https://karpathy.bearblog.dev/vibe-coding-menugen/
  *Take:* the email-vs-user-ID payment bug. A demo that works is not a design that's right.
- **Karpathy on the Dwarkesh Podcast** (2025-10-17). https://www.dwarkesh.com/p/andrej-karpathy
  *Take:* agents "just not net useful" for novel nanochat code, and the "march of nines". This is why off-distribution work steps the dial down.
- **Simon Willison, "Vibe engineering"** (2025-10-07). https://simonwillison.net/2025/Oct/7/vibe-engineering/ and the *Agentic Engineering Patterns* guide: https://simonwillison.net/guides/agentic-engineering-patterns/
  *Take:* the practices that make agents effective (tests, planning, docs, CI, review culture), and the claim that AI amplifies existing expertise.
- **Simon Willison, "Embracing the parallel coding agent lifestyle"** (2025-10-05). https://simonwillison.net/2025/Oct/5/parallel-coding-agents/
  *Take:* review is the bottleneck. "I can only focus on reviewing and landing one significant change at a time."

## The leash moving

- **OpenAI, "Harness engineering: leveraging Codex in an agent-first world"** (Feb 2026; date from secondary listings, the fetched page showed none). https://openai.com/index/harness-engineering/ (read via a text proxy, since openai.com returns 403 to direct fetches)
  *Take:* "Humans steer. Agents execute." Zero manually written lines, roughly 1M lines and about 1,500 PRs, 3→7 engineers, runs of "upwards of six hours", optional human review, lints with remediation text, and cleanup agents. Also the caveat that minimal merge gates rely on very high throughput.
- **OpenAI, "Run long horizon tasks with Codex"** (about Feb 2026; author and date not shown on the page). https://developers.openai.com/blog/run-long-horizon-tasks-with-codex
  *Take:* about 25 hours, 13M tokens and 30k lines on GPT-5.3-Codex at Extra High effort. Durable spec, plan, runbook and status files. "not perfect or production-ready, but it was real and testable."
- **Stripe (Alistair Gray), "Minions: Stripe's one-shot, end-to-end coding agents"** (2026-02-09). https://stripe.dev/blog/minions-stripes-one-shot-end-to-end-coding-agents
  *Take:* more than 1,000 minion-produced PRs merged per week, all human-reviewed. Pre-warmed devboxes in 10 s. At most two CI rounds.
- **Anthropic (Osmani, Westlee Lunt, Wang), "How the Claude Code team does code review"** (2026-10-15). https://claude.dev/blog/solving-code-review-at-anthropic/
  *Take:* about 90% Claude-written code. Risk tiers needing 0/1/2 humans, assigned by a classifier. Verifier voting. The three-round cap. An agent's approval never counts as a human's. Merged PRs more than doubled while the revert share fell by more than 40%. One-round pass rate went from 65% to 78%.
- **Spotify (Charas, Bruggmann), "Honk" part 1** (2025-11-06). https://engineering.atspotify.com/2025/11/spotifys-background-coding-agent-part-1 · Part 3 (feedback loops): https://engineering.atspotify.com/2025/12/feedback-loops-background-coding-agents-part-3
  *Take:* more than 1,500 merged agent PRs, and 60–90% time savings on migrations "compared to writing the code by hand" (method not described). The three failure modes, with "passes CI but wrong" the most serious (part 3). Verifiers plus a Stop hook.
- **Claude Code hooks reference.** https://code.claude.com/docs/en/hooks (checked 2026-10-19)
  *Take:* for `Stop`, exit 2 "Prevents Claude from stopping, continues the conversation." Used in the [02](02-the-leash-moved.md) gate.

## Evidence on productivity

- **METR, "Measuring the Impact of Early-2025 AI on Experienced Open-Source Developer Productivity"** (2025-07-10). https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/ · Paper: https://arxiv.org/abs/2507.09089
  *Take:* 16 developers and 246 issues, randomized per issue. 19% longer with AI (CI +2% to +39%), against forecasts of 24% faster (developers), 39% (economists) and 38% (ML experts), and a post-hoc belief of 20% faster. METR now marks these results out of date.
- **METR, late-2025 uplift update** (2026-02-24). https://metr.org/blog/2026-02-24-uplift-update/
  *Take:* point estimates of −18% (CI −38% to +9%) and −4% (CI −15% to +9%). "likely that developers are more sped up from AI tools now" but "only very weak evidence for the size". Selection effects: 30–50% of developers withheld tasks. This is the design flaw [05](05-measure-yourself.md) is built to avoid.

## Statistics used in the kit

- Welch's t interval on log durations, with the t quantile from a Cornish–Fisher expansion (stdlib has no `t.ppf`). Accurate to within 0.1% of table values for df ≥ 3; this is tested in `code/test_selfmeasure_stats.py`.
- Permutation test for the p-value, and permuted-block randomization within strata. These are standard designs. For the deeper treatment of error bars, paired tests and power, see [12-hill-climbing](../12-hill-climbing/README.md).

## Not verified, so not quoted

- Karpathy's original "vibe coding" post on X (Feb 2025) and the claim that he coined "agentic engineering" on X in Feb 2026. We cite the Sequoia summary instead.
- The "Iron Man suit vs robot" wording. The Latent Space notes use "Iron Man Suit analogy" without the robot contrast.
- The byline of the OpenAI harness-engineering post, and the author of the long-horizon post.
