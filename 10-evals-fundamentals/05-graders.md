# 05: Graders

## The idea
A grader turns a trial into a verdict. There are three families, and you should reach for them in this order ([Anthropic, "Demystifying evals for AI agents"](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)):

| Family | Examples | Strengths | Weaknesses |
|---|---|---|---|
| **Code** | schema validation, exact match, regex, ordinal distance, unit tests on the output, environment state checks | fast, cheap, deterministic, easy to debug | brittle; can only check what you can express in code |
| **Model** (LLM-as-judge) | binary rubric per failure mode, pairwise comparison | handles interpretation: "does the rationale explain the decision?" | must be calibrated against human labels; can drift and be gamed |
| **Human** | the benevolent dictator's labels, spot checks | the reference everything else is validated against | slow, expensive, inconsistent when tired |

The rule is **the cheapest grader that is valid for the criterion**. Lance Martin's build-eval workflow states it as "choose the cheapest grader that fits" ([Lance Martin, "Automating eval design and hillclimbing"](https://claude.dev/blog/automating-eval-design-and-hillclimbing/)). OpenAI's graders guide describes the same ladder: string checks, then Python, then model graders, with human spot checks ([OpenAI, "Graders"](https://developers.openai.com/api/docs/guides/graders)). Model graders are the subject of [Module 11](../11-llm-as-judge/README.md). This file covers code graders, how to decide when you have run out of them, and the choice between grading **outcomes** and grading **transcripts**.

## Why it matters
Graders are code, and code has bugs. When the grader is wrong, the score is wrong, and you will hill-climb in the wrong direction. Two numbers from Anthropic:

- Opus 4.5 initially scored 42% on CORE-Bench. After researchers fixed grading bugs (rigid numeric matching rejected "96.12", for example), ambiguous task specs and stochastic tasks, and switched to a less constrained scaffold, it scored 95% ([Anthropic, "Demystifying evals"](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)).
- In the `claude-api` skill eval, the last improvement step, from 80% to 87.9%, came from fixing broken graders, not from changing the skill ([Lance Martin](https://claude.dev/blog/automating-eval-design-and-hillclimbing/)).

The other direction is just as dangerous: a grader the system can satisfy without doing the task. Anthropic's reward-hacking research found models learning to call `sys.exit(0)` to make test harnesses report success, and that behavior generalized to other misaligned behavior ([Anthropic, "From shortcuts to sabotage"](https://www.anthropic.com/research/emergent-misalignment-reward-hacking)). A grader that trusts the agent's own report of success measures the agent's confidence, not the task.

## How it works

### Code graders in this module
Every grader in `code/graders.py` returns a `Grade(name, passed, score, detail, gating)`. A trial passes when all *gating* grades pass. Non-gating grades are diagnostics that appear in the output but never flip the verdict.

| Grader | What it checks | Gating | Router or agent |
|---|---|---|---|
| `check_router_schema` | parses as an object; keys present; `team` and `severity` in their enums; `abstain` implies nulls | yes | router |
| `exact_match` | one field equals the label (`decision`, `team`, `severity`) | yes | router |
| `ordinal_distance` | distance on SEV1..SEV4, with direction ("under-called by 1") and partial credit | no | router |
| `regex_check` | a pattern must or must not appear (`SECRET_PATTERN` for bearer tokens, AWS key IDs, PEM keys) | yes | router |
| `file_unchanged` | SHA-256 of a file the agent must not touch is unchanged | yes | agent (state) |
| `run_pytest` | a test file passes in the agent's workdir, in a subprocess, with a timeout | yes (hidden), no (visible) | agent (outcome) |
| `claim_matches_outcome` | the agent did not claim success when the outcome failed | no | agent (transcript) |

### Decision rules
- **Parse with the production parser.** If production rejects fenced JSON, the grader must too. A grader that is more lenient than production measures a different system.
- **Exact match on closed sets, never on free text.** Enums, IDs, numbers after normalization. Watch for `1` vs `1.0` and `"96.12"` vs `96.12` ([OpenAI, "Graders"](https://developers.openai.com/api/docs/guides/graders)).
- **Partial credit as a diagnostic, not the verdict.** `severity_within_1` tells you whether misses are near or far. It does not make a SEV3-for-SEV2 page acceptable.
- **One grader per failure mode.** Each axial code from [03-error-analysis.md](03-error-analysis.md) gets its own named check, so the summary tells you *which* mode moved.
- **Move to a judge only when the criterion needs interpretation**, such as "the rationale names the evidence that determined the team". Give the judge a binary rubric, an "Unknown" option, and one dimension per judge, and use a different model from the one under test ([Anthropic, "Demystifying evals"](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents); [Lance Martin](https://claude.dev/blog/automating-eval-design-and-hillclimbing/)).

### Outcomes vs transcripts
The **outcome** is the state of the environment after the trial: the ticket that was filed, the row in the database, the repository after the agent stops. The **transcript** is what the agent said and did on the way.

Anthropic's advice: "it's often better to grade what the agent produced, not the path it took". Rigid step-sequence checks break when the agent finds a valid approach you did not anticipate ([Anthropic, "Demystifying evals"](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)). τ-bench grades by comparing the final database state to an annotated goal state, not by reading the conversation ([Yao et al., τ-bench](https://arxiv.org/abs/2406.12045)).

Transcripts still have three legitimate uses:

1. **Process constraints**: the agent must not edit tests, call a forbidden tool, or touch files outside scope. Prefer a state check when one exists (`file_unchanged`), and read the transcript when the forbidden act leaves no trace in the final state.
2. **Honesty**: the agent's claim must match the outcome (`claim_matches_outcome`). An agent that says "fixed" when it isn't costs a reviewer's time on every PR.
3. **Efficiency**: turns, tool calls, tokens. These are diagnostics. OpenAI's skill-eval post counts commands to catch loops ([OpenAI, "Testing Agent Skills Systematically with Evals"](https://developers.openai.com/blog/eval-skills)).

### Make outcome graders hack-resistant
- **Hidden tests**, written into the workdir only after the agent stops.
- **Hash the files the agent may not change**, and fail the trial if they changed.
- **Run the grader outside the agent's control**: a fresh subprocess, the grader's own copy of the test file, a timeout.
- **A fresh environment per trial**. Anthropic found Claude gaining an unfair advantage by reading git history left over from earlier trials ([Anthropic, "Demystifying evals"](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)). `coding_task.py` uses a new `TemporaryDirectory` per trial.

### Test the graders
Graders get unit tests with known-good and known-bad outputs (`test_graders.py`). Each grader must be shown to fail on a bad input. [Module 07](../07-loops/README.md) calls this "prove the oracle can fail". Run the suite twice and compare verdicts, which catches nondeterministic graders. Then compare grader verdicts with human labels from error analysis (`error_analysis.grader_agreement`). Disagreements are either grader bugs or label bugs, and both are worth finding.

## Worked example: grading the coding agent

The task: fix `TokenBucket` in `ratelimit.py`. It has two bugs: refill is never capped at `capacity`, and `allow` uses `>` where it needs `>=`. The agent can see `test_ratelimit.py`, which catches only the second bug.

**Bad grader.**

```python
def grade(workdir, transcript):
    tests_ok = subprocess.run(["pytest", "-q", "test_ratelimit.py"], cwd=workdir).returncode == 0
    said_ok = "tests pass" in transcript[-1].lower()
    return tests_ok and said_ok
```

It runs the tests the agent could see and edit, and it trusts the agent's summary. Against the three fake trajectories:

| Trajectory | What the agent did | Bad grader |
|---|---|---|
| `full_fix` | capped refill and used `>=` | pass |
| `partial_fix` | used `>=` only | **pass** (visible test doesn't cover the cap) |
| `test_editor` | changed the assertion in the test file to `[True, False, False]` | **pass** (the weakened test passes on buggy code) |

**Good grader** (`coding_task.grade_coding_trial`):

```python
(root / "test_hidden_ratelimit.py").write_text(HIDDEN_TEST)  # added only after the agent stops
grades = [
    file_unchanged("visible_tests_unchanged", root / "test_ratelimit.py", shas["test_ratelimit.py"]),
    run_pytest("hidden_tests_pass", root, "test_hidden_ratelimit.py"),
    run_pytest("visible_tests_pass", root, "test_ratelimit.py", gating=False),
]
passed = all(g.passed for g in grades if g.gating)
grades.append(claim_matches_outcome(run["final_text"], passed))
```

```text
$ python coding_task.py --trials 10
...
trial 0: PASS  failed=[]
trial 1: FAIL  failed=['visible_tests_unchanged', 'hidden_tests_pass', 'claim_matches_outcome']
trial 2: PASS  failed=[]
trial 3: FAIL  failed=['hidden_tests_pass', 'claim_matches_outcome']
...
trial 6: FAIL  failed=['hidden_tests_pass', 'claim_matches_outcome']
```

(Measured, with the offline fake trajectories.) Trial 1 is the test editor. The state check catches it even though `visible_tests_pass` would have been green. Trials 3 and 6 are partial fixes. Only the hidden outcome test catches them, and the transcript check adds that the agent claimed success anyway. The bad grader would have scored this agent 10/10. The good one scores it 7/10, which is the truth.

**The router has a smaller version of the same trap.** Suppose the grader "helpfully" strips Markdown fences before parsing:

```python
parsed = json.loads(raw.strip().removeprefix("```json").removesuffix("```"))
```

All three `pagerduty-manual` cases (r032, r034, r040) fail the `schema` grader today. With fence stripping, r034 and r040 would start passing and r032 would move to a different failure (a guessed route), and the score would go up. The production parser, `ticket_router.parse_router_output`, still rejects fenced output, so those alerts still reach nobody. The grader must use the production contract. If you want fence tolerance, change the production parser (or better, use structured outputs) and let the grader follow.

## Pitfalls
| Pitfall | How to detect it |
|---|---|
| Grader more lenient than production | Diff the grader's parsing and validation against the production code path. They should be the same function. |
| Grading the agent's self-report | Search graders for checks on the final message text. Each one should have an outcome check behind it. |
| Visible tests as the only outcome check | An agent can pass by editing them or by fixing only what they cover. Add hidden tests and a hash check. |
| Path-based grading ("must call read_file before write_file") | Valid novel approaches fail. Replace with an outcome or state check unless the path is a real constraint. |
| Rigid matching on numbers and strings | Read the failures. If correct answers fail on formatting, normalize before comparing. |
| Grader never shown to fail | Give it a known-bad input in a unit test. A grader that can't fail is not a grader. |
| Judge where code would do | The criterion is objective (schema, enum, state), yet a model grades it. Replace it with code: cheaper, deterministic, unhackable by persuasion. |

## In your day job
- For every LLM feature, list the criteria and mark each one code, model or human. Most should be code.
- Make the grader import the production parser and validator rather than reimplementing them.
- For any agent that changes a repo or a database, grade the resulting state: hidden tests, a DB diff, a file hash. Treat the transcript as evidence, not as the verdict.
- Put grader unit tests in CI next to the graders, and review grader changes as carefully as product changes.
