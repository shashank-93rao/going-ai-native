# 06: Human-in-the-loop design: approval tiers, agent UX, the inbox

## The idea

A human reviewer is a verifier with very high precision and very low throughput, high latency and high cost. Like any scarce resource, you place it deliberately. Put humans where **the automated oracle is weakest** and **the blast radius is largest**, and nowhere else. Everywhere else they are a bottleneck, and worse, a rubber stamp.

Three design questions decide whether a human-in-the-loop (HITL) system works:

1. **Tiering.** Which actions need a human, how many, and synchronously or asynchronously?
2. **The request.** What does the human see when asked? Can they decide in 30 seconds with evidence, or do they have to reconstruct the context?
3. **The channel.** Where do requests go, how are they ordered, what happens on timeout, and how do you stop an approval from being reused for a different action?

Distributed-systems anchor: approvals are a **two-phase commit with a human coordinator**. The agent prepares the action (phase 1) and the human commits or aborts it (phase 2). Everything you know applies. The prepared state must be durable, because the agent may be gone by the time the human answers. The commit must bind to *exactly* what was prepared, or you get time-of-check-to-time-of-use bugs. And you need a timeout policy for a coordinator who never answers.

## Why it matters

- **Approval fatigue is measured.** Anthropic reports that Claude Code users approve 93% of permission prompts. At that rate the prompt is a ritual, not a check, and it's the motivation for auto mode, which replaces most prompts with a classifier ([Anthropic, "How we built Claude Code auto mode"](https://www.anthropic.com/engineering/claude-code-auto-mode)). The same post gives the honest classifier numbers: 0.4% false-positive rate on 10k real actions, and a 17% false-negative rate on 52 real overeager actions. Neither humans clicking "yes" nor a classifier is a perfect gate, which is why tiers and containment exist.
- **Risk tiers at agent volume.** The Claude Code team's review process sets low-risk changes to zero human approvals, medium to one, and high to two. A classifier assigns the tier, an agent's approval never counts as a human's, and an approval covers one commit ([Anthropic, "How the Claude Code team does code review"](https://claude.dev/blog/solving-code-review-at-anthropic/)). They report merged PRs more than doubling while the revert share fell by more than 40% over the period.
- **OpenAI's practical guide** rates each tool low, medium or high risk by read vs write access, reversibility and financial impact, and names two triggers for handing control to a human: exceeding failure thresholds and high-risk actions ([OpenAI, "A practical guide to building agents"](https://cdn.openai.com/business-guides-and-resources/a-practical-guide-to-building-agents.pdf)).
- **Where the interrupt goes.** 12-Factor Agents says the most-requested framework feature is an interrupt *between tool selection and tool invocation*, for approval. It treats "contact a human" as a tool call that breaks the loop, with thread state saved and resumed by webhook ([HumanLayer, 12-factor-agents](https://github.com/humanlayer/12-factor-agents)).

## How it works

### Approval tiers

Score each action on three axes and take the worst:

| Axis | Low | High |
|---|---|---|
| Reversibility | `git revert`, a feature flag | a sent email, a charge, a dropped table, a force-push |
| Blast radius | your branch, your worktree | shared infra, customer data, other teams |
| Verifiability | strong oracle (tests, typecheck, diff check) | judgment only ("is this the right design?") |

| Tier | Policy | Examples | Mechanism in Claude Code |
|---|---|---|---|
| **T0** auto | no human; logged | reads, in-repo edits (git makes them reviewable), the fast test command | `allow` rules, `acceptEdits` or `auto` mode |
| **T1** auto + gate + post-hoc review | no human before; a deterministic gate before "done"; human review at PR | finish a task, open a draft PR | Stop gate ([03](03-hooks-as-gates.md)), drift monitor ([05](05-detecting-drift.md)) |
| **T2** async approval | human approves in an inbox; the agent parks or continues other work | push a branch, deploy to staging, a migration on a dev DB | `ask` rules; or a "request_approval" tool that ends the turn |
| **T3** sync, two-person | two humans; the action is prepared, never executed by the agent | prod infra, data deletion, money movement, IAM | `deny` for the agent; the agent writes a runbook or PR and humans execute it |

Two rules sit above the table:

- **An agent never approves its own T2/T3 action**, and an agent's approval never counts as a human's. This is the same reason a service doesn't sign its own certificates.
- **Approvals bind to the exact action.** Hash the tool name plus its full input (command, args, target, diff SHA) when the request is made, and execute only if the hash still matches when the approval arrives. If the agent changes one flag after approval, the approval is void. "Approvals cover one commit" is the same rule for code review.

### Agent UX: what an approval request must contain

A good request lets a human decide in under a minute without opening a terminal.

```json
{
  "id": "apr_01J9Z4Q7",
  "tier": "T2",
  "action": {"tool": "Bash", "command": "kubectl -n payments rollout undo deploy/charge-api --to-revision=41"},
  "action_sha256": "9f2c...e1",
  "why": "p99 for POST /charges rose 180ms -> 2.4s at 14:02 UTC, matching deploy rev 42 (14:01). Rev 41 was healthy for 6 days.",
  "evidence": [
    "grafana: charge-api p99 panel, 13:30-14:20 (link)",
    "kubectl rollout history: rev 42 = image charge-api:2026.10.19-3 (diff: connection pool size 50 -> 5)"
  ],
  "blast_radius": "charge-api in payments namespace only; ~3 min rolling restart; no schema change between 41 and 42",
  "rollback": "kubectl rollout undo --to-revision=42",
  "if_no_answer": "expire in 15 min; do nothing; re-page on-call",
  "alternatives_considered": ["scale replicas 6 -> 12 (rejected: pool exhaustion is per-pod)"]
}
```

Each field answers a question the approver would otherwise have to ask. **What exactly** (`action`, the hash)? **Why now** (`why`, `evidence`)? **What can go wrong** (`blast_radius`)? **How do I undo it** (`rollback`)? **What if I'm busy** (`if_no_answer`)? Compare this with the default prompt for the same action:

```text
Claude wants to run: kubectl -n payments rollout undo deploy/charge-api --to-revision=41
[Yes] [Yes, don't ask again] [No]
```

That prompt is fine at T0 and T1, and it is where the 93% approval rate comes from. At T2 and above it asks the human to reconstruct the agent's reasoning from nothing, so they either take ten minutes or click Yes.

The Anthropic automations post states the trust rule for agent-produced status well: "One stale 'still waiting on you' costs more trust than ten missing items, so never hedge an item's status: assert it or drop it" ([Anthropic, "Building effective agent automations"](https://claude.dev/blog/building-effective-agent-automations/)). Approval requests are the same. A request whose evidence is stale or vague trains people to ignore the channel.

### The inbox

Harrison Chase's ambient-agents post names three HITL patterns ([LangChain, "Introducing ambient agents"](https://www.langchain.com/blog/introducing-ambient-agents)):

- **Notify**: flag something without acting ("CI on main red for 2h, likely flaky test X").
- **Question**: ask instead of guessing ("Two readings of the spec lead to different migrations. A or B?").
- **Review**: approve, edit, or give feedback on a planned action.

They built an "Agent Inbox" on ticket-queue metaphors because Slack notifications got lost. Treat the inbox like any work queue:

- **Durable and ordered by risk and age**, not by arrival.
- **Each item is self-contained** (the JSON above), so the agent can be gone when the human answers.
- **Timeouts with a safe default**, which for T2 and above is almost always "do nothing".
- **Idempotent resolution.** Approving twice must not execute twice. Key execution on the approval id.
- **Edit as a first-class answer.** "Approve with `--to-revision=40`" should produce a *new* action hash and re-validation, not a silent mutation.

```mermaid
sequenceDiagram
    participant A as Agent
    participant G as Guard (PreToolUse)
    participant I as Inbox (durable)
    participant H as Human
    A->>G: kubectl rollout undo ...
    G-->>A: deny: "T2 action; file an approval request with evidence"
    A->>I: request_approval(action, sha, why, evidence, rollback)
    A-->>A: end turn / continue other work
    H->>I: approve apr_01J9Z4Q7
    I->>I: verify sha(action) unchanged, not already executed
    I->>A: resume thread with approval
    A->>G: kubectl rollout undo ... (approval token)
    G-->>A: allow (token matches sha)
```

## Worked example: tiering an on-call triage agent

Your team wants an agent that responds to `charge-api` latency pages. Here is the naive tiering and what happens with it.

**Naive.** The agent runs in `default` (Manual) mode. The on-call engineer approves each command from the terminal.

*What happens* (illustrative): at 03:00 the engineer approves 14 prompts in four minutes. Twelve are reads (`kubectl get`, `logs`). One is `kubectl rollout undo`, and one is `kubectl scale --replicas=40`, which exhausts the DB connection limit. Both were approved in the same rhythm as the reads. Prompting everything means nothing gets reviewed.

**Tiered.**

| Action | Tier | Mechanism |
|---|---|---|
| `kubectl get/describe/logs`, Grafana queries, reading runbooks | T0 | `allow: ["Bash(kubectl get *)", "Bash(kubectl describe *)", "Bash(kubectl logs *)"]` |
| Writing an incident summary, drafting a status-page update | T1 | draft only; a human publishes |
| `kubectl rollout undo` to the previous revision | T2 | `pre_tool_guard.py` returns `ask`; better, deny plus a `request_approval` tool with the JSON above |
| `kubectl scale`, config changes, anything touching the DB | T3 | `deny` for the agent; it writes the proposed command and justification into the incident doc |

*Result* (illustrative): the engineer sees one rich request instead of 14 prompts, and spends a minute on the one decision that mattered.

## Pitfalls

- **Prompting everything.** It yields a 93%-style approval rate and zero real review. *Detect:* measure your own approval rate and time-to-approve per tier. If T2 approvals take under 3 seconds, people aren't reading them.
- **Approvals not bound to the action.** The agent gets "yes" for `rollout undo --to-revision=41`, then runs `--to-revision=40` because it "noticed 41 was also bad". *Detect:* log the hash at request and at execution, and alert on any mismatch.
- **No timeout policy.** A T2 request with no default either blocks the agent forever or gets auto-approved by a well-meaning script. *Detect:* every inbox item needs an `if_no_answer` field. Reject requests without one.
- **Synchronous blocking for T2.** The agent sits idle holding context while the human is in a meeting. Save state and end the turn (12-factor's launch/pause/resume), or continue other work.
- **Human review standing in for an oracle.** If a human approves every PR because there are no tests, that isn't HITL; it's a missing check. Fix the check, then tier the review.
- **Counting agent review as human review.** A clean-context reviewer agent is valuable ([Module 17](../17-ai-native-engineer-and-team/README.md)), but it is a T1 mechanism. It doesn't satisfy a T2 or T3 requirement.

## In your day job

- Write your team's tier table for the agent actions you already allow. Most teams find that their "high-risk" actions sit in the allow list and their reads sit in the prompt queue.
- Move T0 actions into `allow` rules so prompts become rare enough to be read.
- For one T2 action (staging deploys, say), build the approval-request JSON and bind execution to its hash. It takes a day and removes a whole class of "it ran something slightly different" incidents.
- Give agent requests a home that isn't a chat channel: a queue with ages, owners and timeouts.
