"""Retry-with-feedback: validate model output, feed the exact errors back, bounded.

The loop is a feedback controller with three governors:
  1. max_attempts      - a hard cap (cost bound)
  2. no-progress stop  - the same error set twice in a row means feedback isn't converging
  3. kind of failure   - truncation and parse errors get specific feedback, not a generic "try again"

Run it:  python repair_loop.py         (offline fake unless ANTHROPIC_API_KEY is set)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from ainative_kit import FakeClient, Tracer, get_client, text
from validators import (
    TRIAGE_CHECKS,
    TRIAGE_SCHEMA,
    SemanticCheck,
    ValidationError,
    extract_json,
    format_errors_for_model,
    make_evidence_grounding_check,
    run_semantic_checks,
    validate,
)


@dataclass
class Attempt:
    n: int
    raw: str
    errors: list[ValidationError]


@dataclass
class RepairResult:
    ok: bool
    value: Any
    stop_reason: str  # "valid" | "max_attempts" | "no_progress"
    attempts: list[Attempt] = field(default_factory=list)


FEEDBACK_TEMPLATE = """Your previous output failed validation. Errors:
<validation_errors>
{errors}
</validation_errors>
Return the complete corrected JSON object and nothing else. Change only what the errors require;
keep every other field as it was. If a field cannot be filled truthfully from the input, use the
schema's 'unknown' option or lower confidence rather than inventing a value."""


def check_output(raw: str, schema: dict[str, Any], checks: list[tuple[str, SemanticCheck]]) -> tuple[Any, list[ValidationError]]:
    """Parse, then schema-validate, then semantic-check. Semantic checks only run on schema-valid data."""
    obj, errs = extract_json(raw)
    if errs:
        return None, errs
    errs = validate(obj, schema)
    if errs:
        return obj, errs
    return obj, run_semantic_checks(obj, checks)


def repair_loop(
    client,
    prompt: str,
    schema: dict[str, Any],
    checks: list[tuple[str, SemanticCheck]] | None = None,
    *,
    system: str | None = None,
    max_attempts: int = 3,
    feedback: bool = True,
    tracer: Tracer | None = None,
    max_tokens: int = 1024,
) -> RepairResult:
    """Ask for JSON, validate, and on failure retry. With feedback=False this is a blind re-sample."""
    checks = checks or []
    tracer = tracer or Tracer()
    messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
    attempts: list[Attempt] = []
    prev_fingerprint: frozenset[str] | None = None

    with tracer.span("repair_loop", max_attempts=max_attempts, feedback=feedback) as root:
        for n in range(1, max_attempts + 1):
            with tracer.span("attempt", n=n) as sp:
                resp = client.complete(messages, system=system, max_tokens=max_tokens)
                obj, errs = check_output(resp.text, schema, checks)
                if resp.stop_reason == "max_tokens":
                    errs = [ValidationError("$", f"output truncated at max_tokens={max_tokens}; be more concise", "parse")] + errs
                sp.attrs.update(errors=len(errs), kinds=sorted({e.kind for e in errs}))
            attempts.append(Attempt(n, resp.text, errs))

            if not errs:
                root.attrs["stop_reason"] = "valid"
                return RepairResult(True, obj, "valid", attempts)

            fingerprint = frozenset(str(e) for e in errs)
            if fingerprint == prev_fingerprint:
                root.attrs["stop_reason"] = "no_progress"
                return RepairResult(False, obj, "no_progress", attempts)
            prev_fingerprint = fingerprint

            if feedback:
                messages = messages + [
                    {"role": "assistant", "content": resp.text or "(empty)"},
                    {"role": "user", "content": FEEDBACK_TEMPLATE.format(errors=format_errors_for_model(errs))},
                ]
            # feedback=False: keep `messages` unchanged and simply re-sample.

        root.attrs["stop_reason"] = "max_attempts"
        return RepairResult(False, obj, "max_attempts", attempts)


# --- Demo: triage a Kafka consumer-lag page into a ticket --------------------

ALERT = """[PagerDuty] HIGH: orders-consumer lag > 500k on topic orders.v2
host=orders-consumer-7 group=orders-billing
2026-10-19T03:12:44Z WARN Rebalance triggered: member orders-consumer-3 left group (max.poll.interval.ms exceeded)
2026-10-19T03:12:51Z WARN Rebalance triggered: member orders-consumer-5 left group (max.poll.interval.ms exceeded)
2026-10-19T03:13:02Z INFO Assigned partitions [4, 5, 11] to orders-consumer-7
2026-10-19T03:13:40Z WARN Rebalance triggered: member orders-consumer-3 left group (max.poll.interval.ms exceeded)"""

PROMPT = f"""Triage this page into a ticket. Output a single JSON object matching this schema:
{json.dumps(TRIAGE_SCHEMA, indent=1)}
Quote evidence lines verbatim from the input.

<alert>
{ALERT}
</alert>"""

_BAD_1 = """```json
{"service": "orders-consumer", "severity": "SEV1", "category": "rebalance_storm",
 "affected_partitions": [4, 5, 11, 5], "summary": "Rebalance storm.", "confidence": 85}
```"""
_BAD_2 = json.dumps({
    "service": "orders-consumer", "severity": "sev1", "category": "rebalance_storm",
    "affected_partitions": [4, 5, 11], "confidence": 0.85,
    "summary": "Repeated rebalances in group orders-billing as members exceed max.poll.interval.ms; lag > 500k on orders.v2.",
    "evidence": ["member orders-consumer-3 left group because poll interval exceeded"],
    "runbook_url": "https://runbooks.internal/kafka/rebalance-storm",
})
_GOOD = json.dumps({
    "service": "orders-consumer", "severity": "sev1", "category": "rebalance_storm",
    "affected_partitions": [4, 5, 11], "confidence": 0.85,
    "summary": "Repeated rebalances in group orders-billing as members exceed max.poll.interval.ms; lag > 500k on orders.v2.",
    "evidence": ["member orders-consumer-3 left group (max.poll.interval.ms exceeded)"],
    "runbook_url": "https://runbooks.internal/kafka/rebalance-storm",
})


def demo_fake() -> FakeClient:
    return FakeClient([text(_BAD_1), text(_BAD_2), text(_GOOD)])


def main() -> None:
    client = get_client(fake=demo_fake())
    checks = TRIAGE_CHECKS + [("evidence_grounded", make_evidence_grounding_check(ALERT))]
    result = repair_loop(client, PROMPT, TRIAGE_SCHEMA, checks, max_attempts=3)
    for a in result.attempts:
        print(f"--- attempt {a.n}: {len(a.errors)} error(s)")
        for e in a.errors:
            print(f"    [{e.kind}] {e}")
    print(f"=> ok={result.ok} stop_reason={result.stop_reason}")
    if result.ok:
        print(json.dumps(result.value, indent=2))


if __name__ == "__main__":
    main()
