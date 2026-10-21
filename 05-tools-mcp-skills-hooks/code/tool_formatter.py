"""Format tool results for a model: concise vs detailed, a token budget, truncation with guidance.

A tool response is a message to an unreliable reader with a small, expensive buffer.
Three rules, all from Anthropic's "Writing effective tools for agents":
  1. Return only high-signal fields by default (`response_format="concise"`), and keep IDs
     available on request (`"detailed"`), because the next call may need them.
  2. Never return an unbounded payload. Truncate to a budget, and say *how* to get the rest.
  3. When you refuse or truncate, the message must tell the model its next move.

`ToolError` is the one exception type a tool should raise for "the model did something
fixable". Its message is written for the model and is returned as an `is_error` tool result.
"""

from __future__ import annotations

import json
from typing import Any, Iterable

CHARS_PER_TOKEN = 4  # crude, but stable; good enough for budgeting tool output
RESPONSE_FORMATS = ("concise", "detailed")


class ToolError(Exception):
    """An error whose message is addressed to the model and says how to fix the call."""


def estimate_tokens(s: str) -> int:
    """Rough token estimate (chars / 4). Use the real token-counting API for billing."""
    return max(1, len(s) // CHARS_PER_TOKEN)


def check_response_format(value: str) -> str:
    if value not in RESPONSE_FORMATS:
        raise ToolError(
            f"response_format must be one of {list(RESPONSE_FORMATS)}, got {value!r}. "
            "Use 'concise' (default) to read results, 'detailed' when you need IDs for a follow-up call."
        )
    return value


def _concise_line(rec: dict[str, Any], fields: Iterable[str]) -> str:
    return " | ".join(f"{f}={rec[f]}" for f in fields if f in rec and rec[f] not in (None, ""))


def _detailed_line(rec: dict[str, Any]) -> str:
    return json.dumps(rec, sort_keys=True, default=str)


def format_records(
    records: list[dict[str, Any]],
    *,
    response_format: str = "concise",
    concise_fields: list[str],
    max_tokens: int = 1500,
    total: int | None = None,
    next_cursor: str | None = None,
    noun: str = "results",
    refine_hint: str = "",
) -> str:
    """Render records into a budgeted text block.

    - concise: one `k=v | k=v` line per record, only `concise_fields`.
    - detailed: one JSON object per line, every field (including IDs).
    The header always states how many were shown out of how many matched, so the model
    never mistakes a page for the whole answer.
    """
    check_response_format(response_format)
    total = len(records) if total is None else total
    if not records:
        hint = f" {refine_hint}" if refine_hint else ""
        return f"0 {noun} matched.{hint}"

    render = (lambda r: _concise_line(r, concise_fields)) if response_format == "concise" else _detailed_line
    budget_chars = max_tokens * CHARS_PER_TOKEN
    lines: list[str] = []
    used = 0
    for rec in records:
        line = render(rec)
        if used + len(line) + 1 > budget_chars and lines:
            break
        lines.append(line)
        used += len(line) + 1

    shown = len(lines)
    header = f"{shown} of {total} {noun} ({response_format})."
    footer: list[str] = []
    if shown < len(records):
        footer.append(
            f"[truncated at ~{max_tokens} tokens: {len(records) - shown} more {noun} on this page not shown. "
            f"{refine_hint or 'Narrow the query'} or request a smaller `limit`.]"
        )
    if next_cursor:
        footer.append(f"[more {noun} available: call again with cursor={next_cursor!r} to get the next page.]")
    elif shown == len(records) and total > shown:
        footer.append(f"[{total - shown} more {noun} matched but were not returned. {refine_hint}]".rstrip())
    return "\n".join([header, *lines, *footer])


def truncate_text(text: str, *, max_tokens: int, hint: str) -> str:
    """Keep the head and tail of a long blob (logs, stack traces) and say what was cut."""
    budget = max_tokens * CHARS_PER_TOKEN
    if len(text) <= budget:
        return text
    head, tail = text[: budget * 2 // 3], text[-budget // 3 :]
    cut = len(text) - len(head) - len(tail)
    return f"{head}\n[... {cut} chars (~{cut // CHARS_PER_TOKEN} tokens) omitted. {hint} ...]\n{tail}"
