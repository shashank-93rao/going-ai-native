import pytest

from ainative_kit import FakeClient, text
from nondeterminism_probe import (
    DEMO_BASE,
    demo_fake,
    first_divergence,
    mean_pairwise_similarity,
    probe,
    seeded_variation_client,
    verdict,
)

MSG = [{"role": "user", "content": "same prompt every time"}]


def test_identical_outputs_report_no_variance():
    client = FakeClient([text("same answer")] * 5)
    r = probe(client, MSG, n=5)
    assert r.distinct == 1
    assert r.modal_share == 1.0
    assert r.first_divergence_token is None
    assert r.mean_pairwise_similarity == 1.0


def test_probe_sends_identical_requests():
    client = FakeClient([text("a")] * 3)
    probe(client, MSG, n=3, max_tokens=100)
    assert len(client.calls) == 3
    assert all(c == client.calls[0] for c in client.calls)
    assert client.calls[0]["temperature"] is None  # never sent by default


def test_first_divergence_index():
    assert first_divergence(["a b c d", "a b x d", "a b c d"]) == 2
    assert first_divergence(["a b", "a b c"]) == 2  # length difference counts
    assert first_divergence(["same", "same"]) is None


def test_similarity_bounds():
    assert mean_pairwise_similarity(["abc"]) == 1.0
    s = mean_pairwise_similarity(["abcdef", "abcxyz"])
    assert 0 < s < 1


def test_seeded_client_is_reproducible():
    a = probe(demo_fake(seed=3), MSG, n=30, extract=verdict)
    b = probe(demo_fake(seed=3), MSG, n=30, extract=verdict)
    assert a.summary() == b.summary()


def test_surface_variance_without_semantic_variance():
    client = seeded_variation_client("VERDICT: yes\nbecause the lag grows", {"grows": ["rises", "climbs"]}, p_diverge=1.0, seed=1)
    r = probe(client, MSG, n=20, extract=verdict)
    assert r.distinct > 1  # bytes differ...
    assert r.answer_agreement == 1.0  # ...but the decision is stable


def test_semantic_flips_are_detected():
    client = seeded_variation_client("VERDICT: yes", {}, p_diverge=0.0, p_flip_answer=0.5, flip=("yes", "no"), seed=2)
    r = probe(client, MSG, n=40, extract=verdict)
    assert set(r.answers) == {"yes", "no"}
    assert r.answer_agreement < 1.0


def test_demo_fake_variance_profile():
    r = probe(demo_fake(), MSG, n=50, extract=verdict)
    assert r.distinct > 1
    assert r.answers.most_common(1)[0][0] == "poll-timeout"
    assert 0.7 <= r.answer_agreement < 1.0


def test_verdict_parser():
    assert verdict(DEMO_BASE) == "poll-timeout"
    assert verdict("") == "<none>"


def test_needs_two_runs():
    with pytest.raises(ValueError):
        probe(FakeClient([text("x")]), MSG, n=1)
