import subprocess
import sys
from pathlib import Path

from test_tamper_check import blocking, check_diff, is_test_path

DATA = Path(__file__).parent / "data"
HOOK = Path(__file__).parent / "hooks" / "test_tamper_check.py"


def mkdiff(path, removed=(), added=(), header=""):
    lines = [f"diff --git a/{path} b/{path}", header, f"--- a/{path}", f"+++ b/{path}", "@@ -10,5 +10,5 @@"]
    lines += [f"-{x}" for x in removed] + [f"+{x}" for x in added]
    return "\n".join(x for x in lines if x) + "\n"


def rules(findings):
    return {f.rule for f in findings}


def test_weakened_assertion_example_is_caught():
    f = check_diff((DATA / "weakened_assertion.diff").read_text())
    assert {"assertion_weakened", "skip_added", "test_removed"} <= rules(f)
    assert len(blocking(f)) >= 4


def test_clean_fix_is_not_flagged():
    assert check_diff((DATA / "clean_fix.diff").read_text()) == []


def test_equality_to_inequality():
    f = check_diff(mkdiff("tests/test_x.py", ["    assert len(rows) == 3"], ["    assert len(rows) >= 3"]))
    assert rules(f) == {"assertion_weakened"}


def test_assert_equal_to_assert_true():
    f = check_diff(mkdiff("tests/test_x.py", ["        self.assertEqual(resp.status, 200)"], ["        self.assertTrue(resp.status)"]))
    assert "assertion_weakened" in rules(f)


def test_tolerance_loosened():
    f = check_diff(mkdiff("tests/test_x.py", ["    assert p99 == pytest.approx(12.0, abs=0.5)"], ["    assert p99 == pytest.approx(12.0, abs=5.0)"]))
    assert "assertion_weakened" in rules(f)


def test_exception_widened():
    f = check_diff(mkdiff("tests/test_x.py", ["    with pytest.raises(IdempotencyConflict):"], ["    with pytest.raises(Exception):"]))
    assert "assertion_weakened" in rules(f)


def test_commented_out_and_vacuous():
    f = check_diff(mkdiff("pkg/foo_test.py", ["    assert out == expected"], ["    # assert out == expected", "    assert True"]))
    assert {"assertion_commented_out", "vacuous_assertion", "assertions_removed"} <= rules(f)


def test_go_skip_and_js_skip():
    assert "skip_added" in rules(check_diff(mkdiff("svc/limiter_test.go", [], ['\tt.Skip("flaky")'])))
    assert "skip_added" in rules(check_diff(mkdiff("web/rate.test.ts", [], ["it.skip('limits bursts', () => {"])))


def test_deleted_test_file():
    d = "diff --git a/tests/test_ledger.py b/tests/test_ledger.py\ndeleted file mode 100644\n--- a/tests/test_ledger.py\n+++ /dev/null\n@@ -1,2 +0,0 @@\n-def test_a():\n-    assert 1 == 1\n"
    assert rules(check_diff(d)) == {"test_file_deleted"}


def test_config_exclusion():
    f = check_diff(mkdiff("pyproject.toml", [], ['addopts = "-q --deselect tests/test_idempotency.py::test_retry"']))
    assert rules(f) == {"test_config_exclusion"}


def test_strengthening_is_fine():
    f = check_diff(mkdiff("tests/test_x.py", ["    assert calls >= 1"], ["    assert calls == 1"]))
    assert f == []


def test_renamed_test_is_not_a_deletion():
    f = check_diff(mkdiff("tests/test_x.py", ["def test_retry():"], ["def test_retry():  # renamed body below"]))
    assert "test_removed" not in rules(f)


def test_non_test_files_ignored():
    assert check_diff(mkdiff("services/payments/idempotency.py", ["    assert x == 1"], ["    assert x"])) == []


def test_human_approval_downgrades_to_info():
    path = "services/payments/tests/test_idempotency.py"
    f = check_diff((DATA / "weakened_assertion.diff").read_text(), approved_paths={path})
    assert f and blocking(f) == [] and {x.severity for x in f} == {"info"}


def test_is_test_path():
    for p in ["tests/test_a.py", "pkg/a_test.go", "web/a.spec.ts", "src/FooTest.java", "conftest.py"]:
        assert is_test_path(p), p
    assert not is_test_path("services/testing_utils.py")


def test_cli_exit_codes():
    bad = subprocess.run([sys.executable, str(HOOK), "--diff", str(DATA / "weakened_assertion.diff")], capture_output=True, text=True)
    good = subprocess.run([sys.executable, str(HOOK), "--diff", str(DATA / "clean_fix.diff")], capture_output=True, text=True)
    assert bad.returncode == 1 and "assertion_weakened" in bad.stdout
    assert good.returncode == 0
