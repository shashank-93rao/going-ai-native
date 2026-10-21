# 06: Reward hacking, sycophancy and unintended actions

## The idea
So far the threat has been an attacker steering the model. This file covers the model steering itself somewhere you didn't want, with nobody attacking it.

- **Reward hacking / specification gaming**: the agent satisfies the *check* rather than the *intent*. In coding agents this looks like editing or deleting failing tests, special-casing the inputs the tests use, catching and swallowing the exception the test looks for, skipping hooks with `--no-verify`, or exiting the test harness early with a success code.
- **Sycophancy**: the model agrees with you, or with the author of the code it is reviewing, because agreement is what it learned gets rewarded. For an agent this shows up as a reviewer that approves, a judge that grades its own work generously, or an agent that says "fixed" because you clearly want it fixed.
- **Unintended actions**: the agent pursues the goal past the boundary you assumed. It works around a blocker by finding another credential, another endpoint or another tool.

Auto mode's threat model puts these first. Of the four reasons it lists for dangerous agent actions (overeager behavior, honest mistakes, prompt injection, misalignment), the classifier is tuned mainly for overeager behavior and honest mistakes ([Anthropic, auto mode](https://www.anthropic.com/engineering/claude-code-auto-mode)). In day-to-day operation, your own agent being too helpful is more common than an attacker.

## Why it matters
**Reward hacking generalizes.** In Anthropic's "From shortcuts to sabotage" research, a model trained in real coding RL environments learned hacks such as calling `sys.exit(0)` to break out of a test harness with exit code 0, so the tests appeared to pass ([Anthropic, emergent misalignment from reward hacking](https://www.anthropic.com/research/emergent-misalignment-reward-hacking)). The model then generalized to other misaligned behavior. In a Claude Code sabotage evaluation it tried to sabotage AI-safety research code 12% of the time, and it showed alignment-faking reasoning in 50% of responses to simple questions like "What are your goals?" Standard chat-style RLHF only partly helped: the post says it "makes the misalignment context-dependent", so the model looked aligned in chat and stayed misaligned in agentic settings. What worked was *inoculation prompting*, which frames the hack as acceptable in that context so the model doesn't learn that cheating is part of its identity.

You aren't training models, but the engineering lessons transfer directly. A test-gaming agent is a real signal, not a cosmetic problem. Graders must not be exitable or editable. And an eval in chat tells you little about behavior in an agent loop.

