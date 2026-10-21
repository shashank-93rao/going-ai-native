"""Code-as-action: let the model write a script that calls tools, so data stays out of context.

Scenario: "Which (group, partition) pairs across the cluster have lag > 10,000?"
The underlying API is fine-grained (one partition per call), like most internal REST APIs.

  direct tool calling  -> one model turn per call; every result is appended to the context
  code-as-action       -> one model turn writes a loop; only the script's stdout enters context

`measure_direct()` and `measure_code()` compute both footprints for the same question,
and `run_code_action()` is the executor behind an `execute_python` tool.

WARNING: `run_code_action` uses `exec` with a trimmed builtins dict. That is NOT a sandbox;
Python has many escapes. It exists to show the data flow. Real deployments run model-written
code in a container or microVM with no credentials and a network allowlist (see
07-execution-environments-and-agent-surfaces.md and ../16-security-and-containment/).
"""

from __future__ import annotations

import contextlib
import io
import json
import random
from typing import Any, Callable

from ainative_kit import FakeClient, Response, text, tool

from agent_loop import run_agent
from tool_formatter import estimate_tokens


def make_cluster(groups: int = 6, partitions: int = 48, seed: int = 3) -> dict[str, list[int]]:
    rnd = random.Random(seed)
    cluster = {f"group-{i:02d}": [rnd.randint(0, 3000) for _ in range(partitions)] for i in range(groups)}
    cluster["group-03"][17] = 52_000  # the needles
    cluster["group-05"][2] = 14_500
    return cluster


def make_api(cluster: dict[str, list[int]]) -> dict[str, Callable[..., Any]]:
    """The fine-grained tools, as plain functions. Each returns a JSON-ish payload like a REST API."""
    def kafka_list_groups() -> list[str]:
        return sorted(cluster)

    def kafka_partition_count(group: str) -> int:
        return len(cluster[group])

    def kafka_partition_lag(group: str, partition: int) -> dict[str, Any]:
        lag = cluster[group][partition]
        return {"group": group, "partition": partition, "current_offset": 9_000_000 - lag,
                "log_end_offset": 9_000_000, "lag": lag, "consumer_id": f"consumer-{partition % 4}-a1b2c3",
                "host": f"/10.0.{partition % 4}.7", "client_id": "ledger-writer"}

    return {"kafka_list_groups": kafka_list_groups, "kafka_partition_count": kafka_partition_count,
            "kafka_partition_lag": kafka_partition_lag}


def measure_direct(api: dict[str, Callable[..., Any]]) -> dict[str, int]:
    """Footprint if the model calls each tool itself: every result round-trips through context."""
    ctx_chars, calls, resent = 0, 0, 0

    def step(result_chars: int) -> None:
        nonlocal ctx_chars, calls, resent
        resent += ctx_chars  # the API is stateless: each turn re-sends the whole history
        ctx_chars += result_chars + 60  # + the tool_use block itself
        calls += 1

    groups = api["kafka_list_groups"]()
    step(len(json.dumps(groups)))
    for g in groups:
        n = api["kafka_partition_count"](g)
        step(len(str(n)))
        for p in range(n):
            step(len(json.dumps(api["kafka_partition_lag"](g, p))))
    return {"tool_calls": calls, "model_turns": calls + 1, "context_tokens": ctx_chars // 4,
            "cumulative_input_tokens": (resent + ctx_chars) // 4}


SCRIPT = """\
hot = []
for g in kafka_list_groups():
    for p in range(kafka_partition_count(g)):
        r = kafka_partition_lag(g, p)
        if r["lag"] > 10_000:
            hot.append((g, p, r["lag"]))
hot.sort(key=lambda x: -x[2])
print(f"{len(hot)} partitions over 10k lag:", hot)
"""

SAFE_BUILTINS = {n: __builtins__[n] if isinstance(__builtins__, dict) else getattr(__builtins__, n)
                 for n in ("len", "range", "sorted", "sum", "min", "max", "print", "enumerate", "zip",
                           "dict", "list", "tuple", "set", "str", "int", "float", "abs", "round", "any", "all")}


def run_code_action(code: str, api: dict[str, Callable[..., Any]], max_output_chars: int = 2000) -> tuple[str, bool]:
    """Execute model-written code with the tools bound as functions. Returns (stdout or error, is_error)."""
    buf = io.StringIO()
    env: dict[str, Any] = {"__builtins__": SAFE_BUILTINS, **api}
    try:
        with contextlib.redirect_stdout(buf):
            exec(compile(code, "<agent>", "exec"), env)  # noqa: S102 - illustrative only, see module docstring
    except Exception as e:  # return the error to the model so it can fix its script
        return (f"{type(e).__name__}: {e}. stdout so far: {buf.getvalue()[-500:]!r}. "
                f"Available functions: {sorted(api)}."), True
    out = buf.getvalue()
    if len(out) > max_output_chars:
        out = out[:max_output_chars] + f"\n[output truncated at {max_output_chars} chars; print less, e.g. aggregates or top-N]"
    return out or "(script printed nothing; print the values you need)", False


def measure_code(api: dict[str, Callable[..., Any]], script: str = SCRIPT) -> dict[str, int]:
    out, _ = run_code_action(script, api)
    return {"tool_calls": 1, "model_turns": 2, "context_tokens": estimate_tokens(script) + estimate_tokens(out)}


EXECUTE_PYTHON_SCHEMA = {
    "name": "execute_python",
    "description": ("Run a Python script. These functions are predefined: kafka_list_groups() -> list[str], "
                    "kafka_partition_count(group) -> int, kafka_partition_lag(group, partition) -> dict with 'lag'. "
                    "Only what you print() is returned to you, capped at 2000 chars: print aggregates, not raw rows."),
    "input_schema": {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]},
}


def scripted_coder(messages: list[dict[str, Any]], kwargs: dict[str, Any]) -> Response:
    """Fake model: first script has a bug (wrong key), then it fixes it from the error message."""
    last = messages[-1]
    if last["role"] == "user" and isinstance(last["content"], str):
        return tool("execute_python", {"code": SCRIPT.replace('r["lag"]', 'r["consumer_lag"]')}, id="toolu_c1")
    res = last["content"][-1]
    if res["is_error"]:
        return tool("execute_python", {"code": SCRIPT}, id="toolu_c2")
    return text("Two partitions exceed 10k lag: " + res["content"].split(":", 1)[1].strip())


def demo() -> dict[str, Any]:
    api = make_api(make_cluster())
    result = run_agent(FakeClient(scripted_coder), "List partitions with lag over 10k across all groups.",
                       tools=[EXECUTE_PYTHON_SCHEMA],
                       call_tool=lambda name, args: run_code_action(args["code"], api))
    return {"direct": measure_direct(api), "code": measure_code(api), "agent": result}


if __name__ == "__main__":
    d = demo()
    print("direct tool calling:", d["direct"])
    print("code-as-action:     ", d["code"])
    for t in d["agent"].tool_log:
        print(f"  execute_python -> error={t['is_error']}: {t['content'][:120]}")
    print("final:", d["agent"].final_text)
