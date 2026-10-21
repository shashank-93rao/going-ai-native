# 01: Code review at agent volume

## The idea
When agents write most of the code, human review stops being the default for every change and becomes a scarce resource to spend where it counts. You allocate it by **risk tier**: the type of change decides how many humans must approve, how many machine verifiers must agree, and how many review rounds are allowed. Most of the line-by-line reading moves to machines. Those machines are themselves unreliable, so you use several of them, give each a fresh context, and post only findings a majority agrees on.

Anthropic's Claude Code team states the goal precisely: not "a human read every line" but "the minimum amount of human review time that doesn't raise reverts or incidents" ([Osmani, Lunt and Wang 2026](https://claude.dev/blog/solving-code-review-at-anthropic/)). That is an optimization with a guardrail, the framing you use for SLOs: human review time is the cost, and revert and incident rates are the error budget.

The course stance, from the [gap analysis](../research/01-gap-analysis.md), is a **risk-tiered review policy**. It sits between "every change gets a thorough human review" (Mitchell Hashimoto, Willison, Stripe) and "human review doesn't scale, so automate verification" (Huntley, OpenAI's harness team). Both camps are right about different tiers.

## Why it matters
The numbers from teams that have done it:

| Team | What they report |
|---|---|
| Anthropic, Claude Code | About 90% of the code is written by Claude. From June to September 2026, merged PRs more than doubled while the share of PRs reverted fell by more than 40%. PRs with substantive review comments went from 16% to 54%. Passing after one review-and-fix round went from 65% to 78%; mean reviews to pass from 2.08 to 1.32. ([source](https://claude.dev/blog/solving-code-review-at-anthropic/)) |
| Stripe, Minions | More than 1,000 PRs merged per week that are fully minion-produced. The engineer who launched the minion checks the result, opens the PR and requests review from another engineer. At most two CI runs per minion. ([source](https://stripe.dev/blog/minions-stripes-one-shot-end-to-end-coding-agents)) |
| Spotify, Honk | 1,500+ merged agent PRs for fleet-wide migrations. All verifiers run in a Stop hook before a PR can open, and an LLM judge compares the diff to the prompt. The judge vetoes about a quarter of sessions; about half of those recover. Spotify says it has not yet built evals for the judge. ([part 3](https://engineering.atspotify.com/2025/12/feedback-loops-background-coding-agents-part-3)) |
| Cognition, Devin Review | A clean-context review agent catches on average 2 bugs per Devin-written PR, about 58% of them severe. It works best when it shares no context with the coding agent. ([source](https://cognition.com/blog/multi-agents-working)) |

Spotify ranks **a PR that passes CI but is functionally incorrect** as "the most serious error, as it erodes trust in our automation", and notes such PRs could break production ([Spotify, Honk part 3](https://engineering.atspotify.com/2025/12/feedback-loops-background-coding-agents-part-3)). Review exists for that failure mode.

The other side fails too. Armin Ronacher notes that review is now the constraint, and that machine review of machine output invites humans to rubber-stamp (["The Final Bottleneck"](https://lucumr.pocoo.org/2026/2/13/the-final-bottleneck/)). And one CLI PR at Anthropic went through more than fifty agent-author/agent-reviewer rounds overnight.

## How it works

### 1. Layer the review, and move most of it before the PR
Anthropic describes seven layers: (1) before the PR, the authoring agent runs tests, build and linters and shows the output, and a subagent reviews the diff in a fresh context (the Stop-hook gate from [module 14](../14-steering-and-guardrails/README.md)); (2) machine review on every PR, with parallel bug hunters and verifiers that vote, style findings dropped, and labels Important / Nit / Pre-existing; (3) a separate security pass whose open findings block merge; (4) required CI, with a PR template asking for "Testing", "Risk" and "How to revert"; (5) risk-based human approval; (6) merge queue and flagged, staged rollout; (7) detection, rollback, and incident reviews that ask which layer should have caught the issue.

Human review is layer 5 of 7. If layers 1 to 4 are weak, no tiering scheme saves you.

### 2. Tier the change
Anthropic's tiers, as published:

| Tier | Examples | Human approvals |
|---|---|---|
| Low | Docs, copy, internal-only features, additive changes behind a flag | 0, once automated and security checks are green |
| Medium | Ordinary product changes; sensitive areas such as caching, the auto-updater, system prompts | 1 |
| High | Highest-risk code, plus a small set of paths that always need two people | 2 |

Rules around the tiers matter as much as the table:
- A classifier picks the tier; a second classifier asks whether this change needs a person regardless of tier. Owner-marked sensitive paths and any CI workflow file always need a person.
- Only trusted authors (mostly the owning team) get the lighter paths.
- **An agent's approval never counts as a person's.** The person directing an agent counts as a required reviewer.
- An approval covers one specific commit.

*Course synthesis:* put a **deterministic router** under the model classifier. Path globs and content patterns are cheap, explainable and testable, and they fail safe: a path no rule knows gets medium, never low. A model may raise the tier above the router's floor; it may never lower it. That is the same split you use between a static admission policy and an ML anomaly score. [`code/review_router.py`](code/review_router.py) implements the floor.

### 3. Vote, with independent voters
A single model reviewer has two noise sources: false positives (it invents a bug) and false negatives (it misses one). Asking several reviewers and posting only majority findings cuts false positives sharply, as long as the reviewers' errors are not correlated. You buy independence the way you buy it for replicas:
- **Fresh context per reviewer.** No shared transcript, no author reasoning, no other reviewers' findings. Cognition's result depends on this: the reviewer reasons backward from the diff and avoids the context rot of a long coding session.
- **Varied inputs where you can.** Different models, different orderings of the diff, different focus prompts (concurrency, durability, API contract).
- **Ask for everything, filter later.** Anthropic's prompting guidance notes that review prompts saying "only report high-severity issues" are followed literally, so the model self-censors. Ask each reviewer for every finding with a category and severity, and filter in code ([Anthropic prompting best practices](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices)).

Then filter, in this order: findings without `file:line` evidence, findings in skip paths, style-only clusters, and clusters without a strict majority. Anthropic does not publish its verifier count or agreement threshold; the course defaults (3 verifiers for low and medium, 5 for high, strict majority) are our choice. [`code/verifier_vote.py`](code/verifier_vote.py) implements it.

One more rule from distributed systems: **a malformed reviewer response is an abstention, not a clean bill of health.** If most reviewers return unparseable output, you have lost quorum; report "machine review degraded" and route to a human.

### 4. Write REVIEW.md
Code owners write a REVIEW.md that tells the reviewer what matters in their area. Anthropic says the good ones are short and:
- say what failure looks like in that repo ("it lies" for docs, "it misroutes" for config),
- cap nits,
- list paths to skip,
- require a file and line as evidence, not a guess from a function name,
- start the summary with a count and say plainly when there is nothing to fix.

When the reviewer keeps repeating a finding, fix it at the source: a lint rule, a skill, a CLAUDE.md line. Then delete it from REVIEW.md. A full example for a Raft-based service is in [code/templates/REVIEW.md](code/templates/REVIEW.md) and is walked through in [examples.md](examples.md#scenario-1-writing-reviewmd-for-a-raft-replicated-ledger).

### 5. Cap the rounds and measure the reviewer
- **Round cap.** After three rounds, Anthropic's reviewer asks the author to step back and reconsider the approach. After the first few passes it re-reviews only the diff, flags the class of bug so all instances get fixed, and never repeats a posted finding. Stripe caps minions at two CI runs. These are retry budgets.
- **An eval set from your incidents.** Anthropic collects past PRs that caused incidents or reverts, has engineers who know the code confirm each bug and its location, and runs the reviewer against the set daily. Every change to the reviewer's prompt, tools or model is scored on the full set and kept only if the score rises. They also run the reviewer on known-clean PRs to measure how often it suggests a harmful change. This is [module 11](../11-llm-as-judge/README.md) applied to your reviewer.

## Worked example
A team runs a Go ledger service on Raft. An agent opens this PR (from [`code/data/diffs/raft_election.diff`](code/data/diffs/raft_election.diff)):

```diff
 	if n.votedFor == "" || n.votedFor == req.CandidateId {
-		n.votedFor = req.CandidateId
-		if err := n.storage.PersistHardState(n.currentTerm, n.votedFor); err != nil {
-			return &pb.VoteResponse{Term: n.currentTerm, Granted: false}
-		}
+		n.votedFor = req.CandidateId
+		go n.storage.PersistHardState(n.currentTerm, n.votedFor) // persist off the hot path
 		return &pb.VoteResponse{Term: n.currentTerm, Granted: true}
```

The description says "cut p99 vote latency". It is a Raft safety bug: the vote is granted before `votedFor` is durable, so a crash and restart in the same term lets the node vote again, and two leaders can be elected in one term.

**Bad version.** Uniform policy: every PR needs one approval. One reviewer agent with the prompt:

```text
Review this PR. Only report high-severity issues. Be thorough.
```

What happens (illustrative output):

```text
1. Consider renaming PersistHardState to persistHardState for consistency. (high)
2. The comment "persist off the hot path" could explain the latency win. (high)
3. becomeFollower may not reset the election timer. (high)
4. Error from PersistHardState is ignored.
```

Two style findings, one guess about a function it did not open, and the real problem reported as a generic dropped error with no mention of double voting. The approver, on their fifteenth agent PR of the day, sees a latency win and some nits, and approves. CI passes: no unit test crashes a node between replying and persisting.

**Good version.** First, the router:

```bash
$ python review_router.py data/diffs/raft_election.diff
```
```json
{
  "tier": "high",
  "human_approvals": 2,
  "verifiers": 5,
  "round_cap": 2,
  "owners": ["@consensus-owners"],
  "reasons": [
    "internal/raft/election.go: consensus (high) - consensus code: bugs show up as split brain or lost writes, rarely in CI"
  ],
  ...
}
```

Two humans, one from `@consensus-owners`, and five verifiers. Each verifier gets REVIEW.md, which says: *"granting a vote before `votedFor` is persisted"* and *"any `go` statement in front of a storage write on the request path"* are Important. Third, votes are counted. With the offline demo's three canned reviewers (two of which also produced a style nit and a speculative finding), `verifier_vote.py` prints this (actual output of the offline demo):

```text
1 important, 0 other finding(s).
- [Important] internal/raft/election.go:42 (3/3 agree): Vote is granted before votedFor is durable; a crash after replying lets this node vote twice in one term.
(dropped: 1 minority, 1 style, 0 without file:line)
```

The style nit is gone even though two reviewers raised it. The speculative timer finding had one vote and is dropped. The owner sees one finding, stated as a failure with a mechanism.

The tier put the right humans on it, REVIEW.md told the machines what failure looks like *in this repo*, and voting cut the noise. What it does not guarantee: if every reviewer shared a blind spot, voting would agree on nothing. That is why this PR still gets two humans, and why the incident eval exists.

## Pitfalls
| Pitfall | How to detect it |
|---|---|
| **Tiers that only go down.** Teams add "low" rules eagerly and never audit them. | Count changes per tier per month. If low-tier share keeps rising while revert rate does too, audit the low rules. Property-test the router: adding a file must never lower the tier (see `test_review_router.py`). |
| **Agent approves agent.** A bot account in the approver group. | Branch protection counts only human accounts. Test it by having a bot approve a high-tier PR in a sandbox repo. |
| **Correlated voters.** Five copies of the same model and prompt agree on the same miss. | Measure recall on your incident eval as you add voters. If recall stays flat while precision rises, you are buying noise reduction only; vary model or focus prompt. |
| **Reviewer always finds something.** Anthropic's own docs warn that reviewers asked to find gaps will always find some, and chasing every one leads to over-engineering. | Run the reviewer on known-clean PRs. Track the "fixed / wrong / intentional / didn't matter" split of author responses, as Anthropic does. |
| **Infinite rounds.** | Alert on any PR past the round cap; track the distribution of rounds-to-pass, not just the mean. |
| **The agent edits its own grader.** CI workflow or REVIEW.md changes slip through at low tier. | Mark those paths always-human. The sample `ci_workflow.diff` removes `-race` and is routed to a human. |

## In your day job
- Write down your team's current implicit tiers ("we look harder at migrations"), then encode them in a router policy and run it over the last 200 merged PRs. Disagreements between the router and what reviewers actually did are your first policy discussion.
- Collect the last ten incident-causing or reverted PRs into a reviewer eval set this week. It costs an afternoon and it is the only way to know whether your machine reviewer works.
- Make sure no bot identity can satisfy a required approval in your branch protection settings.
