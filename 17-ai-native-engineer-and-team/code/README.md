# Code: module 17

Everything here runs offline. With `ANTHROPIC_API_KEY` set (and `AINATIVE_FAKE` unset), `verifier_vote.py` calls the real model; otherwise it uses three canned reviewers that only make sense for `data/diffs/raft_election.diff`.

From the course root:

```bash
.venv/bin/python -m pytest -q 17-ai-native-engineer-and-team/code
```

To run the scripts directly, put the kit on the path (or `pip install -e .` from the course root):

```bash
cd 17-ai-native-engineer-and-team/code
export PYTHONPATH=../../shared
```

## Files
| File | What it does |
|---|---|
| `review_router.py` | Parses a unified diff and routes it to a risk tier using `data/review_policy.json`: human approvals, owners, verifier count, round cap, and the reason for each decision. Deterministic, fails safe (unknown paths are medium), and escalates large or untrusted-author low-tier diffs. |
| `verifier_vote.py` | Runs N independent fresh-context reviewers through `ainative_kit`, parses JSON findings, drops findings without `file:line` evidence or in REVIEW.md skip paths, clusters by location, drops style-only clusters, and posts clusters with a strict majority. Malformed output is an abstention; losing majority marks the run degraded. Traces one span per reviewer. |
| `templates/REVIEW.md` | Example REVIEW.md for a Raft-replicated Go ledger (`ledgerd`). |
| `templates/AGENT_POLICY.md` | Team agent policy: ownership, tiers, unattended work, budgets, shared understanding, inbox and on-call, measurement, incidents. |
| `data/review_policy.json` | Router rules for `ledgerd`. |
| `data/diffs/*.diff` | Eight sample diffs: docs, flag flip, replication config, additive and destructive migrations, a Raft safety bug, a test weakening, a CI change. |
| `test_review_router.py` | Parsing edge cases, every sample diff's expected tier, escalations, and a Hypothesis property: adding files never lowers the tier. |
| `test_verifier_vote.py` | Majority, style dropping, clustering window, evidence and skip-path filters, abstention and degraded quorum, reviewer independence, tracing, comment format. |
| `test_templates.py` | Keeps the templates honest: required sections, REVIEW.md length, owners match the router policy, the AGENT_POLICY tier table matches `review_policy.json`. |

## Examples
```bash
python review_router.py data/diffs/raft_election.diff
python review_router.py data/diffs/docs_only.diff --untrusted     # escalates to medium
git diff main... | python review_router.py - --policy my_policy.json

AINATIVE_FAKE=1 python verifier_vote.py data/diffs/raft_election.diff
python verifier_vote.py data/diffs/raft_election.diff --n 5      # real API, 5 reviewers
```

Offline output of the second command group:

```text
1 important, 0 other finding(s).
- [Important] internal/raft/election.go:42 (3/3 agree): Vote is granted before votedFor is durable; a crash after replying lets this node vote twice in one term.
(dropped: 1 minority, 1 style, 0 without file:line)
```

## Design notes
- **Router before model.** A model classifier may raise the router's tier and never lower it (exercise 5). Path globs use `fnmatch`, so `*` matches across `/`.
- **Denominator is N configured reviewers**, not N that answered. Abstentions make posting harder and trip the degraded flag, rather than silently shrinking the quorum.
- **Clustering is positional** (same file, same bucket, lines within 2). Real systems dedupe semantically; this keeps the voting logic testable. Exercise 4 adds a hunter/verifier phase.
- **No temperature is set** for reviewers. Independence comes from fresh contexts; vary models or focus prompts for more (exercise 3 stretch).
