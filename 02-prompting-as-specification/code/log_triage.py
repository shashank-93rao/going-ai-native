"""Log-triage classifier: a prompt with a schema, a validator, and one bounded retry.

The schema is the contract between the model and the pager router. Two layers check it:
  1. shape: mini_schema.validate (what structured outputs would guarantee for you)
  2. meaning: semantic_errors (what no schema can guarantee: evidence is really in the log, etc.)

Production note: on the Claude API you would pass the schema as
`output_config={"format": {"type": "json_schema", "schema": TRIAGE_SCHEMA}}` and get
constrained decoding. The course's `ainative_kit` client does not expose that
parameter, so this file asks for JSON in the prompt and validates locally. Keep the
local validator anyway: constrained decoding guarantees shape, not truth, and it
does not cover `stop_reason` of "refusal" or "max_tokens".

    python log_triage.py            # fake model unless ANTHROPIC_API_KEY is set
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from ainative_kit import FakeClient, LLMClient, Tracer, get_client

from mini_schema import validate

CATEGORIES = ["infra", "dependency", "app_bug", "config", "data", "noise", "unknown"]
SEVERITIES = ["page", "ticket", "ignore"]

TRIAGE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "category": {"type": "string", "enum": CATEGORIES},
        "severity": {"type": "string", "enum": SEVERITIES},
        "service": {"type": "string"},
        "summary": {"type": "string"},
        "evidence": {"type": "array", "items": {"type": "string"}, "minItems": 1},
        "needs_human": {"type": "boolean"},
    },
    "required": ["category", "severity", "service", "summary", "evidence", "needs_human"],
    "additionalProperties": False,
}

MAX_SUMMARY = 200  # structured outputs do not support maxLength, so check it here


@dataclass
class TriageResult:
    output: dict[str, Any] | None
    errors: list[str] = field(default_factory=list)
    attempts: int = 0
    raw: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.output is not None


def parse_strict(text: str) -> tuple[dict[str, Any] | None, list[str]]:
    """The router accepts exactly one JSON object. Prose around it is a contract violation."""
    try:
        obj = json.loads(text.strip())
    except json.JSONDecodeError as e:
        return None, [f"response is not a bare JSON object ({e.msg} at char {e.pos}); first 60 chars: {text[:60]!r}"]
    if not isinstance(obj, dict):
        return None, ["response JSON is not an object"]
    return obj, []


def semantic_errors(obj: dict[str, Any], excerpt: str) -> list[str]:
    errs = []
    flat = " ".join(excerpt.split())
    for line in obj.get("evidence", []):
        if " ".join(line.split()) not in flat:
            errs.append(f"evidence not found verbatim in excerpt: {line[:60]!r}")
    if len(obj.get("summary", "")) > MAX_SUMMARY:
        errs.append(f"summary is {len(obj['summary'])} chars; limit is {MAX_SUMMARY}")
    if obj.get("category") == "unknown" and obj.get("needs_human") is not True:
        errs.append("category 'unknown' requires needs_human=true")
    return errs


def check(text: str, excerpt: str, stop_reason: str = "end_turn") -> tuple[dict[str, Any] | None, list[str]]:
    if stop_reason in ("max_tokens", "refusal"):
        return None, [f"stop_reason={stop_reason}; output cannot be trusted to match the schema"]
    obj, errs = parse_strict(text)
    if obj is None:
        return None, errs
    errs = validate(obj, TRIAGE_SCHEMA) or semantic_errors(obj, excerpt)
    return (None, errs) if errs else (obj, [])


def classify(
    client: LLMClient,
    system_prompt: str,
    excerpt: str,
    *,
    retries: int = 1,
    tracer: Tracer | None = None,
    prompt_ref: str = "unversioned",
    model: str | None = None,
) -> TriageResult:
    """Classify one excerpt. On a contract violation, show the model the errors once and retry.

    The retry appends a *user* turn with the validator's errors. It never prefills an
    assistant turn (that returns a 400 on current Claude models).
    """
    tracer = tracer or Tracer()
    messages: list[dict[str, Any]] = [{"role": "user", "content": f"<excerpt>\n{excerpt}\n</excerpt>"}]
    result = TriageResult(output=None)
    with tracer.span("triage", prompt_ref=prompt_ref) as span:
        for attempt in range(retries + 1):
            resp = client.complete(messages, system=system_prompt, model=model, max_tokens=1024)
            result.attempts += 1
            result.raw.append(resp.text)
            obj, errs = check(resp.text, excerpt, resp.stop_reason)
            if obj is not None:
                result.output, result.errors = obj, []
                break
            result.errors = errs
            if attempt < retries:
                messages.append(resp.to_assistant_message())
                messages.append({"role": "user", "content": (
                    "Your response failed validation:\n- " + "\n- ".join(errs)
                    + "\nRespond again with only the corrected JSON object.")})
        span.attrs.update(attempts=result.attempts, ok=result.ok, errors=result.errors[:3])
    return result


def demo() -> None:
    from prompt_registry import Registry
    from sim_model import simulated_model

    reg = Registry.load()
    pv = reg.resolve("log_triage", "stable")
    system = pv.render(services="orders-api, payments-api, ledger-worker, search-api, billing-consumer")
    excerpt = ("2026-10-02T03:20:11Z payments-api POST /v1/charges 502\n"
               "2026-10-02T03:20:11Z payments-api upstream stripe returned 429 Too Many Requests")
    client = get_client(fake=FakeClient(simulated_model))
    res = classify(client, system, excerpt, prompt_ref=pv.ref)
    print(f"prompt: {pv.ref}  attempts: {res.attempts}  ok: {res.ok}")
    print(json.dumps(res.output, indent=2) if res.ok else res.errors)


if __name__ == "__main__":
    demo()
