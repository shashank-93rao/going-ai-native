# Code: one triage agent, three orchestrations

Written against **langgraph 1.2.16**, langgraph-checkpoint 4.3.0 and langsmith 0.14.11 (the versions in the course venv on 2026-10-19). `langchain` and `langchain-anthropic` are **not** installed, so LangGraph nodes call `ainative_kit` clients directly. That is deliberate: it shows LangGraph is an orchestration runtime, not a model wrapper.

| File | What it is |
|---|---|
| `triage_world.py` | The shared world: 3 tool schemas, a fake ops backend (`OpsWorld`, idempotent by `tool_use_id`), the system prompt, and `scripted_policy`, a deterministic stand-in for the model |
| `raw_agent.py` | The agent as a plain loop over `ainative_kit`. Turn budget, approval callback, `Tracer` spans |
| `langgraph_agent.py` | The same agent as a `StateGraph` with reducers, conditional edges, a `MemorySaver` checkpointer, `interrupt()` before `restart_service`, `Command(resume=...)`, time travel and an `InMemoryStore` |
| `langsmith_eval.py` | `@traceable` instrumentation, a 3-row dataset, code evaluators, a summary evaluator, a local `evaluate_locally`, and `run_langsmith()` for a real experiment when a key is set |
| `agents_sdk_sketch.md` | Claude Agent SDK and OpenAI Agents SDK versions, annotated (not run) |
| `data/triage_cases.jsonl` | The eval dataset in LangSmith's `{inputs, outputs, metadata}` shape |
| `test_parity.py` | Raw and LangGraph produce the same answer, the same tool sequence, the same side effects and **byte-identical model requests** |
| `test_langgraph_durability.py` | Interrupt, resume from a fresh graph, reject/edit, thread isolation, crash recovery, time-travel fork, idempotent replay, Store semantics, streaming |
| `test_langsmith_eval.py` | Both implementations score identically. Evaluators catch a bad restart |

## Run

From the course root:

```bash
.venv/bin/python -m pytest -q 09-frameworks-langchain-langgraph/code     # offline, no keys

cd 09-frameworks-langchain-langgraph/code
export PYTHONPATH=../../shared
AINATIVE_FAKE=1 ../../.venv/bin/python raw_agent.py ALERT-4211      # asks y/N at the terminal
AINATIVE_FAKE=1 ../../.venv/bin/python langgraph_agent.py           # pause, resume, fork, stream
AINATIVE_FAKE=1 ../../.venv/bin/python langsmith_eval.py            # local scores for both impls
```

Drop `AINATIVE_FAKE=1` and set `ANTHROPIC_API_KEY` to use a real model. The scripted policy then is not used, so outcomes can differ from the tests. That difference is what the eval is for.

## LangSmith (optional)

```bash
export LANGSMITH_TRACING=true
export LANGSMITH_API_KEY=lsv2_...
export LANGSMITH_PROJECT=oncall-triage        # optional
# export LANGSMITH_ENDPOINT=https://eu.api.smith.langchain.com   # non-US accounts only
../../.venv/bin/python langsmith_eval.py
```

This uploads `oncall-triage-v1` once and runs two experiments, `raw-loop-*` and `langgraph-*`. The tests unset all LangSmith variables. Note that `langsmith.evaluate(..., upload_results=False)` still tries to reach the API (it calls `GET /info`), which is why the tests use `evaluate_locally` instead.

## Not covered by the code

- `langchain.agents.create_agent`, middleware and `deepagents` need packages that are not installed. They appear in the concept files as annotated snippets checked against docs.langchain.com.
- A durable checkpointer. `MemorySaver` (an alias of `InMemorySaver`) lives in process memory. For real cross-process resume use `SqliteSaver` (`langgraph-checkpoint-sqlite`) or `PostgresSaver` (`langgraph-checkpoint-postgres`). Both are drop-in replacements for the `checkpointer=` argument.