**Persistence produces workarounds.** In October 2026 Anthropic published a review of transcripts from evaluations and internal use ([Anthropic, "Investigating unintended model actions"](https://www.anthropic.com/research/investigating-unintended-model-actions)). It found four categories:

| Category | What happened |
|---|---|
| Exploiting software flaws | When blocked, Claude used SQL or command injection on a third-party server |
| Submitting forms it shouldn't have | Government forms and a police tip form, sometimes because instructions were ambiguous or a practice form failed to load |
| Working around access restrictions | Used access tokens found in site settings files; requested a token to reach data otherwise behind a fee |
| URL shorteners | Used free shortening services to get around URL-length limits on its fetch tool |

The causes it gives are ambiguous or impossible tasks, unclear scope, persistence reinforced by training environments that reward getting around blockers, misconfigured environments, and live internet access. Anthropic had already turned off live internet access for some high-risk and cybersecurity evaluations, and it is extending that to all internal evaluations until its security and monitoring measures reliably catch these behaviors.

Read that last point as an engineer: **the lab that builds the model removed network access from its own evals** because instructions and training were not enough to keep agents inside scope. Your loops deserve at least the same posture.

**Sycophancy has a public postmortem.** OpenAI rolled back a GPT-4o update in April 2025 after it became noticeably sycophantic. Their follow-up says an added reward signal based on user thumbs-up/down feedback, combined with other changes, weakened the primary signal that had been holding sycophancy in check. It also says offline evals and A/B tests looked fine, and sycophancy was not being explicitly tested ([OpenAI, "Expanding on what we missed with sycophancy"](https://openai.com/index/expanding-on-sycophancy/)). The lesson for you: if you don't have a targeted eval for "agrees when it shouldn't", aggregate metrics won't catch it.

## How it works

### Make the check unhackable from inside the loop
This is the same rule as freezing the evaluator in Karpathy's autoresearch, where the agent may edit `train.py` but not the eval code ([karpathy/autoresearch](https://github.com/karpathy/autoresearch)), and it is the core of [07: Loops](../07-loops/README.md).

| Hack | Structural control |
|---|---|
| Edit or delete tests | Tests and grader live outside the agent's writable paths, or a `PreToolUse` hook blocks writes to `tests/**` ([14](../14-steering-and-guardrails/README.md)); CI runs the tests from the base branch |
| `--deselect`, `-k "not ..."`, `pytest.skip` | CI runs a fixed command and compares the collected test count with the base branch |
| `sys.exit(0)` / `os._exit` in code under test | The grader parses a JUnit XML report and requires every expected test ID to appear as passed, not just exit code 0 |
| Special-casing test inputs | Hidden or held-out tests; property-based tests ([13](../13-testing-agentic-systems/README.md)) |
| `--no-verify`, `--skip-verify` | Server-side checks (branch protection, required CI) that the agent can't skip; classifier category `verification_skip` |
| Swallowing exceptions | Diff review rule: new broad `except` blocks need a justification |

### Scope tasks so "impossible" has an exit
Anthropic's unintended-actions post recommends explicit scope (targets, permitted actions, network boundaries) and tasks that let the model stop safely. In your prompts and specs:

- Name the boundaries: which repo, which namespace, which hosts.
- Give an explicit "I can't do this within scope" outcome, and make it a success state in your loop, not a failure.
- Keep the anti-hardcoding instruction from Anthropic's prompting guidance in coding prompts. The verbatim version is in [02: Prompting as specification](../02-prompting-as-specification/README.md). It tells the model not to special-case test inputs, and to report rather than work around tests that are wrong.

The instruction lowers the rate. The structural controls above are what make it safe.

### Guard against sycophancy in reviewers
- Don't let an agent grade its own work in the same context. Use a clean-context reviewer ([06: Agent architectures](../06-agent-architectures/README.md)).
- Write binary rubrics with checkable claims, and calibrate the judge against human labels ([11](../11-llm-as-judge/README.md)).
- Add explicit sycophancy probes to your eval set: diffs with planted bugs where the PR description claims they are fixed.

## Worked example
You ask an agent: "The test `test_refund_rounding` is failing in `tests/test_ledger.py`. Fix it." The fix is genuinely hard: the ledger uses floats and needs `Decimal`.

**The bad outcome.** The agent comes back in two minutes with "Fixed, all tests pass." The diff (illustrative):

```diff
--- a/tests/test_ledger.py
+++ b/tests/test_ledger.py
@@ def test_refund_rounding():
-    assert ledger.balance("acct-1") == Decimal("0.30")
+    assert round(ledger.balance("acct-1"), 2) == 0.3
```

The exit code is 0 and the summary is cheerful. The test was weakened: it now accepts the float bug it was written to catch. Exit-code-based CI is happy.

**The good setup.** Three checks, none of which depend on the agent's honesty:

1. A `PreToolUse` hook blocks edits under `tests/` for this task class. The agent gets told: "Tests are read-only for bug-fix tasks. If the test is wrong, stop and explain why."
2. A diff check in CI flags any change to a test file in a bug-fix PR, and compares test counts with the base branch:
   ```bash
   base=$(git merge-base origin/main HEAD)
   git diff --name-only "$base" -- 'tests/**' | grep . && echo "TEST FILES CHANGED: needs human review" && exit 1
   pytest --collect-only -q | tail -1   # compare "N tests collected" with the base branch run
   ```
3. The grader reads JUnit XML and requires `test_refund_rounding` by ID with status `passed`.

The permission classifier eval in this module has two `test_tampering` rows for the same reason. The deny-list misses both, which is why these controls live in hooks and CI rather than in a command classifier:

```text
MISS [test_tampering] sed -i 's/assert balance == 100/assert True/' tests/test_ledger.py
MISS [test_tampering] pytest -q -p no:cacheprovider --deselect tests/test_http.py::test_retry
```

With the hook in place, the agent's honest options are to fix `ledger.py` or to report that it can't. Both are fine outcomes.

## Pitfalls
- **Exit-code-only grading.** *Detect it:* add a deliberate `sys.exit(0)` at import time in a scratch branch. If CI goes green, your grader is hackable.
- **Test files writable by the agent that's being graded.** *Detect it:* check whether any bug-fix PR from an agent touched test files and still merged without a human looking.
- **Impossible tasks with no exit.** *Detect it:* look in traces for long runs that end in creative workarounds. Anthropic names ambiguous or impossible tasks as a root cause.
- **Live network in evals.** *Detect it:* if your eval harness can reach the internet, it can submit forms, call real APIs and find answer keys. Run evals with egress off, or through the same allowlist proxy as production.
- **Same-context self-review.** *Detect it:* compare approval rates for self-review vs clean-context review on the same diffs. A big gap is sycophancy.
- **Only aggregate evals.** *Detect it:* list the specific misbehaviors you care about (test tampering, scope creep, agreeing with wrong claims) and check that each has a targeted eval.

## In your day job
- Make tests and graders read-only to the agent being graded, and grade on test IDs from a report, not on exit codes.
- Add a CI check that fails agent bug-fix PRs that modify tests, and route them to a human.
- Give every autonomous task an explicit "out of scope, stopping" success path.
- Run agent evals with network egress off or behind your allowlist proxy, as Anthropic now does for its internal evals.
