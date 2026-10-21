"""The templates are policy. These tests keep them from silently losing required parts."""

import re
from pathlib import Path

from review_router import load_policy

HERE = Path(__file__).parent
REVIEW = (HERE / "templates" / "REVIEW.md").read_text()
POLICY_MD = (HERE / "templates" / "AGENT_POLICY.md").read_text()


def headings(md: str) -> list[str]:
    return [h.lower() for h in re.findall(r"^#+\s+(.*)$", md, re.M)]


def test_review_md_has_the_sections_anthropic_reports_good_ones_have():
    hs = " | ".join(headings(REVIEW))
    for needed in ["what failure looks like", "what does not count", "evidence", "nit cap", "paths to skip", "output"]:
        assert needed in hs, needed


def test_review_md_is_short():
    assert len(REVIEW.split()) < 600, "REVIEW.md is read on every review; keep it short"


def test_review_md_owners_exist_in_router_policy():
    policy_owners = {o for r in load_policy()["rules"] for o in r.get("owners", [])}
    mentioned = set(re.findall(r"@[\w-]+", REVIEW))
    assert mentioned <= policy_owners


def test_agent_policy_covers_operating_model():
    hs = " | ".join(headings(POLICY_MD))
    for needed in ["ownership", "review tiers", "unattended", "budgets", "shared understanding",
                   "inbox and on-call", "measurement", "incidents"]:
        assert needed in hs, needed


def test_agent_policy_tier_table_matches_router_policy():
    tiers = load_policy()["tiers"]
    for name, row in tiers.items():
        m = re.search(rf"^\| {name.title()} \| (\d+)[^|]*\| (\d+) \| (\d+) \|", POLICY_MD, re.M)
        assert m, name
        assert (int(m.group(1)), int(m.group(2)), int(m.group(3))) == (
            row["human_approvals"], row["verifiers"], row["round_cap"])


def test_agent_policy_bans_vanity_metrics_for_people():
    assert "not used for evaluating people" in POLICY_MD.lower()
