import pytest

from tool_formatter import ToolError, estimate_tokens, format_records, truncate_text

RECS = [{"id": f"pay_{i:04d}", "status": "failed", "amount": i * 10, "note": "x" * 40} for i in range(200)]


def test_concise_drops_fields_detailed_keeps_ids():
    concise = format_records(RECS[:3], concise_fields=["status", "amount"])
    detailed = format_records(RECS[:3], concise_fields=["status", "amount"], response_format="detailed")
    assert "pay_0000" not in concise and "pay_0000" in detailed
    assert estimate_tokens(concise) < estimate_tokens(detailed)


def test_header_reports_shown_vs_total():
    out = format_records(RECS[:5], concise_fields=["status"], total=200, noun="payments")
    assert out.splitlines()[0] == "5 of 200 payments (concise)."
    assert "195 more payments matched" in out


def test_budget_truncates_and_tells_the_model_what_to_do():
    out = format_records(RECS, concise_fields=["id", "note"], max_tokens=200, refine_hint="Filter by status")
    assert estimate_tokens(out) < 260
    assert "[truncated" in out and "Filter by status" in out


def test_cursor_is_surfaced():
    out = format_records(RECS[:10], concise_fields=["id"], total=200, next_cursor="10")
    assert "cursor='10'" in out


def test_empty_result_is_explicit():
    assert format_records([], concise_fields=["id"], refine_hint="Widen the window.").startswith("0 results matched.")


def test_bad_response_format_is_actionable():
    with pytest.raises(ToolError, match="'concise'"):
        format_records(RECS[:1], concise_fields=["id"], response_format="short")


def test_truncate_text_keeps_head_and_tail():
    blob = "HEAD" + "." * 10_000 + "TAIL"
    out = truncate_text(blob, max_tokens=100, hint="Use logs_search with a query")
    assert out.startswith("HEAD") and out.endswith("TAIL") and "omitted" in out and len(out) < 600
    assert truncate_text("short", max_tokens=100, hint="") == "short"
