# 07: Exercises

Offline exercises use the course `FakeClient` and need no key. Exercises marked **[API]** need `ANTHROPIC_API_KEY`, and those marked **[agent]** need a coding agent such as Claude Code. Run everything from the course root.

---

## 1. Read the loop by breaking it (offline, 30 min)

**Goal.** Know what each line of `run_agent` is for.

**Steps.**
1. Run `PYTHONPATH=shared .venv/bin/python 07-loops/code/agent_loop.py` and read the trace.
2. In a scratch copy of `agent_loop.py`, introduce each of these bugs one at a time, and run `pytest -q 07-loops/code/test_agent_loop.py` after each:
   - append the assistant turn once per tool call instead of once per response
   - return each tool_result in its own user message
   - let a `ToolError` propagate instead of returning `is_error`
   - treat `max_tokens` as success
3. For each bug, write down which test caught it, or that none did.

**Done when.** You have a 4-row table (bug, test that failed, what the real API would have done). For any bug no test caught, you've added a test that catches it.

**Stretch.** Add a `stop_reason == "refusal"` path that exits with a new typed code, and a test for it.

---

## 2. Prove your own oracle can fail (offline, 45 min)

**Goal.** Apply "write the oracle first and prove it can fail" to code you own.

**Steps.**
1. Pick a function from your day job with real logic: an idempotency-key check, a retry backoff, a pagination cursor. Copy it and its tests into a scratch workspace.
2. Write 5 mutants using `oracle.replace_in`: at least one off-by-one, one "always succeed", one deleted side effect, and one hard-coded return of the expected test value.
3. Run `prove_it_can_fail(PytestOracle([...]), workspace, mutants)`.
4. For every survivor, add the smallest test that kills it.

**Done when.** `prove_it_can_fail` returns `[]`, and you've committed a test that runs it, so a future weakening of the tests fails CI.

**Stretch.** Run a real mutation-testing tool (for example `mutmut`, if your environment allows installing it) and compare its survivors with yours.

---

## 3. Evade the governor, then close the gap (offline, 45 min)

**Goal.** Think like the runaway.

**Steps.**
1. Write a `FakeClient` responder that never makes progress but evades every current breaker in `governor.py`. Ideas: vary whitespace in an `edit_file` `old_str` so the signatures differ, cycle through 7 different files to beat a window of 6, or alternate one success with two failures so the error breaker never reaches 3.
2. Confirm it runs to `max_iterations` (or burns budget) in `run_agent`.
3. Extend `Governor` to catch it without breaking the existing tests. Options: normalise args before hashing, track per-file edit counts (like LangChain's `LoopDetectionMiddleware`), or use a ratio-based error breaker.
4. Add your responder to `test_agent_loop.py` as a regression test.

**Done when.** Your new test fails on the original `governor.py` and passes on yours, and all 55 existing tests still pass.

**Stretch.** Measure the false-positive rate: run `fixing_script()` and a version with 3x more legitimate `run_tests` calls, and confirm neither trips.

---

## 4. Does reflection pay? Measure it on a real model [API] (45 min, about $1)

**Goal.** Replace "reflection helps" with a number for one task.

**Steps.**
1. Create 30 cases for `self_correct.py`, with requirements that tempt a mistake (for example `"burst must equal 2x the hourly rate / 3600, rounded down"`).
2. Run `measure(lambda: get_client(), cases, max_rounds=2)` with a real key for both modes. Use the same cases for both.
3. Add a third mode: plain resampling, a fresh call with the original prompt each round and no feedback.
4. Report pass rate by round and mean tokens for all three modes.

**Done when.** You have a table with 3 modes × 3 rounds plus tokens, and a one-line decision ("cap at 1 round of external feedback") backed by it. If the differences are under about 10 points on 30 cases, say the result is inconclusive. [12-hill-climbing](../12-hill-climbing/README.md) explains why.

**Stretch.** Repeat on a second model or effort level and see whether the decision changes.

---

## 5. Ralph a real backlog [agent] (2–3 h including review)

**Goal.** Run a fresh-context loop unattended on real code, with the course governors.

**Steps.**
1. Pick a mechanical backlog in a repo you own: lint warnings in one package, `Optional` misuse, a deprecated API. Write the oracle as an error count plus the test suite, and prove it can fail (Exercise 2).
2. Write `specs/` (one file), `fix_plan.md` (10–20 items), and a `PROMPT.md` under 150 words.
3. Start a container or VM with only the network access the build needs, and no production credentials.
4. Run `ralph.py` with a real agent command, `--max-iterations 30 --max-hours 2`, and `--max-budget-usd` on the agent.
5. Review the result as a PR, by risk.

**Done when.** The run ended with a typed exit code, `.ralph/log.jsonl` shows $/kept-iteration, and you've written 5 lines on what you'd change in the spec, prompt or oracle before the next run. A `STALLED` exit with a clear reason counts as done.

**Stretch.** Run the same backlog with the official Stop-hook plugin (`/ralph-loop ... --max-iterations 30 --completion-promise "DONE"`) and compare keep-rate, cost and diff quality with the fresh-context run.

---

## 6. Make a scheduled agent idempotent (offline, 60 min)

**Goal.** Build the bookmark + ledger + "maybe posted" machinery and test it against late, early, duplicate and failed-read runs.

**Steps.**
1. Write `digest.py` with `run_digest(sources, ledger_path, post)`, where each source is a callable that returns items with stable ids, or raises.
2. Implement per-source bookmarks, a ledger keyed by id, check-then-post, and the posting / posted / maybe-posted states.
3. Write tests with a fake clock and fake sources for: a run 40 minutes late (no gap), two runs in quick succession (no duplicates), `post` raising a timeout after the message actually landed (no double post on the next run), and one source raising (bookmark not advanced, report says "unavailable").

**Done when.** All four tests pass, and you can explain each in terms of consumer offsets and an outbox.

**Stretch.** Wire `run_digest` into a real `/loop 30m` or a routine that posts to a test Slack channel.

---

## 7. Price a loop before you run it (offline or [API], 30 min)

**Goal.** Estimate, run, compare.

**Steps.**
1. For the Ralph run in Exercise 5 (or the toy task with a real key), run a 3–5 item pilot and record input, cached and output tokens and wall time per iteration.
2. Use the method in [08-loop-economics](08-loop-economics.md) to predict total cost and wall time for the full backlog, and set the governor limits from that prediction.
3. Run it, then compare actual against predicted.

**Done when.** You have predicted vs actual for cost, iterations and wall time, and the prediction was within 2x. If it wasn't, you've explained which assumption was wrong.

**Stretch.** Turn on (or deliberately break) prompt caching by changing the system prompt each iteration, and measure the cost difference.
