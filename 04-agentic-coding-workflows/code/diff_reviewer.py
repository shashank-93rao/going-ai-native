"""Clean-context reviewer: check a diff against SPEC.md and return structured findings.

The reviewer sees only the spec and the diff, never the implementing session's
reasoning, so it judges the result on its own terms (Claude Code docs, "Add an
adversarial review step"). Two guards against the known failure mode that a
reviewer asked for gaps always finds some:

1. The prompt asks only for gaps that affect correctness or a stated requirement.
2. Code drops any finding without a file, a line, and quoted evidence, and drops
   the "style" category entirely.

    python diff_reviewer.py --spec SPEC.md --diff change.diff
    (uses the real API if ANTHROPIC_API_KEY is set, otherwise a canned fake)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    from ainative_kit import FakeClient, LLMClient, get_client, text
except ImportError:  # running as a script from this folder without PYTHONPATH=shared
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "shared"))
    from ainative_kit import FakeClient, LLMClient, get_client, text

SYSTEM = """You review a code diff against its spec. You did not write this code.
Report only gaps that would make the change incorrect or violate a requirement,
invariant, or out-of-scope rule in the spec. Do not report style or naming.
For each finding, quote the exact diff line(s) as evidence.
Reply with JSON only: {"findings": [{"category": "correctness|requirement|scope|test",
"severity": "high|medium|low", "file": str, "line": int, "claim": str, "evidence": str}]}.
If there are no such gaps, reply {"findings": []}."""

ALLOWED = {"correctness", "requirement", "scope", "test"}


@dataclass
class Finding:
    category: str
    severity: str
    file: str
    line: int
    claim: str
    evidence: str


def build_prompt(spec: str, diff: str) -> str:
    return f"<spec>\n{spec}\n</spec>\n\n<diff>\n{diff}\n</diff>\n\nReview the diff against the spec."


def parse_findings(raw: str, diff: str) -> list[Finding]:
    """Parse model JSON, then keep only findings with evidence that really appears in the diff."""
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        raise ValueError("reviewer did not return JSON")
    items = json.loads(m.group(0)).get("findings", [])
    kept = []
    for it in items:
        try:
            f = Finding(str(it["category"]), str(it["severity"]), str(it["file"]),
                        int(it["line"]), str(it["claim"]), str(it["evidence"]).strip())
        except (KeyError, TypeError, ValueError):
            continue
        if f.category not in ALLOWED or not f.evidence:
            continue
        if f.evidence not in diff:  # unquotable evidence is usually a hallucinated finding
            continue
        kept.append(f)
    return kept


def review(spec: str, diff: str, client: LLMClient, model: str | None = None) -> list[Finding]:
    """One review pass with one retry if the reply is not parseable JSON."""
    messages = [{"role": "user", "content": build_prompt(spec, diff)}]
    for attempt in range(2):
        resp = client.complete(messages, system=SYSTEM, model=model, max_tokens=2000)
        try:
            return parse_findings(resp.text, diff)
        except (ValueError, json.JSONDecodeError):
            if attempt == 1:
                raise
            messages += [resp.to_assistant_message(),
                         {"role": "user", "content": "Reply with the JSON object only."}]
    return []


DEMO_SPEC = "Requirement R3: a replayed request with the same key and a different body returns 422."
DEMO_DIFF = """+++ b/payments/idempotency.py
@@ -40,3 +40,6 @@
+    if row is not None:
+        return row.response  # replay
"""
DEMO_REPLY = json.dumps({"findings": [
    {"category": "requirement", "severity": "high", "file": "payments/idempotency.py", "line": 41,
     "claim": "Replay ignores the request fingerprint, so a different body with the same key "
              "returns the old response instead of 422 (R3).",
     "evidence": "return row.response  # replay"},
    {"category": "style", "severity": "low", "file": "payments/idempotency.py", "line": 41,
     "claim": "Comment could be clearer.", "evidence": "# replay"},
]})


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec")
    ap.add_argument("--diff")
    a = ap.parse_args(argv)
    spec = Path(a.spec).read_text() if a.spec else DEMO_SPEC
    diff = Path(a.diff).read_text() if a.diff else DEMO_DIFF
    client = get_client(fake=FakeClient([text(DEMO_REPLY)]))
    findings = review(spec, diff, client)
    for f in findings:
        print(f"[{f.severity}] {f.file}:{f.line} ({f.category}) {f.claim}\n    evidence: {f.evidence}")
    print(f"{len(findings)} finding(s) kept")
    return 1 if any(f.severity == "high" for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
