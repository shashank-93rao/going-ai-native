# 05: LangSmith: tracing, datasets, evaluators, experiments, pairwise, annotation queues, online evals

## The idea

LangSmith is a tracing and evaluation platform. It is framework-agnostic: you can trace a raw loop with `@traceable` as easily as a LangGraph graph. Its concepts line up one-to-one with the evals modules of this course, and LangChain Academy organises them as the **Agent Development Lifecycle (ADLC)**: Build, Test, Deploy, Monitor, then close the loop.

| LangSmith concept | What it is | Course module |
|---|---|---|
| **Trace / run** | A tree of runs (spans) with `run_type` (`llm`, `chain`, `tool`, `retriever`, ...), inputs, outputs, latency, tokens, cost | [10](../10-evals-fundamentals/README.md), [15](../15-observability-and-production/README.md) |
| **Thread** | Traces grouped into one conversation by a shared session or thread id | 15 |
| **Dataset / example** | `{inputs, outputs (reference), metadata}` rows | 10 |
| **Evaluator** | A function `(inputs, outputs, reference_outputs) -> score`, either code or LLM-as-judge | 10, [11](../11-llm-as-judge/README.md) |
| **Summary evaluator** | A function over the whole experiment (precision, recall, pass rate) | 10 |
| **Experiment** | One run of a target over a dataset, scored by the evaluators | [12](../12-hill-climbing/README.md) |
| **Pairwise experiment** | Two experiments compared by a comparative evaluator, with `randomize_order` | 11, 12 |
| **Annotation queue** | A human review workflow over runs or threads with a rubric, optionally pairwise | 11 |
| **Online evaluator** | An evaluator that runs on a filtered, sampled slice of production traces | 15 |
| **Automation** | A rule: filter traces, then add them to a dataset or queue, or alert | 15 |

The Academy courses that teach this are "Introduction to Agent Observability & Evaluations" (Tracing Basics, Types of Runs, Datasets, Evaluators, Experiments, Pairwise, Summary Evaluators, Annotation Queues, Online Evaluation, Automations), "Quickstart: LangSmith Essentials", "Building Reliable Agents with LangSmith" (code-based, LLM-as-judge and pairwise evals, Insights, online evals), "Monitoring Production Agents" (cost, sentiment, A/B testing, alerts), and "Autonomous Agent Improvement with LangSmith Engine", which automates the find-fix-test loop.

## Why it matters

An agent fails in its trajectory, not only in its final answer. The triage agent can give a correct `DIAGNOSIS:` line and still have called `restart_service` on a disk-full broker. If you only log the final text, you miss that. Tracing first, then error analysis over real traces, then evals for the failures you found: that is the order from [Module 10](../10-evals-fundamentals/README.md) (Hamel Husain and Shreya Shankar's method), and LangSmith is one implementation of the tooling.

The platform question is a "buy vs build" one. `ainative_kit.Tracer` writes JSONL spans, which is enough for one engineer reading 30 traces. Once three people triage failures, or production runs thousands of traces a day, you need search, filters, side-by-side experiment diffs, a review queue and sampling-based online scoring. That is a product, not a weekend project. The course's position ([`research/anthropic.md`](../research/anthropic.md) #23, Anthropic's evals post): LangSmith, Braintrust, Langfuse and Arize are all reasonable. Pick one quickly and spend your effort on tasks and graders.

## How it works

### 1. Tracing without LangChain

Set the environment, then decorate. LangGraph auto-traces LangChain chat models only. A custom client such as `ainative_kit` needs its own `llm` run:

```bash
export LANGSMITH_TRACING=true
export LANGSMITH_API_KEY=lsv2_...
export LANGSMITH_PROJECT=oncall-triage                         # optional: groups traces
# export LANGSMITH_ENDPOINT=https://eu.api.smith.langchain.com # non-US accounts only
```

```python
from langsmith import traceable

class TracedClient:
    def __init__(self, inner): self.inner = inner

    @traceable(run_type="llm", name="claude.complete")
    def complete(self, messages, **kwargs):
        return self.inner.complete(messages, **kwargs)

@traceable(run_type="chain", name="triage_raw")
def raw_target(inputs: dict) -> dict:
    world = OpsWorld()
    r = raw_agent.run(inputs["alert_id"], TracedClient(get_client(...)), world)
    return {"final_text": r.final_text, "tools": r.tool_sequence, "turns": r.turns, "restarts": world.restarts}
```

That is [`code/langsmith_eval.py`](code/langsmith_eval.py). With `LANGSMITH_TRACING` unset, `@traceable` is a pass-through, which is why the tests can import it offline.

### 2. Dataset

[`code/data/triage_cases.jsonl`](code/data/triage_cases.jsonl) is in LangSmith's example shape:

```json
{"inputs": {"alert_id": "ALERT-4212"}, "outputs": {"action": "recommend_owner", "must_not_call": ["restart_service"]}, "metadata": {"why": "capacity: restart would not free disk and drops ISR"}}
```

Note the **negative constraint** (`must_not_call`). For agents with side effects, "did not do the dangerous thing" is often the most important label.

### 3. Evaluators

LangSmith inspects an evaluator's argument names and passes `inputs`, `outputs`, `reference_outputs`, `run` or `example` as requested:

```python
def correct_action(outputs: dict, reference_outputs: dict) -> dict:
    return {"key": "correct_action", "score": outcome_of(outputs["final_text"]) == reference_outputs["action"]}

def no_forbidden_tools(outputs: dict, reference_outputs: dict) -> dict:
    bad = set(outputs["tools"]) & set(reference_outputs["must_not_call"])
    return {"key": "no_forbidden_tools", "score": not bad, "comment": f"called {sorted(bad)}" if bad else ""}

def restart_precision(outputs: list[dict], reference_outputs: list[dict]) -> dict:   # summary evaluator
    did = [ref["action"] == "restart" for out, ref in zip(outputs, reference_outputs) if out["restarts"]]
    return {"key": "restart_precision", "score": (sum(did) / len(did)) if did else 1.0}
```

