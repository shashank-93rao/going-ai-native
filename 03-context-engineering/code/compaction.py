"""Compaction with a verifiable contract, plus the lighter and heavier alternatives.

Three tools, from lightest to heaviest:

- `clear_tool_results`: replace old tool outputs with a placeholder. No model
  call. The client-side analogue of the API's tool-result clearing.
- `compact`: summarize everything before a safe split point with a model call,
  keep the recent tail verbatim, and *check* that pinned facts survived. Any
  fact the summary dropped is re-attached and reported.
- `EventLog`: an append-only log the evicted turns are written to, so
  compaction is not an irreversible decision; the agent can query it later.

Messages use the Anthropic shape: {"role": ..., "content": str | [blocks]}.

    python compaction.py
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from ainative_kit import FakeClient, LLMClient, get_client, text

SUMMARY_SYSTEM = """You compact an agent's working history so it can continue the task.
Keep, verbatim where possible:
- the task goal and any constraints the user stated
- decisions made and the reason for each
- identifiers: incident ids, file paths, commit SHAs, topic and partition numbers, ticket ids
- open problems, failed approaches and why they failed
- the next step
Drop: raw tool output already acted on, repeated logs, pleasantries.
Write terse bullet points under the headings Goal, Decisions, Facts, Failed approaches, Next step."""

PLACEHOLDER = "[tool result cleared to save context; re-run the tool if needed]"

# Facts the harness refuses to lose. Extend per domain. The point is that the
# compaction contract is checked by code, not trusted to the summarizer.
DEFAULT_PIN_PATTERNS = [
    r"\bINC-\d+\b",  # incident ids
    r"\bcommit\s+[0-9a-f]{7,40}\b",  # "commit 3f9c2ab"
    r"\b(?:DECISION|CONSTRAINT):[^\n]*",  # explicit markers, anywhere in a line
    r"(?:[\w.-]+/)+[\w.-]+\.\w+",  # file paths with a directory
]


def content_text(content: Any) -> str:
    """Flatten a message's content (str or block list) into plain text."""
    if isinstance(content, str):
        return content
    parts = []
    for b in content:
        t = b.get("type")
        if t == "text":
            parts.append(b["text"])
        elif t == "tool_use":
            parts.append(f"[tool_use {b['name']} {json.dumps(b.get('input', {}))}]")
        elif t == "tool_result":
            inner = b.get("content", "")
            parts.append(f"[tool_result] {content_text(inner) if not isinstance(inner, str) else inner}")
    return "\n".join(parts)


def render_transcript(messages: list[dict]) -> str:
    return "\n\n".join(f"{m['role'].upper()}: {content_text(m['content'])}" for m in messages)


def _has_tool_result(msg: dict) -> bool:
    c = msg["content"]
    return not isinstance(c, str) and any(b.get("type") == "tool_result" for b in c)


def clear_tool_results(messages: list[dict], keep_last: int = 3) -> tuple[list[dict], int]:
    """Replace all but the newest `keep_last` tool results with a placeholder.

    Returns (new_messages, n_cleared). The tool_use blocks stay, so the model
    still sees *that* it called the tool and with what input. Note: clearing
    changes earlier bytes, so it invalidates the prompt cache from that point.
    """
    positions = [(i, j) for i, m in enumerate(messages) if not isinstance(m["content"], str)
                 for j, b in enumerate(m["content"]) if b.get("type") == "tool_result"]
    to_clear = set(positions[:-keep_last] if keep_last else positions)
    out = []
    for i, m in enumerate(messages):
        if isinstance(m["content"], str):
            out.append(dict(m))
            continue
        blocks = []
        for j, b in enumerate(m["content"]):
            blocks.append({**b, "content": PLACEHOLDER} if (i, j) in to_clear else dict(b))
        out.append({**m, "content": blocks})
    return out, len(to_clear)


def safe_split(messages: list[dict], keep_last: int) -> int:
    """Index where the verbatim tail starts.

    The tail must begin with a plain user turn: never with an assistant turn,
    and never with a user turn holding tool_results, which would orphan them
    from the tool_use blocks that were summarized away (the API rejects that).
    """
    i = max(len(messages) - keep_last, 0)
    while i > 0 and (messages[i]["role"] != "user" or _has_tool_result(messages[i])):
        i -= 1
    return i


@dataclass
class EventLog:
    """Append-only, queryable history. Compaction writes evicted turns here."""

    events: list[dict] = field(default_factory=list)

    def append(self, msg: dict) -> int:
        self.events.append(json.loads(json.dumps(msg)))
        return len(self.events) - 1

    def slice(self, start: int, end: int | None = None) -> list[dict]:
        return self.events[start:end]

    def grep(self, pattern: str) -> list[tuple[int, str]]:
        rx = re.compile(pattern)
        return [(i, content_text(e["content"])) for i, e in enumerate(self.events) if rx.search(content_text(e["content"]))]


