# Authoring Guide: going-ai-native

Every module writer follows this guide, so that 19 modules read as one course.

## The reader
- An **experienced backend or distributed-systems engineer** who likes to understand things in depth. They know race conditions, idempotency, consensus, backpressure, observability and SLOs cold.
- They have used AI tools, mostly with detailed prompts.
- They do **not** need programming, testing or systems concepts explained. They **do** need AI-specific mechanics explained precisely, and connected to things they already know.
- Never write down to the reader, and leave out hype. Write like a sharp senior colleague writing an internal engineering doc.

## The course thesis (keep it visible)
**Autonomy should scale with verifiability.** Every module comes back to it:
- What can be checked here?
- How do we make it checkable?
- How do we use that check to steer, loop or hill-climb?

## Module folder layout
```
NN-slug/
  README.md          # overview (template below)
  01-<concept>.md    # concept files, 3–7 per module, numbered in reading order
  ...
  examples.md        # 3–6 realistic scenarios
  exercises.md       # 4–8 hands-on exercises
  references.md      # sources, with what to take from each
  code/              # runnable Python plus tests (when the module has code; most do)
    README.md        # how to run each file
    *.py, test_*.py, data/*.jsonl ...
```

### README.md template
```markdown
# NN: Title
> One-sentence promise: what you can do after this module.

## Why this matters
(2–4 paragraphs. Concrete stakes. What goes wrong without this skill.)

## The distributed-systems anchor
(Map the core idea to something the reader knows, and say where the analogy breaks.)

## Learning goals
- [ ] Verb-led, checkable goals

## Reading order
1. [01-...](01-....md): one line
...
- [examples.md](examples.md), [exercises.md](exercises.md), [code/](code/)

## Prerequisites
(Module links.)

## Key takeaways
(5–8 bullets the reader could paste into a team wiki.)
```

### Concept file template
Each concept file is **800–2000 words** and follows this structure:
1. **The idea**: precise, 1–3 paragraphs.
2. **Why it matters**: a failure story, or a number from a source.
3. **How it works / how to do it**: mechanics, steps, decision rules.
4. **Worked example**: **required in every concept file**. Use real prompts, real code and concrete before/after output. Show the bad version, explain why it fails, then show the good version.
5. **Pitfalls**: specific mistakes, with how to detect each.
6. **In your day job**: 2–4 bullets on how he applies this on Monday.

## Examples are the point
The course brief says: *"Examples are very important. Practical examples. How to use a certain something topic. How it's relevant. How best to use it."*
- Prefer examples from **the reader's world**: Kafka consumers, idempotent APIs, a flaky integration test, an on-call incident, a schema migration, a rate limiter, a data pipeline, a Go/Java/Python service. Avoid toy chatbots unless the topic calls for one.
- Show **real artifacts**: the exact prompt, CLAUDE.md, SPEC.md, hook config, eval JSONL rows, judge rubric, trace snippet, terminal session.
- Model outputs you show without having run them must be labelled `(illustrative output)`. Never present an invented result as measured.
- Each `examples.md` scenario follows: *Situation → Naive approach and what happens → AI-native approach (step by step, with artifacts) → What to check.*

## Exercises
Each exercise has:
- Goal
- Steps
- **Done when**: objective, checkable criteria
- Stretch goal (optional)

Each exercise also carries a time estimate. Mix offline exercises (FakeClient, no key needed) with ones that use a real API or a real coding agent.

## Code rules
- Python 3.11+.
- **All model calls go through `ainative_kit`** (in `shared/ainative_kit/`). Use `from ainative_kit import FakeClient, get_client, text, tool, Tracer, RecordingClient, ReplayClient, Response, ToolCall`. Read `shared/ainative_kit/llm.py` before you write code, and do not reimplement a client.
- Tests use `FakeClient`, so they are **deterministic and offline**. The scripts `python foo.py` should use `get_client(fake=...)`, so they use the real API when `ANTHROPIC_API_KEY` is set and otherwise fall back to a fake.
- Name module-local files distinctively, e.g. `agent_loop.py` rather than `utils.py`. Tests are `test_*.py` in `code/` and import siblings directly (`from agent_loop import run`).
- Run tests with `.venv/bin/python -m pytest -q NN-slug/code` from the course root. They must pass. The venv already has `anthropic`, `pytest`, `hypothesis` and `langgraph`. Do not install anything else; if you truly need another package, say so in code/README.md and guard its import.
- Keep code readable over clever. Use type hints and short docstrings. Each file should be under about 300 lines.
- The default model is `ainative_kit.DEFAULT_MODEL` (`claude-sonnet-5-5`). Other current IDs are `claude-opus-5-5`, `claude-haiku-5-5` and `claude-fable-5-1`.
- Do **not** use assistant prefill. It errors on current Claude models.

## Sources and honesty
- Research notes live in `research/`: `anthropic.md`, `openai-karpathy.md`, `practitioners.md` and `curricula.md`. `01-gap-analysis.md` gives the course's stance on each controversy, and `02-final-topics.md` is the module scope.
- Cite inline with links: `([Anthropic, "Building effective agents"](url))`.
- Anything marked **[UNVERIFIED]** or **[secondary]** in research must either be re-verified with WebFetch or presented as "reported by X". Never present it as fact, and never quote it word for word.
- Mark your own synthesis: "*Course synthesis:*", or a callout like `> **Synthesis:** ...`.
- Where sources disagree, present both sides and then state the course's stance from `01-gap-analysis.md`.
- Facts about fast-moving tools (CLI flags, API params) should be checked against current docs with WebFetch when possible. When you can't check one, say what version or date it applies to.

## Voice and format
- Address the reader directly ("you").
- Keep paragraphs short. Use tables for comparisons, and fenced code blocks with language tags.
- Use mermaid diagrams where a loop or flow is easier to see than to read.
- Cross-link other modules with relative links (`[Module 12](../12-hill-climbing/README.md)`), and say what to find there.
- No emoji. No "In today's rapidly evolving landscape".

## Module directory names
00-orientation, 01-llms-for-systems-engineers, 02-prompting-as-specification, 03-context-engineering, 04-agentic-coding-workflows, 05-tools-mcp-skills-hooks, 06-agent-architectures, 07-loops, 08-harness-engineering, 09-frameworks-langchain-langgraph, 10-evals-fundamentals, 11-llm-as-judge, 12-hill-climbing, 13-testing-agentic-systems, 14-steering-and-guardrails, 15-observability-and-production, 16-security-and-containment, 17-ai-native-engineer-and-team, 18-rag-systems, 99-capstone
