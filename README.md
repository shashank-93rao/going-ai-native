# going-ai-native

> A course for experienced engineers who want to move from "using AI with good prompts" to **engineering AI systems with rigor**: evals, hill-climbing, loops, harnesses, testing agentic systems, and steering agents so they do what you asked.

## Why this exists
I ([Shashank Rao](https://github.com/shashank-93rao)) put this course together for myself. I'd been using AI for a while, but mostly by writing detailed prompts. I wanted to learn to use it well: with evals, verification and loops, rather than by feel. It's published in case it helps someone else make the same shift.

It was researched and written with heavy help from AI agents, which seemed fitting. I've reviewed it, but treat it like any engineering doc: check the sources it cites, and run the code yourself.

You already have this reflex: *multithreaded code → race conditions → write tests that catch them.* This course builds the same reflex for AI:

*Agent output → which failure modes exist? → what check would catch them? → how do I use that check to steer, loop, or climb?*

## The thesis
**Autonomy should scale with verifiability.**

The parts of software work that agents automate fastest are the parts that can be checked automatically. The engineer's job moves from writing each diff to designing what the agent works inside: specs, oracles, evals, guardrails and loops. In short, the leash moved from the diff to the harness.

## Modules

| # | Module | Track |
|---|---|---|
| 00 | [Orientation: going AI-native](00-orientation/README.md) | Core |
| 01 | [LLMs for systems engineers](01-llms-for-systems-engineers/README.md) | Core |
| 02 | [Prompting as specification](02-prompting-as-specification/README.md) | Builder |
| 03 | [Context engineering, retrieval & memory](03-context-engineering/README.md) | Builder |
| 04 | [Agentic coding workflows](04-agentic-coding-workflows/README.md) | Core |
| 05 | [Tools, MCP, skills, hooks & execution environments](05-tools-mcp-skills-hooks/README.md) | Builder |
| 06 | [Agent architectures](06-agent-architectures/README.md) | Builder |
| 07 | [Loops](07-loops/README.md) | Core |
| 08 | [Harness engineering: agent-ready codebases](08-harness-engineering/README.md) | Builder |
| 09 | [Frameworks: LangChain, LangGraph, LangSmith & the landscape](09-frameworks-langchain-langgraph/README.md) | Builder |
| 10 | [Evals fundamentals](10-evals-fundamentals/README.md) | Core |
| 11 | [LLM-as-judge](11-llm-as-judge/README.md) | Core |
| 12 | [Hill-climbing](12-hill-climbing/README.md) | Core |
| 13 | [Testing agentic systems](13-testing-agentic-systems/README.md) | Core |
| 14 | [Steering & guardrails](14-steering-and-guardrails/README.md) | Core |
| 15 | [Observability & production](15-observability-and-production/README.md) | Production |
| 16 | [Security & containment](16-security-and-containment/README.md) | Production |
| 17 | [The AI-native engineer & team](17-ai-native-engineer-and-team/README.md) | Production |
| 99 | [Capstone (A: ops agent, B: LLM data pipeline)](99-capstone/README.md) | Production |

### Suggested paths
- **Core track** (about 60% of the value, do it first): 00 → 01 → 04 → 07 → 10 → 11 → 12 → 13 → 14
- **Builder track:** 02 → 03 → 05 → 06 → 08 → 09
- **Production track:** 15 → 16 → 17 → 99

Each module is a folder:
- `README.md`: why it matters, the distributed-systems anchor, learning goals and reading order
- numbered concept files, each with a worked example
- `examples.md`: realistic scenarios
- `exercises.md`: each with "done when" criteria
- `references.md`
- `code/`: runnable Python

## Setup
```bash
cd going-ai-native
uv venv --python 3.12 .venv && source .venv/bin/activate
uv pip install -e ".[frameworks]"      # or: pip install -e ".[frameworks]"
export ANTHROPIC_API_KEY=...            # optional; everything runs offline without it
./run_all_tests.sh                      # runs every module's tests offline
```

All model calls go through [`shared/ainative_kit`](shared/ainative_kit/llm.py). It provides:
- `get_client()`: uses the real API when a key is set
- `FakeClient`: deterministic and scripted, used by every test
- `RecordingClient` / `ReplayClient`: capture real traffic, then replay it offline
- `Tracer`: JSONL spans for error analysis

Set `AINATIVE_FAKE=1` to force offline mode.

## How this course was built
The curriculum comes from roughly 130 sources plus a survey of existing courses. The research notes are kept in [`research/`](research/), so every claim can be traced to a source:
- [Anthropic](research/anthropic.md)
- [Karpathy & OpenAI](research/openai-karpathy.md)
- [practitioners](research/practitioners.md)
- [course curricula](research/curricula.md)

The gap analysis, including the course's stance where sources disagree, is in [research/01-gap-analysis.md](research/01-gap-analysis.md). Claims marked *[UNVERIFIED]* in research are hedged or omitted in course text.

Authoring conventions are in [STYLE.md](STYLE.md).

## License
- **Code** (everything under `shared/`, each module's `code/`, and the top-level scripts) is under the [MIT License](LICENSE).
- **Course content** (the Markdown lessons, examples, exercises and research notes) is under [Creative Commons Attribution 4.0](LICENSE-CONTENT) (CC BY 4.0). You may share and adapt it, including commercially, as long as you give credit.

Quotes and figures from third-party sources belong to their authors and are cited in place. This course is not affiliated with Anthropic, OpenAI, LangChain or any other company it mentions.
