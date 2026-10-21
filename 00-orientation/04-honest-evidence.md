# 04: Honest evidence: METR's slowdown vs company speedups

## The idea

Two bodies of evidence seem to contradict each other.

**The controlled study.** METR ran a randomized controlled trial in early 2025 with 16 experienced open-source developers working on 246 real issues in repos they had maintained for years. The repos averaged 22k+ stars and 1M+ lines. Each issue was randomly assigned to "AI allowed" or "AI disallowed". The main tools were Cursor Pro with Claude 3.5/3.7 Sonnet, and tasks averaged about two hours. Results:

| | Change in completion time with AI |
|---|---|
| Economics experts' forecast | 39% shorter |
| ML experts' forecast | 38% shorter |
| Developers' own forecast, before | 24% shorter |
| Developers' own estimate, after | 20% shorter |
| **Measured** | **19% longer** (95% CI +2% to +39%) |

([METR, July 2025](https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/); [paper](https://arxiv.org/abs/2507.09089))

**The company reports.** Stripe: "Over a thousand pull requests merged each week at Stripe are completely minion-produced", human-reviewed but with no human-written code ([Stripe](https://stripe.dev/blog/minions-stripes-one-shot-end-to-end-coding-agents)). Spotify: more than 1,500 agent PRs merged into production, and for migrations "a total time saving of 60–90% compared to writing the code by hand" ([Spotify, Honk part 1](https://engineering.atspotify.com/2025/11/spotifys-background-coding-agent-part-1)). Anthropic: merged PRs more than doubled from June to September 2026 while the revert share fell by more than 40% ([Anthropic](https://claude.dev/blog/solving-code-review-at-anthropic/)).

> **Course stance:** both are true. Gains concentrate in narrow, verifiable task classes. The perception gap is real and large. **Measure your own productivity** rather than adopting anyone's number, including METR's.

## Why it matters

The finding to remember from METR is not the 19%. It is the **39-point gap between what developers felt (20% faster) and what was measured (19% slower)**. These were experts on their own code, and they got the sign wrong. If your evidence that AI helps you is that it feels faster, METR is direct evidence that this feeling is unreliable, even for people with deep expertise.

The opposite error is just as costly. METR itself marks the 2025 results as out of date, and dismissing agents because of a study of early-2025 tools is reading the evidence lazily in the other direction.

## How it works: why both can be true

### 1. The 2026 update: the effect moved, and measuring it got harder

METR's late-2025 follow-up ([METR, Feb 2026](https://metr.org/blog/2026-02-24-uplift-update/)) found point estimates that had flipped to speedups:

| Group | Time change with AI | 95% CI |
|---|---|---|
| Original developers | −18% | −38% to +9% |
| Newly recruited developers | −4% | −15% to +9% |

METR's own reading is that "we believe it is likely that developers are more sped up from AI tools now", but that "our data is only very weak evidence for the size of this increase". Both intervals cross zero.

The reason it is weak is the most important lesson in this file for your own measurement: **selection effects broke the design.**
- 30–50% of developers said they withheld some tasks because they didn't want to do them without AI.
- METR also reports developers being unwilling to work without AI at all.
- Pay dropped from $150/hr to $50/hr.
- Concurrent agents made time tracking hard.

If the tasks people expect AI to help most with are kept out of the no-AI arm, the comparison is biased, and you can't say in which direction without a model of who withheld what. [05-measure-yourself](05-measure-yourself.md) designs against exactly this.

### 2. Different task classes

| | METR | Stripe / Spotify reports |
|---|---|---|
| Tasks | Heterogeneous real issues in mature repos | Mostly narrow and repeated: migrations, upgrades, fleet-wide changes |
| Who | Experts on code they had maintained for years | Platform teams building agents for a task class |
| Oracle | Whatever the repo had | Purpose-built verifiers (Spotify's Maven verifier, Stripe's lint plus at most two CI rounds) |
| Unit measured | Wall time per issue, randomized | PR counts, or time saved vs a hand-coding estimate |

The companies built a strong oracle for a task class and then pointed agents at it. That is the dial in [03](03-autonomy-dial.md) turned right for loopable work. METR measured experts on varied work where the oracle was "the maintainer's judgment". That is where the dial says chat or pair, and where Karpathy found agents "not net useful" on his own novel code.

### 3. Different outcome variables

"PRs merged per week" is a volume metric. It can rise while productivity stays flat or falls, through smaller PRs, more follow-up fixes or more review load. Anthropic's report is stronger evidence than a raw count because it pairs volume with a guardrail (revert share fell) and a quality signal (one-round pass rate rose from 65% to 78%). Spotify's 60–90% is measured against "writing the code by hand", and the post doesn't say how it was measured. Treat it as reported by Spotify, not as a controlled estimate.

### 4. Publication and survivorship

Companies publish the programs that worked. Nobody writes the "we tried agent migrations and stopped" post at the same rate. This is ordinary survivorship, not bad faith, and it means the company literature is an existence proof ("this can work, here is how") rather than an effect size.

### 5. Time

The METR 2025 tools predate the step change Karpathy dates to December 2025 ([Sequoia 2026](https://karpathy.bearblog.dev/sequoia-ascent-2026/)). Any number older than a model generation is a historical data point.

> **Synthesis:** read every productivity claim through five questions. *Which tasks? Which oracle? Which outcome variable? Who chose what got measured? Which model generation?* Most apparent contradictions dissolve when you answer them.

## Worked example: auditing a claim before it reaches your planning doc

A peer team's quarterly update says (illustrative):

```text
"Since rolling out coding agents, the payments-platform team ships 2.3x more PRs per engineer.
 We recommend all teams adopt the agent workflow."
```

**Bad reading:** "2.3x, let's do it", and next quarter's headcount plan assumes 2x throughput.

**Good reading:** run the five questions and write down what's missing.

```markdown
## Claim audit: "2.3x PRs per engineer" (payments-platform, Q3)

| Question | Answer from the report | Gap |
|---|---|---|
| Which tasks? | Not stated | Ask for PR breakdown by type. If dominated by dependency bumps / codemods, it's a task-class result |
| Which oracle? | "CI" | What fraction of agent PRs touched code with contract tests vs none? |
| Outcome variable | PR count | Need: median PR size, revert rate, follow-up fix PRs within 14d, review time per PR |
| Who chose? | Engineers picked which tickets to give the agent | Selection: the agent got the tickets people expected it to do well on. No comparison arm |
| Model generation | Mixed over the quarter | Split before/after the model change if possible |

**Decision:** Not adoptable as "2x". Adoptable as: "agents look effective on <task class>, pending revert/rework data."
Ask: run a randomized personal A/B on the next 30 tickets (see 00-orientation/05).
```

The audit doesn't call the claim false. It says what the claim is evidence *for*, which is usually narrower than its headline.

## Pitfalls

| Pitfall | How to detect it |
|---|---|
| **Citing METR's 19% as "AI makes you slower"** | METR marks it out of date and gives a 2026 update. If someone cites only the 2025 figure, ask about the update. |
| **Citing company numbers as effect sizes** | Look for a comparison arm and a guardrail metric. Without both, it's an existence proof. |
| **Trusting your own sense of speed** | Write down your forecast before a task and compare it with the clock afterwards. The gap is the METR effect, measured on you. |
| **Volume metrics without quality metrics** | Every dashboard that shows PR counts should show revert or rework rate next to them. |
| **Ignoring selection in your own data** | If you choose which tasks get AI, your before/after numbers measure your choosing as much as the tool. |

## In your day job

- When a productivity number appears in a planning doc, attach the five-question audit. It takes ten minutes and prevents a bad headcount plan.
- Start recording, for each task, your estimate before and the actual time after. This is the cheapest measurement you can make, and it calibrates your sense of speed.
- Use the company posts for what they're good at: the *mechanisms* (verifiers, round caps, risk tiers), not the multipliers.
- For a team-level version of this measurement, see [17-ai-native-engineer-and-team](../17-ai-native-engineer-and-team/README.md).
