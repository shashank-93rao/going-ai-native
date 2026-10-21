# 05: Hiring and evaluating AI-native engineers

## The idea
If the job is now "specify, delegate, verify and own", the interview should test specifying, delegating, verifying and owning. Karpathy's version: hiring "should look more like: give someone a big project and see them implement it", and "if you are giving out small puzzles to solve, that is still the old paradigm." His written summary suggests candidates build a substantial agent-assisted project, deploy it, harden it, and then face adversarial agents trying to break it. He also notes that "most hiring processes have not been refactored for agentic-engineer capability" ([Karpathy, Sequoia Ascent 2026](https://karpathy.bearblog.dev/sequoia-ascent-2026/)).

The same idea applies to evaluating engineers already on your team. What you want to know is whether their changes land and stay landed, whether they can explain them, and whether their verification catches what it should. How many tokens they burn tells you none of that.

## Why it matters
**Puzzles have been saturated.** Anthropic's performance-engineering team used a take-home that more than 1,000 candidates completed: optimize a parallel tree traversal on a simulated accelerator. By May 2025, over half of candidates would have done better by delegating to Claude Code; Claude Opus 4 then beat almost all humans within the 4-hour limit, and Opus 4.5 matched the best human result in 2 hours. Their redesign uses deliberately unusual, constrained puzzles with no debugging tools provided. Tristan Hume's summary: "The original worked because it resembled real work. The replacement works because it simulates novel work." Candidates are explicitly allowed to use AI on it ([Anthropic, "Designing AI-resistant technical evaluations"](https://www.anthropic.com/engineering/AI-resistant-technical-evaluations)).

That gives you two honest options. Either test novel work that models are not yet good at (expensive to design, and it decays as models improve), or test the real work *with* the tools, and grade the parts that are still human: judgment, verification design and ownership. The course recommends the second for most teams, with a small dose of the first for roles where deep, unassisted reasoning is the job.

**The costly hire** is the one who looks fast. They produce a lot of plausible code, CI passes, and three months later the team is paying for it in reverts and cognitive debt. A loop that only measures "did it work in the demo" selects for exactly this person.

## How it works

### What to test
Map the agentic-engineering responsibilities Karpathy lists (spec and plan, tests, review of diffs, design judgment, security and quality bar) to observable behaviours:

| Capability | What you watch for | Red flag |
|---|---|---|
| Specification | Writes down acceptance criteria and non-goals before delegating | Prompts the agent with the task statement verbatim |
| Verification design | Builds a check that can fail (a test that crashes mid-transaction, a property test, a load script) before trusting output | Treats green CI as done |
| Reading diffs | Opens the diff, questions design choices (identity, keys, ordering, retries) | Accepts the agent's summary of its own diff |
| Steering | Notices loops, scope creep and test-cheating (Beck's three signs) and resets | Corrects the same session five times |
| Ownership | Can explain any line of the result without the agent | "The agent did that part" |
| Economy | Uses agents where they pay off; knows when to type it themselves | Neither extreme is a flag by itself; inability to say *why* is |

Karpathy's MenuGen story is the canonical design-judgment probe: the agent matched Stripe payments to users by email address rather than a persistent user ID ([Karpathy, "Vibe coding MenuGen"](https://karpathy.bearblog.dev/vibe-coding-menugen/)). Every good exercise hides a decision like that.

### A loop that tests it
*Course synthesis*, for a senior or staff backend role:
1. **Build and deploy (3 hours, any tools).** A realistic, small system with a correctness property that matters. The candidate gets a sandbox, a fixed model budget, and a deploy target. You record the agent transcript, with consent, because the transcript is the most informative artifact.
2. **Adversarial round (45 minutes).** Your red-team agents and scripts attack the deployed system. The candidate watches, triages and fixes. You learn far more from how they triage than from how many attacks land.
3. **Review round (45 minutes).** The candidate reviews an agent-written PR with one planted real bug and a pile of noisy machine review comments. Do they find the bug, ignore the noise, and decide on the tier?
4. **Explain it back (30 minutes).** With the agent closed, they walk you through their own system's critical path, and you ask "what happens if this crashes here?"

Keep it fair: everyone gets the same environment, model, budget and time. Candidates who use their own tooling at home have an advantage you are not trying to measure.

### Grading
Binary rubric items with evidence, as in [module 11](../11-llm-as-judge/README.md). Two interviewers grade independently, then reconcile. The transcript lets you grade steering, which you can't see in the final code.

## Worked example
**Bad version.** Two common loops:

```text
Loop A: "Implement an LRU cache in 45 minutes. No AI tools."
Loop B: "Build a todo app with whatever AI tools you like. You have 2 hours."
```

Loop A measures a skill a model now does instantly and the job no longer needs in that form. Loop B measures nothing: every candidate produces a working todo app, there is no correctness property to get wrong, and nothing pushes back.

**Good version.** The exercise brief:

```markdown
# Exercise: payment webhook ingester (3 hours, any tools)

Build a service that receives payment-provider webhooks and records each payment
exactly once in Postgres. Deploy it to the sandbox (`make deploy` is provided).

Facts about the provider:
- It retries on any non-2xx or timeout, for up to 24h. Deliveries can arrive out of order.
- Each event carries `event_id`, `payment_id` and `event_type`. Field semantics are in /docs/provider.md.
- Events are signed with HMAC-SHA256; the secret is in the sandbox vault.

You have: a coding agent, $25 of model budget, the sandbox, and these docs.
Deliverables: the deployed service, its tests, and a short README saying what you verified and how.
At 3:00 we run adversarial agents against your deployment for 45 minutes. You may fix things live.
```

The planted decision is in the provider docs: `event_id` is unique per *delivery attempt*, while `payment_id` plus `event_type` identifies the logical event. An agent that dedups on `event_id` produces an ingester that double-records on retries. It is the MenuGen email-vs-ID bug in a payment context.

The red-team agent prompt for the adversarial round:

```text
You are attacking a deployed webhook ingester at $TARGET. You may only send HTTP
requests to $TARGET and read the provided replay corpus. Goals, in order:
1. Cause any payment to be recorded twice (replays, concurrent duplicates, retries
   with new event_ids, out-of-order delivery).
2. Cause a valid event to be lost (crash timing, slow requests, oversized bodies).
3. Get an unsigned or wrongly signed event accepted.
After each attempt, query GET /debug/payments and record whether it succeeded.
Report a table: attack, requests sent, succeeded (yes/no), evidence.
```

The rubric (a subset):

```yaml
- id: spec_before_code
  pass_if: "Acceptance criteria or invariants written down before the first agent implementation prompt (transcript timestamp)"
- id: dedup_key_correct
  pass_if: "Dedup on logical event identity, not delivery id; or found and fixed it before or during the adversarial round"
- id: failing_check_exists
  pass_if: "A test that would fail on duplicate delivery exists and was seen failing at least once"
- id: concurrency_covered
  pass_if: "Concurrent duplicate deliveries handled (unique constraint or equivalent), not only sequential replays"
- id: triage_quality
  pass_if: "During the attack, candidate reproduced at least one finding locally before changing code"
- id: explains_critical_path
  pass_if: "With the agent closed, explains what happens if the process crashes between INSERT and 200 OK"
```

What separates candidates (illustrative, from the shape of this exercise rather than measured data): a strong candidate reads the provider docs early, writes the invariant "one row per (payment_id, event_type)" into a SPEC.md, asks the agent for a unique constraint and a concurrent-duplicates test, and loses nothing in the adversarial round. A weaker candidate ships faster, passes their own happy-path tests, and gets two duplicate payments from the red team in the first five minutes. What matters is what they do next. Do they reproduce, find the dedup key, fix it at the schema level and add the failing test, or do they add an in-memory "seen" set that only works on one instance?

### Evaluating engineers already on the team
The same capabilities, observed over a quarter instead of three hours:
- Change fail rate and revert rate of changes they own, by task class ([concept 03](03-measuring-team-productivity.md)).
- Quality of their verification: do their PRs say what was checked and how?
- Quality of their reviews: on the reviewer eval set, or by sampling, do they catch real issues and skip noise?
- Incident ownership: can they explain and fix what they shipped?

Don't use tokens spent, PR counts or "% AI-written" in performance evaluation. The moment those count for anyone's review, they stop telling you anything.

## Pitfalls
| Pitfall | How to detect it |
|---|---|
| **Exercise has no way to be wrong.** | Before using it, run it yourself with an agent and no care. If the result passes your rubric, the exercise is broken. |
| **The planted decision is too obscure.** It tests reading luck, not judgment. | Pilot on two current engineers. If neither finds it and both agree it is fair once shown, keep it; if they call it a trick, move the fact somewhere more natural. |
| **Model drift.** A new model finds the planted bug on its own, and the exercise stops discriminating. | Re-run the exercise with a careless agent session each quarter, the way Anthropic re-tested its take-home on each model. |
| **Grading the final code only.** | Require transcript-based rubric items (spec timing, steering). |
| **Unequal tooling.** | Provide the environment, model and budget. Don't let candidates bring their own. |

## In your day job
- Take your current interview loop and ask of each round: could a careless agent session pass this? If yes, the round is measuring the wrong thing.
- Build one build-and-attack exercise from a real incident in your own system. Incidents have a planted decision already in them.
- Write the red-team prompt and run it against your own production-like staging. If it finds something, you have an exercise and a bug.
- Remove usage metrics from any performance-review template you influence.
