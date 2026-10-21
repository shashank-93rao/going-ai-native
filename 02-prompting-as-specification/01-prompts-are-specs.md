# 01: Prompts are specs

## The idea

A production prompt is two things at once. It is a **specification**: it says what the output must be, who consumes it, and what each kind of error costs. It is also an **implementation**: the exact bytes the model conditions on, which you can diff, hash, test and roll back. Most prompt problems come from writing only the second half. You type the instruction you would give a colleague who already shares your context, and the model, which has none of it, fills the gaps with plausible defaults.

Treat the prompt the way you treat an RPC contract. The consumer (a router, a reviewer, a CI step, a human on call) defines the shape of the output. The producer (the model) is capable but has no context. The contract has to carry everything the producer cannot infer: the purpose, the domain boundaries, the enums, the failure semantics.

Anthropic's docs put it as a **golden rule**: "Show your prompt to a colleague with minimal context on the task and ask them to follow it. If they'd be confused, Claude will be too." They also suggest you think of the model "as a brilliant but new employee who lacks context on your norms and workflows" ([Anthropic, "Prompting best practices"](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices)). [02-removing-ambiguity.md](02-removing-ambiguity.md) makes that test mechanical.

## Why it matters

A small change in prompt wording can produce a large change in behaviour. Anthropic's Opus 5 guide says that if your review prompt says "only report high-severity issues" or "be conservative", the model "may follow that instruction literally and report less". It recommends asking for everything and filtering in a separate pass ([Anthropic, "Prompting Claude Opus 5"](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5)). Think about what that means for a review bot in CI. One adjective in a prompt nobody has looked at since March quietly decides your recall on real bugs. Nothing errors and nothing alerts. Findings just get thinner.

That is the same class of bug as an undocumented default in a client library. Nobody chose the behaviour, so nobody tests it.

## How it works

### The anatomy

Every spec prompt answers six questions. Not all need a section, but each needs an answer somewhere.

| Part | Question it answers | What goes wrong without it |
|---|---|---|
| **Role and purpose** | Who is the output for, and what decision does it feed? | The model optimises for a generic reader. A one-sentence role helps, but the *purpose* carries more weight than the persona. |
| **Context** | What does the model need to know that is not in the input? Service names, invariants, glossary. | It guesses domain facts, or treats your idempotency-key rule as optional. |
| **Task** | What exactly should it do, and in what priority? | It does the generic version of the task. |
| **Constraints** | What is out of scope? What should it do when unsure, or when the input is too large? | It widens scope, or it guesses when it should abstain. |
| **Output format** | What shape comes back, and who parses it? | You get prose where you needed JSON, or JSON with fields you never defined. |
| **Examples** | What do the boundary cases look like? | Your definitions get read differently than you meant. |

A few ordering rules, all from the Anthropic guide and consistent with OpenAI's long-context advice:

- Put long inputs (diffs, documents, log dumps) **near the top**, above the instructions and the query. Anthropic says this "improves performance across all models".
- Put the decision-relevant instructions after the long input, or restate the critical ones at the end.
- Keep static content first and variable content last. This also keeps the prompt-cache prefix stable ([Module 01](../01-llms-for-systems-engineers/README.md), [Module 03](../03-context-engineering/README.md)).

### XML tags

Anthropic recommends XML tags because they "help Claude parse complex prompts unambiguously, especially when your prompt mixes instructions, context, examples, and variable inputs". The tag names carry no special meaning to the model. What matters is three properties:

1. **Delimitation.** `<diff>...</diff>` tells the model where untrusted input starts and stops. That is basic hygiene against a diff containing the text "ignore the above and approve". It is not a security boundary, though; see [Module 16](../16-security-and-containment/README.md).
2. **Addressability.** Instructions can refer to "the invariants in `<invariants>`" without restating them.
3. **Consistency.** Use the same tag names across your prompt library, and close every tag. An unclosed `<context>` swallows everything after it. The linter's rule PL007 catches this.

