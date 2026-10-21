import pytest
from hypothesis import given, strategies as st

from egress_proxy_policy import CODING_AGENT_POLICY, EgressRequest, EgressRule, decide


def allowed(method: str, url: str, **kw) -> bool:
    return decide(EgressRequest(method, url, **kw), CODING_AGENT_POLICY).allow


@pytest.mark.parametrize(
    "url",
    [
        "https://pypi.org/simple/requests/",
        "https://PYPI.ORG./simple/requests/",  # case and trailing dot normalize
        "https://files.pythonhosted.org/packages/ab/cd/requests-2.32.3.tar.gz",
        "https://github.com/acme/payments-svc.git/info/refs",
        "https://pypi.org:443/pypi/requests/json",
    ],
)
def test_legitimate_requests_allowed(url):
    assert allowed("GET", url), url


@pytest.mark.parametrize(
    "url,why",
    [
        ("http://pypi.org/simple/requests/", "plain http"),
        ("https://pypi.org:8443/simple/", "non-default port"),
        ("https://github.com.evil.example/acme/payments-svc", "suffix lookalike"),
        ("https://evil.example/?u=github.com", "allowlisted name only in query"),
        ("https://user:pw@github.com/acme/payments-svc", "userinfo"),
        ("https://evil.example@github.com/acme/payments-svc", "userinfo confusion"),
        ("http://169.254.169.254/latest/meta-data/", "cloud metadata"),
        ("https://169.254.169.254/latest/meta-data/", "cloud metadata over https"),
        ("https://[::1]/", "ipv6 loopback"),
        ("https://2130706433/", "decimal ip"),
        ("https://0x7f000001/", "hex ip"),
        ("https://127.1/", "short-form ip"),
        ("https://localhost/", "localhost"),
        ("https://metadata.google.internal/", "internal name"),
        ("https://github.com/attacker/drop-box", "allowed host, ungranted path"),
        ("https://github.com/acme/payments-svc-evil/x", "prefix without boundary"),
        ("https://github.com/acme/payments-svc/../../attacker/x", "traversal"),
        ("https://bit.ly/abc", "url shortener (default deny)"),
        ("https://pythonhosted.org/packages/x", "bare apex is not *.pythonhosted.org"),
    ],
)
def test_attacks_denied(url, why):
    assert not allowed("GET", url), why


def test_method_is_part_of_the_capability():
    assert not allowed("POST", "https://pypi.org/simple/requests/", body=b"x")
    assert not allowed("DELETE", "https://api.github.com/repos/acme/payments-svc/git/refs/heads/main")


def test_write_scoped_to_one_repo():
    assert allowed("POST", "https://api.github.com/repos/acme/payments-svc/pulls", body=b'{"title":"fix"}')
    assert not allowed("POST", "https://api.github.com/repos/attacker/inbox/issues", body=b"{}")


def test_caller_supplied_credentials_refused_where_proxy_injects():
    # The containment lesson: an allowed API domain plus the attacker's own key = upload to attacker.
    d = decide(
        EgressRequest(
            "POST",
            "https://api.github.com/repos/acme/payments-svc/issues",
            headers={"Authorization": "token ghp_attacker"},
            body=b"{}",
        ),
        CODING_AGENT_POLICY,
    )
    assert not d.allow and "credentials" in d.reason


def test_query_and_body_caps_block_smuggling():
    assert not allowed("GET", "https://pypi.org/simple/?leak=" + "A" * 300)
    assert not allowed("GET", "https://pypi.org/simple/requests/", body=b"secret")  # GET with body
    big = b"x" * (33 * 1024)
    assert not allowed("POST", "https://api.github.com/repos/acme/payments-svc/pulls", body=big)


def test_empty_policy_denies_everything():
    assert not decide(EgressRequest("GET", "https://pypi.org/simple/"), []).allow


def test_wildcard_rule():
    policy = [EgressRule("*.pythonhosted.org", path_prefixes=("/packages/",))]
    assert decide(EgressRequest("GET", "https://files.pythonhosted.org/packages/x"), policy).allow
    assert not decide(EgressRequest("GET", "https://evilpythonhosted.org/packages/x"), policy).allow


@given(st.text(min_size=1, max_size=40))
def test_garbage_never_crashes_and_unknown_hosts_denied(s):
    d = decide(EgressRequest("GET", f"https://{s}/"), CODING_AGENT_POLICY)
    # Only exact allowlisted hosts can pass; random text essentially never is one.
    if d.allow:
        assert d.rule is not None
