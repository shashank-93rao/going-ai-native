"""A deliberately small JSON Schema validator.

It covers the subset that Anthropic's structured outputs accept and that this
module's schemas use: type, enum, const, required, properties,
additionalProperties: false, items, and minItems (0 or 1).

Why write one instead of importing `jsonschema`? The course venv does not have
it, and seeing the whole validator in ~70 lines makes the point that a schema
is a *contract you can check*, the same way you would check an Avro or
protobuf payload at a service boundary.
"""

from __future__ import annotations

from typing import Any

_TYPES: dict[str, tuple[type, ...]] = {
    "object": (dict,),
    "array": (list,),
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "null": (type(None),),
}


def _type_ok(value: Any, expected: str) -> bool:
    # bool is a subclass of int in Python; JSON does not agree.
    if expected in ("integer", "number") and isinstance(value, bool):
        return False
    return isinstance(value, _TYPES[expected])


def validate(value: Any, schema: dict[str, Any], path: str = "$") -> list[str]:
    """Return a list of human-readable errors. An empty list means valid."""
    errors: list[str] = []

    expected = schema.get("type")
    if expected is not None:
        options = expected if isinstance(expected, list) else [expected]
        if not any(_type_ok(value, t) for t in options):
            return [f"{path}: expected {expected}, got {type(value).__name__}"]

    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: expected const {schema['const']!r}, got {value!r}")

    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: {value!r} is not one of {schema['enum']}")

    if isinstance(value, dict):
        props: dict[str, Any] = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{path}: missing required field {key!r}")
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in props:
                    errors.append(f"{path}: unexpected field {key!r}")
        for key, sub in props.items():
            if key in value:
                errors.extend(validate(value[key], sub, f"{path}.{key}"))

    if isinstance(value, list):
        min_items = schema.get("minItems")
        if min_items is not None and len(value) < min_items:
            errors.append(f"{path}: expected at least {min_items} item(s), got {len(value)}")
        item_schema = schema.get("items")
        if item_schema:
            for i, item in enumerate(value):
                errors.extend(validate(item, item_schema, f"{path}[{i}]"))

    return errors
