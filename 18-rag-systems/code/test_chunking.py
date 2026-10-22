from chunking import (expand_to_parents, fixed_chunks, heading_chunks, load_docs, parent_child_chunks,
                      parse_doc, sections)

DOC = next(d for d in load_docs() if d.id == "rb-kafka-consumer-lag")


def test_parse_front_matter():
    d = parse_doc("---\nid: x\ntitle: T\nkind: adr\nteam: data\nacl: data, sre\nversion: 3\n---\n# T\n\nbody")
    assert d.acl == frozenset({"data", "sre"}) and d.version == 3


def test_heading_chunks_have_stable_ids_and_carry_acl_and_version():
    chunks = heading_chunks(DOC)
    assert [c.id for c in chunks] == [f"rb-kafka-consumer-lag#{s}" for s in
                                      ("overview", "symptoms", "diagnosis", "mitigation", "verification")]
    assert all(c.acl == DOC.acl and c.version == DOC.version for c in chunks)
    assert [c.id for c in heading_chunks(DOC)] == [c.id for c in chunks]  # deterministic


def test_contextual_header_is_indexed_but_not_shown():
    c = heading_chunks(DOC)[3]
    assert "Kafka consumer lag" in c.indexed_text and "Kafka consumer lag" not in c.text


def test_fixed_chunks_cover_every_word_and_can_split_a_command():
    chunks = fixed_chunks(DOC, size=40, overlap=10)
    words = " ".join(t for _, t in sections(DOC)).split()
    assert set(words) <= set(" ".join(c.text for c in chunks).split())
    cmd = "kubectl -n billing scale deploy/invoice-consumer --replicas=12"
    tiny = fixed_chunks(DOC, size=4, overlap=0)  # 6-word command, 4-word windows
    assert not any(cmd in c.text for c in tiny)  # the failure mode fixed windows invite


def test_parent_child_expansion_dedupes_to_parents():
    pc = parent_child_chunks(DOC)
    kids = {c.id: c for c in pc.children}
    ids = [c.id for c in pc.children if c.parent_id.endswith("#mitigation")]
    assert len(ids) >= 2
    shown = expand_to_parents(ids, pc.parents, kids)
    assert [c.id for c in shown] == ["rb-kafka-consumer-lag#mitigation"]


def test_parent_doc_mode_returns_the_whole_document():
    pc = parent_child_chunks(DOC, parent="doc")
    assert list(pc.parents) == ["rb-kafka-consumer-lag#doc"]
    assert "## Mitigation" in pc.parents["rb-kafka-consumer-lag#doc"].text