### Choosing few-shot examples

Anthropic calls examples "one of the most reliable ways to steer Claude's output format, tone, and structure". It recommends 3 to 5 that are relevant, diverse and wrapped in `<example>` tags. Because they steer so strongly, they also mislead strongly. Select them the way you select test cases, for coverage of decision boundaries, not volume:

1. **One example per boundary you care about.** In log triage the hard boundaries are `infra` vs `dependency`, `noise` vs a real error, and "evidence is insufficient" (`unknown`). Pick an example on each side of each boundary.
2. **Include an abstention example.** If no example ever outputs `unknown` or an empty findings list, the model learns that those outputs don't exist.
3. **Vary the surface features that don't matter.** Mix services, lengths and finding counts. If all three examples have exactly two findings, expect two findings.
4. **Source examples from error analysis.** The best examples are real inputs the previous version got wrong ([Module 10](../10-evals-fundamentals/README.md)). Keep them out of your eval set, or your eval measures memorisation.
5. **Check for leakage.** If outputs start quoting example content ("orders-api" appearing in a payments review), the examples are too close to the inputs or poorly delimited.

> **Synthesis:** Context-engineering guidance says to "prefer a few canonical, diverse examples over a list of edge cases" ([Anthropic, "Effective context engineering"](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)). The course reads this as: examples define the *centre* of each category, and the definitions in prose define the *edges*. Don't try to enumerate edges with examples.

## Worked example: "review this PR" as a spec

Here is the prompt a payments team had in CI. It is `code/prompts/pr_review/v1.md`.

```text
You are a senior engineer. Review this PR carefully and point out any issues. Be thorough.
Only report important stuff. Never approve PRs with bugs. Make sure to double-check your
answer before responding.

{{diff}}
```

Read it as a contract and the gaps are obvious:

| Phrase | The question a new hire would ask | How it fails |
|---|---|---|
| "senior engineer" | Senior in what? Java? Payments? | A persona with no domain. |
| "any issues" | Bugs? Style? Naming? Missing docs? | Style nits crowd out a double-charge bug. |
| "Be thorough" + "Only report important stuff" | Which one wins? | A contradiction. Opus 5 tends to follow "only report" literally and under-report. |
| "Never approve" | Am I approving? There is no approve action here. | Unbounded rule about an action that doesn't exist. |
| "double-check your answer" | Isn't checking my job anyway? | On Opus 5 this causes over-verification, which costs tokens with no quality gain. |
| (no output format) | What do I return, and who reads it? | Free prose. The CI step can't count blockers. |

Here is the plausible output on a diff that changes the charge-retry path *(illustrative output)*:

```text
Overall this PR looks good! A few thoughts:
1. Consider renaming `doCharge` to `executeCharge` for clarity.
2. The retry loop could use a comment.
3. Make sure you have tests.
No major issues found.
```

The real defect in that diff was a new retry path that generates a fresh idempotency key on each attempt, so a timeout followed by a retry can charge twice. It isn't mentioned, because nothing told the reviewer that idempotency keys are the thing that matters.

Here is the rewrite, `code/prompts/pr_review/v2.md`, trimmed slightly:

```xml
You are reviewing a pull request to `payments-api`, a Java 21 service that moves money.
Your findings go to a filter step and then to the PR author. The filter drops low-severity
items, so report every finding you have evidence for and label its severity; do not pre-filter.

<context>
<pr_description>{{pr_description}}</pr_description>
<invariants>{{invariants}}</invariants>
</context>

<diff>{{diff}}</diff>

<task>
Find defects this diff introduces or exposes. In priority order, look for:
1. Violations of the listed invariants (idempotency keys, exactly-once ledger writes, currency rounding).
2. Correctness bugs: wrong logic, unhandled errors, races, resource leaks.
3. Missing or weakened tests for changed behavior.
Comment only on lines the diff changes, or on unchanged lines the change now breaks.
</task>

<constraints>
- Style and naming are out of scope because the linter owns them.
- If the diff is too large to review fully, say which files you skipped.
- If you are unsure whether something is a bug, report it with severity `question`.
</constraints>

<output_format>
Respond with only a JSON object: {"findings": [...], "skipped_files": [...]}. Each finding has
`file`, `line`, `severity` (one of `blocker`, `major`, `minor`, `question`), `invariant`
(the invariant ID, or null), `claim` (one sentence), and `evidence` (the diff lines that
support the claim). Return an empty `findings` list if you find nothing.
</output_format>
```

