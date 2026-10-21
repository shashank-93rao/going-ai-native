# 02: Removing ambiguity

## The idea

An instruction is **ambiguous** when two reasonable readers would do materially different work from it. A new hire who hits an ambiguous instruction asks you. A model usually doesn't. It picks a reading and runs, and the output is fluent whichever reading it picked, so the ambiguity doesn't surface as an error. It surfaces as drift between what you meant and what you get, often only on a subset of inputs.

The fix is an engineering habit, not a writing style. Before a prompt ships, find the questions a smart new hire would ask, and answer each one in the prompt, with an example, or with a check in code. This file gives you the question list, a catalogue of smells, and a linter (`code/prompt_lint.py`) that catches the mechanical ones.

## Why it matters

Ambiguity is expensive in two ways.

**It is resolved arbitrarily.** Claude Code's docs say that if two instructions in your CLAUDE.md files contradict each other, "Claude may pick one arbitrarily" ([Claude Code docs, "How Claude remembers your project"](https://code.claude.com/docs/en/memory)). Arbitrary means it can flip between runs, between model versions, or when unrelated context shifts attention. That is a nondeterministic config merge, and you would never accept that in a service.

**It costs tokens and quality even when the answer comes out right.** OpenAI's GPT-5 prompting guide (now archived) says that given contradictory instructions the model "expends reasoning tokens searching for a way to reconcile the contradictions", and that such prompts "can be more damaging to GPT-5 than to other models" ([OpenAI Cookbook, GPT-5 prompting guide](https://developers.openai.com/cookbook/examples/gpt-5/gpt-5_prompting_guide)). Claude Code now ships an audit for the same problem: `/doctor prompt-audit` looks for "instructions written for older models, references to files or commands that don't exist, and files that contradict each other" (Claude Code v2.1.283 or later, per the memory docs above).

## How to do it

### The smart-new-hire questions

Read the prompt as someone who joined today, is very good, and knows nothing about your team. For each sentence, ask:

1. **What does this word mean here?** "Important", "relevant", "large", "recent", "properly", "issues". If you can't define it in one line, give an example.
2. **When does this rule apply, and why?** An absolute with no scope ("Always page for errors") is either wrong at the edges or a rule you should enforce in code.
3. **What if two instructions disagree?** "Be thorough" and "be concise", or "report everything" and "only report important stuff".
4. **What do I do when I'm unsure, when the input is empty, or when it's too big?** Missing failure semantics is the most common gap in production prompts.
5. **Who reads my output, and in what shape?** If nothing says, the model picks a shape.
6. **What is out of scope?** Without a stated boundary, capable models widen scope. Anthropic notes Opus 5 "can also expand the scope of a task" and gives a scope-constraining prompt for narrow tasks ([Anthropic, "Prompting Claude Opus 5"](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5)).

You can run this check with a model. Use a fresh context with no system prompt and only the prompt under review, so it reads like a new hire would:

```text
Below is a prompt that will be given to an AI model with no other context.
Do not perform the task. Instead, list:
1. every term whose meaning you would have to guess,
2. every pair of instructions that could conflict, and which you would follow,
3. every input situation the prompt does not say how to handle,
4. what shape you would return your answer in, and why.

<prompt_under_review>
{{prompt}}
</prompt_under_review>
```

### The smell catalogue

| Smell | Example | Fix |
|---|---|---|
| Undefined term | "Report any issues" | Define the categories, or list what is out of scope. |
| Unbounded absolute | "NEVER speculate" | Add the scope and the reason, or enforce the rule in a validator. |
| Contradiction | "Be thorough but concise" | Pick one, or say which wins and when. |
| No output format | "Classify the problem" | Give a schema or a named section layout, and say who parses it. |
| No failure behaviour | (nothing about unclear input) | Add an abstain path (`unknown`, `question`, an empty list). |
| Implicit priority | Five equal-weight bullet points | Number them, and say what to drop first. |
| Shouting | "CRITICAL: You MUST..." | Use normal case and give the reason. |
| Negative-only instruction | "Don't use markdown" | Say what to do instead ("plain prose in three paragraphs"). |

Two of these need more explanation.

**Absolutes.** OpenAI's GPT-5.5 guide observes that older prompts "often use strict instructions like `ALWAYS`, `NEVER`, `must`, and `only`", and advises: "Use those words for true invariants, such as safety rules, required output fields, or actions that should never happen" ([OpenAI, prompt guidance](https://developers.openai.com/api/docs/guides/prompt-guidance?model=gpt-5.5)). Anthropic's version is the ellipses example. "NEVER use ellipses" is weaker than "Your response will be read aloud by a text-to-speech engine, so never use ellipses since the text-to-speech engine will not know how to pronounce them", because "Claude is smart enough to generalize from the explanation" ([Anthropic, "Prompting best practices"](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices)). With the reason attached, the model can handle the cases your rule didn't anticipate, such as an em-dash pause that a TTS engine would also stumble on.

**Shouting.** The same Anthropic guide notes that recent Claude models are more responsive to the system prompt, so prompts written to fight under-triggering now over-trigger. It says: "Where you might have said 'CRITICAL: You MUST use this tool when...', you can use more normal prompting like 'Use this tool when...'". Emphasis was a workaround for inattentive models. On attentive ones, it acts like an exaggerated weight.

### The linter