@dataclass
class CompactionResult:
    messages: list[dict]
    summary: str
    pinned: list[str]
    missing_from_summary: list[str]  # pinned facts the summarizer dropped (re-attached)
    evicted: int
    log_range: tuple[int, int] | None


def extract_pinned(transcript: str, patterns: list[str]) -> list[str]:
    seen: dict[str, None] = {}
    for p in patterns:
        for m in re.finditer(p, transcript):
            seen.setdefault(m.group(0).strip(), None)
    return list(seen)


def compact(
    messages: list[dict],
    client: LLMClient,
    *,
    keep_last: int = 4,
    pin_patterns: list[str] | None = None,
    log: EventLog | None = None,
    max_tokens: int = 1500,
) -> CompactionResult:
    """Summarize the head of the conversation, keep the tail, verify pinned facts."""
    split = safe_split(messages, keep_last)
    head, tail = messages[:split], messages[split:]
    if not head:
        return CompactionResult([dict(m) for m in messages], "", [], [], 0, None)

    transcript = render_transcript(head)
    pinned = extract_pinned(transcript, pin_patterns or DEFAULT_PIN_PATTERNS)
    resp = client.complete(
        [{"role": "user", "content": f"<history>\n{transcript}\n</history>\n\nCompact this history."}],
        system=SUMMARY_SYSTEM,
        max_tokens=max_tokens,
    )
    summary = resp.text.strip()
    missing = [f for f in pinned if f not in summary]
    if missing:  # the check: re-attach what the summarizer lost
        summary += "\n\nPinned facts (restored by harness):\n" + "\n".join(f"- {f}" for f in missing)

    log_range = None
    if log is not None:
        first = len(log.events)
        for m in head:
            log.append(m)
        log_range = (first, len(log.events))
        summary += f"\n\nFull earlier history: event log entries {first}..{len(log.events) - 1} (query with grep/slice)."

    block = f"<compacted_history>\n{summary}\n</compacted_history>"
    if tail:
        first_msg = tail[0]
        c = first_msg["content"]
        merged = f"{block}\n\n{c}" if isinstance(c, str) else [{"type": "text", "text": block}, *c]
        new_messages = [{**first_msg, "content": merged}, *[dict(m) for m in tail[1:]]]
    else:
        new_messages = [{"role": "user", "content": block + "\n\nContinue the task."}]
    return CompactionResult(new_messages, summary, pinned, missing, len(head), log_range)


def lossy_fake_summarizer(drop: Callable[[str], bool]) -> FakeClient:
    """A FakeClient that 'summarizes' by keeping only lines `drop` rejects, like a careless model."""

    def respond(messages, kwargs):
        hist = messages[0]["content"].split("</history>")[0]
        kept: dict[str, None] = {}
        for ln in hist.splitlines():
            if ln.strip() and not ln.startswith("<") and "[tool_result]" not in ln and not drop(ln):
                kept.setdefault(ln.strip()[:160], None)
        return text("\n".join(f"- {ln}" for ln in list(kept)[:12]))

    return FakeClient(respond)


def demo_history() -> list[dict]:
    return [
        {"role": "user", "content": "INC-7731: invoice-consumer lag on invoices.v2. CONSTRAINT: do not reset offsets.\nCONSTRAINT: no deploys before 09:00 UTC."},
        {"role": "assistant", "content": [{"type": "tool_use", "id": "t1", "name": "get_logs", "input": {"service": "invoice-consumer"}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "WARN Revoking previously assigned partitions\n" * 50}]},
        {"role": "assistant", "content": "Rebalance storm. Batch takes ~45s; max.poll.interval.ms is 30000 in deploy/invoice-consumer/values.yaml."},
        {"role": "user", "content": "DECISION: raise max.poll.interval.ms to 300000, keep batch size. Commit it."},
        {"role": "assistant", "content": "Committed in commit 3f9c2ab: deploy/invoice-consumer/values.yaml."},
        {"role": "user", "content": "Lag is still 60k on partition 7 only. Why?"},
        {"role": "assistant", "content": "Partition 7 alone suggests a poison message, not throughput."},
        {"role": "user", "content": "Check offset 99120 on p7."},
    ]


if __name__ == "__main__":
    # Fake summarizer that drops every CONSTRAINT line: the failure we must catch.
    fake = lossy_fake_summarizer(lambda ln: "CONSTRAINT" in ln)
    client = get_client(fake=fake)
    log = EventLog()
    result = compact(demo_history(), client, keep_last=3, log=log)
    print(f"evicted {result.evicted} messages; pinned {len(result.pinned)} facts")
    print(f"summarizer dropped: {result.missing_from_summary}")
    print(result.messages[0]["content"][:1200])
    print("\nlog grep 'Revoking':", len(log.grep("Revoking")), "entries")
