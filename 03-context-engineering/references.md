# References

Read in roughly this order. Anything quoted in this module was checked against the live page on 2026-10-19 unless it is marked as reported or secondary.

## Anthropic

- **[Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)** (2025-09-29). The core source for this module. Take: the attention budget and context rot; "smallest set of high-signal tokens"; just-in-time retrieval with lightweight identifiers; Claude Code as a hybrid (CLAUDE.md up front, glob/grep just in time); compaction as "the first lever", with tool-result clearing as its lightest form; structured notes; subagents returning 1,000 to 2,000 token summaries.
- **[Prompting best practices: workflows across multiple context windows](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices)** (living doc). Take: "consider starting with a brand new context window rather than using compaction"; the startup instructions (pwd, progress.txt, tests.json, git log); JSON for structured state and text for progress notes; the context-awareness prompt.
- **[Effective harnesses for long-running agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)** (2025-11-26). Take: why compaction alone wasn't enough; the initializer session; `feature_list.json` where agents only flip `passes`; the startup ritual.
- **[Harness design for long-running application development](https://www.anthropic.com/engineering/harness-design-long-running-apps)** (2026-03-24). Take: "context anxiety" on Sonnet 4.5, resets dropped for compaction on Opus 4.5, and the general rule that harness components encode assumptions about model weaknesses.
- **[Scaling Managed Agents](https://www.anthropic.com/engineering/managed-agents)** (2026-04-08). Take: compaction and trimming "all involve irreversible decisions about what to keep"; the session as an append-only log living outside the window; `getEvents()` slices; resets that "had become dead weight".
- **[Introducing Contextual Retrieval](https://www.anthropic.com/engineering/contextual-retrieval)** (2024-09-19). Take: the under-200k-token "skip RAG" rule; chunk context of 50 to 100 tokens; failure-rate reductions of 35%, 49% and 67% (5.7% to 1.9%); top-20 over top-5 or top-10; 1 minus recall@20 as the metric.
- **[Prompt caching docs](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)** (living doc, read October 2026). Take: the tools, system, messages prefix order; TTLs and multipliers; minimum cacheable lengths per model; what invalidates which level; `usage` fields. Re-check before quoting prices.
- **[Context editing](https://platform.claude.com/docs/en/build-with-claude/context-editing)** and **[Compaction](https://platform.claude.com/docs/en/build-with-claude/compaction)** docs (beta, October 2026). Take: tool-result and thinking clearing; server-side compaction on demand or at a threshold, with a custom summarization prompt; how each interacts with caching. Parameter names are beta and may change.
- **[Claude Code: how Claude remembers your project](https://code.claude.com/docs/en/memory)** (living doc). Take: "target under 200 lines"; load order; subdirectory files loading on demand; path-scoped rules; imports not reducing cost; HTML comments stripped; AGENTS.md support; auto memory's four note types and its 200-line/25KB index limit.
- **[Claude Code: subagents](https://code.claude.com/docs/en/sub-agents)** (living doc). Take: what a subagent does and doesn't see at startup; forks; frontmatter (`tools`, `model`, `maxTurns`, `isolation`, `memory`).
- **[Claude Code best practices](https://code.claude.com/docs/en/best-practices)** (living doc). Take: "Would removing this cause Claude to make mistakes?"; `/clear` after two failed corrections; the named failure patterns (kitchen-sink session, over-specified CLAUDE.md).
- **[Code execution with MCP](https://www.anthropic.com/engineering/code-execution-with-mcp)** and **[Introducing advanced tool use](https://www.anthropic.com/engineering/advanced-tool-use)** (Nov 2025). Take: tool definitions as a context cost; the reported 150k to 2k token reduction; deferred tool loading. These matter more in [Module 05](../05-tools-mcp-skills-hooks/README.md).
- **[Writing effective tools for agents](https://www.anthropic.com/engineering/writing-tools-for-agents)** (2025-09-11). Take: filter at the source, `response_format`, pagination and truncation, and meaningful identifiers.
- **[Building effective agent automations](https://claude.dev/blog/building-effective-agent-automations/)** (2026-10-08). Take: a read-only preference store re-read every run, and re-verifying before acting.

## OpenAI

- **[Harness engineering](https://openai.com/index/harness-engineering/)** (Feb 2026). Take: AGENTS.md as a ~100-line map, not a manual; `docs/` as the system of record; "anything it can't access in-context while running effectively doesn't exist"; doc-gardening agents.
- **[Unrolling the Codex agent loop](https://openai.com/index/unrolling-the-codex-agent-loop/)** (Jan 2026). Take: exact-prefix caching; appending change messages instead of editing; the MCP tool-ordering cache bug; quadratic to linear; AGENTS.md aggregation with a 32 KiB default cap.
- **[Run long horizon tasks with Codex](https://developers.openai.com/blog/run-long-horizon-tasks-with-codex)** (Feb 2026). Take: durable memory in Prompt.md, Plans.md, Implement.md and Documentation.md.

## Practitioners and research

- **[Chroma, "Context Rot"](https://www.trychroma.com/research/context-rot)** (Hong, Troynikov, Huber, 2025-07-14). Take: 18 models; degradation with input length on simple tasks; distractor effects; coherent vs shuffled haystacks.
- **[Drew Breunig, "How Long Contexts Fail"](https://www.dbreunig.com/2025/06/22/how-contexts-fail-and-how-to-fix-them.html)** (2025-06-22). Take: poisoning, distraction, confusion and clash as diagnostic categories.
- **[LangChain, "Context engineering for agents"](https://www.langchain.com/blog/context-engineering-for-agents)** (2025-07-02). Take: write, select, compress and isolate as the four strategies, which map onto files 02, 03 and 07.
- **[HumanLayer, Advanced context engineering for coding agents](https://github.com/humanlayer/advanced-context-engineering-for-coding-agents/blob/main/ace-fca.md)** (Dex Horthy). Take: frequent intentional compaction; research, plan, implement as fresh sessions; 40-60% utilization; "the contents of your context window are the ONLY lever".
- **[HumanLayer, "A brief history of Ralph"](https://humanlayer.dev/blog/brief-history-of-ralph)** (2026-01-06). Take: the argument for fresh context per unit of work over same-session continuation.
- **[Geoffrey Huntley, "how to build a coding agent"](https://ghuntley.com/agent/)**, **["Ralph"](https://ghuntley.com/ralph/)** and **["nobody should type code by hand anymore"](https://ghuntley.com/agency/)**. Take: context as scarce memory; ripgrep misses leading to duplicate implementations; test AGENTS.md and skills with and without them, and delete and re-test periodically.
- **[repomirror write-up](https://github.com/repomirrorhq/repomirror/blob/main/repomirror.md)** (Aug 2025). Take: the 1,500-word prompt that did worse than 103 words.
- **[Jason Liu, "There are only 6 RAG evals"](https://jxnl.co/writing/2025/05/19/there-are-only-6-rag-evals/)** and the **[RAG series](https://jxnl.co/writing/2025/09/11/rag-series-index/)**. Take: Q/C/A relationships; retrieval metrics before generation; diagnosis by symptom; his report of grep beating embeddings for coding agents.
- **[Mitchell Hashimoto, "My AI adoption journey"](https://mitchellh.com/writing/my-ai-adoption-journey)** (2026-02-05). Take: "engineer the harness": each agent mistake becomes an AGENTS.md line or a tool.
- **[Eugene Yan, "How to work and compound with AI"](https://eugeneyan.com/writing/working-with-ai/)** (2026-05-03). Take: context as infrastructure; greppable file organization with an index; each rule in one place.
- **[DeepLearning.AI, "Long-term agentic memory with LangGraph"](https://www.deeplearning.ai/short-courses/long-term-agentic-memory-with-langgraph/)** (Harrison Chase). Take: the semantic, episodic and procedural taxonomy, with procedural memory as a prompt refined from feedback.

## Secondary or unverified (used with hedges only)

- Boris Cherny's "add it to CLAUDE.md whenever Claude gets something wrong" habit: reported by VentureBeat (2026-01-04). The original thread was not checked.
- Karpathy's "LLM wiki" idea: secondary coverage only. Presented as an idea, not a result.
- Karpathy's "context engineering" definition ("the delicate art and science of filling the context window..."): widely quoted. The original post was not fetched for this module, so it isn't quoted here.
