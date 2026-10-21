import pytest

from ainative_kit import FakeClient, text
from oncall_assistant import answer, quoting_fake
from retrieval_eval import evaluate, grounding_check, hit_at_k, load_eval, recall_at_k, reciprocal_rank
from runbook_retriever import build_index, load_corpus


def test_metric_math():
    got = ["a", "b", "c", "d"]
    assert recall_at_k(got, ["b", "z"], k=2) == 0.5
    assert hit_at_k(got, ["d"], k=3) == 0.0
    assert reciprocal_rank(got, ["c"]) == pytest.approx(1 / 3)
    with pytest.raises(ValueError):
        recall_at_k(got, [], k=1)


def test_eval_set_labels_point_at_real_chunks():
    ids = {c.id for c in load_corpus()}
    for row in load_eval():
        assert set(row["relevant"]) <= ids, row["id"]


def test_contextualized_bm25_recall_floor():
    # Measured on this corpus: 0.955 at k=5. A regression gate, not a target.
    rows = load_eval()
    ctx = evaluate(build_index(contextualize=True), rows, k=5)
    plain = evaluate(build_index(contextualize=False), rows, k=5)
    assert ctx.recall >= 0.9
    assert ctx.recall >= plain.recall


def test_known_lexical_gap_is_still_a_miss():
    # Characterization test: "out of space" shares no terms with "DiskPressure /
    # ephemeral-storage". If this starts passing, someone changed the tokenizer
    # or corpus; update the docs that cite this miss.
    report = evaluate(build_index(), [r for r in load_eval() if r["id"] == "q20"], k=5)
    assert report.recall == 0.0


def _chunks(*ids):
    by = {c.id: c for c in load_corpus()}
    return [by[i] for i in ids]


def test_grounding_accepts_verbatim_cited_command():
    shown = _chunks("tls-cert-expiry#mitigation")
    ans = "Force renewal with `cmctl renew -n billing ledger-api-tls` [tls-cert-expiry#mitigation]"
    assert grounding_check(ans, shown).ok


def test_grounding_rejects_invented_command_and_unknown_citation():
    shown = _chunks("kafka-consumer-lag#mitigation")
    ans = ("Reset offsets: `kafka-consumer-groups --reset-offsets --to-latest` [kafka-consumer-lag#mitigation]\n"
           "Also see [kafka-consumer-lag#appendix]\n"
           "Then run `kubectl -n billing scale deploy/invoice-consumer --replicas=12`")
    g = grounding_check(ans, shown)
    assert not g.ok
    assert g.ungrounded_commands == ["kafka-consumer-groups --reset-offsets --to-latest"]
    assert g.unknown_citations == ["kafka-consumer-lag#appendix"]
    assert len(g.uncited_command_lines) == 1


def test_assistant_end_to_end_with_fake_is_grounded():
    a = answer("force cert-manager to renew the ledger-api certificate", build_index(), quoting_fake())
    assert a.shown[0].id == "tls-cert-expiry#mitigation"
    assert a.grounding.ok, a.text


def test_assistant_flags_a_hallucinating_model():
    liar = FakeClient(lambda m, kw: text("Run `rm -rf /var/lib/kafka` [kafka-consumer-lag#mitigation]"))
    a = answer("how do I mitigate kafka consumer lag", build_index(), liar)
    assert not a.grounding.ok
    assert a.grounding.ungrounded_commands == ["rm -rf /var/lib/kafka"]


def test_tight_budget_drops_lowest_ranked_chunks():
    a = answer("prune unused container images on a node", build_index(), quoting_fake(), k=5, budget=700)
    assert 1 <= len(a.shown) < 5
    assert a.prompt.tokens <= 700
