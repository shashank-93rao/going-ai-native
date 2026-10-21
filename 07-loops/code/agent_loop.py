"""The agent loop from scratch: model -> tools -> observe -> repeat, with governors and a trace.

The whole trick (Thorsten Ball: "an LLM, a loop, and enough tokens"):
  1. send the full message list + tool schemas (the API is stateless)
  2. append the assistant turn exactly as returned
  3. if it asked for tools, run them and append ONE user turn holding every tool_result
  4. stop when it ends its turn without tool calls... unless a completion gate says no

Run the toy demo:  python agent_loop.py   (FakeClient unless ANTHROPIC_API_KEY is set)
"""

from __future__ import annotations

import fnmatch
import json
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from ainative_kit import LLMClient, Tracer, get_client
from governor import ExitCode, Governor, GovernorTripped, Limits

SYSTEM = (
    "You are a coding agent working in a sandboxed workspace. Use the tools to inspect, edit and test. "
    "The spec_*.py files are the oracle: never edit them. Run run_tests before claiming you are done, "
    "and quote its verdict line. If you cannot proceed, reply with a line starting 'BLOCKED:' and why."
)
MAX_TOOL_OUTPUT = 4_000  # compact tool output before it enters context (12-factor #9)


class ToolError(Exception):
    """Raised by tools for expected failures; becomes an is_error tool_result the model can read."""


@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict[str, Any]
    fn: Callable[..., str]

    def schema(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description, "input_schema": self.input_schema}


@dataclass
class RunResult:
    exit_code: ExitCode
    reason: str
    final_text: str
    iterations: int
    messages: list[dict[str, Any]] = field(repr=False)
    governor: dict[str, Any] = field(default_factory=dict)


