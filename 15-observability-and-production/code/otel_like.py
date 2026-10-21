"""Map ainative_kit Tracer spans onto OpenTelemetry GenAI semantic-convention names.

The course tracer (`ainative_kit.Tracer`) writes flat JSONL spans with free-form
attrs. A production backend (Honeycomb, Datadog, Langfuse, LangSmith, Grafana...)
expects OTel-shaped spans with `gen_ai.*` attributes. This file is that adapter,
so you can see exactly which field lands where, and which fields are sensitive.

Course span conventions (what the rest of this module writes):

    span name     attrs we read
    -----------   -------------------------------------------------------------
    llm_call      model, response_model, input_tokens, output_tokens,
                  cache_read_tokens, cache_write_tokens, stop_reason,
                  max_tokens, temperature, effort, conversation_id,
                  prompt_name, prompt_version, response_id
                  (content, opt-in): system, messages, output
    tool_call     tool_name, tool_call_id, tool_type
                  (content, opt-in): tool_input, tool_output
    agent_run     agent_name, agent_id, agent_version, conversation_id

Attribute names follow the OTel GenAI semantic conventions (status: Development)
as published in github.com/open-telemetry/semantic-conventions-genai, checked
2026-10-19. They are still changing; pin the version you emit and re-check on upgrade.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, is_dataclass
from typing import Any, Callable

from ainative_kit import DEFAULT_MODEL, LLMClient, Response, Tracer

PROVIDER = "anthropic"

# Content attributes. The spec marks all of these Opt-In and warns they are
# likely to contain sensitive information (user data, PII).
CONTENT_KEYS = {
    "system": "gen_ai.system_instructions",
    "messages": "gen_ai.input.messages",
    "output": "gen_ai.output.messages",
    "tool_input": "gen_ai.tool.call.arguments",
    "tool_output": "gen_ai.tool.call.result",
}

# Course attr -> OTel attr, for non-content fields.
LLM_KEYS = {
    "model": "gen_ai.request.model",
    "response_model": "gen_ai.response.model",
    "response_id": "gen_ai.response.id",
    "max_tokens": "gen_ai.request.max_tokens",
    "temperature": "gen_ai.request.temperature",
    "effort": "gen_ai.request.reasoning.level",
    "conversation_id": "gen_ai.conversation.id",
    "prompt_name": "gen_ai.prompt.name",
    "prompt_version": "gen_ai.prompt.version",
    "output_tokens": "gen_ai.usage.output_tokens",
    "cache_read_tokens": "gen_ai.usage.cache_read.input_tokens",
    "cache_write_tokens": "gen_ai.usage.cache_write.input_tokens",
}
TOOL_KEYS = {"tool_name": "gen_ai.tool.name", "tool_call_id": "gen_ai.tool.call.id", "tool_type": "gen_ai.tool.type"}
AGENT_KEYS = {
    "agent_name": "gen_ai.agent.name",
    "agent_id": "gen_ai.agent.id",
    "agent_version": "gen_ai.agent.version",
    "conversation_id": "gen_ai.conversation.id",
}

# Attrs we never forward even under the app.* namespace.
DENYLIST = {"api_key", "authorization", "password", "user_email", "ip_address"}

_REDACTIONS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}"), "[REDACTED_API_KEY]"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[REDACTED_AWS_KEY]"),
    (re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"), "[REDACTED_EMAIL]"),
    (re.compile(r"\b(?:\d[ -]?){13,16}\b"), "[REDACTED_CARD]"),
]


def redact(value: Any) -> Any:
    """Scrub obvious secrets and PII from strings, recursively. A floor, not a guarantee."""
    if isinstance(value, str):
        for pat, repl in _REDACTIONS:
            value = pat.sub(repl, value)
        return value
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, dict):
        return {k: redact(v) for k, v in value.items()}
    return value


def content_hash(value: Any) -> str:
    """Stable short hash of content: lets you group identical prompts without storing them."""
    blob = json.dumps(value, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def _operation(name: str) -> str:
    return {"llm_call": "chat", "tool_call": "execute_tool", "agent_run": "invoke_agent"}.get(name, name)


def _error_type(error: str | None) -> str | None:
    """`error.type` must be low-cardinality: keep the exception class, drop the message."""
    if not error:
        return None
    return error.split(":", 1)[0].strip() or "_OTHER"


def to_otel(span: Any, *, capture_content: bool = False, redactor: Callable[[Any], Any] = redact) -> dict[str, Any]:
    """Convert one course span (dict or Span) to an OTel-shaped dict with gen_ai.* attributes.

    capture_content=False (the default, matching the spec's Opt-In level) drops prompt and
    completion bodies and records only a content hash. capture_content=True keeps them,
    passed through `redactor` first.
    """
    s = asdict(span) if is_dataclass(span) else dict(span)
    attrs: dict[str, Any] = dict(s.get("attrs") or {})
    op = _operation(s["name"])
    out: dict[str, Any] = {"gen_ai.operation.name": op}

    if op == "chat":
        out["gen_ai.provider.name"] = PROVIDER
        keymap = LLM_KEYS
        # Anthropic reports input_tokens EXCLUDING cached tokens; the convention says
        # gen_ai.usage.input_tokens = input + cache_read + cache_write.
        if "input_tokens" in attrs:
            out["gen_ai.usage.input_tokens"] = (
                int(attrs["input_tokens"]) + int(attrs.get("cache_read_tokens", 0)) + int(attrs.get("cache_write_tokens", 0))
            )
        if "stop_reason" in attrs:
            out["gen_ai.response.finish_reasons"] = [attrs["stop_reason"]]
        span_name = f"chat {attrs.get('model', '')}".strip()
        kind = "CLIENT"
    elif op == "execute_tool":
        keymap = TOOL_KEYS
        span_name = f"execute_tool {attrs.get('tool_name', '')}".strip()
        kind = "INTERNAL"
    elif op == "invoke_agent":
        keymap = AGENT_KEYS
        span_name = f"invoke_agent {attrs.get('agent_name', '')}".strip()
        kind = "INTERNAL"
    else:
        keymap, span_name, kind = {}, s["name"], "INTERNAL"

    consumed = {"input_tokens", "stop_reason"}
    for src, dst in keymap.items():
        if src in attrs and attrs[src] is not None:
            out[dst] = attrs[src]
            consumed.add(src)

    for src, dst in CONTENT_KEYS.items():
        if src not in attrs:
            continue
        consumed.add(src)
        if capture_content:
            out[dst] = redactor(attrs[src])
        else:
            out[f"app.{src}.sha256"] = content_hash(attrs[src])

    # Everything else is app-specific: namespace it so it never collides with semconv.
    for k, v in attrs.items():
        if k in consumed or k.lower() in DENYLIST:
            continue
        out[f"app.{k}"] = v

    err = _error_type(s.get("error"))
    if err:
        out["error.type"] = err
    start, end = s.get("start") or 0.0, s.get("end") or s.get("start") or 0.0
    return {
        "name": span_name,
        "kind": kind,
        "trace_id": s["trace_id"],
        "span_id": s["span_id"],
        "parent_span_id": s.get("parent_id"),
        "start_time_unix_nano": int(start * 1e9),
        "end_time_unix_nano": int(end * 1e9),
        "status": {"code": "ERROR", "message": s["error"]} if s.get("error") else {"code": "UNSET"},
        "attributes": out,
    }


class TracedClient:
    """Wrap any LLMClient so every call emits an `llm_call` span with usage and prompt version.

    Cache token counts are read from `usage.cache_read_input_tokens` /
    `usage.cache_creation_input_tokens` when the response carries them (the real
    Anthropic usage object does; the kit's Usage dataclass does not, so fakes can
    set them as extra attributes).
    """

    def __init__(self, inner: LLMClient, tracer: Tracer, *, prompt_name: str | None = None,
                 prompt_version: str | None = None, record_content: bool = True):
        self.inner, self.tracer = inner, tracer
        self.prompt_name, self.prompt_version = prompt_name, prompt_version
        self.record_content = record_content

    def complete(self, messages, *, system=None, tools=None, model=None, max_tokens=2048, temperature=None) -> Response:
        attrs: dict[str, Any] = {"model": model or DEFAULT_MODEL, "max_tokens": max_tokens}
        if temperature is not None:
            attrs["temperature"] = temperature
        if self.prompt_name:
            attrs["prompt_name"] = self.prompt_name
            attrs["prompt_version"] = self.prompt_version
        if self.record_content:
            attrs["messages"] = messages
            if system:
                attrs["system"] = system
        with self.tracer.span("llm_call", **attrs) as sp:
            resp = self.inner.complete(messages, system=system, tools=tools, model=model,
                                       max_tokens=max_tokens, temperature=temperature)
            sp.attrs.update(
                response_model=resp.model,
                input_tokens=resp.usage.input_tokens,
                output_tokens=resp.usage.output_tokens,
                cache_read_tokens=getattr(resp.usage, "cache_read_input_tokens", 0),
                cache_write_tokens=getattr(resp.usage, "cache_creation_input_tokens", 0),
                stop_reason=resp.stop_reason,
            )
            if self.record_content:
                sp.attrs["output"] = resp.text
            return resp


if __name__ == "__main__":
    from ainative_kit import FakeClient, Usage, get_client, text

    tracer = Tracer()
    fake = FakeClient([text("Lag is caused by a rebalance storm; raise max.poll.interval.ms.", usage=Usage(1240, 86))])
    client = TracedClient(get_client(fake=fake), tracer, prompt_name="kafka-triage", prompt_version="v7")
    with tracer.span("agent_run", agent_name="oncall-triage", conversation_id="inc-4821"):
        client.complete([{"role": "user", "content": "Consumer lag on orders-v2 (owner: dana@example.com)?"}],
                        system="You triage Kafka incidents.", max_tokens=300)
    for sp in tracer.spans:
        print(json.dumps(to_otel(sp), indent=2))
