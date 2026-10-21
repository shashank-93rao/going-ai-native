# 06: Why models hallucinate, and why they agree with you

## The idea

**Hallucination** is a confident, plausible, wrong output: a config key that doesn't exist, a function signature from a different library version, a log line the model "remembers" from your excerpt that isn't there. **Sycophancy** is the related failure where the model's output bends toward what it thinks you want to hear. It agrees with your hypothesis, approves your diff, or rates its own work highly.

Neither is a mysterious defect. Both follow from what the model was optimized for. Pretraining rewards plausible continuations. Post-training and evaluation have rewarded *answering* over *abstaining*, and *pleasing a rater* over *being right*. If you understand the incentive, you can design around it the way you'd design around a component whose failure mode is "returns stale data with a 200".

## Why it matters

OpenAI's paper "Why Language Models Hallucinate" (Kalai, Nachum, Vempala, Zhang, September 2025) makes two claims ([arXiv:2509.04664](https://arxiv.org/abs/2509.04664)). First, "Hallucinations need not be mysterious -- they originate simply as errors in binary classification." A model can't separate true from false facts that it saw rarely or never, such as an arbitrary person's birthday or an obscure config key, so pretraining alone produces some error rate on them. Second, they persist because "the training and evaluation procedures reward guessing over acknowledging uncertainty". Under accuracy-only scoring, a guess sometimes scores and "I don't know" never does, so "language models are optimized to be good test-takers".

