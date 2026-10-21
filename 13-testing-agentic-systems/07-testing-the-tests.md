# 07: Testing the tests

## The idea
Everything in this module rests on checks: `promotion_allowed`, `check_claim_matches_state`, `world.violations()`, the codex-trace regexes. A check that can't fail is worse than no check, because it produces green builds that people trust. Three techniques test the tests:

1. **Mutation testing.** Make small, plausible bugs in the code under test (flip `==` to `!=`, swap `and` for `or`, invert a boolean) and run the suite against each mutant. A suite that still passes on a mutant hasn't constrained that piece of logic. The **mutation score** is killed / total.
2. **Tautology detection.** Statically flag tests that can't fail by construction: no assertion, `assert x == x`, `assert ... or True`, asserting a mock returns what the test configured, type-only assertions, swallowed exceptions.
3. **Negative controls.** For every check, keep at least one known-bad input it *must* reject: a bad trajectory, a negative-control prompt, a label-changing transform. Then run the check against it in CI.

This matters more in an AI-native codebase, because more and more of the tests are written by agents, and agents are good at producing tests that pass.

## Why it matters
Agent-written tests have a typical failure mode. Asked to "add tests", a coding agent reads the implementation and writes tests that mirror it. Expected values come from calling the code under test, assertions check types rather than values, and a test that would fail gets "fixed" by weakening the assertion. OpenAI's current prompt guidance warns that its newest models over-test, and tells them not to write tests for reversible, low-impact changes that mirror the implementation ([OpenAI prompt guidance](https://developers.openai.com/api/docs/guides/prompt-guidance)). Spotify's background-agent judge checks diffs against the prompt in part to catch overreach such as disabled flaky tests ([Spotify, Honk part 3](https://engineering.atspotify.com/2025/12/feedback-loops-background-coding-agents-part-3)).

The graders in evals have the same problem. Anthropic reports Opus 4.5 scoring 42% on CORE-Bench and 95% once grader and scaffold bugs were fixed (rigid numeric matching rejected "96.12"). It also reports that the last step on its claude-api skill eval, from 80% to 87.9%, came from fixing broken graders ([Anthropic, "Demystifying evals"](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents); [Claude blog, "Automating eval design and hillclimbing"](https://claude.dev/blog/automating-eval-design-and-hillclimbing/)). Those are false negatives. Tautological checks give false positives, which are worse, because nobody investigates a green run.

## How it works

### Mutation testing a trajectory check (`mutation_demo.py`)
The target is the guard that decides whether a prod deploy was preceded by a verified-healthy staging:

```python
def promotion_allowed(steps_before, version):
    verified = False
    for s in steps_before:
        env = s.args.get("env")
        if s.tool == "deploy" and env == "staging" and s.result.get("ok"):
            verified = False  # a new rollout invalidates any earlier verification
        if s.tool == "get_status" and env == "staging":
            verified = s.result.get("version") == version and bool(s.result.get("healthy"))
    return verified
```

`mutants()` parses its source with `ast`, applies one mutation at a time (`Eq↔NotEq`, `And↔Or`, `True↔False`), compiles each mutant, and returns it. `mutation_score(suite)` first checks that the suite passes on the original. A suite that fails on correct code is broken, not strict. Then it counts kills. For real codebases, use a maintained tool (mutmut or cosmic-ray for Python, PIT for the JVM). The mini version exists to make the mechanism visible.

### Linting for tautologies (`tautology_lint.py`)
It's AST-based. Each rule has a fix hint that can be fed straight back to the agent as a lint error ([Module 08](../08-harness-engineering/README.md) on lints that explain how to fix the error):

```text
test_promotion_allowed_runs:10: no_assertion  -> assert on an observable outcome (world state, return value), not just that it ran
test_promotion_allowed_returns_bool:15: type_only  -> add an assertion on the value itself, and a negative case that must fail
test_promotion_allowed_is_consistent:22: self_comparison  -> compare against an expected value written from the spec, not recomputed by the code
test_deploy_client_called:28: mock_echo  -> assert on what the code under test DID with the mock, not what the mock returns
test_handles_errors:34: swallowed_exception  -> use pytest.raises, or let the exception fail the test
test_happy_path:39: always_true  -> remove `or True`; the assertion can never fail
```

The linter has its own negative control. `test_lint_negative_control_on_this_modules_real_tests` asserts that it reports *nothing* on this module's real test files. A linter that flags good tests teaches people to ignore it.

### Negative controls everywhere
| Check | Its negative control in this module |
|---|---|
| Each trajectory assertion | A policy flag that injects exactly that bug (`test_negative_controls_each_bug_is_caught_by_its_check`) |
| `world.violations()` | `skip_staging`, `delete_prod_first`, `new_id_on_retry` under ack loss |
| Skill trigger eval | `should_trigger=false` CSV row with a zero-mutation check (`deploy-03`) |
| User-sim audit | A leaky, bossy simulated user (`test_audit_flags_leaky_and_bossy_user_sim`) |
| Metamorphic relation | The brittle classifier, which Hypothesis must break |
| Property test | `find()` must locate the retry bug |
| Mutation suite | The suite must pass on the original first |

*Course synthesis:* this is Huntley's "write the oracle first and prove it can fail" ([Module 07](../07-loops/README.md)) applied to every layer of the test stack.

## Worked example: the agent-written suite vs the spec suite
You ask a coding agent to "write tests for `promotion_allowed`". It writes the equivalent of `agent_written_suite`:

```python
def agent_written_suite(guard):
    steps = [DEPLOY_OK, HEALTHY]
    return [
        isinstance(guard(steps, "v2.4.0"), bool),
        guard(steps, "v2.4.0") == guard(list(steps), "v2.4.0"),
        guard(steps, "v2.4.0") == trajectory_checks.promotion_allowed(steps, "v2.4.0") or True,
    ]
```
All green, with three tests for one function. Run the mutation score:

```text
agent-written suite: killed 0/10 mutants (0%)
    survived: line 4: False -> True
    survived: line 7: Eq -> NotEq
    survived: line 7: And -> Or
    ...
```
Every mutant survives, including `verified = True` as the initial value, which approves every promotion. The suite would stay green if the guard were deleted and replaced with `return True`.

**The spec suite** is derived from the rule, not from the code, and most of its cases are negative controls:

```python
def spec_suite(guard):
    return [
        guard([DEPLOY_OK, HEALTHY], "v2.4.0") is True,
        guard([DEPLOY_OK], "v2.4.0") is False,                                   # never verified
        guard([DEPLOY_OK, S("get_status", "staging", version="v2.4.0", healthy=False)], "v2.4.0") is False,
        guard([DEPLOY_OK, S("get_status", "staging", version="v2.3.0", healthy=True)], "v2.4.0") is False,
        guard([HEALTHY, DEPLOY_OK], "v2.4.0") is False,                          # verified, then a new rollout
        guard([DEPLOY_OK, S("get_status", "prod", version="v2.4.0", healthy=True)], "v2.4.0") is False,
        guard([], "v2.4.0") is False,
    ]
```

Its first run scored **9/10**. The survivor was `line 7: And -> Or`. With `or`, *any* staging step (even `get_logs`) resets verification. None of the seven cases had a harmless staging step after verification, so the suite couldn't tell the difference. That survivor is a missing test, and it would be a real bug: an agent that reads logs after verifying would be blocked from promoting. One case kills it:

```python
guard([DEPLOY_OK, HEALTHY, S("get_logs", "staging", lines=[])], "v2.4.0") is True,
```
```text
spec suite: killed 10/10 mutants (100%)
```

Reading survivors this way is the most useful habit in this file. Each surviving mutant is either a missing test case or dead code.

## Pitfalls
- **Chasing 100% on everything.** Some mutants are *equivalent*: they don't change behavior, so nothing can kill them. *Detect:* when a survivor resists a sensible test for 10 minutes, check whether it's equivalent and mark it.
- **Asking the same agent to write the tests and fix the code.** It will reconcile them by weakening one of the two. *Detect:* diffs where a test's expected value changed in the same commit as the implementation. Route those to a human, or give a clean-context reviewer agent only the spec and the tests ([Module 06](../06-agent-architectures/README.md)).
- **Tests derived from the implementation.** *Detect:* expected values computed by calling the function under test (the `self_comparison` rule), or test names that paraphrase the code ("returns verified variable").
- **Checks without negative controls.** *Detect:* for each check function, grep the tests for a case where it returns False or fails. None means it's untested.
- **Lint as gatekeeper with no escape hatch.** Heuristics have false positives. *Detect:* track overrides. If a rule is overridden more than it fires correctly, fix or drop it.

## In your day job
- Run mutmut or cosmic-ray on your agent's check and grader functions (not the whole codebase) and read every survivor.
- Add `tautology_lint.py` (or the equivalent rules in your linter) to CI for test files in agent-authored diffs, with fix hints the agent can act on.
- For every grader, trajectory check, or Stop-hook verifier, add one known-bad input to CI that it must reject.
- When you delegate test writing to an agent, give it the spec (SPEC.md, acceptance criteria) and not the implementation, and ask for negative cases first ([Module 04](../04-agentic-coding-workflows/README.md)).
