# References

Grouped by concept file. "Checked" means fetched and read on 2026-10-19 while writing this module.

## Tokens and the context window ([01](01-tokens-and-the-context-window.md))

- **Hong, Troynikov, Huber (Chroma), "Context Rot: How Increasing Input Tokens Impacts LLM Performance"**, 2025-07-14. https://www.trychroma.com/research/context-rot. Checked. *Take:* 18 models, and performance falls with input length even on simple tasks. Low needle-question similarity and a single distractor both make it worse. Focused (~300-token) prompts beat full (~113k-token) ones on LongMemEval.
- **Anthropic, "Effective context engineering for AI agents"**, 2025-09-29. https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents. From course research notes. *Take:* context as a finite attention budget, context rot as a gradient, just-in-time retrieval, compaction, notes, subagents.
- **Liu et al., "Lost in the Middle: How Language Models Use Long Contexts"**, 2023. https://arxiv.org/abs/2307.03172. Not re-fetched for this module. *Take:* information at the start and end of a long context is used better than information in the middle.
- **Anthropic, Prompting best practices** (living doc). https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices. Checked. *Take:* long data at the top and the query at the end ("up to 30 percent" quality improvement in their tests), grounding in quotes, and the `<investigate_before_answering>` prompt.
- **Anthropic, "Introducing advanced tool use"**, 2025-11-24. https://www.anthropic.com/engineering/advanced-tool-use. From course research notes. *Take:* tool definitions consumed 55k to 134k tokens before a conversation started. Tool search with deferred loading.
- **Karpathy, "Deep Dive into LLMs like ChatGPT"**, 2025-02-05. https://www.youtube.com/watch?v=7xTGNNLPyMI. *Take:* tokenization explains failures at spelling, counting and `9.11` vs `9.9`. "Models need tokens to think." Use code for arithmetic.

## Sampling and nondeterminism ([02](02-sampling-and-nondeterminism.md))

