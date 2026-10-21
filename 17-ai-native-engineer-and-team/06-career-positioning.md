# 06: Career positioning for a senior engineer

## The idea
When implementation gets cheap, the scarce inputs to software are the ones agents can't supply on their own: knowing what to build, stating precisely what "correct" means, building the checks that prove it, and owning the result when it breaks. A senior engineer's leverage was always in those inputs. What changes is the ratio. You used to spend most of your time implementing and some on design and review. Now you can spend most of it designing the environment that many agents (and the engineers directing them) work inside: specs, oracles, review policy, harnesses, and the team's shared understanding.

Karpathy puts the responsibility plainly: "You are still responsible for your software, just as before," and "you are in charge of taste, engineering, design, and whether the system makes sense" ([Sequoia Ascent 2026](https://karpathy.bearblog.dev/sequoia-ascent-2026/)). Simon Willison's version is that agentic engineering demands *more* skill, because AI amplifies existing expertise ([Willison, "Vibe engineering"](https://simonwillison.net/2025/Oct/7/vibe-engineering/)). Anthropic's source-control team, running at more than 30,000 changes a day, found that "very often, we found that the role of the engineers was to tell Claude 'no'" ([Anthropic, "Redesigning source control"](https://www.anthropic.com/engineering/redesigning-source-control)).

## Why it matters
Two careers diverge from here. In one, an engineer uses agents to produce more of what they produced before, and is measured on volume, which agents make cheap. In the other, the engineer becomes the person whose specs, verifiers and review policies make everyone else's agents safe to run. The second is the staff role, and it compounds: a REVIEW.md, a tier policy or a conformance suite gets used thousands of times.

The risk on the first path is concrete. Anthropic's own take-home was saturated by models within a year ([concept 05](05-hiring-and-evaluating-ai-native-engineers.md)). Skills that look like well-documented work are the ones models absorb first.

## How it works

### What gets more valuable, and what less
*Course synthesis*, drawn from the sources above and the rest of this course:

| More valuable | Why | Where in this course |
|---|---|---|
| **Judgment and taste**: what to build, what to reject | Agents will build whatever you ask, including the wrong thing | [00](../00-orientation/README.md), [04](../04-agentic-coding-workflows/README.md) |
| **Specification**: invariants, non-goals, acceptance criteria | The spec is now the main input; ambiguity becomes code at scale | [02](../02-prompting-as-specification/README.md), [04](../04-agentic-coding-workflows/README.md) |
| **Verification design**: oracles that can fail, evals, property tests, fault injection | "Autonomy scales with verifiability." Whoever builds the check decides how much autonomy is safe | [07](../07-loops/README.md), [10](../10-evals-fundamentals/README.md), [13](../13-testing-agentic-systems/README.md) |
| **Systems thinking**: failure modes, coupling, blast radius | Agents optimize locally; system-level properties (safety, liveness, cost) are where they fail | [15](../15-observability-and-production/README.md), [16](../16-security-and-containment/README.md) |
| **Reading code and diffs critically** | Reading is the bottleneck now, not writing | [concept 01](01-code-review-at-agent-volume.md) |
| **Harness and policy engineering** | One good harness multiplies a whole team | [08](../08-harness-engineering/README.md), this module |
| **Debugging and incident ownership** | Someone has to know what correct looks like at 3 a.m. | [concept 02](02-cognitive-debt-and-shared-understanding.md) |
| **Teaching and writing** | Policies, ADRs and REVIEW.md files are how understanding scales | this module |

| Less valuable | Why | What to do instead |
|---|---|---|
| Typing speed, syntax and API recall | Agents have it, and can read current docs | Spend the time on specs and checks |
| Boilerplate, glue code, routine migrations | Spotify reports 60 to 90% time savings on migrations | Own the migration's conformance suite, not its diff |
| Being the only person who knows framework X | Agents read framework source quickly | Be the person who knows *why* the system uses it |
| Puzzle-solving on well-known problems | Saturated by models (Anthropic's take-home) | Novel problems and system-level design |
| Writing code alone for days | Throughput no longer comes from one person typing | Short delegate-verify cycles, and pairing with agents on hard parts |

One thing does *not* become less valuable: being able to write the code yourself. You need it to judge the agent's output, to work when the agent is stuck (Mitchell Hashimoto researches stubborn bugs by hand and deletes fixes he doesn't understand), and to keep cognitive debt in check. Treat it like a pilot's manual flying hours: you don't use it most of the time, and you can't afford to lose it.

### Position yourself
- **Own a verifier other people depend on.** A linearizability checker for your storage layer, a replay harness for your Kafka consumers, the reviewer eval set. Infrastructure for checking is staff work that agents make more valuable, not less.
- **Write the team's policies.** The REVIEW.md, tier policy and AGENT_POLICY.md in this module are senior-engineer artifacts. Whoever writes them shapes how the team works.
- **Publish measured results.** One honest write-up of "what actually got faster on our team, with error bars" is worth more than ten confident talks. It also protects you from the METR perception gap.
- **Stay hands-on in critical paths.** Be the person who can still explain the consensus code.

## Worked example: a 90-day personal adoption plan
**Bad version.**

```markdown
Q4 goals
- Use Claude Code more
- Try Cursor and Codex
- Read up on agents
- Be 2x more productive
```

None of these can be checked. "2x more productive" will be confirmed by feeling, which METR shows is unreliable. There is no baseline, no task class, no artifact.

**Good version.** Each phase has an output and a check.

```markdown
# 90-day plan: agentic engineering (senior engineer, storage team)

## Days 1-14: baseline and calibration
- Log every task: class (mechanical / bug-with-repro / feature / critical-path / investigation),
  start, merged, reverted-or-reworked within 30 days. Spreadsheet, 2 min/task.
- Reproduce 3 of my own past commits with an agent from the original ticket text (Hashimoto's
  exercise). Note where it went wrong and why.
- Check: >= 15 logged tasks; 3 reproduction write-ups, 1 paragraph each.

## Days 15-45: adopt per task class, with verification first
- Mechanical and bug-with-repro work: agent-first. Before each delegation write the check
  (failing test, script) and see it fail.
- Critical-path work: agent for research and tests only; I write the core change.
- Randomize 10 bug-with-repro tickets: coin flip decides agent-first or manual.
- Check: per-class median time to merge with bootstrap CI; revert/rework count per arm.
  Written comparison of my forecast speedup vs measured.

## Days 46-75: build team leverage
- Write REVIEW.md for our repo and a tier policy; run the router over the last 200 merged PRs
  and review disagreements with the team.
- Build the reviewer eval set: 10 incident-causing or reverted PRs, confirmed by owners.
- Run one background schedule in report-only mode (flaky-test triage) with an owner and a budget.
- Check: REVIEW.md merged; eval set in repo with baseline recall; schedule has 10+ reports,
  each marked useful / wrong / noise.

## Days 76-90: measure and publish
- Write up: what got faster, what didn't, what broke, cost per merged change by class.
- Propose next quarter's policy changes (tiers, schedules to promote, practices to drop).
- Check: write-up reviewed by my manager and one peer outside the team; at least one
  decision made from it.

## Guardrails throughout
- I can explain every high-tier change I own without the agent.
- One human-only bug fix per month in the WAL or Raft code.
```

Why this version works: it starts with a measurement, so the end-of-quarter claim has a baseline. It adopts per task class, matching where gains are expected. It builds artifacts (REVIEW.md, eval set, schedule) that outlive the quarter and that only someone with staff-level context can write. And it ends with a decision, not a feeling.

## Pitfalls
| Pitfall | How to detect it |
|---|---|
| **Becoming the team's prompt person.** You write prompts for everyone instead of building checks. | Count how many of your artifacts are verifiers or policies versus prompts. Prompts expire with models; checks last longer. |
| **Skill atrophy in the critical path.** | The monthly human-only fix. If it takes much longer each time, you are losing it. |
| **Over-claiming.** Presenting your own speedup without a baseline. | Your write-up has a comparison group and intervals, or it says "unmeasured". |
| **Ignoring cost.** | Report cost per merged change by class. A senior engineer who can say "this practice costs $60 per critical-path change and saves 0 days" is making the decision others can't. |
| **Waiting for the tools to settle.** | They won't. The plan above is tool-agnostic; the measurements and artifacts carry across tools. |

## In your day job
- Start the task log today. It costs two minutes per task and is the base for every claim you will make this quarter.
- Pick one verifier your team lacks and build it with agents. That is the highest-leverage use of this module.
- Volunteer to write the team's REVIEW.md and tier policy.
- Book a recurring hour a month for a human-only change in your most critical component.
