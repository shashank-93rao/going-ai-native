"""The same on-call triage agent as a LangGraph StateGraph (written against langgraph 1.2.x).

What the framework adds over raw_agent.py:
  * a checkpoint after every super-step (MemorySaver here; SqliteSaver/PostgresSaver in prod)
  * threads: each alert is a thread_id, resumable from any process sharing the checkpointer
  * interrupt(): pause before the risky tool, persist, and resume later with Command(resume=...)
  * time travel: list checkpoints, fork from one, and replay a different decision
  * a cross-thread Store for long-term memory (prior resolutions)

Nodes call ainative_kit clients (no langchain-anthropic), so tests run offline with FakeClient.

    python langgraph_agent.py            # pause -> resume -> stream -> time-travel demo
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, Literal, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from langgraph.store.memory import InMemoryStore
from langgraph.types import Command, interrupt

from ainative_kit import FakeClient, LLMClient, get_client

from triage_world import RISKY_TOOLS, SYSTEM_PROMPT, TOOL_SCHEMAS, OpsWorld, scripted_policy

MEMORY_NS = ("triage_memory",)


def merge_dicts(left: dict, right: dict) -> dict:
    """Reducer: approvals from several interrupts merge instead of overwriting."""
    return {**left, **right}


class TriageState(TypedDict, total=False):
    alert_id: str
    messages: Annotated[list[dict[str, Any]], operator.add]   # append-only, like an event log
    tool_sequence: Annotated[list[str], operator.add]
    approvals: Annotated[dict[str, dict[str, Any]], merge_dicts]  # tool_use_id -> human decision
    turns: int
    final_text: str


def _pending_calls(state: TriageState) -> list[dict[str, Any]]:
    last = state["messages"][-1]
    if last["role"] != "assistant":
        return []
    return [b for b in last["content"] if b["type"] == "tool_use"]


def build_graph(client: LLMClient, world: OpsWorld, *, checkpointer=None, store=None, max_turns: int = 8):
    """Compile the triage graph. `client` and `world` are closed over, so state stays plain JSON."""

    def model(state: TriageState, runtime: Runtime) -> dict[str, Any]:
        system = SYSTEM_PROMPT
        if runtime.store is not None:  # long-term memory: what we concluded on earlier alerts
            prior = runtime.store.search(MEMORY_NS, limit=5)
            if prior:
                system += "\n\nPrior resolutions:\n" + "\n".join(f"- {i.key}: {i.value['action']}" for i in prior)
        resp = client.complete(state["messages"], system=system, tools=TOOL_SCHEMAS)
        update: dict[str, Any] = {"messages": [resp.to_assistant_message()], "turns": state.get("turns", 0) + 1}
        if not resp.tool_calls:
            update["final_text"] = resp.text
            if runtime.store is not None:
                action = next((ln for ln in resp.text.splitlines() if ln.startswith("ACTION:")), resp.text)
                runtime.store.put(MEMORY_NS, state["alert_id"], {"action": action})
        return update

    def approve(state: TriageState) -> dict[str, Any]:
        """Human gate. On resume, this node re-runs from the top, so it must stay side-effect free."""
        decisions: dict[str, dict[str, Any]] = {}
        for call in _pending_calls(state):
            if call["name"] not in RISKY_TOOLS:
                continue
            decision = interrupt({  # Agent-Inbox-style HumanInterrupt payload
                "action_request": {"action": call["name"], "args": call["input"]},
                "config": {"allow_accept": True, "allow_edit": True, "allow_respond": True, "allow_ignore": False},
                "description": f"Agent wants to run {call['name']} on {call['input'].get('service')}: "
                               f"{call['input'].get('reason', '')}",
                "tool_use_id": call["id"],
            })
            decisions[call["id"]] = decision
        return {"approvals": decisions}

    def tools(state: TriageState) -> dict[str, Any]:
        """The only node with side effects. Runs once per super-step; checkpointed after."""
        results, used = [], []
        for call in _pending_calls(state):
            args = call["input"]
            if call["name"] in RISKY_TOOLS:
                d = state.get("approvals", {}).get(call["id"], {"type": "response", "args": "no decision"})
                if d["type"] == "edit":
                    args = d["args"]
                elif d["type"] != "accept":
                    results.append({"type": "tool_result", "tool_use_id": call["id"], "is_error": True,
                                    "content": f"rejected by human: {d.get('args', '')}"})
                    continue
            results.append({"type": "tool_result", "tool_use_id": call["id"],
                            "content": world.execute(call["name"], args, call["id"])})
            used.append(call["name"])
        return {"messages": [{"role": "user", "content": results}], "tool_sequence": used}

    def route_after_model(state: TriageState) -> Literal["approve", "tools", "__end__"]:
        calls = _pending_calls(state)
        if not calls or state.get("turns", 0) >= max_turns:
            return END
        return "approve" if any(c["name"] in RISKY_TOOLS for c in calls) else "tools"

    g = StateGraph(TriageState)
    g.add_node("model", model)
    g.add_node("approve", approve)
    g.add_node("tools", tools)
    g.add_edge(START, "model")
    g.add_conditional_edges("model", route_after_model, ["approve", "tools", END])
    g.add_edge("approve", "tools")
    g.add_edge("tools", "model")
    return g.compile(checkpointer=checkpointer, store=store)


# --- thin helpers the tests and the demo share --------------------------------------------

def thread(thread_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": thread_id}}


def start(graph, alert_id: str, thread_id: str) -> dict[str, Any]:
    return graph.invoke({"alert_id": alert_id, "messages": [{"role": "user", "content": f"Triage {alert_id}."}]},
                        thread(thread_id))


def resume(graph, thread_id: str, decision: dict[str, Any]) -> dict[str, Any]:
    return graph.invoke(Command(resume=decision), thread(thread_id))


def pending_interrupt(result: dict[str, Any]) -> dict[str, Any] | None:
    pending = result.get("__interrupt__")
    return pending[0].value if pending else None


def fork_before_approval(graph, thread_id: str) -> dict[str, Any]:
    """Time travel: find the checkpoint whose next node is 'approve' and return its config."""
    history = list(graph.get_state_history(thread(thread_id)))  # newest first
    snap = next(s for s in history if s.next == ("approve",))
    return snap.config


def main() -> None:
    world, saver, store = OpsWorld(), MemorySaver(), InMemoryStore()
    client = get_client(fake=FakeClient(scripted_policy))
    graph = build_graph(client, world, checkpointer=saver, store=store)

    print("== 1. run until the human gate ==")
    out = start(graph, "ALERT-4211", "incident-4211")
    print("paused with:", pending_interrupt(out)["description"])
    print("next node:", graph.get_state(thread("incident-4211")).next, "| restarts so far:", world.restarts)

    print("\n== 2. 'new process': fresh graph object, same checkpointer, resume with accept ==")
    graph2 = build_graph(client, world, checkpointer=saver, store=store)
    out = resume(graph2, "incident-4211", {"type": "accept"})
    print(out["final_text"], "\nrestarts:", world.restarts)

    print("\n== 3. time travel: fork before approval, replay with a rejection ==")
    fork_cfg = fork_before_approval(graph2, "incident-4211")
    replay = graph2.invoke(None, fork_cfg)  # approve re-runs and interrupts again
    print("re-paused:", pending_interrupt(replay) is not None)
    out = resume(graph2, "incident-4211", {"type": "response", "args": "not during peak; page owners"})
    print(out["final_text"], "\nrestarts (unchanged, fork never restarted):", world.restarts)

    print("\n== 4. stream a read-only alert, node by node (stream_mode='updates') ==")
    for chunk in graph2.stream({"alert_id": "ALERT-4213",
                                "messages": [{"role": "user", "content": "Triage ALERT-4213."}]},
                               thread("incident-4213"), stream_mode="updates"):
        for node, update in chunk.items():
            print(f"  {node:6s} -> {sorted((update or {}).keys())}")
    print("long-term memory keys:", [i.key for i in store.search(MEMORY_NS)])


if __name__ == "__main__":
    main()