def _obj(props: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {"type": "object", "properties": props, "required": required or []}


def workspace_tools(root: Path, oracle=None) -> tuple[list[Tool], dict[str, Any]]:
    """read_file / list_files / edit_file / run_tests confined to `root`.

    Returns (tools, state). state["last_score"] holds the last oracle score, which the
    loop feeds to the governor for no-progress detection without re-running the oracle.
    """
    root = root.resolve()
    state: dict[str, Any] = {"last_score": None, "last_ok": False}

    def safe(rel: str) -> Path:
        p = (root / rel).resolve()
        if p != root and root not in p.parents:
            raise ToolError(f"path escapes workspace: {rel}")
        return p

    def read_file(path: str) -> str:
        p = safe(path)
        if not p.is_file():
            raise ToolError(f"no such file: {path}. Use list_files to see what exists.")
        return p.read_text()

    def list_files(path: str = ".", pattern: str = "*") -> str:
        d = safe(path)
        if not d.is_dir():
            raise ToolError(f"not a directory: {path}")
        names = sorted(str(p.relative_to(root)) for p in d.rglob("*")
                       if p.is_file() and "__pycache__" not in p.parts and fnmatch.fnmatch(p.name, pattern))
        return "\n".join(names) or "(no matching files)"

    def edit_file(path: str, old_str: str, new_str: str) -> str:
        p = safe(path)
        if p.name.startswith("spec_"):
            raise ToolError("spec_*.py files are the oracle and are read-only. Change the implementation instead.")
        if old_str == "":
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(new_str)
            return f"created {path}"
        src = read_file(path)
        count = src.count(old_str)
        if count != 1:
            raise ToolError(f"old_str must match exactly once in {path}; matched {count} times. Re-read the file.")
        p.write_text(src.replace(old_str, new_str, 1))
        return f"edited {path}"

    def run_tests() -> str:
        if oracle is None:
            raise ToolError("no oracle configured")
        r = oracle.run(root)
        state["last_score"], state["last_ok"] = r.score, r.ok
        return r.summary_for_agent()

    tools = [
        Tool("read_file", "Read a UTF-8 file. Path is relative to the workspace root.",
             _obj({"path": {"type": "string"}}, ["path"]), read_file),
        Tool("list_files", "List files under a directory (recursive), optionally filtered by a glob on the name.",
             _obj({"path": {"type": "string"}, "pattern": {"type": "string"}}), list_files),
        Tool("edit_file", "Replace old_str (must occur exactly once) with new_str. Empty old_str creates the file.",
             _obj({"path": {"type": "string"}, "old_str": {"type": "string"}, "new_str": {"type": "string"}},
                  ["path", "old_str", "new_str"]), edit_file),
        Tool("run_tests", "Run the oracle (the spec tests). Returns a PASS/FAIL verdict line and failing tests.",
             _obj({}), run_tests),
    ]
    return tools, state


def _execute(tools: dict[str, Tool], name: str, args: dict[str, Any]) -> tuple[str, bool]:
    """Run one tool. Errors are data for the model, not exceptions for the loop."""
    t = tools.get(name)
    if t is None:
        return f"unknown tool {name!r}; available: {', '.join(tools)}", True
    try:
        out, err = t.fn(**args), False
    except ToolError as e:
        out, err = f"error: {e}", True
    except TypeError as e:
        out, err = f"bad arguments for {name}: {e}", True
    if len(out) > MAX_TOOL_OUTPUT:
        out = out[:MAX_TOOL_OUTPUT] + f"\n... [truncated {len(out) - MAX_TOOL_OUTPUT} chars]"
    return out, err


def run_agent(
    client: LLMClient,
    task: str,
    tools: list[Tool],
    *,
    governor: Governor | None = None,
    tracer: Tracer | None = None,
    system: str = SYSTEM,
    model: str | None = None,
    max_tokens: int = 2048,
    completion_gate: Callable[[], tuple[bool, str]] | None = None,
    max_gate_blocks: int = 8,
    metric: Callable[[], Any] | None = None,
) -> RunResult:
    gov = governor or Governor()
    tracer = tracer or Tracer()
    by_name = {t.name: t for t in tools}
    schemas = [t.schema() for t in tools]
    messages: list[dict[str, Any]] = [{"role": "user", "content": task}]
    last_text, gate_blocks = "", 0

    def done(code: ExitCode, reason: str) -> RunResult:
        run_span.attrs.update(exit_code=code.name, reason=reason, **gov.snapshot())
        return RunResult(code, reason, last_text, gov.iterations, messages, gov.snapshot())

    with tracer.span("agent_run", task=task[:120]) as run_span:
        try:
            while True:
                gov.tick()
                with tracer.span("llm_call", iteration=gov.iterations, n_messages=len(messages)) as s:
                    resp = client.complete(messages, system=system, tools=schemas, model=model, max_tokens=max_tokens)
                    s.attrs.update(stop_reason=resp.stop_reason, input_tokens=resp.usage.input_tokens,
                                   output_tokens=resp.usage.output_tokens, tools=[c.name for c in resp.tool_calls])
                gov.record_usage(resp.usage.input_tokens, resp.usage.output_tokens)
                messages.append(resp.to_assistant_message())
                last_text = resp.text or last_text

                if resp.stop_reason == "max_tokens" and not resp.tool_calls:
                    gov.record_outcome(False)  # truncation counts toward the error breaker
                    messages.append({"role": "user", "content": "Your reply hit max_tokens. Continue, more briefly."})
                    gov.check()
                    continue

                if not resp.tool_calls:  # the model thinks it is done
                    if resp.text.lstrip().startswith("BLOCKED:"):
                        return done(ExitCode.BLOCKED, resp.text.strip()[:200])
                    if completion_gate is None:
                        return done(ExitCode.SUCCESS, "model ended turn (no gate: unverified)")
                    with tracer.span("completion_gate", blocks_so_far=gate_blocks) as gs:
                        ok, why = completion_gate()
                        gs.attrs["ok"] = ok
                    if ok:
                        return done(ExitCode.SUCCESS, "completion gate passed")
                    gate_blocks += 1
                    if gate_blocks >= max_gate_blocks:
                        return done(ExitCode.FAIL, f"completion gate blocked {gate_blocks}x with no tool use between")
                    messages.append({"role": "user", "content": f"Not done. The oracle says:\n{why}\nKeep working."})
                    continue

                gate_blocks = 0  # like Claude Code: the block cap counts blocks with no tool call between
                results = []
                for call in resp.tool_calls:
                    gov.record_tool_call(call.name, call.input)
                    with tracer.span("tool_call", tool=call.name, args=json.dumps(call.input)[:200]) as ts:
                        out, is_err = _execute(by_name, call.name, call.input)
                        ts.attrs.update(is_error=is_err, out_chars=len(out))
                    gov.record_outcome(not is_err)
                    results.append({"type": "tool_result", "tool_use_id": call.id, "content": out, "is_error": is_err})
                messages.append({"role": "user", "content": results})
                if metric is not None:
                    gov.record_metric(metric())
                gov.check()
        except GovernorTripped as t:
            return done(t.code, t.reason)


def oracle_gate(oracle, root: Path) -> Callable[[], tuple[bool, str]]:
    """A Stop-hook-style gate: the harness, not the model, decides whether the run is done."""

    def gate() -> tuple[bool, str]:
        r = oracle.run(root)
        return r.ok, r.summary_for_agent()

    return gate


def demo() -> int:
    sys.path.insert(0, str(Path(__file__).parent / "examples"))
    from ainative_kit import FakeClient
    from oracle import PytestOracle
    from toy_task import fixing_script, make_workspace

    tmp = Path(tempfile.mkdtemp(prefix="loop-demo-"))
    ws = make_workspace(tmp)
    oracle = PytestOracle(["spec_tokenbucket.py"])
    tools, state = workspace_tools(ws, oracle)
    trace_path = tmp / "trace.jsonl"
    result = run_agent(
        get_client(fake=FakeClient(fixing_script())),
        "Make spec_tokenbucket.py pass. The rate limiter lives in tokenbucket.py.",
        tools,
        governor=Governor(Limits(max_iterations=15, max_cost_usd=1.0)),
        tracer=Tracer(trace_path),
        completion_gate=oracle_gate(oracle, ws),
        metric=lambda: state["last_score"],
    )
    print(f"exit={result.exit_code.name} reason={result.reason!r} iterations={result.iterations}")
    print(f"governor: {result.governor}")
    print(f"final text: {result.final_text}")
    for line in trace_path.read_text().splitlines():
        s = json.loads(line)
        print(f"  span {s['name']:15s} {json.dumps(s['attrs'])[:110]}")
    shutil.rmtree(tmp, ignore_errors=True)
    return int(result.exit_code)


if __name__ == "__main__":
    raise SystemExit(demo())
