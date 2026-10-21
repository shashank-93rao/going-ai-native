# 02: Prompting as specification
> After this module you can write a prompt the way you write an API contract: unambiguous, with a checkable output schema, versioned and hashed, linted in CI, and promoted only through a paired A/B gate that can say "no".

## Why this matters

You have been writing detailed prompts for a year, so you already know prompts work. This module is about why some of them stop working without anyone touching them, and why others work in your terminal and fail in production.

There are three failure modes, and each is an engineering failure, not a wording failure:

1. **The prompt is an underspecified contract.** "Review this PR" or "classify this log" leaves the output shape, the decision boundaries and the cost of each error to the model. The model fills those gaps with plausible defaults, and they are not your defaults. Your router then parses `"Severity: HIGH"` from a sentence of prose and pages nobody.
2. **The prompt encodes assumptions about an older model.** A 2025 prompt full of `You MUST`, `think step by step`, `double-check your answer` and an eight-step procedure was compensating for a model weakness. Current models do those things on their own, and the scaffolding now costs tokens and quality. Anthropic says explicit verification instructions "cause over-verification on Claude Opus 5" ([Anthropic, "Prompting Claude Opus 5"](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5)). OpenAI says legacy process-heavy prompts can "narrow the model's search space" ([OpenAI, GPT-5.5 prompt guidance](https://developers.openai.com/api/docs/guides/prompt-guidance?model=gpt-5.5)). Some techniques have gone further than expired: prefill now returns a 400.
3. **Prompt changes ship like config edits rather than deploys.** In April 2026 Anthropic shipped one system-prompt line limiting response length in Claude Code. A broader ablation later showed a 3% drop on Opus 4.6 and 4.7, and the line was reverted four days after it shipped. The fix they committed to is a deploy process: per-model evals for every system-prompt change, line-by-line ablations, soak periods and gradual rollouts ([Anthropic, April 23 postmortem](https://www.anthropic.com/engineering/april-23-postmortem)).

The course thesis applies directly. **Autonomy should scale with verifiability**, and a prompt becomes verifiable when its output has a schema you can validate, its versions have hashes you can trace, and its changes go through an eval you can fail.

## The distributed-systems anchor

**A prompt is an API contract, and a prompt change is a schema migration.**

| You know | In prompting |
|---|---|
| OpenAPI or protobuf contract | Output schema plus the prose that defines each field's meaning |
| Versioned, append-only migrations with an applied-migrations table | `vN.md` files that are never edited after publish, plus `prompts.lock.json` with their hashes |
| Request IDs and build SHAs in every log line | `prompt_ref = name@vN#sha12` on every trace span |
| Canary, soak, automated rollback | A/B gate on an eval set, then a canary channel, then a pointer move back to `vN-1` |
| Config precedence (flags > env > file > defaults) | Instruction hierarchy (platform > system > developer > AGENTS.md > skill > user > tool output) |

**Where the analogy breaks.** A protobuf consumer either parses a field or fails. A model *interprets* your contract, and how it interprets it changes when the model version changes, even if you didn't change a byte. So you have to version the (prompt, model) pair, not the prompt alone. The "server" can also be upgraded under you, which is why re-testing on every model upgrade is part of the contract. Config precedence is also enforced by code, while instruction precedence is only *trained into* the model. It usually holds, it is not guaranteed, and anything that must hold belongs in a hook or a validator ([Module 14](../14-steering-and-guardrails/README.md)).

## Learning goals
- [ ] Rewrite a vague task prompt into a spec with role, context, task, constraints, output format and examples, using XML tags to separate them
- [ ] Choose few-shot examples for coverage of decision boundaries, not for volume
- [ ] Run the "smart new hire" test and the linter, and fix each ambiguity they find
- [ ] Convert an over-specified legacy prompt into an outcome-first one, and say which lines encoded an expired model weakness
- [ ] Resolve a conflict between the system prompt, AGENTS.md, a skill and a user message, and write the precedence rule down
- [ ] Define a JSON schema for a classifier, and validate both shape and meaning
- [ ] Version prompts with content hashes and a changelog, and gate a change with a paired A/B that can reject it
- [ ] Re-run your prompt evals on a model upgrade before you switch

## Reading order
1. [01-prompts-are-specs.md](01-prompts-are-specs.md): the anatomy of a spec prompt, XML tags, and choosing few-shot examples. Worked example: "review this PR" rewritten.
2. [02-removing-ambiguity.md](02-removing-ambiguity.md): the smart-new-hire test, the common ambiguity smells, and a linter that catches them.
3. [03-outcome-first-and-expired-techniques.md](03-outcome-first-and-expired-techniques.md): outcome-first prompting for current models, the techniques that expired (prefill, "think step by step", the think tool), and the model-upgrade drill.
4. [04-instruction-hierarchy.md](04-instruction-hierarchy.md): what happens when the system prompt, AGENTS.md, a skill and the user disagree.
5. [05-structured-outputs.md](05-structured-outputs.md): schemas, constrained decoding, and why shape is not truth. Worked example: the log-triage classifier.
6. [06-prompts-as-deploys.md](06-prompts-as-deploys.md): the registry, content hashes, changelogs, and the gate, soak and rollback process.
- [examples.md](examples.md), [exercises.md](exercises.md), [references.md](references.md), [code/](code/)

## Prerequisites
- [01: LLMs for systems engineers](../01-llms-for-systems-engineers/README.md), for effort, sampling and prompt caching.
- This module points forward to [10: Evals fundamentals](../10-evals-fundamentals/README.md) and [12: Hill-climbing](../12-hill-climbing/README.md). The A/B harness here is deliberately small, and those modules make it statistically honest.

## Key takeaways
- A prompt is a contract plus an implementation. Write down the reader, the purpose, the cost of each kind of error, the decision boundaries and the output shape. Leave the method to the model unless the method *is* the requirement.
- If a smart new hire with no context would ask a clarifying question about your prompt, the model will guess instead. Find those questions before the model does.
- Use ALWAYS and NEVER only for true invariants, and give each rule its reason. A rule that has to hold belongs in a validator or a hook, not in capital letters.
- Prompt advice expires. Prefill returns a 400 on Claude 4.6 and later. "Think step by step" is redundant on reasoning models. The think tool was superseded by extended thinking. Re-baseline every prompt on every model upgrade.
- Instruction conflicts across the system prompt, AGENTS.md, skills and the user get resolved arbitrarily unless you state the precedence. Give each rule one owner and one location.
- A schema guarantees shape, not truth. Validate the meaning too (is the evidence really in the log?), and treat `max_tokens` and `refusal` stop reasons as failures, never as data.
- Version prompts like migrations: immutable files, a content hash on every trace, a changelog entry per version, a lock file checked in CI.
- Gate prompt changes on a paired eval with must-pass rows. A gate that can never say "inconclusive" or "reject" is decoration.
