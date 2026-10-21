import ops_tools as ot
from tool_formatter import estimate_tokens


def test_schemas_match_registry_and_are_namespaced():
    names = [s["name"] for s in ot.TOOL_SCHEMAS]
    assert sorted(names) == sorted(ot.REGISTRY)
    assert all(n.split("_")[0] in {"deploys", "kafka", "logs"} for n in names)
    for s in ot.TOOL_SCHEMAS:
        assert len(s["description"]) > 30 and s["input_schema"]["type"] == "object"


def test_unknown_group_suggests_the_right_one():
    content, is_error = ot.call_tool("kafka_consumer_lag", {"group": "ledger-writer"})
    assert is_error and "Did you mean 'ledger-writer-v2'" in content


def test_lag_concise_flags_skew_and_is_small():
    concise, _ = ot.call_tool("kafka_consumer_lag", {"group": "ledger-writer-v2"})
    detailed, _ = ot.call_tool("kafka_consumer_lag", {"group": "ledger-writer-v2", "response_format": "detailed"})
    assert "p3=48211" in concise and "One partition dominates" in concise
    assert estimate_tokens(concise) < estimate_tokens(detailed)
    uniform, _ = ot.call_tool("kafka_consumer_lag", {"group": "search-indexer"})
    assert "dominates" not in uniform


def test_logs_search_paginates():
    page1, err = ot.call_tool("logs_search", {"service": "ledger-writer", "level": "ERROR", "limit": 5})
    assert not err and page1.startswith("5 of 14 log lines") and "cursor='5'" in page1
    page3, _ = ot.call_tool("logs_search", {"service": "ledger-writer", "level": "ERROR", "limit": 5, "cursor": "10"})
    assert page3.startswith("4 of 14") and "cursor=" not in page3


def test_validation_errors_name_valid_values():
    for args, needle in [({"service": "ledger-writer", "level": "FATAL"}, "level must be one of"),
                         ({"service": "ledger-writer", "limit": 500}, "page with the returned cursor"),
                         ({"service": "ledger-writer", "cursor": "abc"}, "Pass back the exact cursor")]:
        content, is_error = ot.call_tool("logs_search", args)
        assert is_error and needle in content


def test_dispatch_errors_are_actionable():
    c, e = ot.call_tool("kafka_lag", {"group": "x"})
    assert e and "Available tools" in c and "kafka_consumer_lag" in c
    c, e = ot.call_tool("deploys_get_status", {"svc": "ledger-writer"})
    assert e and "Accepted parameters" in c and "service" in c


def test_deploy_status_shows_rollout():
    c, e = ot.call_tool("deploys_get_status", {"service": "ledger-writer"})
    assert not e and "status=rolling" in c and "pods_ready=7/12" in c
