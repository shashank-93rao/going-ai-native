"""Agentic RAG: the model drives retrieval through a tool, inside a governed loop.

Single-shot RAG retrieves once with the user's words. Here the model can
rewrite the query, follow a reference ("see ADR-027") to a second search, and
decide when it has enough. That buys multi-hop answers and costs latency,
tokens and a new class of failure (loops), so the loop has governors
(Module 07): a step cap, a search cap, a context budget, a duplicate-query
breaker and a no-new-evidence breaker. The final answer must pass the same
deterministic grounding check as single-shot RAG, or it is turned into an
abstention.

The ACL is bound into the tool when the loop starts. The model never supplies
a team, so a prompt-injected "search as identity" has nothing to set (Module 16).

    PYTHONPATH=shared .venv/bin/python 18-rag-systems/code/agentic_rag.py
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ainative_kit import DEFAULT_MODEL, FakeClient, LLMClient, Response, ToolCall, Tracer, get_client

from chunking import Chunk
from hybrid import HybridRetriever, tokenize
from rag_eval import grounding_check
from rag_pipeline import NOT_COVERED, SYSTEM as RAG_SYSTEM, build_default, terms

SEARCH_TOOL = {
    "name": "search_docs",
    "description": "Search runbooks, ADRs, postmortems and guides. Returns chunks with ids to cite. "
                   "Use specific terms: service names, alert names, ADR numbers, error strings.",
    "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
}

SYSTEM = RAG_SYSTEM.replace("Use only the documents in <documents>.",
                            "Use search_docs to find documents, and use only what it returns.") + (
    "\nIf a result points to another document (for example 'ADR-027'), search for it before answering.")


@dataclass
class Limits:
    max_steps: int = 6  # model calls
    max_searches: int = 4
    max_context_words: int = 3000  # words of retrieved text fed back to the model
    no_new_evidence: int = 2  # consecutive searches that add nothing new


@dataclass
class Result:
    exit: str  # ANSWERED | ABSTAINED | UNGROUNDED | STALLED | BUDGET
    answer: str
    searches: list[str] = field(default_factory=list)
    seen: dict[str, Chunk] = field(default_factory=dict)
    steps: int = 0
    ignored_args: list[str] = field(default_factory=list)  # tool args the model may not set: a security signal


def _norm_query(q: str) -> tuple[str, ...]:
    return tuple(sorted(set(tokenize(q))))


def run(client: LLMClient, retriever: HybridRetriever, question: str, teams: frozenset[str],
        limits: Limits = Limits(), tracer: Tracer | None = None, k: int = 4, model: str = DEFAULT_MODEL) -> Result:
    tracer = tracer or Tracer()
    res = Result(exit="", answer="")
    messages: list[dict[str, Any]] = [{"role": "user", "content": f"<question>{question}</question>"}]
    seen_queries: set[tuple[str, ...]] = set()
    words, dry = 0, 0
    with tracer.span("agentic_rag", question=question) as root:
        while True:
            if res.steps >= limits.max_steps:
                res.exit = "BUDGET"
                break
            res.steps += 1
            with tracer.span("llm_call", step=res.steps):
                resp = client.complete(messages, system=SYSTEM, tools=[SEARCH_TOOL], model=model, max_tokens=800)
            messages.append(resp.to_assistant_message())
            if not resp.tool_calls:
                res.answer = resp.text.strip()
                res.exit = _finish(res)
                break
            results = []
            for call in resp.tool_calls:
                out, stop = _search(call, retriever, teams, k, limits, res, seen_queries)
                if stop:
                    res.exit = stop
                    break
                new = [c for c in out if c.id not in res.seen]
                dry = 0 if new else dry + 1
                for c in out:
                    res.seen[c.id] = c
                words += sum(len(c.text.split()) for c in new)
                body = "\n".join(f'<chunk id="{c.id}">{c.text}</chunk>' for c in out) or "no results"
                results.append({"type": "tool_result", "tool_use_id": call.id, "content": body})
            if res.exit:
                break
            if dry >= limits.no_new_evidence:
                res.exit = "STALLED"
                break
            if words > limits.max_context_words:
                res.exit = "BUDGET"
                break
            messages.append({"role": "user", "content": results})
        root.attrs.update(exit=res.exit, steps=res.steps, searches=len(res.searches), ignored_args=res.ignored_args)
    if res.exit not in ("ANSWERED",):
        res.answer = res.answer if res.exit == "ABSTAINED" else NOT_COVERED
    return res


def _search(call: ToolCall, retriever, teams, k, limits, res: Result, seen_queries) -> tuple[list[Chunk], str]:
    if call.name != "search_docs":
        return [], ""
    query = str(call.input.get("query", ""))
    res.ignored_args += sorted(set(call.input) - {"query"})  # e.g. "team": ignored by design, logged
    key = _norm_query(query)
    if key in seen_queries:
        return [], "STALLED"  # the same search twice: the model is looping
    if len(res.searches) >= limits.max_searches:
        return [], "BUDGET"
    seen_queries.add(key)
    res.searches.append(query)
    return [h.chunk for h in retriever.search(query, teams, k=k)], ""


def _finish(res: Result) -> str:
    if res.answer.startswith(NOT_COVERED):
        return "ABSTAINED"
    return "ANSWERED" if grounding_check(res.answer, list(res.seen.values())).ok else "UNGROUNDED"


def fake_agent_responder(min_overlap: int = 2):
    """A deterministic stand-in for the model's policy: search with the question;
    if any result names an ADR not yet searched, search for it; then answer with
    the best-overlapping sentence among everything seen, or abstain."""

    def respond(messages, kwargs) -> Response:
        question = re.search(r"<question>(.*?)</question>", messages[0]["content"], re.S).group(1)
        tool_texts = [b["content"] for m in messages if m["role"] == "user" and isinstance(m["content"], list)
                      for b in m["content"] if b.get("type") == "tool_result"]
        searched = [b["input"]["query"] for m in messages if m["role"] == "assistant"
                    for b in m["content"] if b.get("type") == "tool_use"]
        if not searched:
            return Response(tool_calls=[ToolCall("t0", "search_docs", {"query": question})], stop_reason="tool_use")
        refs = sorted(set(re.findall(r"ADR-\d{3}", tool_texts[-1])) - {s for s in searched})
        if refs:
            return Response(tool_calls=[ToolCall(f"t{len(searched)}", "search_docs", {"query": refs[0]})], stop_reason="tool_use")
        q, best = terms(question), (0, "", "")
        for text in tool_texts:
            for cid, body in re.findall(r'<chunk id="([^"]+)">(.*?)</chunk>', text, re.S):
                for sent in re.split(r"(?<=[.!?])\s+", body.replace("\n", " ")):
                    score = len(q & terms(sent))
                    if score > best[0]:
                        best = (score, sent.strip(), cid)
        return Response(text=NOT_COVERED if best[0] < min_overlap else f"{best[1]} [{best[2]}]")

    return respond


Q39 = "the double charge postmortem says the idempotency design was correct; what does that design say about key scope"


def scripted_multi_hop() -> list[Response]:
    """What a good model does on q39, as a script: search, follow the ADR reference, answer with a citation."""
    return [
        Response(tool_calls=[ToolCall("t1", "search_docs", {"query": "double charge postmortem idempotency design"})], stop_reason="tool_use"),
        Response(tool_calls=[ToolCall("t2", "search_docs", {"query": "ADR-012 idempotency keys decision"})], stop_reason="tool_use"),
        Response(text="Idempotency keys are scoped per merchant and stored with a 24h TTL. [adr-012-idempotency-keys#decision]"),
    ]


if __name__ == "__main__":
    r = build_default()
    single = [h.chunk.id for h in r.search(Q39, frozenset({"payments"}), k=5)]
    print("single-shot top-5:", single)
    print("  contains adr-012-idempotency-keys#decision:", "adr-012-idempotency-keys#decision" in single)
    out = run(get_client(fake=FakeClient(scripted_multi_hop())), r, Q39, frozenset({"payments"}))
    print(f"agentic: exit={out.exit} steps={out.steps} searches={out.searches}\n  answer: {out.answer}")
    q = "what is the on-call compensation rate for weekend pages"
    out = run(FakeClient(fake_agent_responder()), r, q, frozenset({"platform"}))
    print(f"unanswerable: exit={out.exit} searches={out.searches} answer={out.answer}")
    loop = [Response(tool_calls=[ToolCall(f"t{i}", "search_docs", {"query": "kafka lag"})], stop_reason="tool_use") for i in range(5)]
    out = run(FakeClient(loop), r, "kafka lag?", frozenset({"payments"}))
    print(f"looping model: exit={out.exit} steps={out.steps} searches={out.searches}")
