"""Assemble a prompt from prioritized sections under a token budget. Stdlib only.

Two separate decisions, made in two separate passes:

1. *Selection* (what gets in) is by priority. Required sections always go in;
   optional ones go in by priority until the budget runs out, and a section
   marked truncatable is cut to fit instead of dropped.
2. *Layout* (where it goes) is by stability, then declared order. Stable
   sections form a byte-identical prefix on every call, so the provider's
   prompt cache can hit; volatile sections go after it.

Mixing the two passes (laying out in priority order) is the classic way to
destroy cache hit rate: a priority tweak reorders the prefix.

Token counts use a chars/4 estimate. For real budgets call the provider's
token-counting endpoint; the estimate is only good to roughly +/-20% on English
and is worse on code and logs.

    python context_budget.py
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

CHARS_PER_TOKEN = 4
MIN_TRUNCATED_TOKENS = 40  # below this a truncated section is noise, so drop it
TRUNC_MARK = "\n[... truncated by context budgeter ...]\n"


def estimate_tokens(text: str) -> int:
    return math.ceil(len(text) / CHARS_PER_TOKEN)


class BudgetError(ValueError):
    """Required sections alone exceed the budget. Fail loudly; never silently drop them."""


@dataclass
class Section:
    name: str
    text: str
    priority: int = 50  # lower number = more important
    required: bool = False
    stable: bool = False  # belongs to the cacheable prefix
    truncatable: bool = False
    keep: Literal["head", "tail"] = "head"  # which end survives truncation (logs: tail)

    def render(self, text: str | None = None) -> str:
        return f'<section name="{self.name}">\n{self.text if text is None else text}\n</section>\n'


@dataclass
class Assembled:
    prompt: str
    tokens: int
    budget: int
    included: list[str] = field(default_factory=list)
    truncated: list[str] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)
    prefix: str = ""  # the stable, cacheable part of `prompt`

    def report(self) -> str:
        return (
            f"tokens {self.tokens}/{self.budget}  prefix {estimate_tokens(self.prefix)}\n"
            f"  included:  {', '.join(self.included) or '-'}\n"
            f"  truncated: {', '.join(self.truncated) or '-'}\n"
            f"  dropped:   {', '.join(self.dropped) or '-'}"
        )


def _truncate(section: Section, max_tokens: int) -> str | None:
    """Cut a section's text so its *rendered* form fits in max_tokens, or None if too small to keep."""
    overhead = estimate_tokens(section.render("")) + estimate_tokens(TRUNC_MARK)
    room = (max_tokens - overhead) * CHARS_PER_TOKEN
    if room < MIN_TRUNCATED_TOKENS * CHARS_PER_TOKEN:
        return None
    if section.keep == "tail":
        return TRUNC_MARK.lstrip("\n") + section.text[-room:]
    return section.text[:room] + TRUNC_MARK.rstrip("\n")


def assemble(sections: list[Section], budget: int, reserve_output: int = 0) -> Assembled:
    """Build the prompt. `reserve_output` holds back room for the model's reply.

    Raises BudgetError if required sections do not fit, and ValueError if a
    stable section is optional (an optional section cannot be part of a
    stable prefix: the day it is dropped, every later byte shifts).
    """
    names = [s.name for s in sections]
    if len(set(names)) != len(names):
        raise ValueError(f"duplicate section names: {names}")
    for s in sections:
        if s.stable and not s.required:
            raise ValueError(f"section {s.name!r} is stable but optional; make it required or volatile")

    limit = budget - reserve_output
    chosen: dict[str, str] = {}  # name -> text actually used
    used = 0
    for s in sections:
        if s.required:
            chosen[s.name] = s.text
            used += estimate_tokens(s.render())
    if used > limit:
        raise BudgetError(f"required sections need {used} tokens, limit is {limit}")

    truncated, dropped = [], []
    for s in sorted((s for s in sections if not s.required), key=lambda s: (s.priority, names.index(s.name))):
        cost = estimate_tokens(s.render())
        if used + cost <= limit:
            chosen[s.name] = s.text
            used += cost
            continue
        cut = _truncate(s, limit - used) if s.truncatable else None
        if cut is None:
            dropped.append(s.name)
            continue
        chosen[s.name] = cut
        used += estimate_tokens(s.render(cut))
        truncated.append(s.name)

    # Layout pass: stable first (declared order), then volatile (declared order).
    ordered = [s for s in sections if s.stable] + [s for s in sections if not s.stable]
    prefix = "".join(s.render(chosen[s.name]) for s in ordered if s.stable)
    body = "".join(s.render(chosen[s.name]) for s in ordered if not s.stable and s.name in chosen)
    prompt = prefix + body
    return Assembled(
        prompt=prompt,
        tokens=estimate_tokens(prompt),
        budget=budget,
        included=[s.name for s in ordered if s.name in chosen],
        truncated=truncated,
        dropped=dropped,
        prefix=prefix,
    )


def common_prefix_tokens(a: str, b: str) -> int:
    """How much of two prompts a prefix cache could share (estimated tokens)."""
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n // CHARS_PER_TOKEN


def triage_sections(alert: str, logs: str, history: str) -> list[Section]:
    """A realistic on-call triage prompt, used by the demo and the tests."""
    return [
        Section("role", "You are the on-call assistant for billing-platform. Cite runbook chunk ids.", required=True, stable=True),
        Section("tool_contract", "Tools: search_runbooks(query), get_logs(service, since). Read before you act.", required=True, stable=True),
        Section("alert", alert, required=True),
        Section("recent_logs", logs, priority=10, truncatable=True, keep="tail"),
        Section("prior_incidents", history, priority=30, truncatable=True),
        Section("style_guide", "Prefer short bullet answers. " * 40, priority=90),
    ]


if __name__ == "__main__":
    logs = "\n".join(f"2026-10-19T03:{i:02d}:00Z invoice-consumer WARN Revoking previously assigned partitions" for i in range(60))
    history = "INC-4412: lag caused by max.poll.interval.ms=30000 with batch size 2000. Fixed by raising to 300000.\n" * 5
    for budget in (2000, 900, 400):
        a = assemble(triage_sections("InvoiceConsumerLagHigh: lag 84k on invoices.v2 p7", logs, history), budget=budget, reserve_output=200)
        print(f"budget={budget}\n{a.report()}\n")
    a1 = assemble(triage_sections("alert A", logs, history), budget=2000)
    a2 = assemble(triage_sections("alert B, different", logs, history), budget=2000)
    print(f"shared prefix between two different alerts: ~{common_prefix_tokens(a1.prompt, a2.prompt)} tokens")
