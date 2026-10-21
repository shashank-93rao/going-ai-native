"""Scripted stand-ins for the model, for offline tests.

Each policy is a FakeClient responder: a pure function of the message history,
just as a real model's next turn is a function of its context. The good policy
follows the rules in ops_agent.SYSTEM. Each flag injects one realistic agent bug,
so tests can prove that the checks actually catch it (negative controls).
"""

from __future__ import annotations

import json
import random
from typing import Any, Callable

from ainative_kit import Response, text, tool

Obs = tuple[str, dict[str, Any], dict[str, Any]]  # (tool name, input, result)


def observations(messages: list[dict[str, Any]]) -> list[Obs]:
    """Pair every tool_use block with its tool_result, in order."""
    uses: dict[str, tuple[str, dict[str, Any]]] = {}
    out: list[Obs] = []
    for m in messages:
        if isinstance(m["content"], str):
            continue
        for b in m["content"]:
            if b["type"] == "tool_use":
                uses[b["id"]] = (b["name"], b["input"])
            elif b["type"] == "tool_result":
                name, inp = uses[b["tool_use_id"]]
                out.append((name, inp, json.loads(b["content"])))
    return out


def _attempts(obs: list[Obs], tool_name: str, env: str) -> list[Obs]:
    return [o for o in obs if o[0] == tool_name and o[1].get("env") == env]


def promote_policy(
    service: str = "payments",
    version: str = "v2.4.0",
    *,
    skip_staging: bool = False,
    skip_verify: bool = False,
    new_id_on_retry: bool = False,
    delete_prod_first: bool = False,
    premature_stop: bool = False,
    loop_forever: bool = False,
    max_attempts: int = 4,
) -> Callable[[list[dict[str, Any]], dict[str, Any]], Response]:
    """Scripted 'model' for the deploy-to-prod task. Flags inject one bug each."""

    def respond(messages: list[dict[str, Any]], _kwargs: dict[str, Any]) -> Response:
        obs = observations(messages)
        tid = f"toolu_{len(obs):03d}"

        def call(name: str, **inp: Any) -> Response:
            return tool(name, {"service": service, **inp}, id=tid)

        if loop_forever:  # the "keeps checking status, never acts" failure
            return call("get_status", env="staging")

        def mutate(name: str, env: str, rid_base: str, **inp: Any) -> Response | None:
            """Call a mutating tool with retries. Returns the next action, or None once it succeeded."""
            tries = _attempts(obs, name, env)
            if tries and "error" not in tries[-1][2]:
                return None
            if tries and not tries[-1][2].get("retryable"):
                return text(f"{name} on {env} failed: {tries[-1][2]['error']}")
            if len(tries) >= max_attempts:
                return text(f"Gave up: {name} on {env} failed {len(tries)} times.")
            rid = f"{rid_base}-{len(tries) + 1}" if new_id_on_retry else rid_base
            return call(name, env=env, request_id=rid, **inp)

        def deploy_to(env: str) -> Response | None:
            return mutate("deploy", env, f"{env}-{version}", version=version)

        if not skip_staging:
            nxt = deploy_to("staging")
            if nxt is not None:
                return nxt
            if premature_stop:
                return text(f"Deployed {service} {version} to prod.")
            if not skip_verify:
                checks = [o for o in obs if o[0] == "get_status" and o[1]["env"] == "staging"]
                if not checks:
                    return call("get_status", env="staging")
                if not checks[-1][2].get("healthy"):
                    nxt = mutate("rollback", "staging", f"staging-rollback-{version}")
                    if nxt is not None:
                        return nxt
                    return text(f"Aborted: {version} unhealthy in staging; rolled staging back.")

        if delete_prod_first and not _attempts(obs, "delete_deployment", "prod"):
            return call("delete_deployment", env="prod", request_id="prod-clean-slate")

        nxt = deploy_to("prod")
        if nxt is not None:
            return nxt
        if not [o for o in obs if o[0] == "get_status" and o[1]["env"] == "prod"]:
            return call("get_status", env="prod")
        status = [o for o in obs if o[0] == "get_status" and o[1]["env"] == "prod"][-1][2]
        if status.get("healthy"):
            return text(f"Deployed {service} {version} to prod; verified healthy.")
        return text(f"Deployed {service} {version} to prod but it is unhealthy; paging on-call.")

    return respond


BUGS = ("skip_staging", "skip_verify", "new_id_on_retry", "premature_stop", "delete_prod_first")


def noisy_policy(seed: int, bug_rates: dict[str, float] | None = None, **kw: Any):
    """A 'model' that is usually right and occasionally makes one mistake.

    The mistake is drawn once per run from `seed`, imitating sampling variance:
    same prompt, same tools, different behavior on different runs.
    """
    rates = bug_rates or {"skip_verify": 0.10, "premature_stop": 0.05, "new_id_on_retry": 0.10}
    rng = random.Random(10_000 + seed)
    flags = {bug: rng.random() < p for bug, p in rates.items()}
    return promote_policy(**kw, **flags)
