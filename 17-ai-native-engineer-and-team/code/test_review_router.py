import json
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from review_router import FileChange, load_policy, main, parse_unified_diff, route

HERE = Path(__file__).parent
DIFFS = HERE / "data" / "diffs"
POLICY = load_policy()


def diff_text(name: str) -> str:
    return (DIFFS / name).read_text()


# ---------- parsing ----------

def test_parse_counts_added_and_removed_per_file():
    files = parse_unified_diff(diff_text("raft_election.diff"))
    assert [f.path for f in files] == ["internal/raft/election.go"]
    assert len(files[0].removed) == 4 and len(files[0].added) == 2


def test_removed_sql_comment_inside_hunk_is_not_a_header():
    diff = (
        "--- a/migrations/1.sql\n+++ b/migrations/1.sql\n"
        "@@ -1,2 +1,1 @@\n--- old comment\n SELECT 1;\n"
    )
    files = parse_unified_diff(diff)
    assert len(files) == 1
    assert files[0].removed == ["-- old comment"]


def test_deleted_file_keeps_old_path():
    diff = "--- a/internal/wal/segment.go\n+++ /dev/null\n@@ -1,1 +0,0 @@\n-package wal\n"
    files = parse_unified_diff(diff)
    assert files[0].path == "internal/wal/segment.go"


def test_multiple_files():
    d = diff_text("docs_only.diff") + diff_text("flag_config.diff")
    assert [f.path for f in parse_unified_diff(d)] == ["docs/runbooks/leader-failover.md", "config/flags/prod.yaml"]


# ---------- routing: the sample diffs ----------

@pytest.mark.parametrize("name,tier,humans,verifiers,owner", [
    ("docs_only.diff", "low", 0, 3, None),
    ("flag_config.diff", "medium", 1, 3, "@ledger-oncall"),
    ("replication_config.diff", "high", 2, 5, "@consensus-owners"),
    ("migration_additive.diff", "medium", 1, 3, "@data-owners"),
    ("migration_destructive.diff", "high", 2, 5, "@data-owners"),
    ("raft_election.diff", "high", 2, 5, "@consensus-owners"),
    ("test_weakening.diff", "medium", 1, 3, "@ledger-team"),
    ("ci_workflow.diff", "medium", 1, 3, "@platform"),
])
def test_sample_diffs_route_as_documented(name, tier, humans, verifiers, owner):
    d = route(diff_text(name), POLICY)
    assert (d.tier, d.human_approvals, d.verifiers) == (tier, humans, verifiers)
    if owner:
        assert owner in d.owners
    assert d.agent_approval_counts_as_human is False


def test_untrusted_author_never_gets_zero_human_path():
    d = route(diff_text("docs_only.diff"), POLICY, trusted_author=False)
    assert d.tier == "medium" and d.human_approvals == 1
    assert any("trusted authors" in r for r in d.reasons)


def test_unknown_path_defaults_to_medium_not_low():
    d = route([FileChange("tools/loadgen/main.go", added=["package main"])], POLICY)
    assert d.tier == "medium"
    assert any("no rule matched" in r for r in d.reasons)


def test_empty_diff_fails_safe_to_default():
    assert route("", POLICY).tier == "medium"


def test_large_low_tier_diff_escalates():
    big = FileChange("docs/guide.md", added=["x"] * 500)
    d = route([big], POLICY)
    assert d.tier == "medium"


def test_content_pattern_escalates_outside_owned_paths():
    fc = FileChange("internal/ledger/snapshot.go", added=["\tif err := f.Sync(); err != nil {"])
    d = route([fc], POLICY)
    assert d.tier == "high" and "@storage-owners" in d.owners


def test_mixed_diff_takes_highest_tier_and_reports_per_file():
    d = route(diff_text("docs_only.diff") + diff_text("raft_election.diff"), POLICY)
    assert d.tier == "high"
    assert d.file_tiers["docs/runbooks/leader-failover.md"] == "low"
    assert d.file_tiers["internal/raft/election.go"] == "high"


def test_always_human_forces_one_approval_even_at_low_tier():
    policy = {
        "default_tier": "medium",
        "tiers": {t: {"human_approvals": h, "verifiers": 3, "round_cap": 3}
                  for t, h in [("low", 0), ("medium", 1), ("high", 2)]},
        "rules": [{"name": "agent-docs", "tier": "low", "paths": ["CLAUDE.md"], "always_human": True}],
    }
    d = route([FileChange("CLAUDE.md", added=["- prefer table tests"])], policy)
    assert d.tier == "low" and d.human_approvals == 1


def test_agent_instruction_files_are_not_low_even_though_they_are_markdown():
    d = route([FileChange("REVIEW.md", added=["## Nit cap"])], POLICY)
    assert d.tier == "medium" and d.human_approvals >= 1


def test_cli_prints_json(capsys):
    assert main([str(DIFFS / "raft_election.diff")]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["tier"] == "high" and out["round_cap"] == 2


# ---------- property: adding files can never lower the tier ----------

PATHS = ["docs/a.md", "README.md", "config/flags/prod.yaml", "migrations/9.sql", "internal/raft/log.go",
         "internal/api/post.go", "tools/x.go", ".github/workflows/ci.yml", "internal/ledger/a_test.go"]
LINES = ["x := 1", "DROP TABLE t;", "f.Sync()", "idempotencyKey := k", "t.Skip(\"later\")", "quorum: 3"]
file_changes = st.builds(FileChange, st.sampled_from(PATHS),
                         st.lists(st.sampled_from(LINES), max_size=3), st.lists(st.sampled_from(LINES), max_size=3))


@settings(max_examples=200, deadline=None)
@given(st.lists(file_changes, min_size=1, max_size=4), file_changes)
def test_tier_is_monotone_in_the_set_of_files(files, extra):
    order = {"low": 0, "medium": 1, "high": 2}
    before = route(files, POLICY)
    after = route(files + [extra], POLICY)
    assert order[after.tier] >= order[before.tier]
    assert after.human_approvals >= before.human_approvals
