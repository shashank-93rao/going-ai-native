# 05: Measure yourself: a personal randomized A/B

## The idea

[04](04-honest-evidence.md) ended with "measure your own productivity". This file shows how to do it with the same core design as METR, scaled down to one engineer:

1. **Register** each task, with your time estimate, *before* you know which arm it gets.
2. **Randomly assign** it to `ai` or `no_ai`, with balance within task-size buckets.
3. **Record** start, merge, any rework in the following 14 days, abandonment, and your guess of how long the other arm would have taken.
4. **Analyze** on log time, adjusting for your own estimate, with honest intervals, and report abandoned tasks instead of dropping them.

The kit lives in [`code/`](code/README.md): an append-only JSONL log, a CLI, a simulator that plants a known effect, and a stats summary. It is the module's application of the thesis to yourself. Your belief that AI is helping is a claim, and the only way to check it is an oracle that can disagree with you.

## Why it matters

METR's developers were wrong about the sign of their own effect ([04](04-honest-evidence.md)). The follow-up was undermined by selection: 30–50% of developers withheld tasks they didn't want to do without AI ([METR 2026](https://metr.org/blog/2026-02-24-uplift-update/)). A personal measurement that ignores these two lessons inherits both failures. It records how fast you feel, on the tasks you chose.

A second motivation is ordinary engineering. You'll make decisions on this: which tasks to delegate, whether a new harness helped, whether a model upgrade changed anything. You wouldn't ship a latency claim without a benchmark and error bars, and this deserves the same rigor.

## How it works

### The log format

One JSON object per line, append-only. State is a fold over events, which is event sourcing applied to an experiment. The fold enforces the invariants that keep the experiment honest:

```json
{"event": "register", "task_id": "PAY-412", "ts": "2026-09-01T09:00:00+00:00", "title": "idempotency key collision", "kind": "bugfix", "size": "M", "est_minutes": 120}
{"event": "assign",   "task_id": "PAY-412", "ts": "2026-09-01T09:00:00+00:00", "arm": "ai", "block": "M", "seed_id": "7a32254e"}
{"event": "start",    "task_id": "PAY-412", "ts": "2026-09-01T09:05:00+00:00"}
{"event": "merge",    "task_id": "PAY-412", "ts": "2026-09-01T13:40:00+00:00", "pr": "#8812", "active_minutes": 95}
{"event": "perceive", "task_id": "PAY-412", "ts": "2026-09-01T13:41:00+00:00", "perceived_other_arm_minutes": 150}
{"event": "rework",   "task_id": "PAY-412", "ts": "2026-09-04T10:00:00+00:00", "rework_kind": "fix", "minutes": 40}
{"event": "abandon",  "task_id": "PAY-419", "ts": "2026-09-05T16:00:00+00:00", "reason": "blocked on vendor API"}
```

| Invariant (enforced by `fold`) | What it prevents |
|---|---|
| `assign` only after `register`, and at most once | Re-rolling an assignment you didn't like |
| `start` / `merge` only after `assign` | Logging work done before you knew the arm |
| `est_minutes` lives on `register` | Estimates contaminated by knowing the arm |
| The seed is never stored, only its fingerprint (`seed_id`) | Peeking at future assignments; the log still proves which seed was used |
| A malformed line fails with its line number | Silent data loss |

### Assignment

Assignment is deterministic given a private seed, via SHA-256, so it is reproducible and auditable. It uses **permuted blocks of 2 within each size bucket (S/M/L)**. Plain coin flips at n=20 can easily land 14/6, with all the large tasks on one side. With blocks, each bucket is balanced to within one task.

Blocks have one cost: once the first task of a pair is assigned, the second is predictable. The defense is procedural. **Register a batch** (say, sprint planning), **then run `assign` once** for the batch. You commit to the tasks before you can know which arm any of them gets.

### Defining the arms

Write the definition down before task 1, and don't change it mid-experiment.

```markdown
## Arms (frozen 2026-09-01)
- ai:    any assistant/agent allowed (Claude Code, chat, autocomplete).
- no_ai: no chat, no agent, no AI autocomplete. Normal IDE, docs, search, colleagues allowed.
- Both:  same review process, same CI. Reviewers are not told the arm.
- Outcome: active minutes (primary); wall-clock start->merge (secondary).
- Rework window: 14 days after merge. Rework = fix, revert, or follow-up PR caused by this change.
- Stop rule: 30 tasks per arm, or 8 weeks, whichever first. No peeking at the p-value before then.
```

### The analysis

`python selfmeasure.py summary` reports:

| Line | What it is | Why |
|---|---|---|
| Unadjusted | geomean(ai) / geomean(no_ai) of minutes | Durations are right-skewed, so a ratio of geometric means is the natural effect. 1.19 means 19% longer |
| **Estimate-adjusted** (primary) | the same ratio on actual ÷ your pre-assignment estimate | Your estimate absorbs task difficulty. At small n, this is the difference between learning something and learning nothing |
| Adjusted, incl. rework | (minutes + rework minutes in the window) ÷ estimate | A change that merges fast and comes back twice was not fast |
| Perceived ratio | the same ratio, with your guess standing in for the unobserved arm | Your METR perception gap, measured on you |
| Detectable at this n | the minimum detectable ratio at 80% power, and the n needed for a 20% effect | Tells you whether a null result means anything |
| Warnings | small n, differing abandon rates between arms, open tasks | The selection-effect alarms |

Statistical choices, for a reader who will check them:
- **CI:** a Welch t interval on mean log time. The kit also includes a percentile bootstrap, but it under-covers at this size. Over 200 simulated experiments with 20 tasks per arm, the bootstrap's nominal 95% interval contained the true ratio 92% of the time, against 95.5% for Welch (measured with `simulate_ab.py`; reproduce it in Exercise 5).
- **p-value:** a permutation test on mean log difference, with no distributional assumption.
- **Abandoned tasks** stay in the denominator of completion rate. If one arm abandons ≥10 points more often, the merged sets are no longer comparable, and the summary says so.

## Worked example

### Bad version: a before/after impression

```text
"Last month I used Claude for most things and closed 31 tickets. The month before, 22.
 So roughly 40% faster."
```

Everything is wrong with this, and every flaw has a direction. You chose which tickets got AI, and the ticket mix changed between months. "Closed" ignores the three that bounced back. Most importantly, you'd have reported the same number feeling the same way if the true effect were zero. Run the five questions from [04](04-honest-evidence.md) and none of them has an answer.

### Good version: a planted-effect dry run, then the real thing

**Step 1. Check the instrument before trusting it.** Generate a synthetic log where you know the truth. Here, AI makes tasks take 19% longer (METR's 2025 number), and you *feel* 20% faster:

```bash
cd 00-orientation/code
python simulate_ab.py --out data/sample_log.jsonl --tasks 40 --true-ratio 1.19 --perceived-ratio 0.80
python selfmeasure.py --log data/sample_log.jsonl summary --outcome active
```

Actual output (synthetic data, seed 7):

```text
Outcome: active minutes

arm     assigned  merged  abandon  open  median_min  geomean_min  rework
ai            20      20        0     0         232          223     20%
no_ai         20      20        0     0         131          124     35%

Unadjusted:              80% longer with AI (ratio 1.80, 95% CI 0.85-3.81, p=0.120)
Estimate-adjusted:       54% longer with AI (ratio 1.54, 95% CI 1.20-1.97, p=0.001)
Adjusted, incl. rework:  44% longer with AI (ratio 1.44, 95% CI 1.11-1.86, p=0.007)
Perceived ratio:         0.81 (your guesses about the other arm, vs active minutes)
Detectable at this n:    ratio <= 0.71 (80% power); ~47 tasks/arm needed for a 20% effect
```

What this teaches before you've logged a single real task:

- **The perception gap is visible.** You "felt" 0.81, and the instrument says 1.54. That is the METR effect reproduced inside your own log.
- **Adjustment matters.** The unadjusted CI (0.85–3.81) can't even tell you the sign. Dividing by your estimate shrinks it to 1.20–1.97.
- **Noise is large even when the model is right.** The planted truth is 1.19, and this draw estimates 1.54. The interval contains 1.19, but only just. At 20 per arm, a point estimate can be off by a third. Read the interval, not the point.
- **Rework is noisy too.** Both arms had a planted 20% rework rate, and this draw shows 20% vs 35%.

Now the same log with the secondary outcome:

```text
Outcome: wall-clock start->merge
...
Estimate-adjusted:       0% longer with AI (ratio 1.00, 95% CI 0.67-1.50, p=0.991)
Detectable at this n:    ratio <= 0.58 (80% power); ~122 tasks/arm needed for a 20% effect
```

Wall clock includes review and CI wait (about 90 minutes median in the simulator, the same for both arms), and that noise buries the effect. The power line shows you'd need around 122 tasks per arm to see a 20% effect this way. **This is why active minutes is the primary outcome**, and why the power line exists: a null result at n=20 on wall clock means nothing.

**Step 2. Run it for real.**

```bash
export SELFMEASURE_SEED="$(openssl rand -hex 16)"   # store it in your password manager
export SELFMEASURE_LOG=~/selfmeasure.jsonl

# Monday: register the sprint's tickets with estimates, then assign them as a batch
python selfmeasure.py register PAY-412 --size M --est 120 --kind bugfix  --title "idempotency key collision"
python selfmeasure.py register PAY-415 --size M --est 90  --kind feature --title "webhook retry budget"
python selfmeasure.py register PAY-420 --size S --est 30  --kind chore   --title "bump kafka-clients"
python selfmeasure.py register PAY-421 --size S --est 40  --kind bugfix  --title "nil map in DLQ handler"
python selfmeasure.py assign

# As you work
python selfmeasure.py start PAY-412
python selfmeasure.py merge PAY-412 --pr "#8812" --active 95
python selfmeasure.py perceive PAY-412 --other 150
# Backfill a merge time from GitHub if you forgot:
python selfmeasure.py merge PAY-415 --ts "$(gh pr view 8820 --json mergedAt -q .mergedAt)" --active 70
```

Here, `assign` prints each task with its arm. Which arm each task gets depends on your seed.

## Pitfalls

| Pitfall | How to detect it |
|---|---|
| **Registering after you've seen the arm**, or "forgetting" to register tasks you'd hate to do without AI | Count tickets you closed against tasks registered. If they diverge, your sample is selected. METR's 2026 problem is exactly this. |
| **Dropping abandoned tasks** | The summary keeps them. If you are tempted to delete a line, the append-only log and the audit trail are working as intended. |
| **Contaminating the no-AI arm** (pasting the error into chat, "just this once") | Decide the rule up front. If it happens, log the task as abandoned with reason `contaminated` rather than recording a clean merge. |
| **Peeking and stopping on a good p-value** | Freeze the stop rule in the arm definition. Peeking at every task inflates false positives. |
| **Generalizing your result** | Your estimate covers *your* tasks, *your* tools, *this* model. Re-run after model upgrades and harness changes, which are themselves the interventions you most want to evaluate ([12-hill-climbing](../12-hill-climbing/README.md)). |
| **Learning effects across the period** | Add a `kind` breakdown, and compare the first half with the second. A strong trend in the AI arm means you're measuring your learning curve. |

## In your day job

- Start the log this week. Even before you have enough data for an effect, the estimate-vs-actual column calibrates your intuitions.
- Use the same harness to evaluate *changes*: "my new CLAUDE.md" vs the old one, or "agent with Stop hook" vs "agent without". Random assignment works for any two arms.
- Report your result with its interval, and the n you'd need. "1.2x, CI 0.9–1.6, need about 45 per arm" is a useful statement, and "feels faster" isn't.
- Bring the protocol to your team when someone proposes a productivity metric. The team version of this design is in [17-ai-native-engineer-and-team](../17-ai-native-engineer-and-team/README.md).