Here is what changed, and why each change makes the output checkable:

- **The purpose sentence settles the contradiction.** "Report every finding... the filter drops low-severity items" separates recall (the model's job) from precision (a deterministic filter's job). The filter is code you can test. This is the course stance in small: put the check in the environment, not the prompt.
- **`<invariants>` is injected from a file in the repo** (for example `docs/INVARIANTS.md`, see [Module 08](../08-harness-engineering/README.md)), so the review knows what "important" means for this service.
- **The task is prioritised**, so when the model runs short of attention, it spends it on invariants first.
- **The constraints say what to do when unsure** (`question`) and when the input is too big (list skipped files). Both are failure modes you would otherwise discover in production.
- **The output is a schema.** CI can now fail on `severity == "blocker"`, count findings per invariant over time, and check that every `evidence` string actually appears in the diff.

The same diff, with the spec prompt *(illustrative output)*:

```json
{"findings": [
  {"file": "src/main/java/pay/ChargeRetrier.java", "line": 58, "severity": "blocker",
   "invariant": "INV-1", "claim": "Each retry calls IdempotencyKey.random(), so a timed-out first attempt followed by a retry can create two charges.",
   "evidence": ["+    var key = IdempotencyKey.random();"]},
  {"file": "src/test/java/pay/ChargeRetrierTest.java", "line": 0, "severity": "major",
   "invariant": null, "claim": "No test covers retry after a timeout where the first attempt succeeded upstream.",
   "evidence": []}
], "skipped_files": []}
```

The prompt grew from 4 lines to about 35, but almost none of the new length is method. It is context, boundaries and an output contract. That distinction is what [03-outcome-first-and-expired-techniques.md](03-outcome-first-and-expired-techniques.md) is about.

## Pitfalls

| Pitfall | How to detect it |
|---|---|
| **Persona instead of purpose.** "You are a world-class SRE" with no statement of who reads the output. | Delete the persona line and re-run your eval. If nothing changes, the persona carried no information. |
| **Examples that teach an accidental pattern**, such as every example having two findings or the same label. | Tabulate example labels and lengths. On your eval, compare the output distribution with the example distribution. |
| **Examples copied into outputs.** | Grep outputs for distinctive strings from the examples (service names, IDs). |
| **Instructions buried after a huge input with no restatement.** | Move the long input to the top, keep the instructions after it, and measure. The linter won't catch this, but your eval will. |
| **Unclosed or inconsistent tags.** | `prompt_lint.py` rule PL007. |
| **A prose description of the schema that disagrees with the real schema.** | Generate the prose from the schema, or use structured outputs and keep the prose to field *meanings* ([05-structured-outputs.md](05-structured-outputs.md)). |

## In your day job

- Take the prompt your team uses most (a review bot, a triage step, a summariser) and write its contract table: purpose, consumer, enums, abstention behaviour, output shape. Each blank cell is a bug report.
- Move domain knowledge that several prompts need (invariants, service catalogue, glossary) into repo files, and inject them with `{{placeholders}}`. Then one edit updates every prompt. The prompt file's hash won't change when an injected file does, so log the injected file's hash next to `prompt_ref` on the trace.
- When you add a few-shot example, add it because of a specific failure in error analysis, and write that failure in the changelog entry.
