"""Trace and evaluate the triage agent with LangSmith (optional), with a local fallback.

LangSmith is OPTIONAL. Everything below runs offline through `evaluate_locally`, which
uses the same evaluator signature LangSmith uses: (inputs, outputs, reference_outputs).
When LANGSMITH_API_KEY is set, `run_langsmith()` uploads the dataset and runs a real
experiment so you can compare raw vs LangGraph side by side in the UI.

    export LANGSMITH_TRACING=true
    export LANGSMITH_API_KEY=...            # from smith.langchain.com
    export LANGSMITH_PROJECT=oncall-triage  # optional; groups traces
    python langsmith_eval.py                # local scores; plus a LangSmith experiment if keyed
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable

from ainative_kit import FakeClient, LLMClient, get_client

import langgraph_agent as lg
import raw_agent
from triage_world import OpsWorld, outcome_of, scripted_policy

try:  # langsmith is installed in the course venv, but keep the module importable without it
    from langsmith import traceable
except ImportError:  # pragma: no cover
    def traceable(*dargs, **dkwargs):  # type: ignore[no-redef]
        if dargs and callable(dargs[0]):
            return dargs[0]
        return lambda f: f

DATA = Path(__file__).parent / "data" / "triage_cases.jsonl"
DATASET_NAME = "oncall-triage-v1"


class TracedClient:
    """Wrap any ainative_kit client so each model call is an 'llm' run nested in the trace.

    LangGraph only auto-traces LangChain chat models; custom clients need this.
    """

    def __init__(self, inner: LLMClient):
        self.inner = inner

    @traceable(run_type="llm", name="claude.complete")
    def complete(self, messages, **kwargs):
        return self.inner.complete(messages, **kwargs)


def _client() -> LLMClient:
    return TracedClient(get_client(fake=FakeClient(scripted_policy)))


@traceable(run_type="chain", name="triage_raw")
def raw_target(inputs: dict[str, Any]) -> dict[str, Any]:
    world = OpsWorld()
    r = raw_agent.run(inputs["alert_id"], _client(), world)
    return {"final_text": r.final_text, "tools": r.tool_sequence, "turns": r.turns, "restarts": world.restarts}


@traceable(run_type="chain", name="triage_langgraph")
def langgraph_target(inputs: dict[str, Any]) -> dict[str, Any]:
    """Auto-accepts every interrupt so the eval measures the agent's decisions, not the human's."""
    world = OpsWorld()
    graph = lg.build_graph(_client(), world, checkpointer=lg.MemorySaver())
    tid = f"eval-{inputs['alert_id']}"
    out = lg.start(graph, inputs["alert_id"], tid)
    while lg.pending_interrupt(out):
        out = lg.resume(graph, tid, {"type": "accept"})
    return {"final_text": out["final_text"], "tools": out["tool_sequence"], "turns": out["turns"],
            "restarts": world.restarts}


# --- evaluators: same signature LangSmith passes (it inspects argument names) -----------------

def correct_action(outputs: dict, reference_outputs: dict) -> dict:
    return {"key": "correct_action", "score": outcome_of(outputs["final_text"]) == reference_outputs["action"]}


def no_forbidden_tools(outputs: dict, reference_outputs: dict) -> dict:
    bad = set(outputs["tools"]) & set(reference_outputs["must_not_call"])
    return {"key": "no_forbidden_tools", "score": not bad, "comment": f"called {sorted(bad)}" if bad else ""}


def within_turn_budget(outputs: dict) -> dict:
    return {"key": "within_turn_budget", "score": outputs["turns"] <= 4}


def restart_precision(outputs: list[dict], reference_outputs: list[dict]) -> dict:
    """Summary evaluator: of the restarts the agent did, how many were warranted?"""
    did = [ref["action"] == "restart" for out, ref in zip(outputs, reference_outputs) if out["restarts"]]
    return {"key": "restart_precision", "score": (sum(did) / len(did)) if did else 1.0}


EVALUATORS = [correct_action, no_forbidden_tools, within_turn_budget]


def load_examples(path: Path = DATA) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def evaluate_locally(target: Callable[[dict], dict], examples: list[dict] | None = None) -> dict[str, Any]:
    """A 30-line stand-in for langsmith.evaluate: run target, apply evaluators, aggregate."""
    examples = examples or load_examples()
    rows, outs, refs = [], [], []
    for ex in examples:
        out = target(ex["inputs"])
        scores = {}
        for ev in EVALUATORS:
            kwargs = {"outputs": out, "reference_outputs": ex["outputs"], "inputs": ex["inputs"]}
            names = ev.__code__.co_varnames[: ev.__code__.co_argcount]
            res = ev(**{k: v for k, v in kwargs.items() if k in names})
            scores[res["key"]] = res["score"]
        rows.append({"alert_id": ex["inputs"]["alert_id"], **scores})
        outs.append(out)
        refs.append(ex["outputs"])
    summary = {k: sum(r[k] for r in rows) / len(rows) for k in rows[0] if k != "alert_id"}
    summary.update({restart_precision(outs, refs)["key"]: restart_precision(outs, refs)["score"]})
    return {"rows": rows, "summary": summary}


def run_langsmith() -> None:  # pragma: no cover - needs network and a key
    """Upload the dataset (once) and run one experiment per implementation."""
    from langsmith import Client, evaluate

    client = Client()
    if not client.has_dataset(dataset_name=DATASET_NAME):
        ds = client.create_dataset(dataset_name=DATASET_NAME, description="On-call triage golden set")
        client.create_examples(dataset_id=ds.id, examples=load_examples())
    names = []
    for prefix, target in [("raw-loop", raw_target), ("langgraph", langgraph_target)]:
        res = evaluate(target, data=DATASET_NAME, evaluators=EVALUATORS,
                       summary_evaluators=[restart_precision], experiment_prefix=prefix,
                       metadata={"impl": prefix, "model": os.environ.get("AINATIVE_MODEL", "claude-sonnet-5-5")})
        names.append(res.experiment_name)
    print("experiments:", names, "(compare them in the LangSmith UI, or run a pairwise evaluate on the tuple)")


if __name__ == "__main__":
    for name, target in [("raw", raw_target), ("langgraph", langgraph_target)]:
        print(name, json.dumps(evaluate_locally(target)["summary"]))
    if os.environ.get("LANGSMITH_API_KEY"):
        run_langsmith()
    else:
        print("LANGSMITH_API_KEY not set: skipped upload. Local scores above use the same evaluators.")
