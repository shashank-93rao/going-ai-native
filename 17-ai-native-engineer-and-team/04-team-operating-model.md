# 04: The team operating model for agents

## The idea
Once agents run in the background (on a schedule, from a Slack thread, on every flaky-test ticket), a team needs the same things it needs for any fleet of workers: a way to hand them work, a place where their results land, an owner for every result, someone on call when they misbehave, and a budget. Most teams get these by accident, one engineer at a time. This concept is about designing them on purpose and writing them down, in an `AGENT_POLICY.md` the team can argue about and enforce.

The shape that works across Stripe, Spotify, Anthropic and Cognition (*course synthesis*):
- **Work comes in through one front door**: a ticket, a Slack mention, a schedule. Each run gets an ID and an owner at creation.
- **Agents run in isolated, disposable environments** with a curated toolset.
- **Deterministic gates run before anything reaches a human**: build, tests, verifiers, machine review.
- **Results land in an inbox**, not in DMs, typed as notify, question or review.
- **One human owns each result** and is the author of record.
- **Budgets and kill switches** are configuration, not heroics.

## Why it matters
Without this, background agents fail in two opposite ways.

They fail **loudly**: an agent opens forty PRs overnight, or two agents edit the same file, or an agent-author and agent-reviewer pair go round fifty times on one CLI PR (which happened at Anthropic before round caps, per [Osmani et al. 2026](https://claude.dev/blog/solving-code-review-at-anthropic/)). Cognition's 2025 "Don't build multi-agents" post is a catalogue of what happens when parallel writers make conflicting implicit decisions; its 2026 update says multi-agent setups work when "writes stay single-threaded and the additional agents contribute intelligence rather than actions" ([Cognition 2026](https://cognition.com/blog/multi-agents-working)). That is the single-writer principle you already use for replicated state.

They also fail **quietly**. Anthropic's guide to scheduled agent automations opens with the observation that scheduled agents lose access to a source or drift from preferences and nobody notices. It recommends that a failed read be reported as unreadable, never as a quiet day ([Anthropic, "Building effective agent automations"](https://claude.dev/blog/building-effective-agent-automations/)). LangChain built its Agent Inbox on ticket-queue metaphors because Slack notifications for agent output got lost ([Chase, "Introducing ambient agents"](https://www.langchain.com/blog/introducing-ambient-agents)).

## How it works

### Intake and isolation
Stripe's minions are most often started by tagging a Slack app in the thread that discusses the change, and can also start from the CLI, a web UI, the docs platform, feature-flag platform or ticketing UI; flaky-test tickets have a button to launch one. Each minion runs in a pre-warmed devbox that spins up in about 10 seconds, cut off from production and the internet, which is what lets it run without per-action permission prompts ([Stripe](https://stripe.dev/blog/minions-stripes-one-shot-end-to-end-coding-agents)). The lessons for your team:
- Launching should be one action from where the work is discussed. If it is hard, people run agents on laptops with their own credentials, outside any policy.
- Isolation buys autonomy. The tighter the sandbox, the fewer approvals the run needs ([module 16](../16-security-and-containment/README.md)).
- Curate tools per task. Stripe hosts 400+ tools in its internal MCP server and gives each minion a subset; Spotify keeps its toolset minimal (verify, restricted git, allowlisted bash).

### The inbox
LangChain's three human-in-the-loop patterns make a good type system for inbox items:

| Type | Meaning | Example | SLO (course default) |
|---|---|---|---|
| notify | FYI, no action needed | "Nightly dependency scan: 3 bumps merged at low tier" | none; auto-archive after 7 days |
| question | The agent needs a decision to continue | "Two callers depend on the old retry semantics. Keep or change?" | 1 working day, then the run pauses |
| review | A result needs a human approval | "PR #5121, medium tier, 1 approval needed" | per tier; tracked as PR wait time |

Mitchell Hashimoto's end-of-day practice fits this: spend the last 30 minutes launching research, exploration and triage agents that only write reports, and read them in the morning ([Hashimoto](https://mitchellh.com/writing/my-ai-adoption-journey)). Those reports are notify items. He turns notifications off for background work, which is the point: the inbox is pulled, not pushed.

### Ownership
Anthropic's rules are a good baseline: the person directing an agent counts as a required reviewer, an agent's approval never counts as a person's, and "a person is accountable for every shipped change". At Stripe the engineer who launched the minion reviews the result and opens the PR. Make this mechanical: the run's owner is recorded at launch and written into the PR as a trailer, and the PR bot rejects agent PRs without one. For scheduled runs, the owner is whoever owns the schedule, and ownership transfers when people move teams, like any other on-call handover.

### On-call for agents
Agents become part of the production surface of your engineering system. Give them the same treatment as a service:
- **A kill switch** that pauses every schedule without a deploy. Anthropic's Claude Code team ships behaviour behind flags that turn off without a deploy and runs a weekly on-call rotation; do the same for your agent fleet.
- **Alerts on the agent system itself**: PRs opened per hour, runs over budget, runs past the round cap, rate of "no PR" outcomes, inbox questions past SLO.
- **Idempotent schedules.** The automations guide recommends bookmarks rather than time windows ("a late run leaves a gap and an early run repeats items"), a ledger with stable IDs, and a "maybe posted" state when an action's success is unknown. You know these as exactly-once-ish delivery with a dedup table.
- **Incident reviews ask which layer should have caught it** (spec, verifier, machine review, human review, rollout), and the fix goes into that layer. Each incident-causing PR goes into the reviewer's eval set.

### Budgets
| Budget | Example | Source |
|---|---|---|
| CI rounds per run | at most 2 | Stripe: "often one, at most two, CI runs" |
| Review rounds per PR | 3, then rethink | Anthropic round cap |
| Spend per scheduled run | start at 3 to 5x a normal run; a capped run pauses | Anthropic automations guide |
| Wall clock per run | 60 min (course default) | |
| Spend per engineer per month | set by the team; reviewed weekly | course default |

A budget breach should **pause and notify the owner**, not kill silently and not continue. A silent kill is the quiet failure mode again.

## Worked example
A team of eight runs a Kafka-based ingestion pipeline. Three engineers have started running agents nightly.

**Bad version.** Each engineer has a cron job on their own devbox:

```bash
# @sam's crontab
0 2 * * * cd ~/ingest && claude -p "Find and fix flaky tests in ./consumer. Open a PR." \
  --permission-mode bypassPermissions >> ~/agent.log 2>&1
```

What goes wrong (a composite of the failure modes above): the agent "fixes" a flaky rebalance test by adding `t.Skip`; CI passes; a teammate approves it among six other overnight PRs. Two weeks later a second engineer's nightly job edits the same consumer for a lag metric, conflicting with Sam's agent. Sam goes on holiday and his cron keeps running with his credentials. Nobody can say what the agents cost last month. The consumer group's rebalance bug, which the skipped test was catching, reaches production.

**Good version.** The team writes [AGENT_POLICY.md](code/templates/AGENT_POLICY.md) and moves scheduled runs onto shared infrastructure with config in the repo:

```yaml
# agents/schedules/flaky-tests.yaml
id: flaky-test-triage
owner: "@ingest-oncall"          # rotates with on-call, not a person's laptop
trigger: { cron: "0 2 * * 1-5" }
scope:
  paths: ["consumer/**"]
  exclusive_lock: "consumer"      # single writer: no other schedule edits consumer/ concurrently
mode: report_only                 # writes an inbox item, not a PR, until this schedule earns trust
tools: [verify, git_readonly, bash_allowlist]
budget: { max_ci_rounds: 2, max_minutes: 45, max_usd: 6.00, on_exceed: pause_and_notify }
gates:
  stop_hook: ["make build", "go test -race -count=3 ./consumer/..."]
  forbid_patterns_in_diff: ["t\\.Skip\\("]
inbox: { channel: ingest-agents, unreadable_source: report_as_error }
```

The inbox item from the first run (illustrative output):

```json
{
  "type": "question",
  "run_id": "flaky-test-triage/2026-10-14",
  "owner": "@ingest-oncall",
  "summary": "TestRebalanceCommitsOffsets fails 3/20 runs under -race. Root cause candidate: offset commit races partition revocation (consumer/rebalance.go:118).",
  "evidence": ["go test -race -count=20 output: 3 failures, same stack"],
  "question": "Fix the race (changes commit ordering, high tier) or quarantine the test?",
  "cost_usd": 2.31
}
```

The on-call engineer answers "fix the race", which launches a separate, interactive, high-tier run with them as owner. The router puts the resulting PR at high tier because it touches offset commit ordering. The skip-the-test path is closed by a gate, not by hoping the reviewer notices.

## Pitfalls
| Pitfall | How to detect it |
|---|---|
| **Personal crons with personal credentials.** | Inventory: list every token used by an agent in the last 30 days and map it to a schedule with an owner. Unmapped tokens get revoked. |
| **Inbox becomes a second Slack.** | Track the age of open question items. If the median passes the SLO, cut the number of schedules before adding more. |
| **Parallel writers on shared code.** | Lock per path scope; alert when two runs touch the same file within a day. |
| **Budgets that kill silently.** | Every budget stop must produce an inbox item. Count stops vs items. |
| **Report-only forever.** Schedules never graduate, so nobody trusts or uses them. | Promote a schedule from report-only to PR mode after N reports with no wrong findings, as a written rule. |

## In your day job
- List every agent your team runs unattended today, with owner, credentials, budget and where results go. The gaps in the list are the policy you need to write.
- Copy [code/templates/AGENT_POLICY.md](code/templates/AGENT_POLICY.md), change it to fit, and get it reviewed like code.
- Put a kill switch on every schedule before adding the next one.
- Give each background agent a "report only" period before it can open PRs.
