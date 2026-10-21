"""Nondeterminism probe: send the same request N times and measure output variance.

Think of it as a flakiness detector for a remote dependency. It reports:
- how many distinct outputs came back, and how often the modal one appeared;
- where outputs first diverge (in whitespace tokens), like Thinking Machines'
  1,000-sample Qwen experiment, which diverged at token 103;
- mean pairwise similarity (difflib ratio), a cheap surface-level distance;
- optional *semantic* agreement: run an `extract` function (e.g. parse the
  verdict out of the text) and see whether the answers agree, not just the bytes.

Offline it uses `seeded_variation_client`, a FakeClient whose responder makes
seeded, batch-like perturbations. With ANTHROPIC_API_KEY set it calls the real API.

Run:  python nondeterminism_probe.py [N]
"""

from __future__ import annotations

import random
import sys
from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher
from itertools import combinations
from pathlib import Path
from typing import Any, Callable

try:
    import ainative_kit  # noqa: F401
except ImportError:  # running as a script without the course conftest on sys.path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "shared"))

from ainative_kit import FakeClient, LLMClient, Response, Usage, get_client


@dataclass
class ProbeReport:
    n: int
    distinct: int
    modal_count: int
    first_divergence_token: int | None  # None if all outputs identical
    mean_pairwise_similarity: float
    answers: Counter  # extracted answers (or the raw text if no extractor)

    @property
    def modal_share(self) -> float:
        return self.modal_count / self.n

    @property
    def answer_agreement(self) -> float:
        """Share of runs that gave the most common *extracted* answer."""
        return self.answers.most_common(1)[0][1] / self.n if self.answers else 0.0

    def summary(self) -> str:
        div = "never" if self.first_divergence_token is None else f"token {self.first_divergence_token}"
        return (
            f"runs={self.n} distinct_outputs={self.distinct} modal_share={self.modal_share:.0%} "
            f"first_divergence={div} mean_similarity={self.mean_pairwise_similarity:.3f} "
            f"answer_agreement={self.answer_agreement:.0%} answers={dict(self.answers)}"
        )


def first_divergence(texts: list[str]) -> int | None:
    """Index of the first whitespace token where any two outputs differ."""
    split = [t.split() for t in texts]
    if len(set(texts)) <= 1:
        return None
    for i in range(max(len(s) for s in split)):
        if len({s[i] if i < len(s) else None for s in split}) > 1:
            return i
    return None  # pragma: no cover - unreachable when texts differ


def mean_pairwise_similarity(texts: list[str], max_pairs: int = 500) -> float:
    pairs = list(combinations(texts, 2))[:max_pairs]
    if not pairs:
        return 1.0
    return sum(SequenceMatcher(None, a, b).ratio() for a, b in pairs) / len(pairs)


def probe(
    client: LLMClient,
    messages: list[dict[str, Any]],
    n: int = 20,
    *,
    extract: Callable[[str], str] | None = None,
    **complete_kwargs: Any,
) -> ProbeReport:
    """Call `client.complete(messages, **complete_kwargs)` n times and measure variance.

    Do not pass `temperature` to current Claude models: Opus 5.5 / Fable 5.x reject
    sampling parameters, and Sonnet 5.5 rejects non-default values (400).
    """
    if n < 2:
        raise ValueError("need at least 2 runs to measure variance")
    texts = [client.complete(messages, **complete_kwargs).text for _ in range(n)]
    counts = Counter(texts)
    answers = Counter(extract(t) for t in texts) if extract else counts
    return ProbeReport(
        n=n,
        distinct=len(counts),
        modal_count=counts.most_common(1)[0][1],
        first_divergence_token=first_divergence(texts),
        mean_pairwise_similarity=mean_pairwise_similarity(texts),
        answers=answers,
    )


def seeded_variation_client(
    base: str,
    swaps: dict[str, list[str]],
    p_diverge: float = 0.3,
    p_flip_answer: float = 0.0,
    flip: tuple[str, str] | None = None,
    seed: int = 0,
) -> FakeClient:
    """A FakeClient that mimics server-side nondeterminism, reproducibly.

    Each call, with probability `p_diverge`, picks one swappable word in `base`
    and replaces it with an alternative; everything after that point is kept,
    which is a simplification (real divergence changes the rest of the text).
    With probability `p_flip_answer` it also replaces `flip[0]` with `flip[1]`,
    modelling the case where variance reaches the actual decision.
    """
    rng = random.Random(seed)
    words = base.split(" ")
    swappable = [i for i, w in enumerate(words) if w in swaps]

    def responder(messages: list[dict[str, Any]], kwargs: dict[str, Any]) -> Response:
        out = list(words)
        if swappable and rng.random() < p_diverge:
            i = rng.choice(swappable)
            out[i] = rng.choice(swaps[words[i]])
        text_out = " ".join(out)
        if flip and rng.random() < p_flip_answer:
            text_out = text_out.replace(flip[0], flip[1])
        return Response(text=text_out, usage=Usage(len(str(messages)) // 4, len(out)))

    return FakeClient(responder)


DEMO_PROMPT = (
    "A Kafka consumer group rebalances every few minutes and lag grows. "
    "max.poll.interval.ms=300000, processing per batch takes up to 340s. "
    "Answer with VERDICT: <cause> on the first line, then one sentence of explanation."
)
DEMO_BASE = (
    "VERDICT: poll-timeout\nProcessing can exceed max.poll.interval.ms, so the broker "
    "evicts the consumer and triggers a rebalance; lower max.poll.records or raise the interval."
)


def verdict(text: str) -> str:
    first = text.strip().splitlines()[0] if text.strip() else ""
    return first.removeprefix("VERDICT:").strip() or "<none>"


def demo_fake(seed: int = 7) -> FakeClient:
    return seeded_variation_client(
        DEMO_BASE,
        swaps={"evicts": ["removes", "kicks"], "triggers": ["forces", "causes"], "lower": ["reduce", "decrease"]},
        p_diverge=0.5,
        p_flip_answer=0.1,
        flip=("poll-timeout", "session-timeout"),
        seed=seed,
    )


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    client = get_client(fake=demo_fake())
    report = probe(client, [{"role": "user", "content": DEMO_PROMPT}], n=n, extract=verdict, max_tokens=200)
    print(report.summary())


if __name__ == "__main__":
    main()
