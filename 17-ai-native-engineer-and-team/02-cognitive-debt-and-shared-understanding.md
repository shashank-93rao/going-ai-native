# 02: Cognitive debt and shared understanding

## The idea
**Cognitive debt** is the gap between what a system does and what the team that owns it understands about it. Technical debt lives in the code; cognitive debt lives in people's heads, or rather in what is missing from them. The Thoughtworks Technology Radar put "codebase cognitive debt" in its Caution ring in April 2026, defining it as "the growing gap between a system's implementation and a team's shared understanding of how and why it works" ([Thoughtworks Radar](https://www.thoughtworks.com/radar/techniques/codebase-cognitive-debt)).

Margaret Storey grounds it in Peter Naur's old argument that a program is a *theory* held by the people who built it, and the source code is only a partial record of that theory ([Storey 2026](https://margaretstorey.com/blog/2026/02/09/cognitive-debt/)). Agents produce code without producing the theory in anyone's head. A team can keep every lint green and every test passing and still end up with a system nobody can safely change.

You already know a version of this from operations: a service whose original authors have all left, with a runbook that says "restart it". Agents let a team build that situation in months instead of years, while the original authors are still on the team.

## Why it matters
Cognitive debt does not show up in any of the dashboards you already have. Storey's phrase is that it "tends not to announce itself through failing builds or subtle bugs after deployment". She describes a student team that stalled in week seven or eight. Their code wasn't messy; nobody could explain the design decisions any more. Her conclusion: "velocity without understanding is not sustainable."

