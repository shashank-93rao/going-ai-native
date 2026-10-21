"""Egress as a capability: the allow/deny decision an outbound proxy makes for an agent sandbox.

The sandbox has no route to the internet. Every outbound request goes through a proxy that
calls `decide(request, policy)`. The policy is default-deny, and each rule grants a *capability*
(host + methods + path prefixes), not just a destination. "github.com is allowed" is too
coarse: the useful question is "which operations on github.com can this agent perform?"

Rules enforced, in order:
  1. https only, default port only, no userinfo in the URL
  2. host must be a DNS name (no IP literals, no decimal/hex IP tricks, no localhost/metadata)
  3. host must match a rule exactly, or a rule's explicit "*." wildcard
  4. method must be granted by that rule; path must start with a granted prefix
  5. caller-supplied credentials are refused on hosts where the proxy injects credentials
     (the "allowlisted API domain + attacker's own key" exfiltration path)
  6. size caps on query strings and bodies, so an allowed GET cannot carry a payload out

Run: python egress_proxy_policy.py
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

MAX_QUERY_BYTES = 256
MAX_BODY_BYTES = 64 * 1024
CREDENTIAL_HEADERS = {"authorization", "x-api-key", "proxy-authorization", "cookie"}
_NUMERIC_HOST = re.compile(r"^(0x[0-9a-f]+|[0-9]+)(\.(0x[0-9a-f]+|[0-9]+))*$")


@dataclass(frozen=True)
class EgressRule:
    """One capability grant. `host` is exact ("pypi.org") or a wildcard ("*.pythonhosted.org").

    Write path prefixes with a trailing slash ("/acme/repo/") so "/acme/repo-evil" cannot match.
    """

    host: str
    methods: frozenset[str] = frozenset({"GET"})
    path_prefixes: tuple[str, ...] = ("/",)
    proxy_injects_credentials: bool = False
    max_body_bytes: int = 0  # 0 means "no request body allowed"

    def matches_host(self, host: str) -> bool:
        if self.host.startswith("*."):
            suffix = self.host[1:]  # ".pythonhosted.org"
            return host.endswith(suffix) and len(host) > len(suffix)
        return host == self.host


@dataclass(frozen=True)
class EgressRequest:
    method: str
    url: str
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes = b""


@dataclass(frozen=True)
class Decision:
    allow: bool
    reason: str
    rule: EgressRule | None = None


def _deny(reason: str) -> Decision:
    return Decision(False, reason)


def normalize_host(raw: str) -> str:
    """Lowercase, strip one trailing dot, IDNA-encode. Raises ValueError on garbage."""
    host = raw.strip().lower().rstrip(".")
    if not host:
        raise ValueError("empty host")
    return host.encode("idna").decode("ascii")


def _is_ip_like(host: str) -> bool:
    try:
        ipaddress.ip_address(host.strip("[]"))
        return True
    except ValueError:
        # 2130706433, 0x7f000001 and 127.1 all resolve to loopback in many resolvers
        return bool(_NUMERIC_HOST.match(host))


def decide(req: EgressRequest, policy: list[EgressRule]) -> Decision:
    """Return allow/deny with a reason. Pure function: no DNS, no I/O."""
    try:
        parts = urlsplit(req.url)
    except ValueError as e:
        return _deny(f"unparseable url: {e}")
    if parts.scheme != "https":
        return _deny(f"scheme {parts.scheme!r} not allowed (https only)")
    if parts.username is not None or parts.password is not None or "@" in parts.netloc:
        return _deny("userinfo in url")
    try:
        if parts.port not in (None, 443):
            return _deny(f"port {parts.port} not allowed")
    except ValueError:
        return _deny("invalid port")
    if parts.hostname is None:
        return _deny("no host")
    if _is_ip_like(parts.hostname):
        return _deny("ip literal hosts are never allowed (metadata endpoints, internal ranges)")
    try:
        host = normalize_host(parts.hostname)
    except (ValueError, UnicodeError) as e:
        return _deny(f"bad host: {e}")
    if host == "localhost" or host.endswith(".localhost") or host.endswith(".internal"):
        return _deny("local/internal host")

    rule = next((r for r in policy if r.matches_host(host)), None)
    if rule is None:
        return _deny(f"host {host} not in allowlist")

    method = req.method.upper()
    if method not in rule.methods:
        return _deny(f"method {method} not granted on {rule.host}")
    path = parts.path or "/"
    if ".." in path.split("/"):
        return _deny("path traversal segment")
    if not any(path.startswith(p) or path == p.rstrip("/") for p in rule.path_prefixes):
        return _deny(f"path {path} not under a granted prefix on {rule.host}")

    supplied = {h.lower() for h in req.headers} & CREDENTIAL_HEADERS
    if supplied and rule.proxy_injects_credentials:
        return _deny(f"caller-supplied credentials {sorted(supplied)} refused; proxy injects its own")
    if len(parts.query.encode()) > MAX_QUERY_BYTES:
        return _deny(f"query string over {MAX_QUERY_BYTES} bytes")
    if len(req.body) > min(rule.max_body_bytes, MAX_BODY_BYTES):
        return _deny(f"body of {len(req.body)} bytes exceeds cap {rule.max_body_bytes} on {rule.host}")
    return Decision(True, f"granted by rule {rule.host}", rule)


# A policy for a coding agent that installs Python deps and opens PRs on one repo.
CODING_AGENT_POLICY: list[EgressRule] = [
    EgressRule("pypi.org", path_prefixes=("/simple/", "/pypi/")),
    EgressRule("files.pythonhosted.org", path_prefixes=("/packages/",)),
    EgressRule("github.com", path_prefixes=("/acme/payments-svc/", "/acme/payments-svc.git/")),
    EgressRule(
        "api.github.com",
        methods=frozenset({"GET", "POST"}),
        path_prefixes=("/repos/acme/payments-svc/",),
        proxy_injects_credentials=True,
        max_body_bytes=32 * 1024,
    ),
]


if __name__ == "__main__":
    probes = [
        EgressRequest("GET", "https://pypi.org/simple/requests/"),
        EgressRequest("GET", "https://github.com.evil.example/x"),
        EgressRequest("GET", "http://169.254.169.254/latest/meta-data/"),
        EgressRequest("POST", "https://api.github.com/repos/acme/payments-svc/pulls", body=b"{}"),
        EgressRequest("POST", "https://api.github.com/repos/someone-else/repo/issues", body=b"{}"),
        EgressRequest("GET", "https://pypi.org/simple/?q=" + "A" * 400),
    ]
    for p in probes:
        d = decide(p, CODING_AGENT_POLICY)
        print(f"{'ALLOW' if d.allow else 'DENY '} {p.method:4} {p.url[:70]:70} {d.reason}")
