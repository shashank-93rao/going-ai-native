"""An event-sourced agent run: append-only log, state = fold(log), resume from checkpoint,
idempotency keys for side-effecting tools.

Invariants (the whole design):
  - Nothing the run depends on lives only in memory. Every decision is an event first.
  - Model responses are logged, so resume REPLAYS them instead of re-sampling. A re-sampled
    model can choose a different tool call, and then no idempotency key can save you.
  - Idempotency keys derive from the logged decision: f"{run_id}:{tool_call_id}".
  - A side effect is preceded by a `tool_intent` event. intent-without-result on resume means
    "in doubt": retry if the tool is idempotent, otherwise stop and ask a human.
  - Checkpoints are snapshots for fast folding; the log stays the source of truth.

Run:  python run_log.py
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from ainative_kit import FakeClient, LLMClient, Response, get_client, text, tool

# --------------------------------------------------------------------------- the log


class EventLog:
    """Append-only JSONL. A torn final line (crash mid-write) is ignored on read."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def append(self, type_: str, **data: Any) -> None:
        seq = len(self.events())
        with self.path.open("a") as f:
            f.write(json.dumps({"seq": seq, "type": type_, **data}) + "\n")
            f.flush()

    def events(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text().splitlines():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                break                                   # torn tail write: everything after is invalid
        return out


@dataclass
class RunState:
    messages: list[dict[str, Any]] = field(default_factory=list)
    step: int = 0
    pending: list[dict[str, Any]] = field(default_factory=list)   # tool calls without a result
    intents: set[str] = field(default_factory=set)               # call ids with a logged intent
    results: dict[str, dict[str, Any]] = field(default_factory=dict)
    finished: bool = False
    final_text: str = ""


def fold(events: list[dict[str, Any]], *, use_checkpoint: bool = True) -> RunState:
    """Derive run state from the log. Starts at the latest checkpoint if allowed."""
    start = 0
    st = RunState()
    if use_checkpoint:
        for i in range(len(events) - 1, -1, -1):
            if events[i]["type"] == "checkpoint":
                st = RunState(messages=json.loads(json.dumps(events[i]["messages"])), step=events[i]["step"])
                start = i + 1
                break
    for ev in events[start:]:
        t = ev["type"]
        if t == "run_started":
            st.messages = [{"role": "user", "content": ev["task"]}]
        elif t == "llm_response":
            resp = Response.from_dict(ev["response"])
            st.messages.append(resp.to_assistant_message())
            st.step = ev["step"]
            st.pending = [{"id": c.id, "name": c.name, "input": c.input} for c in resp.tool_calls]
            st.results = {}
        elif t == "tool_intent":
            st.intents.add(ev["call_id"])
        elif t == "tool_result":
            st.results[ev["call_id"]] = {"type": "tool_result", "tool_use_id": ev["call_id"],
                                         "content": ev["content"], "is_error": ev["is_error"]}
            if st.pending and all(c["id"] in st.results for c in st.pending):
                st.messages.append({"role": "user", "content": [st.results[c["id"]] for c in st.pending]})
                st.pending = []
        elif t == "run_finished":
            st.finished, st.final_text = True, ev["text"]
    st.pending = [c for c in st.pending if c["id"] not in st.results]
    return st


# --------------------------------------------------------------------------- tools


@dataclass
class ToolDef:
    schema: dict[str, Any]
    fn: Callable[[dict[str, Any], str | None], str]     # (input, idempotency_key) -> result
    side_effecting: bool = False
    idempotent: bool = True                             # does the remote honour the key?


class InDoubt(Exception):
    """A non-idempotent side effect may or may not have happened. Same as an in-doubt 2PC txn."""


class SimulatedCrash(Exception):
    pass


class TicketAPI:
    """A remote that dedups on Idempotency-Key, like Stripe or any well-built payments API."""

    def __init__(self, honour_keys: bool = True):
        self.tickets: list[dict[str, Any]] = []
        self._by_key: dict[str, str] = {}
        self.honour_keys = honour_keys

    def create(self, input: dict[str, Any], key: str | None) -> str:
        if self.honour_keys and key in self._by_key:
            return self._by_key[key]
        tid = f"OPS-{1000 + len(self.tickets)}"
        self.tickets.append({"id": tid, **input})
        if key:
            self._by_key[key] = tid
        return tid


# --------------------------------------------------------------------------- the durable run


class DurableRun:
    def __init__(self, client: LLMClient, log: EventLog, tools: dict[str, ToolDef], *, run_id: str,
                 system: str | None = None, max_steps: int = 8, crash_at: str | None = None):
        self.client, self.log, self.tools, self.run_id = client, log, tools, run_id
        self.system, self.max_steps, self.crash_at = system, max_steps, crash_at

    def _maybe_crash(self, point: str) -> None:
        if self.crash_at == point:
            self.crash_at = None                          # crash once
            raise SimulatedCrash(point)

    def start(self, task: str) -> str:
        self.log.append("run_started", run_id=self.run_id, task=task)
        return self.resume()

    def resume(self) -> str:
        """Idempotent itself: calling resume on a finished run returns the logged answer."""
        while True:
            st = fold(self.log.events())
            if st.finished:
                return st.final_text
            if st.pending:
                for call in st.pending:
                    self._execute(call, st)
                self.log.append("checkpoint", step=st.step, messages=fold(self.log.events()).messages)
                continue
            if st.step >= self.max_steps:
                self.log.append("run_finished", text="[stopped: step budget exhausted]")
                continue
            resp = self.client.complete(st.messages, system=self.system,
                                        tools=[t.schema for t in self.tools.values()])
            self.log.append("llm_response", step=st.step + 1, response=resp.to_dict())
            self._maybe_crash("after_llm_response")
            if not resp.tool_calls:
                self.log.append("run_finished", text=resp.text)

    def _execute(self, call: dict[str, Any], st: RunState) -> None:
        tdef = self.tools.get(call["name"])
        if tdef is None:
            self.log.append("tool_result", call_id=call["id"], content=f"unknown tool {call['name']}", is_error=True)
            return
        key = f"{self.run_id}:{call['id']}" if tdef.side_effecting else None
        if tdef.side_effecting:
            if call["id"] in st.intents and not tdef.idempotent:
                raise InDoubt(f"{call['name']} {call['id']} may have run; no idempotency guarantee")
            if call["id"] not in st.intents:
                self.log.append("tool_intent", call_id=call["id"], name=call["name"], key=key)
            self._maybe_crash("after_tool_intent")
        try:
            content, is_error = tdef.fn(call["input"], key), False
        except Exception as e:                               # errors are results, for the model to see
            content, is_error = f"{type(e).__name__}: {e}", True
        if tdef.side_effecting:
            self._maybe_crash("after_side_effect")          # the nasty one: done, but not recorded
        self.log.append("tool_result", call_id=call["id"], content=content, is_error=is_error)


# --------------------------------------------------------------------------- demo wiring

TICKET_SCHEMA = {"name": "create_ticket", "description": "Open an ops ticket. Side-effecting.",
                 "input_schema": {"type": "object", "properties": {"title": {"type": "string"},
                                                                    "severity": {"type": "string"}},
                                  "required": ["title", "severity"]}}
LAG_SCHEMA = {"name": "get_consumer_lag", "description": "Read consumer lag for a group. Read-only.",
              "input_schema": {"type": "object", "properties": {"group": {"type": "string"}}, "required": ["group"]}}


def make_tools(api: TicketAPI) -> dict[str, ToolDef]:
    return {
        "get_consumer_lag": ToolDef(LAG_SCHEMA, lambda inp, _k: json.dumps({"group": inp["group"], "lag": 512_330})),
        "create_ticket": ToolDef(TICKET_SCHEMA, api.create, side_effecting=True),
    }


def scripted_model() -> FakeClient:
    return FakeClient([
        tool("get_consumer_lag", {"group": "notify-svc"}, id="toolu_01"),
        tool("create_ticket", {"title": "notify-svc lag 512k on user-events", "severity": "sev2"}, id="toolu_02"),
        text("Opened OPS ticket for notify-svc lag (512k)."),
    ])


def main() -> None:
    import tempfile
    api = TicketAPI()
    with tempfile.TemporaryDirectory() as d:
        log = EventLog(Path(d) / "run.jsonl")
        client = get_client(fake=scripted_model())
        run = DurableRun(client, log, make_tools(api), run_id="run-42", crash_at="after_side_effect")
        try:
            run.start("Check notify-svc consumer lag and open a ticket if it is above 100k.")
        except SimulatedCrash as c:
            print(f"crashed at {c}; tickets so far: {[t['id'] for t in api.tickets]}")
        print("resumed ->", DurableRun(client, log, make_tools(api), run_id="run-42").resume())
        print("tickets:", [t["id"] for t in api.tickets])
        for ev in log.events():
            print(ev["seq"], ev["type"], {k: v for k, v in ev.items() if k in ("call_id", "key", "step")})


if __name__ == "__main__":
    main()