These are **code evaluators**: deterministic, cheap, and they should be most of your suite. Use an LLM-as-judge evaluator only for what code cannot check (for example "is the DIAGNOSIS line supported by the log lines?"), and calibrate it first ([Module 11](../11-llm-as-judge/README.md)).

### 4. Experiments

```python
from langsmith import Client, evaluate

client = Client()
if not client.has_dataset(dataset_name="oncall-triage-v1"):
    ds = client.create_dataset(dataset_name="oncall-triage-v1")
    client.create_examples(dataset_id=ds.id, examples=load_examples())

evaluate(raw_target, data="oncall-triage-v1", evaluators=[correct_action, no_forbidden_tools],
         summary_evaluators=[restart_precision], experiment_prefix="raw-loop",
         metadata={"impl": "raw", "model": "claude-sonnet-5-5"})
```

`metadata` keys such as model or prompt version become columns in the experiment comparison view. Record everything you might later want to slice by, including the harness version ([Module 12](../12-hill-climbing/README.md) treats model, effort and harness as separate dimensions).

### 5. Pairwise experiments

When there is no reference answer ("which diagnosis is more useful to the on-call?"), compare two experiments directly:

```python
evaluate(("raw-loop-1a2b", "langgraph-3c4d"), evaluators=[ranked_preference], randomize_order=True)
```

A comparative evaluator receives `outputs` as a two-item list and returns per-run scores. Use a feedback key prefixed `pairwise_` or `ranked_`. `randomize_order=True` shuffles position per example to reduce position bias. It does not remove the bias, so measure it ([Module 11](../11-llm-as-judge/README.md)).

### 6. Annotation queues

Queues give human reviewers a rubric over runs or threads. **Single-run** queues show one item at a time. **Pairwise** queues show two experiments side by side. Automation rules can route matching production traces into a queue: for example, every trace where `restart_service` was called, or every thread with negative user feedback. Reviewers can edit a run's inputs and outputs and click "Add to Dataset", which is how production failures become regression examples. These human labels are also what you calibrate an LLM judge against.

### 7. Online evaluators and automations

Online evaluators score production traces in near real time. **Filters** choose which runs qualify (by tool call, metadata, feedback or another evaluator's score), and a **sampling rate** (for example 0.1 for 10%) bounds the cost. For the triage agent, sample every `restart_service` trace at 100% and everything else at 5%.

## Worked example: local first, platform second

**Bad version.** Point the eval at the platform before you have a local harness. Every test run now needs network and a key, CI is flaky, and nobody can reproduce a score offline. Worse, `langsmith.evaluate(..., upload_results=False)` looks offline but still calls the API: in the course venv, with an unreachable endpoint, it logged `Failed to get info from http://127.0.0.1:9: LangSmithConnectionError(...)`. It completed anyway, but a test that depends on it would depend on the network.

**Good version.** Keep a 30-line `evaluate_locally` with the **same evaluator signature**, run it in CI, and upload only when a key is present:

```text
$ AINATIVE_FAKE=1 python langsmith_eval.py
raw {"correct_action": 1.0, "no_forbidden_tools": 1.0, "within_turn_budget": 1.0, "restart_precision": 1.0}
langgraph {"correct_action": 1.0, "no_forbidden_tools": 1.0, "within_turn_budget": 1.0, "restart_precision": 1.0}
LANGSMITH_API_KEY not set: skipped upload. Local scores above use the same evaluators.
```

That is real output, with the scripted model, so all 1.0 is expected. It proves the harness, not the agent. Swap in a real model and the numbers start to mean something. `test_evaluators_catch_a_bad_restart` proves that the evaluators can fail, which is the "prove it can fail" rule from [Module 07](../07-loops/README.md):

```python
bad = {"final_text": "DIAGNOSIS: disk\nACTION: restarted kafka-broker-3", "tools": ["restart_service"], ...}
assert le.no_forbidden_tools(bad, ref)["score"] is False
assert le.restart_precision([bad], [ref])["score"] == 0.0
```

## Pitfalls

- **Tracing sensitive data by default.** Traces contain full prompts and tool outputs: log lines, customer ids, tokens. Detection: grep a trace export for an email address. Fix: redact in the wrapper, or use the SDK's input and output hiding options, before enabling tracing on production logs.
- **Evaluators that cannot fail.** Every evaluator needs a test with a known-bad output.
- **Only final-answer evals.** Add trajectory checks (`must_not_call`, turn budget) for agents with side effects.
- **Comparing experiments run on different dataset versions.** Pin the dataset version or tag in experiment metadata.
- **Treating online-eval scores as ground truth.** They come from a judge on a sample. Calibrate the judge, and watch for drift ([Module 11](../11-llm-as-judge/README.md)).
- **Automated improvement before manual.** LangSmith Engine (find errors in traces, propose a fix, test it, monitor it) automates the [Module 12](../12-hill-climbing/README.md) loop. Run that loop by hand first, so you can tell when the automation overfits.

## In your day job

- Wrap your model client with one `@traceable(run_type="llm")` adapter, and set `LANGSMITH_PROJECT` per service and environment.
- Keep evaluators as plain functions in your repo with unit tests. LangSmith runs them, but it does not own them.
- Add an automation: every trace that called a mutating tool goes to an annotation queue reviewed by the owning team. Reviewed items flow into the regression dataset.
- Gate merges on a local experiment over the golden set ([Module 12](../12-hill-climbing/README.md)). Upload to LangSmith for the side-by-side view, not for the gate.
