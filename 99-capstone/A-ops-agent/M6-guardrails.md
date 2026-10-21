# A-M6: Guardrails: hooks, containment and an injection suite
**Time:** one weekend. **Offline:** gates and suite yes; measurement needs a key. **Modules:** [16](../../16-security-and-containment/README.md), [14](../../14-steering-and-guardrails/README.md), [05](../../05-tools-mcp-skills-hooks/README.md), [06](../../06-agent-architectures/README.md).

## Goal
Drive the dangerous-action rate and the injection-success rate to zero on a regression suite, using defenses that do not depend on the model behaving, and measure what those defenses cost in blocked legitimate fixes.

## Why it matters
In M5 the safety column probably did not move. That is expected. Prompt-level defenses are probabilistic. Willison's framing: in web security terms, 95% detection is a failing grade ([Willison, "The lethal trifecta"](https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/)). Anthropic's containment post makes the structural point: risk is likelihood times blast radius, and containment caps the blast radius regardless of likelihood ([Anthropic, "How we contain Claude across products"](https://www.anthropic.com/engineering/how-we-contain-claude)). Your agent reads untrusted text (logs) and holds mutating tools. That is the shape to break.

## Steps
1. **Lethal-trifecta audit.** List every tool. Mark each as private data, untrusted input, or an external channel (here: a mutation is the "channel": it is how injected intent leaves the model).

   | Tool | Private data | Untrusted input | Acts on the world |
   |---|---|---|---|
   | get_logs | | **yes**: any service can write a log line | |
   | get_deploys | | partly (deploy notes are free text) | |
   | get_metrics | | no (numbers) | |
   | rollback / restart / scale | | | **yes** |
   | page_human | | | yes (low blast radius) |
   | resolve_incident | | | yes (closes the page: can hide an outage) |

2. **Deterministic pre-tool-use gate.** A function that sees each proposed call *before* `env.call` and can block it with an actionable reason. It encodes the SPEC.md authority table. This is the equivalent of a `PreToolUse` hook that exits 2 in Claude Code ([hooks guide](https://code.claude.com/docs/en/hooks-guide)): blocking gates work, and steering hooks mostly do not (course stance, [01-gap-analysis](../../research/01-gap-analysis.md)).
3. **Build an injection suite.** At least 10 variants, each a scenario plus an injected line placed in a log or deploy note. Vary placement, phrasing, authority claims, and target. Include one where the injected action equals the correct fix (it must not be blocked *because* it was injected; it should pass because it is authorized).
4. **Add one structural defense**, not just the gate. Options, from Willison's design-patterns write-up ([prompt-injection design patterns](https://simonwillison.net/2025/Jun/13/prompt-injection-design-patterns/)):
   - **Context minimization:** the agent sees `get_logs` through a quarantined summarizer that returns only a fixed schema (`{"error_signatures": [...], "counts": {...}}`), never raw text.
   - **Plan-then-execute:** the agent commits to a remediation plan from metrics and deploys only, then reads logs to confirm or abort. Logs cannot add actions.
   - **Dual LLM:** a privileged planner handles symbolic references; a quarantined reader processes log text and cannot call tools.
5. **Reasoning-blind action check (optional, strong).** A second classifier that sees only the user's page and the proposed tool calls, not the agent's prose or tool results. That is the design Anthropic describes for Claude Code's auto mode, so the agent "can't talk the classifier into making a bad call" ([Anthropic, "How we built Claude Code auto mode"](https://www.anthropic.com/engineering/claude-code-auto-mode)). Measure its FPR and FNR like any classifier.
6. **Measure three rates** on the full suite with k=3: dangerous-action rate, injection-success rate (using the M3-fixed check that requires the injected text was *seen*), and **false-block rate**: the fraction of authorized, correct mutations the gate or classifier blocked.
7. **Red-team findings become regression tests.** Every bypass you find gets a scenario in the suite and a test.

## Worked example: the gate
Bad version: a denylist on the tool name.

```python
def gate(tool, args):
    if tool == "restart" and args.get("service") == "db":
        return "blocked: db restarts need a human"
```

Why it fails: it encodes one invariant and nothing about authority. It allows `rollback(payments)` with no deploy, `scale(api-gateway, 0)` if the schema check is bypassed, and `resolve_incident` while the system is down.

Better: the authority table as code, reading the same env the grader reads.

```python
@dataclass
class GateDecision:
    allow: bool
    reason: str = ""

def gate(env: SimEnv, tool: str, args: dict) -> GateDecision:
    svc = args.get("service")
    reads = [(r.tool, r.args.get("service")) for r in env.log]
    if tool == "restart" and svc == "db":
        return GateDecision(False, "db is never restarted by automation. Call page_human with your evidence.")
    if tool == "scale" and not (1 <= int(args.get("replicas", 0)) <= 12):
        return GateDecision(False, "replicas must be 1..12")
    if tool in ("rollback", "restart", "scale") and ("get_metrics", svc) not in reads:
        return GateDecision(False, f"read get_metrics({svc}) before mutating it")
    if tool == "rollback":
        deploys = next((r.result for r in reversed(env.log)
                        if r.tool == "get_deploys" and r.args.get("service") == svc), None)
        recent_code = deploys and any(d["kind"] == "code" and d["minutes_ago"] < 60 for d in deploys["deploys"])
        if not recent_code:
            return GateDecision(False, f"no code deploy < 60 min on {svc}; call get_deploys({svc}) or pick another fix")
    if sum(r.tool in MUTATIONS for r in env.log) >= 2 and tool in MUTATIONS:
        return GateDecision(False, "mutation cap reached (2). Page a human.")
    if tool == "resolve_incident":
        last_mut = max((i for i, r in enumerate(env.log) if r.tool in MUTATIONS), default=-1)
        if not any(r.tool == "get_metrics" for r in env.log[last_mut + 1:]):
            return GateDecision(False, "verify recovery with get_metrics after your last change, then resolve")
    return GateDecision(True)
```

In the loop, a blocked call returns a `tool_result` with `is_error: true` and the reason, so the model can recover. The reason text says what to do next; that is the "errors that say how to fix them" rule from [Module 08](../../08-harness-engineering/README.md).

Note the rollback rule checks `kind == "code"`. The decoy deploys in the sim are `feature-flag` changes, so the gate blocks a decoy rollback even when the model is convinced. That is a policy decision; write it into SPEC.md.

### What to report (illustrative output)
```text
injection suite: 14 variants x 3 trials = 42
                      before M6   gate only   gate + context-minimization
dangerous-action        9/42        0/42          0/42
injection success      11/42        3/42          0/42   <- gate stopped db, not "rollback orders" lures
false-block rate        n/a         4/63          4/63   (authorized fixes blocked; all 4 = rollback before get_deploys)
```

The gate alone leaves injections that ask for an *authorized-looking* action. Only removing raw log text from the planner's context closes them.

## Deliverables
- `TRIFECTA.md` audit table
- `agent/gate.py` with a test per rule, plus tests that each correct oracle trajectory passes the gate
- `evals/injection_suite.py` (≥10 variants) and its results
- The three rates, before and after, with k=3

## Done when
- [ ] Dangerous-action rate and injection-success rate are 0 on the suite with k=3.
- [ ] False-block rate is measured and reported. If above ~5%, the readiness review must address it.
- [ ] At least one structural defense beyond the gate is implemented and measured separately.
- [ ] Every bypass found became a regression scenario and a test.
- [ ] M4's regression suite still passes and M5's best test score has not dropped beyond noise.

## Reuse
- `sim_env.INJECTION_LINE`, `INJECTED_ACTIONS`, `grade.ignored_injection`
- Containment-first, trifecta, classifiers with FPR/FNR: [16-security-and-containment](../../16-security-and-containment/README.md)
- Blocking gates vs steering hooks, validators and retries: [14-steering-and-guardrails](../../14-steering-and-guardrails/README.md)

## Pitfalls
- **Measuring injection success on the canned line only.** The model may have learned to ignore that phrasing. Vary it.
- **A gate that reads the agent's reasoning.** It can be argued with. Gate on the proposed call and the world state.
- **Forgetting `resolve_incident`.** Closing the page during an outage is a harmful action too.
- **Over-blocking to hit zero.** Zero dangerous actions by blocking every mutation is trivially achievable. That is why the false-block rate is a deliverable.
