from runbook_retriever import BM25, Chunk, build_index, load_corpus, tokenize


def test_chunks_have_stable_ids_per_heading():
    ids = {c.id for c in load_corpus()}
    assert "kafka-consumer-lag#mitigation" in ids
    assert "deploy-rollback#when-to-roll-back" in ids
    assert len(ids) == len(load_corpus())  # unique


def test_tokenize_splits_identifiers_and_stems():
    assert tokenize("max.poll.interval.ms") == ["max", "poll", "interval", "ms"]
    assert tokenize("Mitigation")[0] == tokenize("mitigate")[0]
    assert "the" not in tokenize("the lag")


def test_exact_identifier_queries_rank_first():
    idx = build_index()
    assert idx.search("cmctl renew", k=1)[0][0].id == "tls-cert-expiry#mitigation"
    assert idx.search("maxmemory-policy volatile-ttl", k=1)[0][0].id.startswith("redis-evictions")


def test_rare_terms_outweigh_common_ones():
    chunks = [Chunk(id=f"d#{i}", doc="d", title="t", heading="h", text=t, tokens=tokenize(t))
              for i, t in enumerate(["lag lag lag lag", "lag coredns", "unrelated text here"])]
    top = BM25(chunks).search("lag coredns", k=1)[0][0]
    assert top.id == "d#1"


def test_contextual_prefix_rescues_section_without_doc_vocabulary():
    # The Kafka "Mitigation" body never says "kafka" or "lag".
    q = "how do I mitigate kafka consumer lag"
    plain = [c.id for c, _ in build_index(contextualize=False).search(q, k=5)]
    ctx = [c.id for c, _ in build_index(contextualize=True).search(q, k=5)]
    assert "kafka-consumer-lag#mitigation" not in plain
    assert "kafka-consumer-lag#mitigation" in ctx
