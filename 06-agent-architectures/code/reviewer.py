"""Clean-context reviewer agents: the reviewer sees the spec and the diff, nothing else.

Three mechanical rules, each enforced in code rather than in the prompt:
  1. Context isolation: build_review_request() takes only (spec, diff). The author's
     transcript cannot leak in, so the reviewer cannot inherit the author's rationalisations.
  2. Evidence: a finding must quote a line that is actually in the diff, in a file the diff
     touches. Hallucinated findings are dropped.
  3. Severity filtering happens after the model reports everything (models follow
     "only report high severity" literally and under-report; filter in a second pass).
Optional: vote_findings() keeps findings that k of n independent reviewers agree on.

Run:  python reviewer.py
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from ainative_kit import FakeClient, LLMClient, Response, get_client
from patterns import parse_json

SEVERITY = {"nit": 0, "low": 1, "medium": 2, "high": 3}

REVIEW_SYSTEM = (
    "You review a code change against its spec. You did not write it and have no other context. "
    "Report every issue you find, including minor ones; a later step filters them. For each issue output "
    '{"file": "<path>", "severity": "high|medium|low|nit", "claim": "<what is wrong and why>", '
    '"evidence": "<one line copied exactly from the diff>"}. Output only {"findings": [...]}.'
)


@dataclass
class Finding:
    file: str
    severity: str
    claim: str
    evidence: str


@dataclass
class ReviewResult:
    kept: list[Finding]
    dropped: list[tuple[Finding, str]] = field(default_factory=list)


def build_review_request(spec: str, diff: str) -> list[dict[str, Any]]:
    """The whole context of the reviewer. Deliberately has no transcript parameter."""
    return [{"role": "user", "content": f"<spec>\n{spec}\n</spec>\n\n<diff>\n{diff}\n</diff>"}]


def diff_lines(diff: str) -> dict[str, set[str]]:
    """Map each file in a unified diff to the set of its lines (with +/-/space prefix stripped)."""
    out: dict[str, set[str]] = {}
    current = None
    for line in diff.splitlines():
        if line.startswith("+++ "):
            current = re.sub(r"^\+\+\+ (b/)?", "", line).strip()
            out[current] = set()
        elif current and line[:1] in "+- " and not line.startswith("--- "):
            out[current].add(line[1:].strip())
    return out


def review(client: LLMClient, spec: str, diff: str, *, min_severity: str = "medium") -> ReviewResult:
    raw = parse_json(client.complete(build_review_request(spec, diff), system=REVIEW_SYSTEM).text)
    lines = diff_lines(diff)
    result = ReviewResult(kept=[])
    for f in (Finding(**x) for x in raw.get("findings", [])):
        evidence = re.sub(r"^[+\- ]", "", f.evidence).strip()
        if f.file not in lines:
            result.dropped.append((f, "file not in diff"))
        elif evidence not in lines[f.file]:
            result.dropped.append((f, "evidence not found in diff"))
        elif SEVERITY.get(f.severity, 0) < SEVERITY[min_severity]:
            result.dropped.append((f, f"below {min_severity}"))
        else:
            result.kept.append(f)
    return result


def vote_findings(results: list[ReviewResult], k: int) -> list[Finding]:
    """Verifier voting: keep a finding if at least k independent reviews cite the same evidence."""
    def key(f: Finding) -> tuple[str, str]:
        return f.file, re.sub(r"^[+\- ]", "", f.evidence).strip()

    counts: Counter[tuple[str, str]] = Counter()
    first: dict[tuple[str, str], Finding] = {}
    for r in results:
        counts.update({key(f) for f in r.kept})       # one vote per reviewer per finding
        for f in r.kept:
            first.setdefault(key(f), f)
    return [first[x] for x, n in counts.items() if n >= k]


# --------------------------------------------------------------------------- the worked example

SPEC = """consumer/handler.py processes the orders topic with AT-LEAST-ONCE semantics:
- an offset is committed only after store.apply() succeeded for that message
- TransientError is retried with backoff (max 5 attempts), never skipped
- store.apply() is idempotent on msg.key, so redelivery is safe"""

DIFF = """--- a/consumer/handler.py
+++ b/consumer/handler.py
@@ -10,6 +10,10 @@ def run(consumer, store, log):
     for msg in consumer:
-        store.apply(msg.value)
-        consumer.commit(msg)
+        consumer.commit(msg)
+        try:
+            store.apply(msg.value)
+        except TransientError:
+            log.warning("apply failed, skipping %s", msg.offset)"""

AUTHOR_TRANSCRIPT = ("user: duplicates are hurting the dashboard\nassistant: I'll commit before applying so "
                     "a crash can't cause a redelivery. That removes duplicates.")


def fake_reviewer(messages: list[dict[str, Any]], kw: dict[str, Any]) -> Response:
    """Illustrative reviewer output: two real findings, one hallucinated, one nit."""
    return Response(text=json.dumps({"findings": [
        {"file": "consumer/handler.py", "severity": "high",
         "claim": "Offset is committed before apply; a crash after commit loses the message (at-most-once).",
         "evidence": "+        consumer.commit(msg)"},
        {"file": "consumer/handler.py", "severity": "high",
         "claim": "TransientError is swallowed and the message skipped; spec requires retry with backoff.",
         "evidence": '+            log.warning("apply failed, skipping %s", msg.offset)'},
        {"file": "consumer/handler.py", "severity": "medium",
         "claim": "store.flush() is no longer called after apply.", "evidence": "+        store.flush()"},
        {"file": "consumer/handler.py", "severity": "nit",
         "claim": "Log message should start with a capital letter.",
         "evidence": '+            log.warning("apply failed, skipping %s", msg.offset)'},
    ]}))


def main() -> None:
    result = review(get_client(fake=FakeClient(fake_reviewer)), SPEC, DIFF)
    for f in result.kept:
        print(f"KEEP [{f.severity}] {f.claim}")
    for f, why in result.dropped:
        print(f"DROP ({why}) {f.claim}")


if __name__ == "__main__":
    main()
