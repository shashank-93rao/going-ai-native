# 00: Orientation: going AI-native
> After this module you can decide, per task, how much autonomy to give an AI by asking what can be checked, explain why the evidence about AI productivity points both ways, and measure your own speedup with a randomized log instead of a feeling.

## Why this matters

Most engineers who have used AI for a year have one working mode: a detailed prompt, a read of the output, a fix by hand. That mode was right for 2025's tools. It is now the bottleneck on work a test suite could judge, and it is still wrong for work where nothing can judge but you. The skill this course teaches is choosing, per task, *how much to let go*. The variable that decides it is **verifiability**: can the output be checked automatically, cheaply, repeatedly, and faithfully?

The stakes run both ways. Turn the dial too far right and you get agents hill-climbing a weak oracle: PRs that pass CI but are functionally wrong, which Spotify calls "the most serious error, as it erodes trust in our automation" ([Spotify, part 3](https://engineering.atspotify.com/2025/12/feedback-loops-background-coding-agents-part-3)). Turn it too far left and you are reading every diff of low-risk work that teams like Anthropic now merge with no human approval at all, behind risk tiers and voting verifiers ([Anthropic](https://claude.dev/blog/solving-code-review-at-anthropic/)).

And you can't trust your sense of which way you're erring. In METR's 2025 trial, experienced developers measured 19% *slower* with AI while believing they were 20% faster ([METR](https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/)). This module ends with a kit to measure that on yourself.

## The distributed-systems anchor

**Choosing consistency levels.** You don't run every query at `ALL` or at `ONE`. You choose per operation, based on what a stale or lost write costs and what the system can guarantee. The autonomy dial is the same kind of decision: chat, pair, supervised agent, loop or scheduled, chosen per task based on what a wrong output costs and what your checks can guarantee.

**Where the analogy breaks.** A consistency level is a *guarantee* the database enforces. An oracle is a *measurement* that can be wrong, and the agent is an optimizer that will find exactly where it's wrong: tests it can edit, retries that hide a race. So the dial has two extra requirements a consistency level doesn't. The check must be **faithful** (proven to fail on wrong output), and unfamiliar code **steps the dial down**, because the model's competence there is unknown.

## Learning goals
- [ ] Explain Software 1.0/2.0/3.0 and Karpathy's verifiability criteria, and score any task on resettable / efficient / rewardable / faithful
- [ ] Distinguish vibe coding from agentic engineering by what checks the output, not by which tool is used
- [ ] Trace the evidence from "keep AI on a tight leash" (2025) to 25-hour runs and zero-human-approval tiers (2026), and name the harness that made each step safe
- [ ] Place a task on the autonomy dial from its oracle strength, reversibility, containment and familiarity, and list the guards that mode needs
- [ ] Reconcile METR's slowdown with Stripe, Spotify and Anthropic's reported gains using the five-question audit
- [ ] Run a randomized personal A/B with an append-only log, and read its estimate, interval and power line correctly
- [ ] Pick a route through the 19 modules for a concrete goal

## Reading order
1. [01-verifiability-thesis](01-verifiability-thesis.md): Software 3.0, specify vs verify, vibe coding vs agentic engineering, the verifiability scorecard
2. [02-the-leash-moved](02-the-leash-moved.md): the evidence trail from Karpathy 2025 to OpenAI's harness and Anthropic's review practice
3. [03-autonomy-dial](03-autonomy-dial.md): task × oracle strength → chat / pair / supervised agent / loop / scheduled
4. [04-honest-evidence](04-honest-evidence.md): METR 2025 and 2026 vs company reports, and why both are true
5. [05-measure-yourself](05-measure-yourself.md): the personal randomized A/B, its log format and statistics
6. [06-course-map](06-course-map.md): all 19 modules, the tracks, and routing for a goal
- [examples.md](examples.md), [exercises.md](exercises.md), [references.md](references.md), [code/](code/README.md)

## Prerequisites
None. This is the entry point. You should have used an AI coding assistant on real work. Every later module assumes the vocabulary here: oracle, faithful, the dial, the leash.

## Key takeaways
- **Autonomy should scale with verifiability.** Ask what can be checked before you ask which tool or prompt to use.
- **A check is only as good as its ability to fail.** Watch your oracle go red on a wrong implementation before you trust its green.
- **Vibe coding and agentic engineering use the same tools.** The difference is whether anything but "it seemed to work" checks the output.
- **The leash moved from the diff to the harness.** Every review step you stop doing by hand must be replaced by a named automated check, and paired with a guardrail metric such as revert rate.
- **Dial per task, conservatively.** A strong oracle moves right. Irreversibility, no sandbox, and unfamiliar code move left.
- **Both the slowdown and the speedup reports are true.** Gains concentrate in narrow, verifiable task classes, and self-perception is unreliable even for experts.
- **Measure yourself with randomization**, register before assignment, keep abandoned tasks, and report the interval and the n you'd need.
