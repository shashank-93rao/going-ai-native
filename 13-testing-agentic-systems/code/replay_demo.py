"""Record/replay for agent runs, and the three ways replay lies.

RecordingClient writes each (request hash -> response) to a JSONL cassette.
ReplayClient serves responses by request hash and fails loudly on a miss.
Because the hash covers the full message list (tool results included), any change
to the prompt, the tools, or the world's responses invalidates the cassette.

What the hash does NOT cover is the trap: anything not passed in the request.
Here that is the model ID (run_agent does not pass `model=`), so a model upgrade
replays green against a cassette recorded on the old model. We store a sidecar
meta file and check it, the same way you would pin a schema version next to a
Kafka topic's recorded fixtures.

    python replay_demo.py
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

from ainative_kit import DEFAULT_MODEL, FakeClient, RecordingClient, ReplayClient, get_client

from ops_agent import SYSTEM, TASK, AgentRun, run_agent
from policies import promote_policy
from trajectory_checks import trajectory_summary
from world import FaultPlan, OpsWorld


def _sha(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()[:12]


def meta_for(system: str, model: str = DEFAULT_MODEL, world_seed: int = 7) -> dict[str, Any]:
    return {"system_sha": _sha(system), "tools_sha": _sha(OpsWorld.tool_schemas()),
            "model": model, "world_seed": world_seed}


def record(cassette: Path, *, system: str = SYSTEM, seed: int = 7, faults: FaultPlan | None = None) -> AgentRun:
    """Record one run. Offline the 'real' model is the scripted policy; with a key it is the API."""
    inner = get_client(fake=FakeClient(promote_policy()))
    rec = RecordingClient(inner, cassette)
    run = run_agent(rec, OpsWorld(seed=seed, faults=faults), TASK, system=system)
    Path(f"{cassette}.meta.json").write_text(json.dumps(meta_for(system, world_seed=seed), indent=2))
    return run


def replay(cassette: Path, *, system: str = SYSTEM, seed: int = 7, faults: FaultPlan | None = None) -> AgentRun:
    """Re-run the agent offline. Tool calls still execute against a fresh simulated world."""
    return run_agent(ReplayClient(cassette), OpsWorld(seed=seed, faults=faults), TASK, system=system)


def cassette_staleness(cassette: Path, *, system: str = SYSTEM, model: str = DEFAULT_MODEL) -> list[str]:
    """Reasons this cassette no longer represents what production would do. Empty list = fresh."""
    meta = json.loads(Path(f"{cassette}.meta.json").read_text())
    now = meta_for(system, model=model, world_seed=meta["world_seed"])
    return [f"{k}: recorded {meta[k]!r}, now {now[k]!r}" for k in ("system_sha", "tools_sha", "model")
            if meta[k] != now[k]]


def main() -> None:
    tmp = Path(tempfile.mkdtemp())
    cas = tmp / "deploy.jsonl"
    rec = record(cas)
    print(f"recorded {len(cas.read_text().splitlines())} model calls -> {cas}")

    rep = replay(cas)
    same = trajectory_summary(rec) == trajectory_summary(rep)
    print(f"1. replay, nothing changed: identical trajectory = {same}")

    try:
        replay(cas, system=SYSTEM + "\n- Prefer canary deploys.")
    except KeyError as e:
        print(f"2. replay after a prompt edit: cassette miss, as it should be ({e})")

    try:
        replay(cas, faults=FaultPlan(transient_rate=1.0))
    except KeyError:
        print("3. replay after the world changed (tool now returns 503): cassette miss, as it should be")

    stale = cassette_staleness(cas, model="claude-opus-5-5")
    rep2 = replay(cas)  # replays fine: the model ID is not part of the request hash
    print(f"4. replay after a model upgrade: replays GREEN ({len(rep2.steps)} steps) but meta says stale: {stale}")


if __name__ == "__main__":
    main()
