import pytest

from ainative_kit import FakeClient
from reviewer import (AUTHOR_TRANSCRIPT, DIFF, SPEC, Finding, ReviewResult, build_review_request, diff_lines,
                      fake_reviewer, review, vote_findings)
from single_writer import (TASK_AUTH, TASK_LOGGING, TASK_RENAME, TASK_SYNC, Conflict, Repo, fake_coder,
                           run_parallel_writers, run_single_writer, undefined_calls)

# --------------------------------------------------------------------------- single writer


def test_seed_repo_is_clean():
    assert undefined_calls(Repo().files) == []


def test_parallel_writers_break_on_implicit_decisions_even_with_occ():
    for occ in (False, True):
        out = run_parallel_writers(FakeClient(fake_coder), Repo(), [TASK_RENAME, TASK_SYNC], occ=occ)
        assert out.conflicts == 0, "different files: no byte-level conflict for OCC to catch"
        assert "jobs.py: call to undefined fetch_user()" in out.problems


def test_blind_writes_lose_updates_on_the_same_file():
    out = run_parallel_writers(FakeClient(fake_coder), Repo(), [TASK_LOGGING, TASK_AUTH], occ=False)
    api = out.files["api.py"]
    assert "PermissionError" in api and "print(" not in api        # the logging change was silently lost


def test_occ_detects_lost_update_and_retries_on_fresh_state():
    out = run_parallel_writers(FakeClient(fake_coder), Repo(), [TASK_LOGGING, TASK_AUTH], occ=True)
    api = out.files["api.py"]
    assert out.conflicts == 1 and "PermissionError" in api and "print(" in api


def test_single_writer_with_read_only_helpers_is_correct():
    fake = FakeClient(fake_coder)
    out = run_single_writer(fake, Repo(), [TASK_RENAME, TASK_SYNC], ["Where is fetch_user used?"])
    assert out.problems == []
    assert "get_user(i)" in out.files["jobs.py"]
    helper_calls = [c for c in fake.calls if c["system"].startswith("You are a read-only")]
    assert len(helper_calls) == 1
    # the writer saw the helper's notes
    assert "<notes>" in fake.calls[1]["messages"][0]["content"]


def test_compare_and_set():
    repo = Repo()
    repo.write("api.py", "x", expected_version=0)
    with pytest.raises(Conflict):
        repo.write("api.py", "y", expected_version=0)


# --------------------------------------------------------------------------- clean-context reviewer


def test_review_request_contains_only_spec_and_diff():
    msgs = build_review_request(SPEC, DIFF)
    assert len(msgs) == 1
    content = msgs[0]["content"]
    assert SPEC in content and DIFF in content
    assert "duplicates are hurting" not in content and AUTHOR_TRANSCRIPT not in content


def test_review_keeps_evidenced_findings_and_drops_the_rest():
    res = review(FakeClient(fake_reviewer), SPEC, DIFF)
    assert len(res.kept) == 2 and all(f.severity == "high" for f in res.kept)
    reasons = sorted(why for _, why in res.dropped)
    assert reasons == ["below medium", "evidence not found in diff"]


def test_severity_filter_is_code_not_prompt():
    fake = FakeClient(fake_reviewer)
    res = review(fake, SPEC, DIFF, min_severity="nit")
    assert len(res.kept) == 3                                       # the nit now survives
    assert "Report every issue" in fake.calls[0]["system"]


def test_diff_lines_parses_files():
    lines = diff_lines(DIFF)
    assert "consumer.commit(msg)" in lines["consumer/handler.py"]


def test_vote_findings_needs_k_independent_reviewers():
    a = Finding("f.py", "high", "bug A", "+ x = 1")
    b = Finding("f.py", "high", "bug B", "+ y = 2")
    a2 = Finding("f.py", "high", "same bug, worded differently", "x = 1")
    results = [ReviewResult([a, b]), ReviewResult([a2]), ReviewResult([a, a])]
    kept = vote_findings(results, k=2)
    assert [f.claim for f in kept] == ["bug A"]
