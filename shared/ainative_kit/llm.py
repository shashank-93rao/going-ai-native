"""A thin, swappable LLM client used by every module in the course.

Every example talks to models through `LLMClient.complete(...)`. That gives us
one seam where we can swap the real API for a deterministic fake (tests),
a recorder (capture real traffic), or a replayer (re-run captured traffic offline).

Same idea as hiding a remote dependency behind an interface so you can
inject faults and replay traffic.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

DEFAULT_MODEL = os.environ.get("AINATIVE_MODEL", "claude-sonnet-5-5")


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict[str, Any]


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class Response:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_reason: str = "end_turn"  # "end_turn" | "tool_use" | "max_tokens"
    usage: Usage = field(default_factory=Usage)
    model: str = DEFAULT_MODEL

    def to_assistant_message(self) -> dict[str, Any]:
        """Render this response as an assistant turn to append to `messages`."""
        content: list[dict[str, Any]] = []
        if self.text:
            content.append({"type": "text", "text": self.text})
        for tc in self.tool_calls:
            content.append({"type": "tool_use", "id": tc.id, "name": tc.name, "input": tc.input})
        return {"role": "assistant", "content": content}

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Response":
        return cls(
            text=d.get("text", ""),
            tool_calls=[ToolCall(**tc) for tc in d.get("tool_calls", [])],
            stop_reason=d.get("stop_reason", "end_turn"),
            usage=Usage(**d.get("usage", {})),
            model=d.get("model", DEFAULT_MODEL),
        )


class LLMClient(Protocol):
    def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 2048,
        temperature: float | None = None,
        tool_choice: dict[str, Any] | None = None,
        effort: str | None = None,
    ) -> Response: ...


class AnthropicClient:
    """Real client. Requires `pip install anthropic` and ANTHROPIC_API_KEY."""

    def __init__(self, model: str = DEFAULT_MODEL):
        import anthropic  # imported lazily so offline tests never need it

        self._client = anthropic.Anthropic()
        self.model = model

    def complete(self, messages, *, system=None, tools=None, model=None, max_tokens=2048, temperature=None,
                 tool_choice=None, effort=None):
        kwargs: dict[str, Any] = {"model": model or self.model, "max_tokens": max_tokens, "messages": messages}
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = tools
        if tool_choice:
            kwargs["tool_choice"] = tool_choice  # e.g. {"type": "tool", "name": "submit_verdict"}
        if effort:
            kwargs["output_config"] = {"effort": effort}  # "low" | "medium" | "high" | ...; see Module 01
        if temperature is not None:
            # Current Claude models reject sampling parameters (see Module 01). Sent raw so you see the API's answer.
            kwargs["extra_body"] = {"temperature": temperature}
        raw = self._client.messages.create(**kwargs)
        text = "".join(b.text for b in raw.content if b.type == "text")
        calls = [ToolCall(b.id, b.name, dict(b.input)) for b in raw.content if b.type == "tool_use"]
        return Response(
            text=text,
            tool_calls=calls,
            stop_reason=raw.stop_reason or "end_turn",
            usage=Usage(raw.usage.input_tokens, raw.usage.output_tokens),
            model=raw.model,
        )


Responder = Callable[[list[dict[str, Any]], dict[str, Any]], Response]


class FakeClient:
    """Deterministic stand-in for the model.

    Pass either a list of canned Responses (returned in order) or a function
    `(messages, kwargs) -> Response` that decides what the "model" says.
    Every call is recorded in `.calls` so tests can assert on what was sent.
    """

    def __init__(self, script: list[Response] | Responder):
        self._script = script
        self._i = 0
        self.calls: list[dict[str, Any]] = []

    def complete(self, messages, *, system=None, tools=None, model=None, max_tokens=2048, temperature=None,
                 tool_choice=None, effort=None):
        kwargs = {"system": system, "tools": tools, "model": model, "max_tokens": max_tokens, "temperature": temperature}
        if tool_choice is not None:
            kwargs["tool_choice"] = tool_choice
        if effort is not None:
            kwargs["effort"] = effort
        self.calls.append({"messages": json.loads(json.dumps(messages)), **kwargs})
        if callable(self._script):
            return self._script(messages, kwargs)
        if self._i >= len(self._script):
            raise RuntimeError(f"FakeClient script exhausted after {self._i} calls")
        resp = self._script[self._i]
        self._i += 1
        return resp


def _request_key(messages, kwargs) -> str:
    blob = json.dumps({"messages": messages, **kwargs}, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


class RecordingClient:
    """Wraps a real client and appends every request/response to a JSONL cassette."""

    def __init__(self, inner: LLMClient, cassette: str | Path):
        self.inner = inner
        self.path = Path(cassette)

    def complete(self, messages, **kwargs):
        resp = self.inner.complete(messages, **kwargs)
        with self.path.open("a") as f:
            f.write(json.dumps({"key": _request_key(messages, kwargs), "response": resp.to_dict()}) + "\n")
        return resp


class ReplayClient:
    """Replays a cassette written by RecordingClient. Unknown requests fail loudly."""

    def __init__(self, cassette: str | Path):
        self._by_key: dict[str, Response] = {}
        for line in Path(cassette).read_text().splitlines():
            row = json.loads(line)
            self._by_key[row["key"]] = Response.from_dict(row["response"])

    def complete(self, messages, **kwargs):
        key = _request_key(messages, kwargs)
        if key not in self._by_key:
            raise KeyError(f"No recorded response for request {key}; re-record the cassette")
        return self._by_key[key]


def get_client(fake: LLMClient | None = None) -> LLMClient:
    """Use the real API if a key is set and AINATIVE_FAKE is not set; else the given fake."""
    if os.environ.get("ANTHROPIC_API_KEY") and not os.environ.get("AINATIVE_FAKE"):
        return AnthropicClient()
    if fake is None:
        raise RuntimeError("No ANTHROPIC_API_KEY set and no fake provided. Set a key or pass fake=FakeClient(...).")
    return fake


def text(s: str, **kw: Any) -> Response:
    """Shorthand for a canned text response: text("hello")."""
    return Response(text=s, **kw)


def tool(name: str, input: dict[str, Any], id: str | None = None, text_: str = "") -> Response:
    """Shorthand for a canned tool-call response."""
    return Response(text=text_, tool_calls=[ToolCall(id or f"toolu_{name}", name, input)], stop_reason="tool_use")
