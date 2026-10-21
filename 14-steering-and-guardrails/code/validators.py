"""A small JSON-Schema-lite validator plus semantic checks, with model-readable errors.

Why not just rely on structured outputs? Constrained decoding guarantees *shape*
(valid JSON, required keys, types, enums). It does not enforce numeric ranges,
string lengths, or any rule that spans two fields, and it says nothing about
whether the values are true. Anthropic's structured-outputs docs list
`minimum`/`maximum`/`minLength`/`maxLength` as unsupported in the decoder, and
the SDK helpers re-check them locally. This file is that local check.

Supported keywords: type, properties, required, additionalProperties (bool),
enum, const, minimum, maximum, minLength, maxLength, pattern, items,
minItems, maxItems.

    errors = validate(obj, TRIAGE_SCHEMA) + run_semantic_checks(obj, TRIAGE_CHECKS)
    feedback = format_errors_for_model(errors)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable

_TYPES: dict[str, tuple[type, ...]] = {
    "object": (dict,),
    "array": (list,),
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "null": (type(None),),
}


@dataclass(frozen=True)
class ValidationError:
    path: str  # JSON-pointer-ish: "$.affected_partitions[2]"
    message: str
    kind: str = "schema"  # "parse" | "schema" | "semantic"

    def __str__(self) -> str:
        return f"{self.path}: {self.message}"


def _type_ok(value: Any, expected: str) -> bool:
    # bool is a subclass of int in Python; JSON does not agree.
    if expected in ("integer", "number") and isinstance(value, bool):
        return False
    return isinstance(value, _TYPES[expected])


def validate(value: Any, schema: dict[str, Any], path: str = "$") -> list[ValidationError]:
    """Return every violation (not just the first), so one retry can fix them all."""
    errs: list[ValidationError] = []
    expected = schema.get("type")
    if expected is not None:
        options = expected if isinstance(expected, list) else [expected]
        if not any(_type_ok(value, t) for t in options):
            got = "null" if value is None else type(value).__name__
            return [ValidationError(path, f"expected type {'|'.join(options)}, got {got}")]

    if "const" in schema and value != schema["const"]:
        errs.append(ValidationError(path, f"must equal {schema['const']!r}"))
    if "enum" in schema and value not in schema["enum"]:
        errs.append(ValidationError(path, f"{value!r} is not one of {schema['enum']}"))

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errs.append(ValidationError(path, f"{value} is below minimum {schema['minimum']}"))
        if "maximum" in schema and value > schema["maximum"]:
            errs.append(ValidationError(path, f"{value} is above maximum {schema['maximum']}"))

    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errs.append(ValidationError(path, f"length {len(value)} is below minLength {schema['minLength']}"))
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errs.append(ValidationError(path, f"length {len(value)} exceeds maxLength {schema['maxLength']}"))
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errs.append(ValidationError(path, f"{value!r} does not match pattern {schema['pattern']!r}"))

    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            errs.append(ValidationError(path, f"has {len(value)} items, minItems is {schema['minItems']}"))
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errs.append(ValidationError(path, f"has {len(value)} items, maxItems is {schema['maxItems']}"))
        if "items" in schema:
            for i, item in enumerate(value):
                errs.extend(validate(item, schema["items"], f"{path}[{i}]"))

    if isinstance(value, dict):
        props: dict[str, Any] = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                errs.append(ValidationError(f"{path}.{key}", "is required but missing"))
        for key, sub in props.items():
            if key in value:
                errs.extend(validate(value[key], sub, f"{path}.{key}"))
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in props:
                    errs.append(ValidationError(f"{path}.{key}", "is not an allowed property"))
    return errs


SemanticCheck = Callable[[dict[str, Any]], list[str]]


def run_semantic_checks(obj: Any, checks: list[tuple[str, SemanticCheck]]) -> list[ValidationError]:
    """Cross-field rules. Each check returns a list of messages (empty means pass)."""
    if not isinstance(obj, dict):
        return []
    out: list[ValidationError] = []
    for name, check in checks:
        for msg in check(obj):
            out.append(ValidationError(f"$ (rule {name})", msg, kind="semantic"))
    return out


_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def extract_json(text: str) -> tuple[Any, list[ValidationError]]:
    """Parse model text as JSON. Tolerates one ```json fence; nothing cleverer.

    Being lenient here is a choice: a fence is harmless, but "find the first {"
    heuristics silently accept prose-wrapped output and hide prompt problems.
    """
    candidate = text.strip()
    m = _FENCE.search(candidate)
    if m:
        candidate = m.group(1).strip()
    try:
        return json.loads(candidate), []
    except json.JSONDecodeError as e:
        snippet = candidate[max(0, e.pos - 20): e.pos + 20].replace("\n", "\\n")
        return None, [ValidationError("$", f"invalid JSON: {e.msg} at char {e.pos} near {snippet!r}", kind="parse")]


def format_errors_for_model(errors: list[ValidationError], limit: int = 10) -> str:
    """Compact, actionable feedback. Cap the list so a garbage output can't flood context."""
    lines = [f"- {e}" for e in errors[:limit]]
    if len(errors) > limit:
        lines.append(f"- ...and {len(errors) - limit} more")
    return "\n".join(lines)


# --- The worked-example schema: triaging a consumer-lag page into a ticket ----

TRIAGE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["service", "severity", "category", "affected_partitions", "summary", "confidence"],
    "additionalProperties": False,
    "properties": {
        "service": {"type": "string", "pattern": r"^[a-z][a-z0-9-]{2,40}$"},
        "severity": {"enum": ["sev1", "sev2", "sev3"]},
        "category": {"enum": ["consumer_lag", "broker_outage", "poison_message", "rebalance_storm", "unknown"]},
        "affected_partitions": {"type": "array", "items": {"type": "integer", "minimum": 0}, "maxItems": 256},
        "summary": {"type": "string", "minLength": 20, "maxLength": 280},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "runbook_url": {"type": "string", "pattern": r"^https://runbooks\.internal/"},
        "evidence": {"type": "array", "items": {"type": "string", "maxLength": 200}, "maxItems": 5},
    },
}


def _sev1_needs_runbook(o: dict[str, Any]) -> list[str]:
    if o.get("severity") == "sev1" and not o.get("runbook_url"):
        return ["severity sev1 requires runbook_url (on-call must have a next step)"]
    return []


def _unknown_means_low_confidence(o: dict[str, Any]) -> list[str]:
    if o.get("category") == "unknown" and isinstance(o.get("confidence"), (int, float)) and o["confidence"] > 0.5:
        return ["category 'unknown' with confidence > 0.5 is contradictory; lower confidence or pick a category"]
    return []


def _partitions_unique(o: dict[str, Any]) -> list[str]:
    parts = o.get("affected_partitions")
    if isinstance(parts, list) and len(parts) != len(set(map(repr, parts))):
        return ["affected_partitions contains duplicates"]
    return []


def make_evidence_grounding_check(source_text: str) -> SemanticCheck:
    """Each evidence string must appear verbatim in the input: a cheap anti-hallucination check."""

    def check(o: dict[str, Any]) -> list[str]:
        bad = [e for e in o.get("evidence", []) if isinstance(e, str) and e not in source_text]
        return [f"evidence not found verbatim in the alert/log input: {e!r}" for e in bad]

    return check


TRIAGE_CHECKS: list[tuple[str, SemanticCheck]] = [
    ("sev1_needs_runbook", _sev1_needs_runbook),
    ("unknown_low_confidence", _unknown_means_low_confidence),
    ("partitions_unique", _partitions_unique),
]
