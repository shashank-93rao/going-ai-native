# 02: Just-in-time retrieval, tool-output hygiene, and subagents as a context firewall

## The idea

There are two ways to get information into the window.

- **Pre-loading.** Put it in up front: system prompt, context file, retrieved documents stuffed in before the first turn. It costs tokens on every call whether or not they get used. In exchange, the model never has to know that it needs the information.
- **Just-in-time (JIT) retrieval.** Give the agent *references*, meaning "lightweight identifiers (file paths, stored queries, web links, etc.)", plus tools to load the content at runtime ([Anthropic, "Effective context engineering"](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)). It costs a tool round-trip and depends on the agent knowing what to look for. In exchange, only what gets used enters the window.

Claude Code is a hybrid on purpose. "CLAUDE.md files are naively dropped into context up front", while "primitives like glob and grep allow it to navigate its environment" and fetch files just in time (same source). Nested CLAUDE.md files and path-scoped rules are a third option in between: they are pre-loaded *conditionally*, when the agent touches a matching directory ([Claude Code docs, memory](https://code.claude.com/docs/en/memory)).

**Subagents** apply the same idea to work rather than data. Exploration that would burn tens of thousands of tokens happens in a separate window, and only a condensed result comes back. Anthropic describes subagents that "might explore extensively, using tens of thousands of tokens or more," and return "only a condensed, distilled summary of its work (often 1,000-2,000 tokens)."

## Why it matters

Pre-loading fails at scale in a way you can calculate. Anthropic's code-execution-with-MCP post reports a workflow going from about 150,000 tokens to about 2,000 once tool definitions were discovered on demand from a filesystem and intermediate data stayed in code instead of passing through the model ([Anthropic, "Code execution with MCP"](https://www.anthropic.com/engineering/code-execution-with-mcp)). Tool Search, which defers loading tool definitions, reportedly cut context from about 77k to 8.7k tokens and raised one MCP eval's accuracy on Opus 4 from 49% to 74% ([Anthropic, "Introducing advanced tool use"](https://www.anthropic.com/engineering/advanced-tool-use)). Those are Anthropic's measurements on Anthropic's evals. The direction is the useful part: fewer irrelevant tokens gave both lower cost *and* higher accuracy.

JIT fails in a different way, and you need to know that one too. Huntley's Ralph write-up lists a characteristic failure: a ripgrep miss leads the agent to conclude "it's not implemented" and to write a duplicate implementation ([Huntley, "Ralph Wiggum as a software engineer"](https://ghuntley.com/ralph/)). JIT moves the risk from "drowned in context" to "didn't look in the right place". The fix is a better map (see [05](05-context-files.md)) and better search tools, not pre-loading everything.

## How it works / how to do it

### Decision rule: pre-load or fetch?

| Pre-load when | Fetch just in time when |
|---|---|
| Nearly every turn needs it (build and test commands, hard constraints) | Only some tasks need it (one service's internals) |
| The agent can't know it's missing (an invariant like "the ledger is append-only") | The agent can tell it needs it ("which runbook covers DiskPressure?") |
| It is small and stable (good for caching) | It is large or changes often (logs, metrics, tickets) |
| A wrong guess is expensive and silent | A miss is loud (a test fails, a file isn't found) |

The second row is the subtle one. A fact the agent doesn't know it needs, such as "invoice ids are not unique across regions", can't be fetched just in time, because nothing prompts the lookup. Those facts belong in the always-loaded map. Everything that has a natural trigger ("I'm editing `migrations/`") can sit behind a pointer or a path-scoped rule.

### Tool-output hygiene

Most window bloat comes from tool results, not from prompts. Rules that pay for themselves:

- **Filter at the source.** Expose `search_logs(service, pattern, since)` rather than `read_logs(service)`. Anthropic's tool guidance recommends consolidating like this, and also recommends offering a `response_format` of concise or detailed ([Anthropic, "Writing effective tools"](https://www.anthropic.com/engineering/writing-tools-for-agents)).
- **Paginate and truncate**, and say so in the result: `"showing 50 of 2,113 matches; refine pattern or pass page=2"`.
- **Return identifiers that mean something**, like `invoice-consumer-7c9f` rather than a UUID, so the agent can reference them in later calls without re-reading.
- **Clear stale results.** Once a tool result has been acted on, its raw bytes are dead weight. Anthropic calls tool-result clearing "one of the safest lightest touch forms of compaction". The API supports it as context editing (`clear_tool_uses_20250919`, behind the `context-management-2025-06-27` beta header as of October 2026; [docs](https://platform.claude.com/docs/en/build-with-claude/context-editing)). `code/compaction.py` has a client-side `clear_tool_results`.

### Subagents as a context firewall

A subagent is a separate model session with its own window. In Claude Code, "each subagent starts with a fresh, isolated context window. It doesn't see your conversation history, the skills you've already invoked, or the files Claude has already read." It does load the CLAUDE.md hierarchy, except for the built-in Explore and Plan agents ([Claude Code docs, subagents](https://code.claude.com/docs/en/sub-agents)). A *fork* is the exception: it inherits the parent conversation, and only its result comes back.

Three rules make subagents work:

1. **Use them for reads, not parallel writes.** Search, log reading, research and review are good fits. Two subagents editing the same files is a race condition with no lock. The course's single-writer rule is in [Module 06](../06-agent-architectures/README.md).
2. **Write the delegation prompt like an RPC contract.** The subagent knows nothing about your conversation. State the objective, the scope, the output format and a size limit, and restate any rule it must obey. Anthropic's research-system post lists objective, output format, tool guidance and boundaries as the parts of a good delegation ([Anthropic, "Multi-agent research system"](https://www.anthropic.com/engineering/multi-agent-research-system)).
3. **Demand evidence in the return value.** A summary without `file:line` references can't be checked, so the main agent either trusts it blindly or re-reads everything, and the second option destroys the savings.

Don't over-spawn. Anthropic's Opus 5 prompting guide warns that the model delegates more readily than earlier ones, and suggests capping it ([Anthropic, "Prompting Claude Opus 5"](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5)). A subagent costs a full session's worth of tokens. Use one when the exploration would cost several thousand tokens and only the conclusion matters.

## Worked example: a flaky integration test in a Java monorepo

**Situation.** `PaymentSettlementIT` fails about 1 run in 20 on CI. You ask the agent to find out why.

**Bad version.** One session, no delegation:

```text
> PaymentSettlementIT is flaky on CI (~5%). Find the root cause.
```

(illustrative trajectory) The agent greps for the test, reads it, reads `SettlementService`, `LedgerClient`, the Testcontainers config, three base classes, then `cat`s two 4,000-line CI logs. By the time it has a hypothesis, the window holds about 120k tokens, mostly log lines. It proposes adding `Thread.sleep(500)`. When you push back, it re-reads the files it already summarized, because the early reads have been compacted away.

**Good version.** Keep the main session as the coordinator, and give the token-heavy reading to subagents with tight contracts.

`.claude/agents/ci-log-reader.md`:

```markdown
---
name: ci-log-reader
description: Reads CI logs for one failing test and reports the failure signature with evidence. Use for any CI log over 500 lines.
tools: Read, Grep, Glob, Bash
model: haiku
maxTurns: 15
---
You read CI logs. You never edit files.
Return at most 25 lines:
1. Failure signature (exception type + first app frame, file:line)
2. Timing: what happened in the 2 seconds before the failure (log lines with timestamps)
3. Differences between the failing run and the passing run, if both logs are given
Quote log lines exactly. If you are unsure, say so; do not guess.
```

Delegation from the main session:

```text
Use the ci-log-reader agent on build-8812.log (failed) and build-8813.log (passed)
for PaymentSettlementIT. In parallel, use the Explore agent to answer: where does
SettlementService read the ledger balance, and is that read on the same transaction
as the write in LedgerClient.post()? Report file:line for each claim.
```

(illustrative output, condensed) The log reader returns 18 lines. The failure is `AssertionError: expected balance 1200 but was 0` at `PaymentSettlementIT.java:88`, and in the failing run the assertion runs 40ms after the Kafka publish while in the passing run it runs 300ms after. The Explore agent reports that the balance is read through `LedgerQueryClient` at `SettlementService.java:142`, which goes through the read replica (`application-it.yml:31`), while the write goes to the primary.

The main window now holds two short, evidence-backed reports, about 2k tokens instead of 120k. The hypothesis is checkable: a read-your-writes race against a replica, the same failure as the `postgres-replication-lag` runbook in `code/data/`. The fix that follows is a test that asserts with a bounded poll on the primary, or a configuration that pins IT reads to the primary. It is not a `sleep`.

**Why the good version works:** the token-heavy work happened in windows that were then thrown away. The main context kept only conclusions with `file:line` evidence, which you or the agent can verify in one read each.

## Pitfalls

- **Pre-loading "for safety".** Detect it: for each pre-loaded section, check in your traces how often the agent's output references it. A section referenced in under 10% of sessions is a candidate for a pointer.
- **JIT for facts with no trigger.** Detect it: the agent keeps violating a rule that lives in a doc it never opens. Move a one-line version into the map.
- **Subagent summaries without evidence.** Detect it: the main agent re-reads the files the subagent already covered. Require `file:line` or quoted lines in the subagent's output format.
- **Parallel writer subagents.** Detect it: merge conflicts, or one subagent's edits overwritten by another's. Give each its own worktree (`isolation: worktree`) or make the helpers read-only.
- **Forgetting that subagents lack your conversation.** Detect it: the subagent violates a constraint you stated earlier in chat. Restate the constraint in the delegation prompt, or put it in CLAUDE.md, which subagents do load.
- **Cascading retrieval misses.** Detect it: the agent concludes that something "doesn't exist" after one grep. Prompt it, or build a tool, to try two or three name variants and to search tests and configs before concluding absence.

## In your day job

- Write one read-only subagent for your noisiest artifact (CI logs, `kubectl describe`, Terraform plans) with a 25-line output contract.
- Change one "read everything" tool in your agent into a filtered, paginated search tool, and measure tokens per session before and after.
- When an agent concludes "not implemented", check its trace for how many search variants it tried before you believe it.
