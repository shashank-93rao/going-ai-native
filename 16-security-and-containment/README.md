# 16: Security and Containment
> After this module you can threat-model an agent, find the lethal trifecta in its tool set, contain it so that a fully compromised model still cannot leak or destroy anything that matters, and prove that with a regression suite and measured classifier error rates.

## Why this matters
An agent is an LLM in a loop with tools. Every token it reads, from an issue body, a log line, a web page or a tool description, can steer what it does next. Nobody knows how to make a model reliably tell your instructions apart from an attacker's text when both sit in the same context window. Simon Willison has been writing about this since he named prompt injection in 2022, and in 2025 he still put it bluntly: "we still don't know how to 100% reliably prevent this" ([Willison, "The lethal trifecta"](https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/)).

Model-level defenses have improved, but they are probabilistic. Anthropic reports that Claude Opus 4.7 had about 0.1% attack success on single attempts in Gray Swan's benchmark, rising to about 5–6% after 100 adaptive attempts ([Anthropic, "How we contain Claude"](https://www.anthropic.com/engineering/how-we-contain-claude)). In an internal phishing exercise, where the malicious instruction came from the user, the prompt got Claude to exfiltrate credentials 24 times out of 25. Model-layer defenses could not catch that, because the instruction came from the person in charge. An attacker gets to retry, so any per-attempt rate above zero eventually becomes an incident.

The engineering response is the same one you already use for untrusted code: **assume compromise and cap the blast radius.** You stop asking "will the model resist?" and start asking "if the model does exactly what the attacker says, what can it reach?" That question has a checkable answer, and the answer lives in the harness: the sandbox, the egress proxy, the credential proxy, the tool list, the permission classifier. This module teaches you to build those pieces, measure them, and keep them from regressing.

This is the course thesis in its sharpest form. *Autonomy should scale with verifiability*, and for security the property you verify is not "the agent behaves well". It is "the agent **cannot** do X", enforced by something that is not a language model.

## The distributed-systems anchor
**Zero trust and blast-radius reduction.** In a zero-trust network you stop trusting traffic because of where it comes from. Every request is authenticated and authorized at the point of use, and you segment the network so one compromised host cannot reach everything. Cells, bulkheads and per-service IAM roles exist so that a failure, or an attacker, stays inside one box.

Map it across:

| Zero-trust / blast radius | Agent containment |
|---|---|
| Compromised host inside the perimeter | Model that has read an injected instruction |
| Egress firewall, default deny | Egress proxy with a capability allowlist |
| Secrets manager plus workload identity; app never holds the root key | Credential proxy; the agent never sees the token |
| Per-service IAM role, least privilege | Per-task tool list and scoped tokens |
| Admission controller | Permission classifier and approval queue |
| Chaos/pen test findings become regression checks | Red-team findings become injection-suite cases |

**Where the analogy breaks.** A compromised host runs the attacker's code deterministically. A "compromised" model is probabilistic. It obeys the injection some of the time, and you cannot tell from outside which run you are in. Worse, the confused deputy is built in: the model *is* the trusted service, and it takes instructions through the same channel it takes data. In networking you can separate the control plane from the data plane. An LLM has no such separation, which is why the fix has to be outside the model.

## Learning goals
- [ ] Explain direct vs indirect prompt injection and why classifiers and system-prompt warnings cannot make it safe
- [ ] Audit any agent's tool manifest for the lethal trifecta and name the cheapest leg to cut (`trifecta_audit.py`)
- [ ] Write an egress policy as capability grants (host + method + path + credential rules) and test it against bypass tricks (`egress_proxy_policy.py`)
- [ ] Design a credential proxy so the agent never holds a secret, and explain the pre-trust code-path class of bugs
- [ ] Measure a permission classifier's FPR and FNR with confidence intervals, and explain why a two-stage pipeline trades one for the other (`permission_classifier_eval.py`)
- [ ] Recognise MCP tool poisoning, rug pulls, skill and plugin supply-chain risk, and confused-deputy patterns
- [ ] Detect reward hacking in a coding agent's diff (test tampering, special-casing, verification skipping)
- [ ] Turn a red-team finding into a regression case that runs against a *compromised* fake model (`injection_suite/`)
- [ ] Write a one-page risk-tier and governance record that references NIST AI RMF and, where relevant, the EU AI Act

## Reading order
1. [01-prompt-injection.md](01-prompt-injection.md): direct vs indirect injection, and why it is still unsolved
2. [02-the-lethal-trifecta.md](02-the-lethal-trifecta.md): private data + untrusted content + exfiltration; break one leg
3. [03-containment-first-design.md](03-containment-first-design.md): sandboxes, egress as a capability, credential proxies, least privilege, pre-trust code paths
4. [04-permission-classifiers.md](04-permission-classifiers.md): replacing approval fatigue with a classifier, and measuring FPR/FNR honestly
5. [05-agent-supply-chain-and-confused-deputy.md](05-agent-supply-chain-and-confused-deputy.md): MCP tool poisoning, skills and plugins, confused deputy
6. [06-reward-hacking-and-unintended-actions.md](06-reward-hacking-and-unintended-actions.md): test tampering, special-casing, sycophancy, persistence
7. [07-red-teaming-and-governance.md](07-red-teaming-and-governance.md): attacks become regression tests; risk tiers, NIST AI RMF, EU AI Act
- [examples.md](examples.md), [exercises.md](exercises.md), [references.md](references.md), [code/](code/README.md)

## Prerequisites
- [05: Tools, MCP, skills, hooks and execution environments](../05-tools-mcp-skills-hooks/README.md): what a tool manifest and a sandbox are
- [10: Evals fundamentals](../10-evals-fundamentals/README.md): code graders, regression vs capability evals
- [14: Steering and guardrails](../14-steering-and-guardrails/README.md): hooks as blocking gates; this module explains why guardrails are not a security boundary
- Helpful: [13: Testing agentic systems](../13-testing-agentic-systems/README.md) for deterministic worlds and fakes

## Key takeaways
- Prompt injection is unsolved. Design as if the model will follow any instruction it reads, because sometimes it will.
- The lethal trifecta (private data, untrusted content, a way to send data out) is a property of the *union* of an agent's tools. If all three are present, assume exfiltration. Remove a leg, usually the outbound one.
- Containment beats detection. A detector that is 95% accurate is a failing grade against an adversary who retries. A default-deny egress proxy is 100% for the paths it blocks.
- An allowlisted domain is a capability grant, not a destination. Write rules as host + method + path + credential policy, and refuse caller-supplied credentials on hosts where the proxy injects its own.
- Secrets the agent never sees cannot leak. Hold credentials in a proxy outside the sandbox and attach them per request after checking the operation.
- A permission classifier is a binary classifier. Report its FNR (missed dangerous actions) and FPR (friction) on labeled real traffic, with intervals, and track both.
- Reward hacking is a security signal, not a style problem. Freeze graders and tests outside the agent's write scope, and diff-check for test tampering.
- Every successful red-team attack becomes a regression case that runs against a *compromised* fake model. Every containment layer should have at least one case that fails when that layer is removed.
