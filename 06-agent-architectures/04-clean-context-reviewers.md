# 04: Clean-context reviewer agents

## The idea

A **clean-context reviewer** is a separate model context whose entire input is the *spec* and the *artifact* (usually a diff). It has none of the author's conversation, none of its tool outputs, and none of its reasoning. Its output is findings, never edits. It is the cleanest example of a helper that "contributes intelligence rather than actions" ([Cognition, 2026](https://cognition.com/blog/multi-agents-working)), and the multi-agent pattern with the strongest published evidence.

Isolation is the point. A reviewer that continues the author's session inherits the author's framing, including every rationalisation the author produced along the way, and it inherits the long degraded context as well. A fresh reviewer has to reconstruct intent from the spec and check the diff against it, which is exactly the check you want.

## Why it matters

- **Cognition:** Devin Review catches an average of 2 bugs per Devin-written PR, about 58% of them severe (logic errors, missing edge cases, security issues). The technique works best "when the coding and review agents do not share any context beforehand", which the author attributes to the reviewer reasoning from the diff rather than from a long inherited context ([Cognition, "Multi-Agents: What's Actually Working"](https://cognition.com/blog/multi-agents-working)).
- **Anthropic's Claude Code team:** most review now happens before the PR, with a runnable check and its output followed by a fresh-context review subagent. At PR time, parallel bug-hunters produce candidates, verifier agents vote on each, and only consensus findings get posted. Style findings were dropped after an A/B test. Over the period described, merged PRs more than doubled while the revert share fell by more than 40% ([Anthropic, "How the Claude Code team does code review"](https://claude.dev/blog/solving-code-review-at-anthropic/)). These are reported numbers from one team, not a controlled study.
- **A related design in Claude Code's auto mode.** The permission classifier is deliberately *reasoning-blind*: it sees user messages and tool calls, never the agent's prose, so "the agent can't talk the classifier into making a bad call" ([Anthropic, auto mode](https://www.anthropic.com/engineering/claude-code-auto-mode)). Same principle: a check is independent only if the checked party can't shape its input.

The failure on the other side: Anthropic's best-practices doc warns that reviewers asked to find gaps *will* find some, and chasing every one leads to over-engineering ([Claude Code best practices](https://code.claude.com/docs/en/best-practices)). A reviewer without an evidence requirement and a severity filter turns into a nit generator.

> **Synthesis:** In distributed-systems terms, the reviewer is an independent validator. Its value comes from failure independence. Clean context gives you *input* independence. It does not give you *model* independence, since the same model family shares blind spots. For the highest-risk paths, vary the model as well as the context, or add a non-LLM check.

## How it works

Four rules, each enforced in code ([`code/reviewer.py`](code/reviewer.py)).

**1. Isolation by construction.** The function that builds the reviewer's request has no parameter that could carry the transcript.

```python
def build_review_request(spec: str, diff: str) -> list[dict]:
    """The whole context of the reviewer. Deliberately has no transcript parameter."""
    return [{"role": "user", "content": f"<spec>\n{spec}\n</spec>\n\n<diff>\n{diff}\n</diff>"}]
```

A test asserts it: `assert AUTHOR_TRANSCRIPT not in content`. With subagent tools, the equivalent is a *non-fork* subagent, which doesn't see conversation history. Claude Code's docs note that you then need to restate project rules in the delegation prompt ([Claude Code docs, subagents](https://code.claude.com/docs/en/sub-agents)).

**2. Report everything, filter in code.** Anthropic's Opus 5 guide says that review prompts asking to "only report high-severity issues" may be followed literally, so the model reports less. Ask for everything and filter in a separate pass ([Prompting Claude Opus 5](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5)).

```python
REVIEW_SYSTEM = ("You review a code change against its spec. You did not write it and have no other context. "
                 "Report every issue you find, including minor ones; a later step filters them. ...")
```

**3. Evidence or it didn't happen.** Every finding must quote a line that is actually in the diff, in a file the diff touches. This is the reviewer's groundedness gate.

```python
for f in findings:
    evidence = re.sub(r"^[+\- ]", "", f.evidence).strip()
    if f.file not in lines:                  dropped.append((f, "file not in diff"))
    elif evidence not in lines[f.file]:      dropped.append((f, "evidence not found in diff"))
    elif SEVERITY[f.severity] < SEVERITY[min_severity]: dropped.append((f, f"below {min_severity}"))
    else:                                    kept.append(f)
```

**4. Optional: k-of-n voting.** `vote_findings(results, k)` keeps a finding only if at least k independent reviews cite the same evidence line, one vote per reviewer. This is the Anthropic verifier-voting idea in about ten lines. It costs n reviews, so reserve it for high-risk tiers ([17-ai-native-engineer-and-team](../17-ai-native-engineer-and-team/README.md) covers risk tiers).

**Closing the loop, with bounds.** When findings go back to the author agent, two things stop ping-pong. First, the author filters findings against the user's instructions, since Cognition notes the need for a "communication bridge" so the coder can reject findings that contradict what the user asked. Second, cap review rounds (two is typical) and escalate to a human after that.

## Worked example: an at-least-once consumer change

**The spec** (`SPEC` in the code):

```text
consumer/handler.py processes the orders topic with AT-LEAST-ONCE semantics:
- an offset is committed only after store.apply() succeeded for that message
- TransientError is retried with backoff (max 5 attempts), never skipped
- store.apply() is idempotent on msg.key, so redelivery is safe
```

**The diff** the author agent produced:

```diff
     for msg in consumer:
-        store.apply(msg.value)
-        consumer.commit(msg)
+        consumer.commit(msg)
+        try:
+            store.apply(msg.value)
+        except TransientError:
+            log.warning("apply failed, skipping %s", msg.offset)
```

### Bad: "review your change" in the same session

The author's session contains this exchange:

```text
user: duplicates are hurting the dashboard
assistant: I'll commit before applying so a crash can't cause a redelivery. That removes duplicates.
```

Asking the same session to review (illustrative output):

```text
The change commits the offset before processing, which prevents redelivery after a crash and
addresses the duplicate problem. Error handling logs and continues, keeping the consumer live. LGTM.
```

The reviewer has adopted the author's goal (fewer duplicates) and lost the spec's goal (at-least-once). It is evaluating the diff against the conversation, not against the contract. The actual fix for duplicates, the idempotent `apply`, is already in the spec.

### Good: spec plus diff, nothing else

`python code/reviewer.py` runs the full pipeline. The model is replaced by a fake that returns two real findings, one hallucinated finding and one nit, which is the mix you should expect from real reviewers:

```text
KEEP [high] Offset is committed before apply; a crash after commit loses the message (at-most-once).
KEEP [high] TransientError is swallowed and the message skipped; spec requires retry with backoff.
DROP (evidence not found in diff) store.flush() is no longer called after apply.
DROP (below medium) Log message should start with a capital letter.
```

What the code did, as opposed to the model:
- Cited `store.flush()`, which appears nowhere in the diff, so the evidence gate removed it. Without that gate, the author agent would "fix" a non-issue by adding a `flush()` call.
- Filtered the nit by severity in code. Rerun with `min_severity="nit"` and it comes back. The prompt never told the model to hold back.

## Pitfalls

- **Leaky isolation.** A "fresh" subagent that receives a summary of the author's reasoning is not clean, because the summary carries the framing. Detect it by grepping the reviewer's actual request in traces for author-session content.
- **No spec.** A reviewer given only a diff reviews for generic quality, which means style. Detect it when finding categories are dominated by naming and formatting. Fix it by always passing the spec or plan.
- **Findings without evidence.** Detect it by measuring the drop rate of the evidence gate. If it is 0%, you are probably not checking. If it is above 30%, the reviewer prompt or model needs work.
- **Infinite author-reviewer loops.** Detect it with a round counter per PR. More than two rounds is a signal to escalate, not to iterate.
- **Correlated reviewer and author.** The same model with the same blind spots. Detect it by seeding known bugs and measuring the reviewer's recall. For critical paths, add a different model or a deterministic check: a property test, a linter rule, or a type.
- **Promoting repeat findings to review prompts.** If the reviewer catches the same class of bug every week, fix it at the source with a lint rule, a CLAUDE.md line, or a REVIEW.md entry, as the Claude Code team describes.

## In your day job

- Add one reviewer subagent with `build_review_request(spec, diff)` semantics to your agent PR flow before adding anything else multi-agent.
- Store the reviewer's raw findings and the dropped-with-reason list in the PR trace. The drop reasons are your reviewer's eval data ([10-evals-fundamentals](../10-evals-fundamentals/README.md)).
- Seed five known bugs from past incidents (commit-before-process, missing retry, off-by-one window) and measure the reviewer's recall on each model upgrade.
- Write a REVIEW.md with what failure looks like in your service. Pass it as part of the spec, not as a "be strict" instruction.
