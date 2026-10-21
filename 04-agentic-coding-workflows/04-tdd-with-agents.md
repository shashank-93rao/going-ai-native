# 04: TDD with agents (augmented coding)

## The idea

Test-driven development is the strongest single technique for agentic coding, because it gives the agent an oracle *before* it writes the code that oracle judges. Simon Willison: "Test-first development is particularly effective with agents that can iterate in a loop." His version is **red/green**: write the tests, *confirm they fail*, then implement ([Willison, Agentic Engineering Patterns, "Red/green TDD"](https://simonwillison.net/guides/agentic-engineering-patterns/red-green-tdd/)).

Kent Beck's "augmented coding" is the most complete public description of TDD with an agent. He separates it from vibe coding: "In vibe coding you don't care about the code, just the behavior of the system. In augmented coding you care about the code, its complexity, the tests, & their coverage." ([Beck, "Augmented Coding: Beyond the Vibes"](https://newsletter.kentbeck.com/p/augmented-coding-beyond-the-vibes), 2025-06-25)

His setup has three parts:

1. A **plan.md listing tests**, one per line, unmarked until done.
2. A **system prompt** that encodes the discipline. Excerpts, verbatim: "When I say "go", find the next unmarked test in plan.md, implement the test, implement only enough code to make that test pass." "Always follow the TDD cycle: Red → Green → Refactor." "Never mix structural and behavioral changes in the same commit." Commit only when "ALL tests are passing" and "ALL compiler/linter warnings have been resolved."
3. A **human watching for three warning signs** that "the genie" is going off track:
   - "Loops."
   - "Functionality I hadn't asked for (even if it was a reasonable next step)."
   - "Any indication that the genie was cheating, for example by disabling or deleting tests."

## Why it matters

When you hand an agent an existing failing test, it optimizes for making *that test* pass. When the agent writes its own tests after the code, they tend to confirm whatever the code does. Both failure modes are well documented:

- Anthropic's prompting guide includes an anti-hardcoding instruction because models will otherwise special-case test inputs: "Do not hard-code values or create solutions that only work for specific test inputs... Tests are there to verify correctness, not to define the solution... If the task is unreasonable or infeasible, or if any of the tests are incorrect, please inform me rather than working around them." ([Anthropic, "Prompting best practices"](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices))
- OpenAI's current model guidance warns the other way, that the model over-tests: "Do not write tests for reversible, low-impact changes that mirror the implementation." ([OpenAI, prompt guidance](https://developers.openai.com/api/docs/guides/prompt-guidance))
- Carlini's 16-agent C compiler run: "For autonomous systems, it is easy to see tests pass and assume the job is done, when this is rarely the case" ([Anthropic, "Building a C compiler with a team of parallel Claudes"](https://www.anthropic.com/engineering/building-c-compiler)).

TDD's ordering defeats both. A test written and *seen to fail* before the implementation exists can't be a mirror of that implementation. The red step is the proof that the oracle can fail, which [Module 07](../07-loops/README.md) treats as the first rule of oracle design.

## How to do it

### 1. Separate who writes the tests from who writes the code

The strongest version keeps the test author out of the implementation context. The Claude Code docs suggest it directly: "have one Claude write tests, then another write code to pass them" ([docs, Writer/Reviewer pattern](https://code.claude.com/docs/en/best-practices)). In practice you have three options:

| Test author | Strength | Cost |
|---|---|---|
| You | Strongest. Tests encode your intent | Your time, and the tests are your bottleneck |
| Session A (from SPEC.md only), implementation in session B | Strong. B can't shape tests around its code | Two sessions |
| Same session, red step enforced | Acceptable for small units | Weakest. Watch for cheating |

### 2. Make red observable

```text
Write the tests listed under Phase 1 in plan.md. Do not write implementation code.
Run them and show me the output. Every new test must FAIL, and for the reason in its
docstring (e.g. "404 because the endpoint does not exist", not ImportError).
```

The parenthetical matters. A test that fails with `ImportError` or `NameError` has proved nothing about behaviour.

### 3. Lock the tests during green

Instructions are advisory and hooks are deterministic: "Unlike CLAUDE.md instructions which are advisory, hooks are deterministic and guarantee the action happens" ([docs](https://code.claude.com/docs/en/best-practices)). Put Beck's "cheating" warning sign into a `PreToolUse` hook that blocks edits to test files while a marker file says you're in the green phase.

`.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          { "type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/protect-tests.sh" }
        ]
      }
    ]
  }
}
```

`.claude/hooks/protect-tests.sh`:

```bash
#!/usr/bin/env bash
# Block edits to test files while .claude/tdd-phase contains "green".
# Exit 2 blocks the tool call; stderr is shown to Claude as the reason.
phase_file="$CLAUDE_PROJECT_DIR/.claude/tdd-phase"
[ "$(cat "$phase_file" 2>/dev/null)" = "green" ] || exit 0
path=$(jq -r '.tool_input.file_path // empty')
case "$path" in
  *_test.go|*/tests/*|*/test_*.py|*Test.java|*IT.java)
    echo "Blocked: $path is a test file and we are in the GREEN phase. Change the implementation, not the test. If the test is wrong, stop and say so." >&2
    exit 2 ;;
esac
exit 0
```

`echo green > .claude/tdd-phase` before you say "go", and `echo red` when you move on to writing the next tests. The exit-2-plus-stderr contract follows the hooks guide (read 2026-10-19). This blocks only the agent's Edit and Write tools, not `sed` through Bash, so pair it with the diff check in [07](07-reviewing-ai-code-and-when-not-to-delegate.md) (`tautology_lint.py --diff`).

### 4. Watch for the warning signs as a rubric

| Beck's sign | What it looks like in a transcript | Response |
|---|---|---|
| Loops | The same edit/revert of one function three times; the same failing test after each "fix" | Stop. `/clear`. Give the failure output plus a hypothesis, or take the step yourself |
| Unrequested functionality | New flags, config options, "also handles X" | Revert the extra, and add it to Non-goals in the spec |
| Cheating | `@Disabled`, `t.Skip()`, `pytest.mark.skip`, weakened asserts, a test file in the diff during green | Revert. Tighten the hook. Restate the anti-hardcoding instruction |

Beck also shows a recovery move: when Rust's ownership model kept the agent stuck in complexity, he had it write the solution in Python first, then transliterate it.

## Worked example: a token-bucket limiter, test first

**The bad version.**

```text
implement a token bucket rate limiter in internal/ratelimit with tests
```

*(Illustrative output.)* The agent writes `bucket.go` first, then `bucket_test.go`:

```go
func TestBucket_Refill(t *testing.T) {
    b := NewBucket(10, time.Second)
    for i := 0; i < 10; i++ { b.Allow() }
    time.Sleep(1100 * time.Millisecond)
    want := b.tokensAt(time.Now()) // computes expected via the implementation's own helper
    if got := b.Tokens(); got != want { t.Fatalf("got %v want %v", got, want) }
}
```

This test can't catch a refill-rate bug: the expected value comes from the code under test. That is the pattern [code/tautology_lint.py](code/tautology_lint.py) flags as `oracle-from-impl` (the linter reads Python, but the pattern is the same in Go). It also sleeps on the wall clock, so it's slow and flaky under CI load.

**The good version.** plan.md lists the tests first, Beck-style:

```markdown
## Tests (implement one at a time on "go")
- [ ] empty bucket after `capacity` Allow() calls at t0
- [ ] one token available after exactly 1/rate seconds (fake clock), none at 1/rate - 1ns
- [ ] tokens never exceed capacity after a long idle period (fake clock +1h)
- [ ] concurrent Allow() from 100 goroutines admits exactly `capacity` at t0 (-race)
- [ ] Allow() on a bucket created with rate=0 always false (no division by zero)
```

Red step, prompt and output *(illustrative output)*:

```text
> write only the first two tests, using a Clock interface I will inject. run them.
--- FAIL: TestBucket_EmptyAfterCapacity (0.00s)  bucket_test.go:21: Allow() #11 = true, want false
--- FAIL: TestBucket_RefillBoundary (0.00s)      bucket_test.go:34: at t0+100ms-1ns Allow() = true, want false
```

Both fail for behavioural reasons: the stub returns `true`. Now `echo green > .claude/tdd-phase` and "go". The agent implements the minimum to pass. Then repeat for the next tests. The concurrency test is the one most likely to expose a real bug (a non-atomic read-modify-write of `tokens`), and it exists before the code does.

**Why the second version works.** Expected values are literals derived from the spec (capacity, 1/rate), time is injected rather than slept, and every test was seen failing for a behavioural reason. The hook makes "fix the test instead of the code" impossible through the edit tools.

## Pitfalls

| Pitfall | How to detect it |
|---|---|
| Red for the wrong reason | Failure output shows `ImportError`, `undefined:`, a compile error or a missing fixture. Require the reason to match the docstring. |
| Tests written after code, labelled TDD | Commit order: the test file's first commit is not earlier than the implementation's. `git log --diff-filter=A -- '*_test.go'`. |
| Expected values computed by the SUT | `tautology_lint.py` flags `oracle-from-impl`. Use literals or an independent model (a reference implementation, or a property). |
| Agent "fixes" a failing test by editing it | Test files appear in the green-phase diff. Use the hook, plus `tautology_lint.py --diff`. |
| Over-testing trivial changes (newer models) | Many tests that restate the implementation for reversible, low-impact changes. Ask for tests of behaviour at boundaries, not of every line (OpenAI guidance). |
| Wall-clock tests | `time.Sleep`/`Thread.sleep` in tests. Inject a clock, or use polling with a timeout. |

## In your day job

- For any change with a crisp contract (limiters, parsers, state machines, idempotency logic), write or approve the test list in plan.md before the agent writes code.
- Install the `protect-tests.sh` hook in repos where you do agentic TDD, and toggle the phase file per cycle.
- Treat Beck's three warning signs as an interrupt condition, not a code-review note. Stop the session when you see one.
- Use property-based tests (Hypothesis, `testing/quick`, jqwik) for invariants like "charged at most once". They are much harder for an agent to game than example tests ([Module 13](../13-testing-agentic-systems/README.md)).
