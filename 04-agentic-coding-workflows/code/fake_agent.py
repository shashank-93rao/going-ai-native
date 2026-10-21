"""A deterministic stand-in for `claude -p` / `codex exec`, used by tests and the demo.

It performs one real-looking migration on a single file:

    emit_event(TOPIC, order)            # legacy: fire-and-forget, no partition key
    ->  publisher.publish(TOPIC, order, key=order["id"])

and misbehaves on purpose when the file contains a marker comment, so you can
watch the fan-out driver handle each failure mode:

    # FAKE: fail      exit 1 without touching the file (agent crash / refusal)
    # FAKE: break     write broken code (verify must catch it)
    # FAKE: flaky     write broken code on the first attempt, fix it once feedback exists
    # FAKE: lie       change nothing but still print "OK" (verify must catch it)
    # FAKE: sleep=N   sleep N seconds first (timeouts, concurrency tests)

Like `claude -p --output-format json`, it prints one JSON object with `result`,
`is_error` and `total_cost_usd` (a made-up cost so cost accounting can be tested).

Usage: python fake_agent.py TARGET [--feedback FILE]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

CALL = re.compile(r"emit_event\((\w+), (\w+)\)")


def migrate(src: str) -> str:
    return CALL.sub(lambda m: f'publisher.publish({m[1]}, {m[2]}, key={m[2]}["id"])', src)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("target")
    ap.add_argument("--feedback", default="")
    a = ap.parse_args(argv)

    path = Path(a.target)
    src = path.read_text()
    markers = set(re.findall(r"# FAKE: (\S+)", src))
    for m in markers:
        if m.startswith("sleep="):
            time.sleep(float(m.split("=", 1)[1]))
    has_feedback = bool(a.feedback) and Path(a.feedback).exists() and Path(a.feedback).read_text().strip()

    def report(result: str, is_error: bool = False) -> None:
        print(json.dumps({"type": "result", "result": result, "is_error": is_error,
                          "total_cost_usd": 0.01}))

    if "fail" in markers:
        report("I could not complete this migration. FAIL", is_error=True)
        return 1
    if "lie" in markers:
        report(f"Migrated {path.name}. OK")
        return 0
    out = migrate(src)
    if has_feedback:
        out = out.replace("key=(", "key=")  # "read the verifier output and repair the file"
    if "break" in markers or ("flaky" in markers and not has_feedback):
        out = out.replace('key=', 'key=(', 1)  # unbalanced paren: a syntax error
    path.write_text(out)
    report(f"Migrated {path.name}. OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