`code/prompt_lint.py` is a heuristic, like any linter. It catches mechanical smells so human review can focus on intent. Each message says how to fix the problem. OpenAI's harness-engineering post describes the same pattern for code: custom lints carry remediation text, so the error message becomes the fix instruction in the agent's context ([OpenAI, "Harness engineering"](https://openai.com/index/harness-engineering/); more in [Module 08](../08-harness-engineering/README.md)).

| Rule | Severity | Catches |
|---|---|---|
| PL001 missing-output-format | error | Nothing describes the output shape |
| PL002 contradiction | error | Brevity vs exhaustiveness, report-all vs report-some, or `always X` vs `never X` sharing two or more content words |
| PL003 unbounded-absolute | warning | ALWAYS/NEVER/MUST with no `because`, `when`, `unless` or `if` in the sentence |
| PL004 shouting | warning | Three or more all-caps emphasis words |
| PL005 expired-technique | warning | "Think step by step", "plan extensively", "double-check", "think tool" |
| PL006 vague-term | info | "appropriate", "relevant", "any issues", "figure out"... |
| PL007 unbalanced-xml | error | An opened tag that is never closed |

## Worked example: linting and fixing the triage prompt

This is `code/prompts/log_triage/v1.md`, written during an incident review:

```text
You are an expert SRE with 20 years of experience. Look at the logs and figure out what is
going on. Classify the problem and rate how severe it is. Be thorough but concise. Always
page for errors.
```

Here is the real linter output:

```text
$ python prompt_lint.py prompts/log_triage/v1.md
prompts/log_triage/v1.md: 5 finding(s)
     9: error   PL001 No output format. Say exactly what comes back (JSON fields, sections, length) and who parses it.
     9: error   PL002 Contradiction (brevity vs exhaustiveness) on line 9. Pick one, or say which wins and when (e.g. 'report every finding with a severity; a later step filters').
     9: warning PL003 Unbounded 'Always' in: 'Always page for errors.'. Add the reason or the scope, or enforce it in code. Reserve absolutes for true invariants.
     9: info    PL006 Vague 'expert'. Would a smart new hire know what you mean? Define it or give an example.
     9: info    PL006 Vague 'figure out'. Would a smart new hire know what you mean? Define it or give an example.
```

The linter can't see the deepest gaps. Run the new-hire questions by hand:

| Question | Answer in v1 | Answer in v2 |
|---|---|---|
| What are the categories? | None given. The model invents them. | Seven, each with a one-line definition, including `unknown`. |
| What does "severe" mean? | Nothing. You'll get `HIGH` or `P2` or "fairly severe". | `page`, `ticket`, `ignore`, each defined by user impact and time. |
| "Always page for errors": is a `DeprecationWarning` an error? A handled retry? | Unclear. | Settled signatures: `DeprecationWarning` and `GET /healthz` map to `noise` and `ignore`. |
| Which error is worse, a false page or a missed one? | Unstated. | "A wrong `page` wakes someone at 3am; a wrong `ignore` hides an outage. When in doubt between the two, choose `page`." |
| What if the excerpt shows two problems? | Unstated. | "Classify the most severe one." |
| What if there isn't enough evidence? | Unstated, so it guesses. | `unknown` plus `needs_human: true`, and an example of exactly that. |
| What shape is the output? | Unstated. | A JSON object with six named fields. |

The fixed version is `code/prompts/log_triage/v2.md`, and it has zero linter findings. [05-structured-outputs.md](05-structured-outputs.md) walks through it field by field. Here is the difference on one real input, using the course's simulated model (`sim_model.py`, scripted, *not* a measurement):

```text
# v1 on "orders-api pod orders-api-6c4d OOMKilled (limit 512Mi)"
Sure! Here's my analysis of the logs.

**Problem:** unknown
**Severity:** LOW

Let me know if you want me to dig deeper.
```

```json
// v2 on the same input
{"category": "infra", "severity": "page", "service": "orders-api",
 "summary": "orders-api: pod orders-api-6c4d OOMKilled (limit 512Mi)",
 "evidence": ["2026-10-03T02:14:07Z orders-api pod orders-api-6c4d OOMKilled (limit 512Mi)"],
 "needs_human": false}
```

The fake behaves this way because it was scripted to, so it proves nothing about real models. Run `ab_harness.py log_triage 1 2` with an API key to get your own numbers. With a real model, v1's output will vary in shape from run to run, and that variance is the point.

## Pitfalls

| Pitfall | How to detect it |
|---|---|
| **Fixing ambiguity by adding rules until the prompt is a policy manual.** The repomirror team reported that a 1,500-word "improved" prompt made their agent slower and worse, and they cut it back to 103 words ([repomirror write-up](https://github.com/repomirrorhq/repomirror/blob/main/repomirror.md)). | Track prompt length in the changelog. Every added rule should name the eval failure it fixes. |
| **Treating linter silence as correctness.** PL001 is satisfied by the word "JSON" anywhere. | The linter is a pre-filter. Your eval is the test. |
| **Linter false positives that people learn to ignore.** For example, "Always cite the log line" is a fine absolute. | Add a reason ("Always cite the log line, because on-call reads it as the justification"). That clears PL003 and improves the prompt. |
| **Defining a term in one prompt and using it differently in another.** | Keep shared definitions (severity levels, service catalogue) in one injected file. |
| **Asking the model to resolve ambiguity "using its best judgement" as a catch-all.** | That moves the ambiguity, it doesn't remove it. Say what judgement means for the two or three cases you've seen. |

## In your day job

- Add `prompt_lint.py` (or your own version) as a pre-commit hook on your prompt directory. Make PL001, PL002 and PL007 blocking.
- Before merging a prompt change, run the new-hire meta-prompt above in a fresh session. Paste its questions into the PR description and answer each one.
- When a reviewer leaves the same prompt-review comment twice, turn it into a lint rule with a fix message.
