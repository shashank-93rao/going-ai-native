# 17: The AI-native engineer and team
> After this module you can run a team where most code is written by agents: route review by risk, vote out noisy machine findings, keep the team's understanding of the system intact, measure whether any of it helps, hire for it, and position your own career.

## Why this matters
Every earlier module made a single agent run checkable. This one deals with what happens when you have hundreds of those runs a week across a team. The first thing to break is review. Anthropic's Claude Code team reports that Claude writes about 90% of Claude Code's code, and that merged PRs more than doubled between June and September 2026 ([Osmani, Lunt and Wang, "How the Claude Code team does code review"](https://claude.dev/blog/solving-code-review-at-anthropic/)). Stripe reports more than 1,000 merged PRs a week that contain no human-written code ([Stripe, "Minions"](https://stripe.dev/blog/minions-stripes-one-shot-end-to-end-coding-agents)). If every one of those PRs gets the same careful human read, review becomes the bottleneck; if none do, you are shipping code nobody read. Neither works.

The second thing to break is understanding, and it breaks quietly. Code can be clean, tested and reviewed and still be something nobody on the team can explain. Margaret Storey calls this cognitive debt, and notes it "tends not to announce itself through failing builds" ([Storey, "Cognitive debt"](https://margaretstorey.com/blog/2026/02/09/cognitive-debt/)). It surfaces at 3 a.m., when the on-call engineer opens a Raft election path that an agent wrote and three people approved, and none of them can say why the vote is persisted asynchronously.

The third thing to break is honesty about results. METR's 2025 randomized trial found experienced developers took 19% longer with AI while believing they were about 20% faster ([METR 2025](https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/)). A team that measures PR count will see PR count go up and learn nothing. A senior engineer is the person who is supposed to notice that.

This module is about running that system: review policy, shared understanding, measurement, the operating model for background agents, hiring, and your own position in all of it.

## The distributed-systems anchor
**You are now running an org of fast but unreliable workers.** You already know how to build a reliable system from unreliable parts:

| What you know | What it becomes here |
|---|---|
| Quorum reads and writes | N independent reviewers, post only what a majority agrees on |
| Independent failure domains | Fresh-context reviewers that do not see each other's output or the author's transcript |
| Admission control by request class | Risk tiers: the change type sets how much review it gets |
| Retry budgets and circuit breakers | Round caps, CI-round caps, spend caps per run |
| Ownership of a service and its pager | A named human owner for every agent run and every merged change |
| SLOs with an error budget | Change fail rate and revert rate as guardrails on review speed |
| Runbooks and design docs | ADRs and "explain it back" so the system's theory survives |

**Where the analogy breaks.** Replicas in a quorum are independent because they run on different hardware. Model reviewers from the same model family, given the same prompt, are *correlated*: they share blind spots. Voting removes noise (one reviewer hallucinating a bug) far better than it removes shared bias (all reviewers missing the same class of bug). That is why the course pairs voting with an eval set built from your own past incidents, and why some paths always get a human. A second break: workers in a distributed system do not leave the team understanding less. Agents can.

## Learning goals
- [ ] Write a risk-tier policy that maps change types (docs, config, schema migration, consensus code) to human approvals, verifier count and round cap, and enforce it with a deterministic router.
- [ ] Explain why voting reviewers reduce noise but not correlated misses, and build a majority-vote reviewer that drops style findings and treats malformed output as an abstention.
- [ ] Write a REVIEW.md that says what failure looks like in your repo, caps nits, lists skip paths and requires file-and-line evidence.
- [ ] Name three signs of cognitive debt on your team and put two practices in place against it (ADRs, explain-it-back, ownership).
- [ ] Choose team metrics that cannot be gamed by agent volume, and design a small experiment that would show whether a practice helps.
- [ ] Write an AGENT_POLICY.md covering ownership, unattended work, budgets, inbox and on-call.
- [ ] Design an interview loop that tests building, verifying and defending a system with agents.
- [ ] Write your own 90-day adoption plan with measurable checkpoints.

## Reading order
1. [01-code-review-at-agent-volume.md](01-code-review-at-agent-volume.md): risk tiers, verifier voting, REVIEW.md, round caps, and how Anthropic, Stripe, Spotify and Cognition handle it.
2. [02-cognitive-debt-and-shared-understanding.md](02-cognitive-debt-and-shared-understanding.md): the debt that lives in people's heads, and the practices that pay it down.
3. [03-measuring-team-productivity.md](03-measuring-team-productivity.md): METR's lessons, DORA metrics, and why PR count is a vanity metric at agent volume.
4. [04-team-operating-model.md](04-team-operating-model.md): background agents, the agent inbox, ownership, on-call for agents, budgets.
5. [05-hiring-and-evaluating-ai-native-engineers.md](05-hiring-and-evaluating-ai-native-engineers.md): interviews where candidates build and deploy with agents, then defend against adversarial agents.
6. [06-career-positioning.md](06-career-positioning.md): what gets more and less valuable for a senior engineer, and a 90-day personal plan.
- [examples.md](examples.md): a REVIEW.md for a distributed-systems repo, a risk-tier table, a 90-day team rollout, and two incident-shaped scenarios.
- [exercises.md](exercises.md): hands-on work, offline and with a real agent.
- [code/](code/): `review_router.py`, `verifier_vote.py`, and the REVIEW.md and AGENT_POLICY.md templates, with tests.
- [references.md](references.md)

## Prerequisites
- [04-agentic-coding-workflows](../04-agentic-coding-workflows/README.md): specs, plans and the writer/reviewer split at the level of one engineer.
- [07-loops](../07-loops/README.md): loop budgets and stop conditions, which reappear here as round caps and spend caps.
- [11-llm-as-judge](../11-llm-as-judge/README.md): a machine reviewer is a judge; calibrating it is the same work.
- [14-steering-and-guardrails](../14-steering-and-guardrails/README.md): Stop-hook gates, which are where most pre-PR review happens.
- Helpful: [15-observability-and-production](../15-observability-and-production/README.md) for change-fail and rollback mechanics, and [16-security-and-containment](../16-security-and-containment/README.md) for why CI and agent-instruction files are always-human paths.

## Key takeaways
- **Review is routed by risk, not applied uniformly.** Low-risk changes can need zero humans once automated checks pass; consensus code, destructive migrations and replication config need two. An agent's approval never counts as a human's.
- **The tier router is deterministic and fails safe.** Unknown paths get medium, not low. A model classifier may raise the tier and never lower it.
- **Vote out noise, eval out blind spots.** Majority voting across fresh-context reviewers kills one-off false positives. It does not catch what every reviewer misses; a daily eval built from your own incident-causing PRs does.
- **Drop style findings from machine review.** Linters own style. Reviewers asked to find problems will always find some; keep them on failures that matter.
- **Cap rounds.** Agent authors and agent reviewers will loop all night if you let them. After about three rounds, stop and rethink the approach.
- **Cognitive debt is the real debt.** For every high-risk change, at least one human must be able to explain it without the agent. Write the why down (ADRs), not just the what.
- **Measure outcomes, not output.** PR count and "% written by AI" are vanity metrics at agent volume. Track lead time, change fail rate, deployment rework rate and revert rate, and run small experiments before believing anyone's speedup, including your own.
- **Every agent run has a human owner, a budget and a kill switch.** Background work reports to an inbox with an SLO, not to DMs.
