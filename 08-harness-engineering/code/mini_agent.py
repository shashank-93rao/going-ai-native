#!/usr/bin/env python3
"""A minimal coding agent (about 150 lines) to plug into autonomy_eval.py.

Four tools: list_files, read_file, replace_in_file, run (allowlisted repo commands).
The system prompt is deliberately thin: everything task-specific must come from
the repo's harness (AGENTS.md, INVARIANTS.md, the lint, diagnose.py). That is the
point of the exercise: improve the harness, not this prompt.

    python mini_agent.py WORKDIR PROMPT_FILE [--trace traces.jsonl] [--max-turns 30]

With ANTHROPIC_API_KEY set it calls the real model; otherwise it runs a scripted
FakeClient demo that solves only the inc-409-spike task.
"""

from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "shared"))
from ainative_kit import FakeClient, LLMClient, Response, Tracer, get_client, text, tool  # noqa: E402

SYSTEM = ("You are a software engineer working in the repository in your current directory. "
          "Use the tools to understand, change and verify the code. Stop when the task is done.")
ALLOWED = ("python tools/", "python -m pytest")
MAX_OUTPUT = 4000

TOOLS: list[dict[str, Any]] = [
    {"name": "list_files", "description": "List files under a directory (relative path).",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
    {"name": "read_file", "description": "Read a text file (relative path).",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
    {"name": "replace_in_file",
     "description": "Replace exactly one occurrence of `old` with `new` in a file. Use an empty `old` to create the file.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "old": {"type": "string"},
                                                       "new": {"type": "string"}}, "required": ["path", "old", "new"]}},
    {"name": "run", "description": "Run a repo command. Allowed prefixes: 'python tools/' and 'python -m pytest'.",
     "input_schema": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}},
]


def _safe(root: Path, rel: str) -> Path:
    p = (root / rel).resolve()
    if root.resolve() not in (p, *p.parents):
        raise ValueError(f"path escapes the repo: {rel}")
    return p


def execute(root: Path, name: str, args: dict[str, Any]) -> tuple[str, bool]:
    """Run one tool call. Returns (output, is_error)."""
    try:
        if name == "list_files":
            base = _safe(root, args["path"])
            files = sorted(str(p.relative_to(root)) for p in base.rglob("*") if p.is_file() and "__pycache__" not in p.parts)
            return "\n".join(files[:300]) or "(empty)", False
        if name == "read_file":
            return _safe(root, args["path"]).read_text()[:MAX_OUTPUT * 4], False
        if name == "replace_in_file":
            p = _safe(root, args["path"])
            if args["old"] == "":
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(args["new"])
                return f"created {args['path']}", False
            src = p.read_text()
            n = src.count(args["old"])
            if n != 1:
                return f"expected exactly 1 occurrence of `old`, found {n}; include more surrounding lines", True
            p.write_text(src.replace(args["old"], args["new"]))
            return f"edited {args['path']}", False
        if name == "run":
            cmd = args["command"].strip()
            if not cmd.startswith(ALLOWED):
                return f"command not allowed; allowed prefixes: {ALLOWED}", True
            argv = shlex.split(cmd)
            argv[0] = sys.executable
            proc = subprocess.run(argv, cwd=root, capture_output=True, text=True, timeout=300)
            out = (proc.stdout + proc.stderr)[-MAX_OUTPUT:]
            return f"exit={proc.returncode}\n{out}", proc.returncode != 0
        return f"unknown tool {name}", True
    except Exception as e:  # tool errors go back to the model, not up the stack
        return f"{type(e).__name__}: {e}", True


def run_agent(client: LLMClient, root: Path, prompt: str, tracer: Tracer, max_turns: int = 30) -> str:
    messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
    with tracer.span("agent_run", workdir=str(root)) as run_span:
        for turn in range(max_turns):
            with tracer.span("llm_call", turn=turn) as s:
                resp: Response = client.complete(messages, system=SYSTEM, tools=TOOLS, max_tokens=4096)
                s.attrs.update(stop_reason=resp.stop_reason, tool_calls=len(resp.tool_calls))
            messages.append(resp.to_assistant_message())
            if not resp.tool_calls:
                run_span.attrs.update(turns=turn + 1, outcome="end_turn")
                return resp.text
            results = []
            for call in resp.tool_calls:
                with tracer.span(f"tool:{call.name}", **{k: str(v)[:120] for k, v in call.input.items()}) as ts:
                    out, is_error = execute(root, call.name, call.input)
                    ts.attrs["is_error"] = is_error
                results.append({"type": "tool_result", "tool_use_id": call.id, "content": out, "is_error": is_error})
            messages.append({"role": "user", "content": results})
        run_span.attrs.update(turns=max_turns, outcome="max_turns")
    return "stopped: turn budget exhausted"


def demo_script() -> list[Response]:
    """Scripted responses for the offline demo on inc-409-spike (illustrative, not a model)."""
    bug = '    rh = request_hash("create_order", {**body, "window": int(_now() // 60)})  # dedupe window'
    return [
        tool("read_file", {"path": "AGENTS.md"}, id="t1"),
        tool("run", {"command": "python tools/diagnose.py conflicts"}, id="t2"),
        tool("read_file", {"path": "orders/api.py"}, id="t3"),
        tool("replace_in_file", {"path": "orders/api.py", "old": bug,
                                 "new": '    rh = request_hash("create_order", body)'}, id="t4"),
        tool("run", {"command": "python tools/check.py"}, id="t5"),
        text("Root cause: create_order hashed a server-side time window into the idempotency request hash, so "
             "retries 60s later hashed differently and raised IdempotencyConflict (I2). Removed it; check passes."),
    ]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("workdir", type=Path)
    ap.add_argument("prompt", type=Path)
    ap.add_argument("--trace", type=Path)
    ap.add_argument("--max-turns", type=int, default=30)
    args = ap.parse_args(argv)
    client = get_client(fake=FakeClient(demo_script()))
    final = run_agent(client, args.workdir, args.prompt.read_text(), Tracer(args.trace), args.max_turns)
    print(final)
    return 0


if __name__ == "__main__":
    sys.exit(main())
