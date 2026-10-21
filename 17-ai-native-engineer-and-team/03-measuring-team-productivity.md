# 03: Measuring team productivity honestly

## The idea
Agents make *output* nearly free: PRs, lines, commits, review comments. Any metric that counts output therefore goes up when you adopt agents, whether or not the team delivers more value. Honest measurement means three things:
1. Measure **outcomes and stability**, not output: how long a change takes to reach users, and how often it breaks something.
2. Measure **per task class**, because gains are concentrated in some kinds of work and absent or negative in others.
3. Treat **self-report as a hypothesis**, not data. People, including you, are bad at estimating their own speedup with AI.

The course stance from the [gap analysis](../research/01-gap-analysis.md): the METR slowdown and the company speedup claims are both true. Gains concentrate in narrow, verifiable task classes (migrations, ports, upgrades). So measure your own team's numbers, by task class, before believing anyone's.

## Why it matters
**The perception gap.** METR's 2025 randomized controlled trial gave 16 experienced open-source developers 246 real issues in repositories they had maintained for years. With AI allowed, tasks took 19% longer (confidence interval roughly +2% to +39%). Before the study the developers forecast a 24% speedup; afterwards they still believed AI had sped them up by about 20% ([METR 2025](https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/)). METR is explicit that this doesn't generalize to most developers or repos, and it now marks the result as out of date. The lesson that does generalize: a felt speedup of 20% is compatible with a measured slowdown.

**Measurement itself is hard now.** METR's February 2026 follow-up found point estimates of a speedup (-18% time for returning developers, CI -38% to +9%; -4% for new recruits, CI -15% to +9%) but called them "very weak evidence" because the study design broke down ([METR 2026 update](https://metr.org/blog/2026-02-24-uplift-update/)):
- Developers refused to participate if it meant working without AI.
- 30 to 50% of developers withheld tasks they didn't want to do without AI, so the highest-uplift tasks were underrepresented.
- Developers ran agents concurrently and worked on other things, which made time tracking unreliable.

Every one of these problems will show up when you try to measure your own team. Selection effects, task-mix shift and concurrency are the confounders you design against.