The accompanying OpenAI post makes the point with SimpleQA numbers from the GPT-5 system card ([OpenAI, "Why language models hallucinate"](https://openai.com/index/why-language-models-hallucinate/)):

| Model | Abstained | Accurate | Wrong |
|---|---|---|---|
| gpt-5-thinking-mini | 52% | 22% | 26% |
| o4-mini | 1% | 24% | 75% |

On an accuracy leaderboard, o4-mini wins, 24% to 22%. In production, it is wrong three times as often. **Accuracy hides the error rate.** This is why [Module 10](../10-evals-fundamentals/README.md) scores correct, abstain and wrong separately.

On sycophancy, Anthropic researchers found it in five state-of-the-art assistants across four free-form tasks, and called it "a general behavior of state-of-the-art AI assistants". In human preference data, responses matching the user's views were more likely to be preferred. Both humans and preference models sometimes preferred a convincingly written sycophantic answer over a correct one ([Sharma et al., "Towards Understanding Sycophancy in Language Models", arXiv:2310.13548](https://arxiv.org/abs/2310.13548)).

The production version: in April 2025 OpenAI rolled back a GPT-4o update that had become noticeably sycophantic. Its postmortem says the update added a thumbs-up/down reward signal that, together with other changes, weakened the signal that had kept sycophancy in check. Offline evals and A/B tests looked fine because nothing measured sycophancy, and some expert testers' sense that the model "felt" off was overridden ([OpenAI, "Expanding on what we missed with sycophancy"](https://openai.com/index/expanding-on-sycophancy/)). An optimization target (user approval) diverged from the property that mattered. Distributed-systems engineers have seen this before, as a health check that passes while the service is broken.

## How it works

### Hallucination: when it's likely

*Course synthesis* from the paper and from practice:

| Higher risk | Lower risk |
|---|---|
| Rare, arbitrary facts: exact flag names, error codes, version-specific APIs, internal service names | Common patterns: standard library calls, popular framework idioms |
| Questions about content that isn't in the context ("what does our `RetryPolicy` do?") | Questions about content pasted in or read by a tool |
| A format that demands an answer (a single field, a forced choice, no "unknown" option) | A format with an explicit abstain option |
| Long contexts with distractors ([01](01-tokens-and-the-context-window.md)) | Short, focused contexts |
| Post-cutoff facts (new releases, new APIs) | Stable, old facts |

Karpathy's MenuGen write-up is a typical case. LLMs kept suggesting deprecated APIs for services that had changed, and he fixed it by pasting current docs into context ([Karpathy, "Vibe coding MenuGen"](https://karpathy.bearblog.dev/vibe-coding-menugen/)).

### Hallucination: what to do

1. **Ground it.** Put the source in the window (docs, the file, the schema) or give a tool to fetch it. Anthropic's prompting guide offers this agentic-coding prompt: "Never speculate about code you have not opened. If the user references a specific file, you MUST read the file before answering" ([Anthropic, Prompting best practices](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices)).
2. **Make abstention legal and cheap.** Give the output schema an `unknown` value. The paper proposes stating an explicit confidence threshold *t* in the instructions, with wrong answers penalized *t*/(1−*t*) points, correct answers worth 1, and abstentions worth 0. Under that scoring, answering only pays when the model's confidence exceeds *t*.
3. **Require evidence.** Ask for the quoted line, file path, or doc section behind each claim. A claim with a citation can be checked mechanically. One without can't.
4. **Check against an oracle.** Config keys can be validated against the library's own config class, flags against `--help`, and APIs by compiling. This is the strongest fix, because it doesn't depend on the model at all.

### Sycophancy: where it shows up in engineering work

- **Leading questions in debugging.** "It's the GC pauses, right?" gets you a fluent argument for GC pauses.
- **Self-review.** Anthropic's harness-design work found that "agents reliably skew positive when grading their own work" ([Anthropic, "Harness design for long-running application development"](https://www.anthropic.com/engineering/harness-design-long-running-apps)).
- **Pushback collapse.** You say "are you sure?", and a correct answer flips to an incorrect one.
- **Review bots.** A reviewer that sees the author's confident PR description inherits the author's framing.

### Sycophancy: what to do

1. **Ask neutrally.** List the hypotheses without ranking them, and ask for evidence for *and against* each one.
2. **Separate the generator from the judge.** Use a fresh context that hasn't seen the author's reasoning, and give it the artifact plus the spec, not the conversation ([Module 06](../06-agent-architectures/README.md), clean-context reviewers; [Module 11](../11-llm-as-judge/README.md)).
3. **Don't rely on "are you sure?".** If you doubt an answer, re-run the question in a fresh context, or check it with a tool.
4. **Evaluate it.** Add cases where the user's stated belief is wrong and score whether the model corrects it. OpenAI's lesson was that what you don't measure, you ship.

## Worked example: an incident hypothesis and a config "fix"

You're investigating p99 latency spikes in a Java service that consumes from Kafka. You suspect GC.

**Bad version.**

```text
Our orders-consumer has p99 spikes every ~5 minutes. I'm pretty sure it's GC pauses from the
large batch deserialization. Can you confirm and give me the consumer config to fix it?
Here are the GC logs and consumer metrics:
<gc_log>...</gc_log>
<metrics>...</metrics>
```

A typical response (illustrative output):

```text
You're right: the pattern is consistent with GC pressure from batch deserialization. To fix it,
reduce max.poll.records to 100 and enable consumer.prefetch.adaptive=true so the consumer
adjusts fetch size to heap pressure.
```

Two failures:

- **Sycophancy.** "I'm pretty sure it's GC" plus "confirm" invites agreement. In this scenario the GC log shows 30 to 40 ms young-gen pauses. The 5-minute period actually matches `metadata.max.age.ms=300000`, which triggers metadata refreshes. The model didn't weigh that, because you didn't ask it to.
- **Hallucination.** `consumer.prefetch.adaptive` is not a Kafka consumer config. It is a plausible-sounding rare string, which is exactly the high-risk class. If you paste it into `application.yml`, Kafka logs an unknown-config warning and ignores it, and you've changed nothing.

**Good version.**

```text
orders-consumer shows p99 latency spikes roughly every 5 minutes.

<gc_log>...</gc_log>
<metrics>...</metrics>
<consumer_config>...full effective config, from the startup log...</consumer_config>

Task:
1. List every mechanism in the data above whose period could be ~5 minutes.
2. For each, quote the evidence for it and the evidence against it. If the data can't tell, say "insufficient data".
3. Rank them by how well the evidence supports them.
4. Propose config changes ONLY using keys that appear in <consumer_config>. If a fix needs a key that
   isn't there, name it and mark it UNVERIFIED.
```

Then check the output mechanically instead of trusting it:

```python
# validate_kafka_keys.py: reject any config key the client library doesn't define.
# KNOWN_CONSUMER_KEYS comes from an authoritative source: e.g. the keys in the consumer's
# startup "ConsumerConfig values:" log block, or ConsumerConfig.configNames() in the Java client.

def unknown_keys(proposed: dict[str, str], known: set[str]) -> set[str]:
    return set(proposed) - known

bad = unknown_keys(model_proposal, KNOWN_CONSUMER_KEYS)
assert not bad, f"model proposed nonexistent config keys: {bad}"
```

The neutral prompt removes the cue to agree. The evidence-for-and-against structure makes the model work through alternatives. The key allowlist and the validator turn "is this key real?" from a judgment call into a set difference. That set difference is the verifiable part of the task, and it now lives in code.

## Pitfalls

| Pitfall | How to detect it |
|---|---|
| Accuracy-only evals | Your eval has no "abstain" outcome. Add one and report the wrong-answer rate separately. |
| Output schemas that forbid "unknown" | Every enum field without an `unknown` member forces a guess. Audit the schemas. |
| Leading prompts in debugging and review | Grep prompt templates for "confirm", "right?", "I'm sure", "verify that X is correct". Rewrite them as neutral questions. |
| Self-grading | The same context that produced an artifact grades it. Move grading to a fresh context or to a deterministic check. |
| Trusting citations without checking them | Spot-check that quoted lines actually appear in the source. A string-containment check is enough. |
| Flipping on pushback | Ask "are you sure?" on a sample of correct answers. If many flip, never use pushback as a verification step. |
| Unvalidated identifiers | Any model-proposed config key, flag, package name or API should pass an allowlist or a compiler before it reaches a commit. |

## In your day job

- Give every structured output an `unknown` option, and track how often it's used. A sudden drop to zero is a warning, not a win.
- Phrase incident questions as "what are the candidate causes, with evidence for and against each", never as "confirm X".
- Validate model-proposed identifiers (config keys, flags, dependency names) against an authoritative list before they're committed.
- Use a fresh-context reviewer for anything the same agent produced ([Module 17](../17-ai-native-engineer-and-team/README.md) on review at agent volume).
