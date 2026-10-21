# 01: Context as a finite, degrading budget

## The idea

Every model call is a pure function of the tokens you send: system prompt, tool definitions, context files, conversation history, tool results and the current message. **Context engineering** is choosing those tokens. Anthropic frames the goal as finding "the smallest set of high-signal tokens that maximize the likelihood of your desired outcome" ([Anthropic, "Effective context engineering for AI agents"](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)).

Two properties make this an engineering problem rather than a writing problem.

1. **The budget is finite and shared.** Tool schemas, the system prompt and the context file are charged on every call before the task even starts. Whatever is left has to hold the history, the tool results and the model's own output.
2. **The budget degrades as you spend it.** Anthropic calls this an "attention budget" and names the effect **context rot**: as the token count grows, "the model's ability to accurately recall information from that context decreases." It is a gradient, not a cliff. Quality does not hold steady until the limit and then fall off; it slides as the window fills.

So the question is never "does it fit?" It is "is each token worth what it costs in attention, latency and money?"

## Why it matters

The evidence is consistent across sources:

- Chroma tested 18 models (GPT-4.1, Claude 4, Gemini 2.5, Qwen3 and others) and found that "performance grows increasingly unreliable as input length grows", even on simple retrieval tasks. "Even a single distractor reduces performance relative to the baseline", and the damage from distractors grows with input length ([Chroma, "Context Rot", July 2025](https://www.trychroma.com/research/context-rot)).
- Drew Breunig sorts long-context failures into four types, which work well as a diagnostic vocabulary ([Breunig, "How Long Contexts Fail"](https://www.dbreunig.com/2025/06/22/how-contexts-fail-and-how-to-fix-them.html)):
  - **Poisoning**: a hallucinated fact enters the context and keeps getting referenced.
  - **Distraction**: the history gets so long that the model starts repeating past actions instead of reasoning afresh.
  - **Confusion**: irrelevant material, such as too many tools, degrades the response.
  - **Clash**: parts of the context contradict each other.
- Anthropic reports that tool definitions alone can consume 55k to 134k tokens before the conversation starts in setups with many MCP servers ([Anthropic, "Introducing advanced tool use"](https://www.anthropic.com/engineering/advanced-tool-use)).
- Practitioners converge on keeping utilization well below the limit. Dex Horthy's workflow aims at "keeping utilization in the 40%-60% range" ([HumanLayer, ACE-FCA](https://github.com/humanlayer/advanced-context-engineering-for-coding-agents/blob/main/ace-fca.md)). Geoffrey Huntley: "The more you allocate to a context window, the worse the performance of the context window will be" ([Huntley, "how to build a coding agent"](https://ghuntley.com/agent/)). Treat those as starting heuristics, not laws: the right number depends on the model and the task, and you only learn it by measuring on your own evals.

A failure story you'll recognize. An incident agent gets a 2,000-line log dump in turn 3. In turn 40 it is asked whether it may reset the consumer offset. The instruction "never reset offsets to latest" is still in the window, at token 6k of 150k, and the agent resets the offsets anyway. Nothing was evicted. The constraint was crowded out.

## How it works / how to do it

### Step 1: Take an inventory

Before you optimize anything, measure where the tokens go. In Claude Code, `/context` shows the breakdown, including which memory files loaded ([Claude Code docs, memory](https://code.claude.com/docs/en/memory)). For your own harness, log token counts per section on every call (the API's `usage` fields, or a token-counting call) and add them to your traces (see [Module 15](../15-observability-and-production/README.md)).

A typical inventory for a coding or ops agent:

| Section | Charged | Typical failure |
|---|---|---|
| System prompt | Every call | Too long, written at the wrong "altitude" |
| Tool definitions | Every call | Too many overlapping tools, which causes confusion |
| Context files (CLAUDE.md/AGENTS.md) | Every call | Bloat, stale rules, contradictions (clash) |
| Conversation history | Grows each turn | Old corrections and dead ends (distraction, poisoning) |
| Tool results | Grows each turn | Raw logs and full file dumps: the largest single source of bloat |
| Retrieved docs | Per call | Low-precision retrieval brings in distractors |
| Output reserve | Per call | Forgotten, so the output gets truncated |

### Step 2: Apply the admission rule

For each candidate piece of context, ask four questions:

1. **Does every turn need it?** If yes, it may be pre-loaded (system prompt, context file). If not, give a reference and a way to fetch it (see [02](02-just-in-time-and-isolation.md)).
2. **Would removing it cause a mistake?** This is the CLAUDE.md test from Anthropic's best practices: "Would removing this cause Claude to make mistakes?" ([Claude Code best practices](https://code.claude.com/docs/en/best-practices)). If not, cut it.
3. **Can a tool enforce it instead?** A formatting rule belongs in a linter, and a "never touch `migrations/`" rule belongs in a hook. Enforcement outside the window costs zero tokens and does not rot. This is the course stance from [Module 14](../14-steering-and-guardrails/README.md): give checks, not instructions.
4. **Is it the smallest form that works?** The last 50 lines of a log, not 2,000. A summary of a 30-file search, not the 30 files. A file path, not the file.

### What belongs in the window and what doesn't

| Belongs | Doesn't belong |
|---|---|
| The goal and the "done when" check | The full history of how the goal changed |
| Hard constraints, stated once, near the top | The same constraint restated five times in caps |
| Commands to build, test and verify | Prose explaining what a test framework is |
| Pointers: paths, ids, queries, doc names | The docs themselves, "just in case" |
| The tail of the relevant log, filtered | Raw logs and full stack traces from three turns ago |
| A few canonical examples | A long list of edge cases ([Anthropic](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) recommends diverse canonical examples over exhaustive edge cases) |
| Tools needed for this task | Every tool from every MCP server you have installed |
| Decisions and their reasons | Failed attempts in full (keep one line on why each failed) |

### Step 3: Enforce a budget in code

The harness, not the model, should decide what fits. `code/context_budget.py` implements this. Sections carry a priority, a `required` flag, a `truncatable` flag and which end to keep. Selection is by priority. Required sections that don't fit raise an error instead of being dropped silently: a missing spec is an outage, not a degradation.

```python
from context_budget import Section, assemble

sections = [
    Section("role", ROLE, required=True, stable=True),
    Section("tool_contract", TOOLS_DOC, required=True, stable=True),
    Section("alert", alert_text, required=True),
    Section("recent_logs", logs, priority=10, truncatable=True, keep="tail"),
    Section("prior_incidents", history, priority=30, truncatable=True),
    Section("style_guide", STYLE, priority=90),
]
prompt = assemble(sections, budget=900, reserve_output=200)
```

## Worked example: an incident-triage prompt

**The bad version.** The first draft of a billing on-call agent built its prompt like this:

```python
prompt = "\n\n".join([
    SYSTEM_PROMPT,                         # 1,900 tokens, including a style guide
    open("CLAUDE.md").read(),              # 600 lines, ~7,500 tokens
    "\n".join(open(p).read() for p in glob("runbooks/*.md")),  # every runbook, ~40k
    subprocess.check_output(["kubectl", "logs", "deploy/invoice-consumer", "--since=1h"]).decode(),  # ~60k
    f"ALERT: {alert}",
])
```

It "worked" in demos. In production it had three distinct failures:

- The one relevant runbook section was one of 40 sections, and a near-duplicate section (Postgres *replication* lag next to Kafka *consumer* lag) was a textbook distractor. The agent mixed commands from both.
- The instructions sat at the top and the alert sat at the bottom, with about 100k tokens of logs and runbooks in between. Every rule the agent needed was as far as possible from the question it was answering.
- Every call re-sent ~110k tokens of input. Latency and cost scaled with log volume, not with problem difficulty.

**The good version.** Budget the prompt, keep the stable parts first, keep the tail of the logs, and fetch runbooks with a tool instead of pre-loading them:

```text
$ python code/context_budget.py
budget=2000
tokens 1771/2000  prefix 58
  included:  role, tool_contract, alert, recent_logs, prior_incidents, style_guide
  truncated: -
  dropped:   -

budget=900
tokens 698/900  prefix 58
  included:  role, tool_contract, alert, recent_logs
  truncated: recent_logs
  dropped:   prior_incidents, style_guide
```

That is real output from the course code. When the budget tightens, the style guide (priority 90) goes first, prior incidents next, and the logs are cut to their **tail**, because the most recent lines are the relevant ones. The role, tool contract and alert are never touched. The runbooks are no longer in the prompt at all. The agent calls `search_runbooks` and receives about 5 chunks, which is the subject of [06](06-retrieval-agentic-search-vs-rag.md).

**What to check:** the budgeter's report goes into the trace on every call. If `dropped` keeps containing `prior_incidents` during real incidents, your budget is too tight or your logs are too verbose. That is a measurable signal, not a vibe.

## Pitfalls

- **Using "fits in the window" as the criterion.** Detect it: plot task success against input tokens from your traces. If success falls as tokens rise, you are paying context rot.
- **Instructions that should be enforcement.** Detect it: grep your context file for "never", "always" and "do not". Each hit is a candidate lint rule, hook or permission setting.
- **Unbounded tool output.** One `cat` of a 5MB log can poison a session. Detect it: alert on any single tool result above N tokens. Claude Code caps tool responses by default (Anthropic's tool-writing post cites 25k tokens; [Anthropic, "Writing effective tools for agents"](https://www.anthropic.com/engineering/writing-tools-for-agents)), and your own harness should cap them too.
- **Tool sprawl.** Anthropic's test: "If a human engineer can't definitively say which tool should be used in a given situation," the agent can't either. Detect it: count tools and look for pairs with overlapping descriptions. See [Module 05](../05-tools-mcp-skills-hooks/README.md).
- **Contradictions across layers** (system prompt, context file, skill, user). Detect it: when the agent's behaviour flips between runs on the same input, look for two instructions that disagree. See [Module 02](../02-prompting-as-specification/README.md) on the instruction hierarchy.
- **Forgetting the output reserve.** Detect it: `stop_reason == "max_tokens"` in traces.

## In your day job

- Run `/context` (or log per-section token counts) on your longest agent session this week. Write down the top three consumers.
- For your team's agent, write the admission rule from Step 2 into the PR template for prompt and context-file changes.
- Cap every tool's output in your harness, and keep the tail for logs and the head for files.
- When an agent "forgets" something, check first whether it was crowded out, before you add another instruction to the prompt.