**Throughput and instability move separately.** DORA's 2025 report frames AI as an amplifier that "magnifies the strengths of high-performing organisations and the dysfunctions of struggling ones". InfoQ's summary reports that AI adoption now correlates positively with delivery throughput while delivery instability continues to rise ([InfoQ on DORA 2025](https://www.infoq.com/news/2025/09/dora-state-of-ai-in-dev-2025)). A team that watches throughput alone will celebrate while its change fail rate climbs.

## How it works

### Pick metrics that agent volume can't inflate
DORA's current five software delivery metrics ([dora.dev](https://dora.dev/guides/dora-metrics/)):

| Group | Metric | Definition |
|---|---|---|
| Throughput | Change lead time | Commit to running in production |
| Throughput | Deployment frequency | Deployments per period |
| Throughput | Failed deployment recovery time | Time to recover from a deployment that needs immediate intervention |
| Instability | Change fail rate | Share of deployments that need immediate intervention (rollback, hotfix) |
| Instability | Deployment rework rate | Share of deployments that are unplanned and caused by a production incident |

Add the review-specific metrics Anthropic's Claude Code team tracks: human approvals per PR (median and p95), human comments, and PR wait time, with revert and incident rates as the guardrail ([Osmani et al. 2026](https://claude.dev/blog/solving-code-review-at-anthropic/)). For machine review specifically, track rounds-to-pass and the author-response split (fixed / wrong / intentional / didn't matter).

### Retire the vanity metrics
| Vanity metric | Why it fails at agent volume | Replace with |
|---|---|---|
| PRs merged per engineer | Agents split work into more, smaller PRs; free to inflate | Lead time per *task* (ticket), by task class |
| Lines of code | Agents add defensive code and tests; more lines can mean worse | Nothing. Don't measure it. |
| "% of code written by AI" | Measures adoption, not value. Anthropic reports ~90% as context, not as a target | Change fail rate and rework on agent-authored vs human-authored changes |
| Tokens or sessions per engineer | Rewards spending | Cost per merged change, by task class |
| Self-reported time saved | METR: forecast +24%, perceived +20%, measured -19% | A controlled comparison (below) |

A Shopify memo in April 2025 reportedly made AI use part of performance reviews ([coverage](https://www.digitalcommerce360.com/2025/04/08/internal-memo-shopify-ceo-declares-ai-non-optional/), secondary). Whatever you think of that as policy, a mandate is not a measurement. If usage is part of someone's review, usage metrics stop telling you anything.

### Segment by task class
Gains are not uniform, so a team-wide average hides everything. Classify each ticket into a small, stable set before the work starts (not after, or people will classify by outcome):
- mechanical: dependency bumps, lint, codemods, migrations with a conformance check
- bug fix with a reproducer
- feature in a well-tested area
- design-heavy or critical-path work (consensus, storage, money movement)
- investigation and incident follow-up

Expect large gains in the first two and small or negative ones in the fourth. Spotify reports 60 to 90% time savings on migrations ([Spotify Honk part 1](https://engineering.atspotify.com/2025/11/spotifys-background-coding-agent-part-1)); METR's slowdown was on general issues in mature repos by experts. Both can hold on one team.

### Run small experiments instead of trusting averages
You won't run an RCT on your team, but you can borrow the design:
- **Stepped rollout.** Turn a practice on (say, background agents for dependency bumps) for one service at a time, two weeks apart. Compare each service to its own before-period and to services not yet switched. It controls for org-wide trends such as a launch freeze.
- **Fixed task sets.** For a personal measurement, METR's later designs move toward fixed tasks rather than developer-chosen ones. Pick 20 tickets of one class, randomize which ones you do with agents, and record wall-clock time to merged, plus whether the change was later reverted or reworked.
- **Error bars or it didn't happen.** Lead times are heavy-tailed. Report medians with bootstrap intervals, and don't act on differences inside the noise. [Module 12](../12-hill-climbing/README.md) covers the statistics.

## Worked example
A platform team of eight adopted background agents in Q3. The engineering manager asks the senior engineer for "the AI impact slide" for the quarterly review.

**Bad version.** The slide that gets made by default:

```text
Q3 AI impact (illustrative)
- PRs merged: 412 -> 988 (+140%)
- 78% of merged code AI-authored
- Engineers report saving 6.5 hours/week on average (survey, n=8)
- 1.9M tokens/engineer/week: top adopter award to @sam
```

Every number on it is either output or self-report. The PR count rose partly because agents open one PR per dependency where humans batched five. "78% AI-authored" says nothing about value. The survey is the METR perception gap waiting to happen. The token leaderboard rewards the most expensive behaviour. Nothing on it would show if things got worse.

**Good version.** The senior engineer pulls deploy, ticket and incident data and segments by task class, using the same quarter a year earlier as a baseline (numbers illustrative):

```text
Delivery, Q3 vs Q3 last year            median [95% bootstrap CI]
Task class         n(tickets)  Lead time (days)                    Change fail rate
mechanical         61 -> 140   3.1 -> 0.8  [0.6, 1.1]              2% -> 3%
bug w/ reproducer  44 -> 52    2.4 -> 1.7  [1.2, 2.3]              6% -> 5%
feature            30 -> 33    9.0 -> 8.1  [6.2, 10.4]  (no signal) 8% -> 9%
critical-path      12 -> 11    14.0 -> 16.5 [11.0, 22.0] (no signal) 8% -> 18%  <-- 
Review: human approvals/PR p50 1 -> 1, p95 2 -> 2; PR wait p50 5h -> 2h
Reverts: 1.9% -> 2.4% of merged changes
Cost: $4.10 per merged mechanical change; $61 per critical-path change
```

What the honest version says:
- Mechanical work got about 4x faster, with tight intervals and stable stability. This is the real win and it is in the class you would predict.
- Bug fixes improved modestly.
- Features show no measurable change. Don't claim one.
- Critical-path changes show no throughput gain, and change fail rate rose from 1 in 12 to 2 in 11. That is two incidents, so it is not statistically meaningful by itself, but it matches the cognitive-debt warning signs in [concept 02](02-cognitive-debt-and-shared-understanding.md). The action is to raise the review tier and require explain-it-back for those paths, not to celebrate.

The recommendation slide becomes "expand agents for mechanical and reproducible-bug work; tighten review on critical-path code; re-measure next quarter." That is a decision someone can act on.

## Pitfalls
| Pitfall | How to detect it |
|---|---|
| **Goodhart on lead time.** Tickets get split so each looks fast. | Track tickets per epic and lead time per epic alongside per-ticket numbers. |
| **Task-mix shift.** The team starts picking agent-friendly work, so averages improve while hard work stalls. | Watch the share of each task class over time, and the age of the oldest critical-path ticket. |
| **Survivorship in agent metrics.** Abandoned agent runs never become PRs and vanish from the data. | Log every run with an outcome (merged, abandoned, no PR, failed CI) as Spotify's failure-mode taxonomy does. Report the abandonment rate and its cost. |
| **Attribution games.** Deciding whether a change is "agent-authored" after an incident. | Record authorship at PR creation via the owner trailer, never retroactively. |
| **Comparing with no baseline.** | No number goes on a slide without a before-period or a comparison group. |

## In your day job
- Replace any PR-count or "% AI" chart on your team's dashboard with lead time and change fail rate, split by task class.
- Start logging every agent run with its outcome and cost, including the ones that never became a PR.
- Before your next "AI is making us faster" claim, find the comparison group. If there isn't one, say "we don't know yet".
- Run the personal version of the experiment on yourself (it is in [exercises.md](exercises.md)). It is the cheapest way to calibrate your own sense of speedup.
