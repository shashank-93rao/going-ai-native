# 05: Jaggedness and the march of nines

## The idea

**Jaggedness.** A model's competence does not follow human difficulty. It can write a correct lock-free ring buffer and then miscount the items in a five-element list. Karpathy describes current models as "at the same time a genius polymath and a confused and cognitively challenged grade schooler" ([Karpathy, "2025 LLM Year in Review"](https://karpathy.bearblog.dev/year-in-review-2025/)). The capability boundary is a jagged frontier, not a smooth difficulty curve, so "it handled the hard case, so it'll handle the easy one" is not a valid inference. (The "jagged frontier" phrase was popularized by a 2023 Harvard Business School and BCG field study of consultants using GPT-4, Dell'Acqua et al.)

**The march of nines.** Reliability is bought one nine at a time, and each nine costs about the same as the last. Karpathy, on why self-driving took so long: "it's a march of nines ... Every single nine is a constant amount of work," and "When you get a demo and something works 90% of the time, that's just the first nine." He calls the gap between them "a very large demo-to-product gap where the demo is very easy, but the product is very hard" ([Dwarkesh Podcast, 2025-10-17](https://www.dwarkesh.com/p/andrej-karpathy)).

Put the two together and you have the core of this module. You can't predict where a model will fail from how hard the task looks to you, so you have to **measure** per task class. And whatever you measure per step gets **multiplied** across the steps of an agent.

## Why it matters

The arithmetic is unforgiving. Here is `code/reliability_nines.py`, run as is:

```text
Chain success p**n (rows: per-step success, cols: steps)
p\n             1        5       10       20       50      100
0.9          0.900    0.590    0.349    0.122    0.005    0.000
0.95         0.950    0.774    0.599    0.358    0.077    0.006
0.99         0.990    0.951    0.904    0.818    0.605    0.366
0.995        0.995    0.975    0.951    0.905    0.778    0.606
0.999        0.999    0.995    0.990    0.980    0.951    0.905
```

A step that works 95% of the time looks great in a demo. Chain 20 of them and the run succeeds 36% of the time. An agent that takes 50 tool calls needs better than 99.5% per step to beat 75% end to end. This is the same calculation as serial availability: a request path through five services at 99.9% each is about 99.5% available. You've done this for SLOs. Agents need the same treatment.

## How it works

### Where jaggedness comes from, and what to do about it

Karpathy's explanation in "Verifiability" is that capability advances fastest where outcomes can be checked automatically, because those tasks can be trained with reinforcement learning: they are resettable, cheap to attempt many times, and automatically rewardable ([Karpathy, "Verifiability"](https://karpathy.bearblog.dev/verifiability/)). In his 2026 Sequoia talk he adds a second factor, how much training attention labs give a domain, and suggests asking whether your task is "on the rails" ([Karpathy, Sequoia Ascent 2026](https://karpathy.bearblog.dev/sequoia-ascent-2026/)).

Practical consequences:

- **On the rails** (common stacks, code with tests, well-trodden refactors): expect high per-step reliability and use more autonomy.
- **Off the rails** (your in-house consensus library, a proprietary DSL, an unusual invariant): expect surprising failures. Karpathy reported coding agents being "just not net useful" when he built nanochat, novel code far from the training distribution ([Dwarkesh](https://www.dwarkesh.com/p/andrej-karpathy)). Add context, tools and evals, and keep the leash short.
- **Known weak spots** (counting, character-level work, arithmetic, ID comparison; see [01](01-tokens-and-the-context-window.md)): route them to code.

Because the frontier is jagged, **public benchmarks transfer poorly to your workload**. Karpathy says he has lost trust in benchmarks because they get "benchmaxxed". The only reliability number that means anything for you is one measured on your own task distribution ([Module 10](../10-evals-fundamentals/README.md)).

### Nines as an SLO

Map the vocabulary:

| SRE concept | Agent equivalent |
|---|---|
| Availability per hop | Per-step success rate *p* (a tool call does what was intended, and the model's interpretation of the result is right) |
| Serial path availability | Run success ≈ *p*<sup>n</sup> for *n* steps |
| Error budget | Expected failed runs = (1 − run success) × runs. At 99% over 10,000 tasks a month, that's 100 failures to absorb |
| Redundancy / retries | Verifier plus retry: catch a failed step and try again |
| Correlated failures | Systematic model errors. The same misunderstanding on every retry |

The calculator answers the planning questions:

```text
Per-step reliability needed for a 20-step agent to hit a run-level target
  run 90.0% (1 nines) -> step 0.99475 (2.28 nines)
  run 99.0% (2 nines) -> step 0.99950 (3.30 nines)
  run 99.9% (3 nines) -> step 0.99995 (4.30 nines)
```

Each run-level nine needs one more nine per step, plus log10(*n*) on top. You can't prompt your way to 4.3 nines per step. You get there with **mechanisms**: deterministic checks, retries, and smaller *n*.

### Verifiers and retries, and their ceiling

A verifier (tests, a type checker, a schema validator, a judge) that catches a fraction *d* of failed steps lets you retry them. With unlimited independent retries, per-step success converges to *p* / (1 − (1 − *p*)·*d*). The failures the verifier *misses* set the ceiling:

```text
Verifier + retry, base step p=0.95, verifier catches 80% of failures
  attempts=1: step=0.9500  20-step run=0.358
  attempts=2: step=0.9880  20-step run=0.785
  attempts=3: step=0.9895  20-step run=0.810
```

One retry more than doubles the run success rate. The third attempt barely helps, because 1% of steps now fail *silently*: the verifier didn't catch them. Past that point, adding retries is pointless. **Improving the verifier** (raising *d*) is the only way forward. This is the course thesis in numbers: autonomy scales with verifiability.

Two caveats keep this honest:

- **Independence is optimistic.** A model that misreads your spec will misread it on the retry too. Real retry gains are smaller than the formula when errors are systematic. Measure the second-attempt success rate directly.
- **Agents can self-correct.** Not every bad step is fatal. A model that runs the wrong command often notices and recovers. Anthropic notes that models recovering from isolated errors made infrastructure bugs *harder* to see ([Anthropic, "A postmortem of three recent issues"](https://www.anthropic.com/engineering/a-postmortem-of-three-recent-issues)). So *p*<sup>n</sup> is pessimistic for recoverable steps and optimistic for irreversible ones. Count the steps that can't be undone (a migration applied, a message sent, a branch force-pushed) separately. Those are your real *n*.

### pass@k versus pass^k

Two metrics answer different questions ([Module 10](../10-evals-fundamentals/README.md) covers both):

```text
pass@k vs pass^k at p=0.7
  k=1   pass@k=0.700  pass^k=0.700
  k=3   pass@k=0.973  pass^k=0.343
  k=5   pass@k=0.998  pass^k=0.168
```

**pass@k** is the probability that at least one of *k* tries succeeds. It's the right metric when a reliable checker can pick the winner, as with a test suite on generated patches. **pass^k** is the probability that all *k* succeed. It's what a user experiences across repeated runs, and what an SLO cares about. A 70% model looks like 97% under pass@3 and 34% under pass^3. Which number you report depends on whether you have a verifier, so say which one you're using.

## Worked example: a 20-step schema-migration agent

Your team wants an agent that takes a Jira ticket ("add `tenant_id` to `orders`, backfill, add an index") and produces a reviewed migration PR for a Postgres-backed Java service. A prototype ran 10 times and succeeded 9 times.

**Bad version.** "9/10 in the demo, ship it behind a feature flag."

What the 9/10 hides:

- Ten trials can't distinguish 90% from 75% or 97%. The 95% interval for 9/10 is roughly 55% to 99.7%.
- The demo tickets were the easy, on-the-rails ones. The hard 20% of tickets (multi-tenant constraints, partitioned tables) weren't in the sample.
- A run is about 20 steps (read schema, read ORM entities, write the migration, write the backfill, update repository code, run tests, and so on). A 90% *run* rate implies about 99.5% per step, and you have no per-step measurement at all.
- One step, running the backfill against the shared staging database, is irreversible.

**Good version.** Treat it like an SLO design review.

1. **Set the target.** Say 95% of PRs are mergeable after at most one human comment, measured over a month.
2. **Measure per step on a real distribution.** Build 50 tasks from past tickets, stratified by difficulty ([Module 10](../10-evals-fundamentals/README.md)). Trace every run and label which step failed ([Module 10](../10-evals-fundamentals/README.md), error analysis).
3. **Do the arithmetic.** Suppose error analysis shows "write the migration" and "update repository code" are the weak steps at about 95%, and the rest are at 99.5% or better. Then 0.95² × 0.995¹⁸ ≈ 0.82. You are about 13 points short.
4. **Add verifiers where the failures are.** A migration linter plus `flyway validate` plus running the migration against an ephemeral Postgres container in the agent's sandbox catches most migration failures. Compilation plus the repository's tests catch most code-update failures. With 80% detection and one retry, the calculator says each weak step goes from 0.95 to 0.988. The run goes to about 0.988² × 0.995¹⁸ ≈ 0.89.
5. **Shrink *n* and remove irreversibility.** Fold the read-only steps into one deterministic script (one step instead of four). Have the agent produce the backfill as a reviewed artifact that a human or CI runs, instead of running it. Now the agent has no irreversible step.
6. **Decide autonomy from the measured number.** At 89% with no irreversible steps and human review of every PR, opening PRs automatically is reasonable. If the target really is 95%, the next investment is a better verifier, such as a property test that the backfill is idempotent ([Module 13](../13-testing-agentic-systems/README.md)). More prompting won't get you there.

Measure the actual results after each change. The numbers above come from the model, not from measurement.

## Pitfalls

| Pitfall | How to detect it |
|---|---|
| Extrapolating from hard successes to easy cases | Stratify your eval by task type. Look for task classes with surprisingly low pass rates. |
| Shipping on a demo-sized sample | Compute a confidence interval before quoting a rate. Under 30 trials, it's usually too wide to act on. |
| Reporting pass@k as reliability | Ask whether production has a checker that picks the winner. If not, report pass^k or the single-run rate. |
| Assuming retries are independent | Measure the success rate of second attempts on tasks whose first attempt failed. If it's far below *p*, failures are correlated. |
| Counting only total steps | List irreversible steps separately. One irreversible step at 99% is a 1% incident rate. |
| Adding retries past the verifier's ceiling | If retries stop moving the needle, measure the verifier's detection rate on a labelled set of failures. |

## In your day job

- For any agent proposal, ask three questions: how many steps, what's the measured per-step rate, and which steps are irreversible. Run `reliability_nines.py` with the answers.
- Put the run-level target in the design doc as an SLO with an error budget, and decide in advance what happens when the budget burns.
- Spend reliability effort on verifiers before prompts. A verifier raises the ceiling, and a prompt tweak moves one point under it.
- Keep a list of your system's "off the rails" areas (in-house libraries, unusual invariants). They get short leashes and extra evals.