Practitioners who are deep into agentic coding say the same thing about their own work. Armin Ronacher, who builds with agent loops daily, writes about code he cares about: "I want to understand the code I ship." He warns that with hands-off loops "we may no longer understand the whole system in the same way", and asks what happens if a team loses "the last remaining ability to understand the code without using the machine" ([Ronacher, "The Coming Loop"](https://lucumr.pocoo.org/2026/6/23/the-coming-loop/)). He also notes that models tend to add defensive code that makes a system look more robust while making it harder to understand.

Karpathy's Sequoia 2026 talk cites a line that sums up the stance: "You can outsource your thinking, but you can't outsource your understanding" ([Karpathy, Sequoia Ascent 2026](https://karpathy.bearblog.dev/sequoia-ascent-2026/)). He presents it as the reason humans stay responsible for spec, plan and design.

For a distributed-systems team the cost is concrete. Incidents in consensus, replication and storage code are rare, high-severity and time-critical. Mean time to recovery depends on someone being able to reason about the code under pressure. An agent can help in the incident, but it can't own the pager, and nothing it says at 3 a.m. can be trusted without someone who knows what correct looks like.

## How it works

### Signs you are accumulating it
From Storey, the Radar entry and course synthesis:
- People hesitate to change a component, or route every change in it through an agent.
- Knowledge sits with one or two people and isn't written down.
- Incident timelines show long stretches of "reading the code to understand what it does" on components that are less than a year old.
- PR descriptions describe *what* changed in detail and never *why*.
- Review comments on agent PRs are mostly approvals with no questions.
- Code keeps growing defensive branches (retries, fallbacks, nil checks) that no requirement asked for. Kent Beck lists "functionality nobody requested" as one of his three warning signs that an agent is going off track, alongside loops and cheating on tests ([Beck, "Augmented Coding: Beyond the Vibes"](https://newsletter.kentbeck.com/p/augmented-coding-beyond-the-vibes)).

### Practices that pay it down
None of these are new. What's new is that they become mandatory instead of good hygiene.

| Practice | What it buys | How to make it cheap |
|---|---|---|
| **Named human ownership** | Someone is accountable for being able to explain each change | The person who launched the agent is the author of record. Enforce with a PR trailer. |
| **Explain it back** | Proof that the owner has the theory, not just the diff | For high-tier changes, the owner writes, without the agent, a few sentences on what changed and what would break if it were wrong. |
| **ADRs** | The *why* survives after people move on | The agent drafts from the spec and PR discussion; a human edits and signs. Short: context, decision, consequences, alternatives rejected. |
| **Spec before code** | Understanding is built at the plan stage, where it is cheapest | [Module 04](../04-agentic-coding-workflows/README.md): interview, SPEC.md, plan review. Dex Horthy's point that one bad line of research becomes thousands of bad lines of code ([HumanLayer](https://github.com/humanlayer/advanced-context-engineering-for-coding-agents/blob/main/ace-fca.md)) applies to understanding too. |
| **Walkthroughs** | Fast onboarding into agent-written code | Simon Willison's "linear walkthroughs" pattern: ask an agent to produce a guided reading of a code path, saved as a doc ([Willison, Agentic Engineering Patterns](https://simonwillison.net/guides/agentic-engineering-patterns/)). Read it with the code open. |
| **Human-only reps** | Skills that don't atrophy | Occasionally fix a bug in a critical component without an agent. Mitchell Hashimoto's practice of reproducing his own past commits with an agent is the mirror image: it builds the skill of knowing what to ask for ([Hashimoto](https://mitchellh.com/writing/my-ai-adoption-journey)). |
| **Fitness functions** | Key constraints keep holding as the code churns | The Radar recommends architectural fitness functions. For a Raft service: a linearizability checker run in CI, a test that fails if any request handler writes to storage from a goroutine. |

*Course synthesis:* tie understanding to the risk tier, like review. Low-tier changes need no explain-it-back. High-tier changes need it every time. This keeps the cost proportional and stops the practice from becoming a ritual everybody skips.

### Explain it back, done well
The owner writes it, the agent doesn't. You can use an agent afterwards to *check* it against the diff, as long as the check looks for contradictions and omissions, not for prose quality. A check prompt that works:

```text
You are checking whether a PR owner understands their change. Below is the diff and
the owner's explanation, which they wrote without AI help.

List only:
1. Statements in the explanation that the diff contradicts (quote both).
2. Behaviour changes in the diff that the explanation does not mention and that
   affect safety, durability, ordering, or API contract.
Do not comment on writing quality. If there is nothing in either list, reply "OK".
```

This is a judge, so the [module 11](../11-llm-as-judge/README.md) rules apply: binary output, and spot-check its verdicts against a human's.

## Worked example
Same Raft service as [concept 01](01-code-review-at-agent-volume.md). After the double-voting bug was caught, an agent produced a correct fix: batch hard-state writes into a group commit, and reply to vote requests only after the batch's fsync returns.

**Bad version.** The agent-written PR description:

```markdown
## Summary
This PR improves vote latency by introducing a HardStateBatcher that batches
PersistHardState calls. It adds a channel-based queue, a flush goroutine with a
2ms ticker, and comprehensive error handling with retries and fallbacks. All
tests pass. This is a robust, production-ready improvement.
```

Two approvals land within an hour. Six months later, p99 vote latency spikes during a disk stall. The on-call engineer finds a retry-with-backoff loop inside the flush goroutine (nobody asked for it), and can't tell whether a retried flush can reorder a `term` bump relative to a `votedFor` write. The two approvers can't either. Nothing in the repo says why 2 ms was chosen, or whether replies are allowed before fsync on retry. This is cognitive debt with a pager attached.

**Good version.** The router marks the PR high-tier, so policy requires an explain-it-back and an ADR. The owner writes:

```markdown
## Explain it back (written by @priya, no AI)
Votes and term changes now go through one batcher. A vote reply is sent only after
the fsync that contains that vote returns; the batch flushes every 2ms or at 64
entries. If fsync fails we crash the node (not retry): a retry could reorder a term
bump after a later votedFor in the same batch, which is the double-vote bug again.
If this is wrong, the symptom is two leaders in one term, which the Jepsen-lite
suite in CI checks for (`make jepsen-lite`, 200 ops, 0 anomalies on this branch).
```

The explanation check from above returns one item: *"The diff includes a retry loop in `flush()` (batcher.go:88-104). The explanation says fsync failure crashes the node."* The owner removes the retry loop the agent had added. The ADR, drafted by the agent and edited by the owner:

```markdown
# ADR-0017: Group commit for Raft hard state

Status: accepted (2026-10-12). Owners: @consensus-owners

## Context
Vote latency p99 was 9ms, dominated by one fsync per vote. A prior attempt persisted
asynchronously and violated election safety (PR #4412, reverted).

## Decision
Batch hard-state writes. Reply only after the covering fsync returns. Flush at 2ms or
64 entries. On fsync error, crash; never retry within a batch.

## Consequences
p99 vote latency 9ms -> 3ms in the bench (illustrative). Vote replies can be delayed
by up to 2ms under low load. Any future change to reply-before-durable is a safety
change and needs @consensus-owners.

## Rejected
Async persist (unsafe). O_DSYNC per write (no latency win on our disks).
```

The difference isn't the amount of text. It is that a human put the safety argument into words, which exposed a contradiction with the code, and the why is now in the repo for the next person.

## Pitfalls
| Pitfall | How to detect it |
|---|---|
| **Agent-written explain-it-back.** The owner pastes the agent's summary. | It reads like the PR description. Ask the owner one follow-up question in review; if they open the agent to answer it, the practice failed. |
| **ADR theatre.** Every PR gets an ADR, so none get read. | ADRs only for decisions others will copy or that change a safety argument. Count ADRs referenced in later PRs or incident docs. |
| **Measuring understanding by survey alone.** | Pair self-reports with an observable: time-to-first-correct-hypothesis in incident reviews, or a quarterly "explain this path" exercise for each critical component. |
| **Blaming the tool.** Banning agents in critical code instead of raising the bar there. | If a component is agent-free by rule, check whether it is also the one with the slowest lead time and the most-deferred fixes. |
| **Defensive bloat accepted as robustness.** | Track lines added in error-handling branches per PR. Ask "which requirement asked for this retry?" in REVIEW.md. |

## In your day job
- Pick your three most critical components. For each, ask two engineers to explain the main write path from memory, then compare. The gaps are your cognitive-debt map.
- Add an explain-it-back section to the PR template, required only when the router says high tier.
- Start a `docs/adr/` directory if you don't have one, and write the first ADR about a decision an agent touched recently.
- When you review an agent PR, ask at least one "why" question. If the author can't answer without the agent, that is the finding.
