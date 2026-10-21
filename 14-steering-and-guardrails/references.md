# References

Fast-moving tool docs were read on 2026-10-19. Re-check them against your installed version.

## Claude Code and Claude API (primary)

| Source | What to take from it |
|---|---|
| [Hooks reference](https://code.claude.com/docs/en/hooks) | The authoritative schema: event inputs (`tool_input`, `stop_hook_active`, `last_assistant_message`), exit-code semantics (2 blocks; other non-zero codes are non-blocking), PreToolUse `permissionDecision` allow/deny/ask/defer with precedence `deny > defer > ask > allow`, Stop `decision: "block"` + `reason`, `continue: false` + `stopReason`, and the 8-consecutive-continuation cap that resets on each tool call (`CLAUDE_CODE_STOP_HOOK_BLOCK_CAP`). |
| [Hooks guide](https://code.claude.com/docs/en/hooks-guide) | Hooks are deterministic while CLAUDE.md is advisory; protect-files and Stop-gate recipes; prompt and agent hook types. |
| [`/goal`](https://code.claude.com/docs/en/goal) | The condition-driven loop: a small-model evaluator over the transcript; met / not met / impossible; it doesn't run tools; how to write conditions (end state, stated check, constraints, budget clause); stall guard; `-p` use. |
| [Interactive mode](https://code.claude.com/docs/en/interactive-mode) | Esc interrupts and keeps work; queued messages are delivered after the current tool calls; Esc Esc opens rewind; Ctrl+G opens the editor. |
| [Permission modes](https://code.claude.com/docs/en/permission-modes) | The mode table; deny rules hold in every mode; allow rules have no effect in `bypassPermissions`; the "run in CI with an exact allowlist" setup using `dontAsk`. |
| [Permissions](https://code.claude.com/docs/en/permissions) | Deny, then ask, then allow; compound-command splitting; wrapper stripping; "isn't a security boundary around the program"; the fragile-argument-pattern warning; hooks can't bypass deny/ask rules, and exit 2 beats allow rules. |
| [Best practices](https://code.claude.com/docs/en/best-practices) | "Give Claude a way to verify its work"; the verification ladder (prompt, `/goal`, Stop hook, refuting subagent); after two failed corrections, `/clear`; fan-out with `--permission-mode dontAsk`. |
| [Prompting Claude Opus 5](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5) | The over-verification finding, with removal advice; the scope-control prompt; subagent damping; "report everything, filter in a separate pass". The other half of the module's central tension. |
| [Structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs) | `output_config.format` (no beta header); strict tool use; the list of JSON Schema features the decoder doesn't support (`minimum`/`maximum`, `minLength`/`maxLength`...); refusal and truncation exceptions. This is why local validators are still needed. |

## Anthropic engineering

| Source | What to take from it |
|---|---|
| [How we built Claude Code auto mode](https://www.anthropic.com/engineering/claude-code-auto-mode) | 93% of permission prompts approved (approval fatigue); a threat model led by overeager behavior and honest mistakes; classifier FPR 0.4% / FNR 17%, an honest example of evaluating a gate. |
| [Claude Code sandboxing](https://www.anthropic.com/engineering/claude-code-sandboxing) | Filesystem *and* network isolation; why `bypassPermissions` belongs inside a box. |
| [How we contain Claude](https://www.anthropic.com/engineering/how-we-contain-claude) | Blast radius as the design variable; hooks in cloned repo settings as a pre-trust code path. |
| [How the Claude Code team does code review](https://claude.dev/blog/solving-code-review-at-anthropic/) | Risk tiers (0/1/2 humans); an agent's approval never counts as a human's; an approval covers one commit; round caps. |
| [Building effective agent automations](https://claude.dev/blog/building-effective-agent-automations/) | Trust rules for agent-produced status ("assert it or drop it"); budgets that pause rather than fail. |

## OpenAI

| Source | What to take from it |
|---|---|
| [Steering guide (Responses API)](https://developers.openai.com/api/docs/guides/steering) | `response.steer` over WebSocket; "Acceptance means the input is queued, not that the model has acted on it"; `incomplete` with reason `steered`; running tools aren't cancelled; queues are connection-scoped. GPT-6 family only, per the docs. |
| [Introducing Structured Outputs](https://openai.com/index/introducing-structured-outputs-in-the-api/) | 93% (prompting) vs 100% (constrained decoding) on their schema eval; values can still be wrong. |
| [A practical guide to building agents](https://cdn.openai.com/business-guides-and-resources/a-practical-guide-to-building-agents.pdf) | Tool risk ratings by read/write, reversibility and financial impact; human handoff on failure thresholds and high-risk actions; layered guardrails. |

## Practitioners

| Source | What to take from it |
|---|---|
| [Spotify Engineering, "Background coding agents" part 3](https://engineering.atspotify.com/2025/12/feedback-loops-background-coding-agents-part-3) | The canonical blocking gate: verifiers run in a Stop hook, and no PR if any fails; regex-filtered verifier output; an LLM judge on diff vs prompt vetoes about a quarter of sessions, with half recovering; the judge has no evals yet; the three failure modes. |
| [Armin Ronacher, "Agentic Coding Things That Didn't Work"](https://lucumr.pocoo.org/2025/7/30/things-that-didnt-work/) | The steering-hook counterexample: no efficiency gains, wanting hooks to change what executes, steering via PATH shims instead. |
| [Armin Ronacher, "The Coming Loop"](https://lucumr.pocoo.org/2026/6/23/the-coming-loop/) | An outer harness decides whether work is done; "The harness just needs some signal that lets it continue." |
| [Kent Beck, "Augmented Coding: Beyond the Vibes"](https://newsletter.kentbeck.com/p/augmented-coding-beyond-the-vibes) | The three warning signs: loops, unrequested functionality, cheating on tests. The basis for `drift_monitor.py` and `test_tamper_check.py`. |
| [HumanLayer, 12-Factor Agents](https://github.com/humanlayer/12-factor-agents) | Factor 7 (contact humans via tool calls), factor 8 (interrupt between selection and invocation), factor 9 (compact errors into context; break after about 3 consecutive errors). |
| [HumanLayer, Advanced Context Engineering (ACE-FCA)](https://github.com/humanlayer/advanced-context-engineering-for-coding-agents/blob/main/ace-fca.md) | Review has the most leverage at research and plan; throw away wrong research and rerun it; 40–60% context utilization. |
| [LangChain, "Introducing ambient agents"](https://www.langchain.com/blog/introducing-ambient-agents) | The notify / question / review HITL patterns; the Agent Inbox. |
| [Steve Kinney, AI Development Setup](https://stevekinney.com/courses/ai-development-setup) | The enforcement ladder; the done signal from CI, a hook or a human, never a file the agent writes; restrictions via `--disallowedTools`, not prompt text. |

## Not verified or hedged in this module
- LangChain's loop-detection middleware (edits-per-file counter) is cited from the course research notes, not re-fetched. It is presented as "reported".
- Version-specific Claude Code behavior (auto mode as the default starting mode, check-in intervals) changes often. The text says which docs date it reflects.