- **Horace He / Thinking Machines Lab, "Defeating Nondeterminism in LLM Inference"**, 2025-09-10. https://thinkingmachines.ai/blog/defeating-nondeterminism-in-llm-inference/. Checked. *Take:* the root cause is lack of batch invariance, not concurrency per se. Qwen3-235B at temperature 0 gave 80 unique completions out of 1,000, diverging at token 103. Batch-invariant kernels fix it at a throughput cost (26 s → 55 s → 42 s in their vLLM test).
- **Anthropic, "A postmortem of three recent issues"**, 2025-09-17. https://www.anthropic.com/engineering/a-postmortem-of-three-recent-issues. From course research notes. *Take:* serving-side bugs (routing, TPU corruption, approximate top-k) degrade output without any change on your side. Models recovering from isolated errors hides the problem.
- **Claude API reference, thinking and sampling parameters** (as bundled in Anthropic's `claude-api` skill, cached 2026-10-06). *Take:* `temperature`, `top_p` and `top_k` are removed (400) on Opus 5.5 and Fable 5.x, and non-default values are rejected on Sonnet 5.5 and Haiku 5.5. Re-check https://platform.claude.com/docs before relying on this.

## Reasoning and effort ([03](03-reasoning-models-and-effort.md))

- **Claude API docs, effort and adaptive thinking** (living). https://platform.claude.com/docs. *Take:* `output_config.effort` from low to max. Defaults are medium on Opus 5.5 and Haiku 5.5 and high on Sonnet 5.5. `budget_tokens` is removed on current models. Thinking is billed whether or not it's displayed.
- **Anthropic, "An update on recent Claude Code quality reports"**, 2026-04-23. https://www.anthropic.com/engineering/april-23-postmortem. From course research notes. *Take:* lowering the default effort, a thinking-history bug that also caused cache misses, and one system-prompt line combined into a regression that passed every test.
- **LangChain, "Improving Deep Agents with harness engineering"**, 2026-02-17. https://www.langchain.com/blog/improving-deep-agents-with-harness-engineering. From course research notes. *Take:* the reasoning sandwich, and max effort throughout scoring worse because of timeouts (53.9% vs 63.6%).
- **OpenAI, GPT-5.1-Codex-Max**. https://openai.com/index/gpt-5-1-codex-max/. From course research notes. *Take:* even with an "xhigh" effort tier, OpenAI recommends medium as the daily driver.
- **Karpathy, "2025 LLM Year in Review"**, 2025-12-19. https://karpathy.bearblog.dev/year-in-review-2025/. *Take:* RLVR adds a test-time compute dial. "Jagged intelligence". Distrust of benchmarks.

## Caching, cost and latency ([04](04-prompt-caching-cost-and-latency.md))

- **Anthropic, Prompt caching docs** (living). https://platform.claude.com/docs/en/build-with-claude/prompt-caching. Checked. *Take:* tools → system → messages hierarchy, exact-prefix matching, 4 breakpoints, the 20-block lookback, TTLs measured from request start, minimum sizes (512 tokens on current models), and the three usage fields.
- **Anthropic, Pricing** (living). https://platform.claude.com/docs/en/about-claude/pricing. Checked. *Take:* per-model input, output, write and read prices. Cache reads at 0.05x on Opus 5.5 and Sonnet 5.5 and 0.025x on Fable 5.1. Batch at 50% off, and the multipliers stack. Haiku 5.5's long-prompt price tier.
- **Anthropic, "Prompt caching with Claude"** (2024 launch post, now at claude.com). https://claude.com/blog/prompt-caching. Checked. *Take:* "up to 90%" cost and "up to 85%" latency reduction for long prompts. 100k-token TTFT 11.5 s → 2.4 s on the models of that time.
- **OpenAI (Michael Bolin), "Unrolling the Codex agent loop"**, 2026-01. https://openai.com/index/unrolling-the-codex-agent-loop/. From course research notes. *Take:* append-only prompts, never mutating tools mid-session, the MCP tool-ordering cache bug, and caching making sampling "linear rather than quadratic".

## Jaggedness and nines ([05](05-jaggedness-and-the-march-of-nines.md))

- **Dwarkesh Podcast, "Andrej Karpathy: AGI is still a decade away"**, 2025-10-17. https://www.dwarkesh.com/p/andrej-karpathy. Checked (transcript). *Take:* "it's a march of nines", "Every single nine is a constant amount of work", "When you get a demo and something works 90% of the time, that's just the first nine", and the demo-to-product gap.
- **Karpathy, "Verifiability"**, 2025-11-17. https://karpathy.bearblog.dev/verifiability/. *Take:* verifiable tasks are trainable, and that explains the shape of the jagged frontier.
- **Karpathy, Sequoia AI Ascent 2026 summary**, 2026-04-30. https://karpathy.bearblog.dev/sequoia-ascent-2026/. *Take:* whether a task is "on the rails" depends on verifiability and on lab attention.
- **Dell'Acqua et al., "Navigating the Jagged Technological Frontier"**, Harvard Business School working paper, 2023. Not fetched (the HBS and SSRN pages returned 403). Cited only as the origin of the phrase, with no numbers.
- **τ-bench** (Sierra) for pass^k as a consistency metric. See [Module 10](../10-evals-fundamentals/README.md) references.

## Hallucination and sycophancy ([06](06-hallucination-and-sycophancy.md))

- **Kalai, Nachum, Vempala, Zhang, "Why Language Models Hallucinate"**, 2025-09-04. https://arxiv.org/abs/2509.04664. Abstract checked. *Take:* hallucinations are binary-classification errors, and they persist because evals "reward guessing over acknowledging uncertainty". The fix is to change scoring to penalize confident errors.
- **OpenAI, "Why language models hallucinate"** (post). https://openai.com/index/why-language-models-hallucinate/. Direct fetch returned 403. The SimpleQA table (52/22/26 vs 1/24/75) was confirmed via search results and the course research notes. *Take:* accuracy leaderboards reward guessing.
- **Sharma et al. (Anthropic), "Towards Understanding Sycophancy in Language Models"**, 2023-10-20 (v4 2025-05-10). https://arxiv.org/abs/2310.13548. Checked. *Take:* sycophancy across five assistants and four tasks. Human preference data favors agreeing responses.
- **OpenAI, "Expanding on what we missed with sycophancy"**, 2025-05. https://openai.com/index/expanding-on-sycophancy/. From course research notes. *Take:* a reward-signal change, offline evals that didn't test the property, and overridden qualitative concerns, leading to a rollback.
- **Anthropic, "Harness design for long-running application development"**, 2026-03-24. https://www.anthropic.com/engineering/harness-design-long-running-apps. From course research notes. *Take:* "agents reliably skew positive when grading their own work".
- **Karpathy, "Vibe coding MenuGen"**, 2025-04-27. https://karpathy.bearblog.dev/vibe-coding-menugen/. *Take:* stale API knowledge in practice. Paste current docs.
