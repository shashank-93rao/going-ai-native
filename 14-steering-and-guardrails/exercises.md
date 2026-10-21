# Exercises

Offline exercises use only this module's code and `FakeClient`. Exercises marked **[API]** need `ANTHROPIC_API_KEY`, and **[agent]** ones need Claude Code on a real repo.

---

## 1. Install the guardrails and prove they can fail (offline + agent, 45 min)

**Goal:** wire the hooks into a real repository and show each guardrail blocks the thing it claims to block.

**Steps**
1. In a scratch repo with a small Python package and tests, copy `code/hooks/*.py` and `code/drift_monitor.py` into `.claude/hooks/`, and `code/settings.example.json` to `.claude/settings.json`. Add `.claude/state/` to `.gitignore`.
2. Seed a bug that makes one test fail. Commit.
3. Without starting an agent, pipe hand-written events into each hook (`echo '{...}' | python3 .claude/hooks/stop_gate.py`):
   - Stop with the bug present.
   - Stop after weakening the failing assertion (`==` to `>=`).
   - Stop after adding `@pytest.mark.skip` instead.
   - PreToolUse with `git push --force origin main`, `git -C . push --force origin main`, and `pytest -k 'not test_x'`.
   - PreToolUse with an `Edit` on `.claude/hooks/stop_gate.py`.
4. Start Claude Code in the repo and ask it to "make the tests pass". Watch what it tries.

**Done when**
- Every case in step 3 produces a block or deny, with a reason that names the problem.
- After fixing the bug for real, a Stop event produces no output, and `.claude/state/stop_gate/<session>.json` is `{}`.
- You have a short log of what the agent in step 4 tried, and which hook (if any) fired.

**Stretch:** set `STOP_GATE_CMD` to a command that doesn't exist and confirm the gate halts with `continue: false` instead of looping.

---

## 2. Mutation-test the tamper check (offline, 45 min)

**Goal:** find tampering patterns `test_tamper_check.py` misses, and close the gap.

**Steps**
1. Write at least six new tampering diffs as test cases in a new file `test_tamper_mutations.py`. Ideas: wrapping an assertion in `if False:`; `assert x == x`; replacing the expected value with the actual call (`assert f(2) == f(2)`); `with contextlib.suppress(AssertionError):`; a retry loop around an assertion; `pytest.mark.flaky(reruns=5)`; Go `if testing.Short() { t.SkipNow() }`; Jest `expect(x).toBeDefined()` replacing `toEqual(…)`.
2. Run them. For each miss, decide whether to add a rule or document it as out of scope.
3. Add rules for at least three misses, keeping all existing tests green.
4. Add two *non*-tampering diffs that a naive rule would flag, such as a strengthened assertion or a renamed test, and make sure they stay clean.

**Done when**
- `test_tamper_mutations.py` has 8 or more cases and passes.
- Your false-positive cases pass (no findings).
- The module's full test suite still passes.

**Stretch:** add a rule that flags assertions whose expected side is computed by the code under test. That's the tautology pattern from [Module 13](../13-testing-agentic-systems/README.md).

---

## 3. Feedback vs blind retry, measured (API, 60 min)

**Goal:** measure whether validator feedback actually beats re-sampling on your inputs.

**Steps**
1. Collect 30 varied alert texts. Write them yourself or adapt real ones with secrets scrubbed. Include 5 that are deliberately ambiguous (no clear category).
2. Use `RecordingClient` to record runs of `repair_loop(..., feedback=True)` and `repair_loop(..., feedback=False)` with `max_attempts=3` on each input.
3. For each arm, compute first-pass validity, final validity, mean attempts, `no_progress` rate, and total output tokens.
4. Hand-label the final outputs of both arms for correctness of `category`.

**Done when**
- You have a table with both arms and all five metrics, plus correctness.
- You can say whether feedback helped *validity*, *correctness*, both or neither, citing the numbers, and with a caveat that 30 samples gives wide error bars ([Module 12](../12-hill-climbing/README.md)).
- Cassettes are saved so the comparison replays offline with `ReplayClient`.

**Stretch:** send the same schema via `output_config.format` (direct SDK call) and add a third arm. Which errors disappear, and which remain?

---

