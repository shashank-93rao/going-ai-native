"""On-call assistant: retrieve runbook chunks, assemble a budgeted prompt, answer, check grounding.

This wires the other three files together:
    runbook_retriever (BM25)  ->  context_budget (assemble)  ->  model  ->  retrieval_eval.grounding_check

With ANTHROPIC_API_KEY set it calls the real model; otherwise a deterministic
fake answers by quoting the top chunk's first command.

    python oncall_assistant.py "what command shows lag per partition for the invoice consumer group"
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass

from ainative_kit import FakeClient, LLMClient, get_client, text
from context_budget import Assembled, Section, assemble
from retrieval_eval import GroundingReport, grounding_check
from runbook_retriever import BM25, Chunk, build_index

SYSTEM = """You are the on-call assistant for billing-platform.
Answer only from the runbook chunks provided in <runbooks>. After every line that
states a fact or a command, cite the chunk id in square brackets, e.g. [kafka-consumer-lag#diagnosis].
Copy commands exactly as written in the chunk, inside backticks. If the chunks do not
answer the question, say "Not covered by the runbooks" and name the closest chunk."""

CHUNK_RE = re.compile(r'<chunk id="([^"]+)">\n(.*?)\n</chunk>', re.S)


@dataclass
class Answer:
    question: str
    text: str
    shown: list[Chunk]
    prompt: Assembled
    grounding: GroundingReport


def build_prompt(question: str, chunks: list[Chunk], budget: int) -> Assembled:
    """Each chunk is its own optional section, priority = retrieval rank, so the
    budgeter drops the lowest-ranked chunks first when space is tight."""
    sections = [Section("question", question, required=True)]
    for rank, c in enumerate(chunks):
        sections.append(Section(f"chunk_{rank}", f'<chunk id="{c.id}">\n{c.text}\n</chunk>', priority=rank))
    return assemble(sections, budget=budget, reserve_output=400)


def answer(question: str, index: BM25, client: LLMClient, k: int = 5, budget: int = 3000) -> Answer:
    hits = [c for c, _ in index.search(question, k=k)]
    prompt = build_prompt(question, hits, budget)
    shown = [c for c in hits if f'<chunk id="{c.id}">' in prompt.prompt]
    resp = client.complete([{"role": "user", "content": f"<runbooks>\n{prompt.prompt}</runbooks>"}], system=SYSTEM, max_tokens=600)
    return Answer(question, resp.text, shown, prompt, grounding_check(resp.text, shown))


def quoting_fake() -> FakeClient:
    """Deterministic stand-in: cite the top chunk and quote its first command."""

    def respond(messages, kwargs):
        chunks = CHUNK_RE.findall(messages[-1]["content"])
        if not chunks:
            return text("Not covered by the runbooks.")
        cid, body = chunks[0]
        cmds = [c for c in re.findall(r"`([^`]+)`", body) if " " in c]  # skip bare identifiers
        first_sentence = body.split(". ")[0].strip()
        lines = [f"{first_sentence}. [{cid}]"]
        if cmds:
            lines.append(f"Run `{cmds[0]}` [{cid}]")
        return text("\n".join(lines))

    return FakeClient(respond)


if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) or "what command shows lag per partition for the invoice consumer group"
    a = answer(q, build_index(), get_client(fake=quoting_fake()))
    print(a.text)
    print(f"\nshown: {[c.id for c in a.shown]}  prompt tokens ~{a.prompt.tokens}")
    g = a.grounding
    print(f"grounded: {g.ok}  unknown_citations={g.unknown_citations}  ungrounded={g.ungrounded_commands}  uncited={g.uncited_command_lines}")
