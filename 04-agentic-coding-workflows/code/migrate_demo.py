"""Offline demo of the 40-call-site migration (examples.md, scenario 3).

Generates 40 small service files that call the legacy `emit_event(topic, entity)`,
plants four misbehaving targets (fail, break, flaky, lie), and runs the fan-out
driver with the fake agent and the AST verifier. No API key or network needed.

    python migrate_demo.py               # writes into a fresh temp dir (path printed)
    python migrate_demo.py --keep DIR    # keep the files and results.jsonl to inspect

To run the same thing against a real agent, swap AGENT for, e.g.:
    claude --bare -p "$(cat prompt.md) Target: $FANOUT_TARGET. Feedback: $(cat "$FANOUT_FEEDBACK")" \
      --allowedTools "Read,Edit" --permission-mode dontAsk --output-format json
"""

from __future__ import annotations

import argparse
import json
import shlex
import sys
import tempfile
import time
from pathlib import Path

from fanout import Fanout, FanoutConfig, summarize

HERE = Path(__file__).resolve().parent
PY = shlex.quote(sys.executable)
AGENT = f"{PY} {shlex.quote(str(HERE / 'fake_agent.py'))} {{target}} --feedback {{feedback}}"
VERIFY = f"{PY} {shlex.quote(str(HERE / 'check_callsite.py'))} {{target}}"

TEMPLATE = '''"""{name}: handles {entity} lifecycle events."""
{marker}
TOPIC = "{entity}.events.v1"


def on_{entity}_updated({entity}):
    {entity}["version"] += 1
    emit_event(TOPIC, {entity})
'''

ENTITIES = ["order", "payment", "refund", "invoice", "customer", "shipment", "ledger", "payout"]
MARKERS = {5: "# FAKE: fail", 12: "# FAKE: break", 20: "# FAKE: flaky", 33: "# FAKE: lie"}


def make_repo(root: Path, n: int = 40) -> list[str]:
    targets = []
    for i in range(n):
        entity = ENTITIES[i % len(ENTITIES)]
        f = root / "services" / f"svc_{i:02d}_{entity}.py"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(TEMPLATE.format(name=f.stem, entity=entity, marker=MARKERS.get(i, "")))
        targets.append(str(f))
    return targets


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", help="directory to write the demo repo into (kept afterwards)")
    ap.add_argument("--concurrency", type=int, default=8)
    a = ap.parse_args(argv)
    root = Path(a.keep) if a.keep else Path(tempfile.mkdtemp(prefix="migrate-demo-"))
    root.mkdir(parents=True, exist_ok=True)
    targets = make_repo(root)

    cfg = FanoutConfig(agent_cmd=AGENT, verify_cmd=VERIFY, concurrency=a.concurrency,
                       retries=1, agent_timeout=30, verify_timeout=30, max_failures=10)
    start = time.monotonic()
    results = Fanout(cfg, root / "results.jsonl").run(targets)
    for r in results:
        if r.status != "ok" or r.attempts > 1:
            if r.status == "ok":
                note = "recovered after verifier feedback"
            elif r.verify_tail.strip():
                note = r.verify_tail.strip().splitlines()[-1].replace(str(root) + "/", "")
            else:
                note = "agent exited non-zero / is_error"
            print(f"{r.status:14} attempts={r.attempts} claimed_ok={r.agent_claimed_ok} "
                  f"{Path(r.target).name}  <- {note}")
    print(json.dumps(summarize(results, time.monotonic() - start), indent=2))
    print(f"results: {root / 'results.jsonl'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