## 4. `/goal` vs Stop gate on the same task (agent, 45 min)

**Goal:** see the difference between a model-judged condition and a deterministic gate.

**Steps**
1. Pick a mechanical task in a real repo (rename a function across call sites, or bump a library and fix the breakages).
2. Run 1: `/goal <condition with a check, a constraint, and "or stop after 15 turns">` and no Stop gate. Press Ctrl+O to read each evaluator reason.
3. Run 2, from the same commit: the same `/goal` plus `stop_gate.py` with the matching oracle.
4. Compare turns, tokens (from `/goal` status), and whether the final state actually satisfies the condition according to `git diff` and a fresh test run.

**Done when**
- You've recorded at least one evaluator reason that was judged from the agent's *claims*, not from shown output, or you can say confidently that none was.
- You have a two-row comparison table: turns, tokens, condition truly met (yes/no).

---

## 5. Bypass audit of your permission rules (offline, 30 min)

**Goal:** turn deny rules from wishful thinking into known coverage.

**Steps**
1. List every `deny` and `ask` rule in your real `.claude/settings.json` (or the example's).
2. For each one, write three alternative spellings that do the same thing (absolute path, `sh -c`, git global options, a different tool).
3. Check each spelling against `pre_tool_guard.decide()` in a Python REPL.
4. For each spelling that gets through and matters, either extend the guard (with a test) or decide it belongs to the sandbox ([Module 16](../16-security-and-containment/README.md)) and write that down.

**Done when**
- You have a table of rule × spelling × caught-by (rule / guard / nothing).
- Every "nothing" row has an owner: a new guard rule with a passing test, or a sandbox control.

---

## 6. Bind approvals to the exact action (offline, 60 min)

**Goal:** implement the two-phase approval from [06](06-human-in-the-loop.md) so that an approval can't be reused for a modified command.

**Steps**
1. Add an approval store to `pre_tool_guard.py`. For T2 rules, compute `sha256(tool_name + json.dumps(tool_input, sort_keys=True))`, and if `.agent/approvals/<sha>.json` exists with `"approved": true` and `"used": false`, return no decision (let it run) and mark it used. Otherwise deny with a reason telling the agent to file a request at `.agent/requests/<sha>.json` with `why`, `evidence`, `blast_radius`, `rollback` and `if_no_answer`.
2. Protect `.agent/approvals/` in `PROTECTED_PATHS`, so only a human writes there.
3. Write tests: an approved exact command runs once; a second run is denied (used); a command differing by one flag is denied; an Edit on the approvals dir is denied.

**Done when**
- All four tests pass along with the existing suite.
- The deny reason for an unapproved T2 command tells the agent exactly what to write and where.

**Stretch:** add expiry (`if_no_answer` timeout) and a test for it with an injected clock.

---

## 7. Calibrate the drift monitor on your own history (offline, 45 min)

**Goal:** set thresholds from data, not from intuition.

**Steps**
1. Pick 10 recent agent-authored PRs (or human ones, if you have none). For each, write the `plan.json` you *would* have written from the ticket.
2. Run `drift_monitor.py --plan ... --diff <(git diff base...pr)` on each.
3. Label each flag by hand: real drift or false positive.
4. Adjust `max_changed_lines` and the scope-creep threshold, and add exclusions (generated files, lockfiles) until the false positives are under about 1 in 5 without losing a real drift you labeled.

**Done when**
- You have a labeled table: PR, flags, true/false positive.
- You've committed a tuned plan template and threshold values with a one-paragraph justification.

---

## 8. Rewrite three nudges (agent, 30 min)

**Goal:** practice turning corrections into specs.

**Steps**
1. Take these real-world-style nudges: *"that's not what I meant"*, *"you broke the build, fix it"*, *"stop over-engineering this"*.
2. For a task in your repo where each might be said, rewrite each as evidence + constraint + check + exit condition ([04](04-mid-run-steering.md)).
3. Try both versions on the same task from the same checkpoint (Esc Esc to rewind between attempts).

**Done when**
- For each pair, you've recorded the number of turns to a passing check and the diff size.
- At least one rewrite includes an explicit "stop and tell me if..." exit that the agent used, or you've noted why it wasn't needed.
