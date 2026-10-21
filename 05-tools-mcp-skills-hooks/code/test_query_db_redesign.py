import pytest

import query_db_redesign as q
from tool_formatter import ToolError, estimate_tokens


@pytest.fixture
def db():
    return q.make_db()


def test_bad_tool_dumps_everything_and_leaks_raw_errors(db):
    dump = q.bad_query_db(db, "SELECT * FROM payments")
    assert estimate_tokens(dump) > 15_000  # most of Claude Code's 25k default tool-output cap
    with pytest.raises(Exception, match="no such column"):
        q.bad_query_db(db, "SELECT * FROM payments WHERE merchant = 'Globex Rail'")


def test_summary_answers_the_question_in_few_tokens(db):
    out = q.payments_failure_summary(db, "globex", since_minutes=30)
    assert "merchant=Globex Rail" in out and "issuer_timeout=" in out
    assert estimate_tokens(out) < 100
    first_code = out.split("failure codes in window: ")[1].split("=")[0]
    assert first_code == "issuer_timeout"


def test_merchant_name_resolution_and_errors(db):
    with pytest.raises(ToolError, match="Known merchants"):
        q.payments_search(db, "Initech")
    out = q.payments_search(db, "Globex Rail", status="failed", since_minutes=30, limit=3)
    assert out.startswith("3 of ") and "cursor='3'" in out and "m_c3a9" not in out


def test_detailed_includes_ids_for_follow_up(db):
    out = q.payments_search(db, "Globex Rail", status="failed", limit=1, response_format="detailed")
    assert '"id": "pay_' in out and '"idempotency_key"' in out


def test_enum_validation(db):
    with pytest.raises(ToolError, match="status must be one of"):
        q.payments_search(db, "Globex Rail", status="error")


def test_sql_escape_hatch_is_read_only_and_explains_schema(db):
    with pytest.raises(ToolError, match="Only a single SELECT"):
        q.payments_sql_readonly(db, "DELETE FROM payments")
    with pytest.raises(ToolError, match="read-only"):
        q.payments_sql_readonly(db, "WITH x AS (SELECT 1) DELETE FROM payments")
    with pytest.raises(ToolError, match=r"payments\(id, merchant_id"):
        q.payments_sql_readonly(db, "SELECT merchant FROM payments")
    out = q.payments_sql_readonly(db, "SELECT id FROM payments", max_rows=5)
    assert out.splitlines()[0] == "id" and "stopped at 5 rows" in out
    assert db.execute("SELECT COUNT(*) FROM payments").fetchone()[0] == 600


def test_demo_runs():
    d = q.demo()
    assert set(d) == {"before_1", "before_2", "after_1", "after_2", "after_3"}
