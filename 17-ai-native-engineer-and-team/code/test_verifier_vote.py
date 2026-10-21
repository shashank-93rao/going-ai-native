import json
from pathlib import Path

from ainative_kit import FakeClient, Tracer, text

from verifier_vote import (
    Finding, cluster_findings, demo_client, format_comment, main, parse_findings,
    parse_skip_paths, review, run_reviewers, vote,
)

HERE = Path(__file__).parent
REVIEW_MD = (HERE / "templates" / "REVIEW.md").read_text()
DIFF = (HERE / "data" / "diffs" / "raft_election.diff").read_text()


def f(file="internal/raft/election.go", line=42, category="bug", severity="important", reviewer=0, summary="s"):
    return Finding(file, line, category, severity, summary, "evidence", reviewer)


def reply(*findings: dict) -> object:
    return text(json.dumps({"findings": list(findings)}))


def F(**kw):
    base = {"file": "internal/raft/election.go", "line": 42, "category": "bug", "severity": "important",
            "summary": "s", "evidence": "e"}
    return {**base, **kw}


def test_majority_posts_and_minority_drops():
    res = vote([[f(reviewer=0)], [f(reviewer=1, line=43)], [f(reviewer=2, line=90)]])
    assert len(res.posted) == 1 and res.posted[0].support == 2
    assert len(res.dropped_minority) == 1 and res.dropped_minority[0].line == 90


def test_unanimous_style_findings_are_still_dropped():
    res = vote([[f(category="style", reviewer=i)] for i in range(3)])
    assert res.posted == [] and len(res.dropped_style) == 1


def test_one_reviewer_repeating_itself_counts_once():
    res = vote([[f(reviewer=0), f(reviewer=0, line=43)], [], []])
    assert res.posted == [] and res.dropped_minority[0].support == 1


def test_bug_and_concurrency_on_same_line_are_one_cluster():
    clusters = cluster_findings([f(category="bug", reviewer=0), f(category="concurrency", reviewer=1)])
    assert len(clusters) == 1


def test_line_window_separates_distant_findings():
    assert len(cluster_findings([f(line=39), f(line=42, reviewer=1)])) == 2
    assert len(cluster_findings([f(line=42), f(line=43, reviewer=1)])) == 1


def test_findings_without_file_line_evidence_are_dropped():
    res = vote([[f(line=0, reviewer=i)] for i in range(3)])
    assert res.posted == [] and len(res.dropped_no_evidence) == 3


def test_skip_paths_from_review_md():
    skips = parse_skip_paths(REVIEW_MD)
    assert "*.pb.go" in skips and "vendor/*" in skips
    res = vote([[f(file="internal/pb/raft.pb.go", reviewer=i)] for i in range(3)], skip_paths=skips)
    assert res.posted == [] and len(res.dropped_skipped_path) == 3


def test_malformed_output_is_abstention_not_clean_bill():
    assert parse_findings("Looks good to me!", 0) is None
    assert parse_findings('{"findings": []}', 0) == []
    assert len(parse_findings("```json\n" + json.dumps({"findings": [F()]}) + "\n```", 0)) == 1


def test_degraded_when_majority_abstains():
    client = FakeClient([text("LGTM"), text("I could not parse the diff."), reply(F())])
    res = review(client, DIFF, REVIEW_MD, n=3)
    assert res.abstained == [0, 1] and res.degraded
    assert format_comment(res).startswith("Machine review DEGRADED")


def test_not_degraded_with_one_abstention_of_three():
    client = FakeClient([text("LGTM"), reply(F()), reply(F(line=43))])
    res = review(client, DIFF, REVIEW_MD, n=3)
    assert not res.degraded and len(res.posted) == 1


def test_reviewers_get_independent_fresh_contexts():
    client = FakeClient([reply(F()), reply(), reply()])
    run_reviewers(client, DIFF, REVIEW_MD, 3)
    assert len(client.calls) == 3
    for call in client.calls:
        assert len(call["messages"]) == 1  # no transcript of other reviewers
        assert "findings" not in call["messages"][0]["content"].split("</review_md>")[1]
    assert client.calls[0]["messages"] == client.calls[2]["messages"]


def test_review_traces_one_span_per_reviewer():
    tracer = Tracer()
    run_reviewers(demo_client(), DIFF, REVIEW_MD, 3, tracer=tracer)
    spans = [s for s in tracer.spans if s.name == "reviewer"]
    assert [s.attrs["reviewer"] for s in spans] == [0, 1, 2]
    assert all(s.attrs["abstained"] is False for s in spans)


def test_demo_end_to_end_posts_the_durability_bug_only():
    res = review(demo_client(), DIFF, REVIEW_MD, n=3)
    assert len(res.posted) == 1
    c = res.posted[0]
    assert c.support == 3 and c.severity == "important" and "vote twice" in c.summary
    assert len(res.dropped_style) == 1 and len(res.dropped_minority) == 1


def test_pre_existing_label_needs_majority():
    res = vote([[f(severity="pre-existing", reviewer=0)], [f(severity="pre-existing", reviewer=1)], [f(reviewer=2)]])
    assert res.posted[0].severity == "pre-existing"


def test_comment_leads_with_count_and_says_nothing_to_fix():
    empty = vote([[], [], []])
    assert format_comment(empty).startswith("0 findings. Nothing to fix.")
    res = vote([[f(reviewer=i)] for i in range(3)])
    assert format_comment(res).startswith("1 important, 0 other")


def test_cli_runs_offline(capsys, monkeypatch):
    monkeypatch.setenv("AINATIVE_FAKE", "1")
    assert main([str(HERE / "data" / "diffs" / "raft_election.diff")]) == 0
    assert "1 important" in capsys.readouterr().out
