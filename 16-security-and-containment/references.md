# References

## Prompt injection and the trifecta
- Simon Willison, ["Prompt injection attacks against GPT-3"](https://simonwillison.net/2022/Sep/12/prompt-injection/) (2022-09-12). The post that named the attack, credited to Riley Goodside's demonstrations. *Take:* the SQL-injection analogy, and why there is no parameterised-query equivalent.
- Simon Willison, ["The lethal trifecta for AI agents"](https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/) (2025-06-16). *Take:* the three legs; "95% is a failing grade"; MCP lets users assemble the trifecta themselves.
- Simon Willison, ["Design patterns for securing LLM agents against prompt injections"](https://simonwillison.net/2025/Jun/13/prompt-injection-design-patterns/) (2025-06-13), summarising Beurer-Kellner et al., [arXiv 2506.08837](https://arxiv.org/abs/2506.08837). *Take:* the six patterns, and the paper's view that general-purpose agents are unlikely to give reliable safety guarantees.
- Anthropic, ["Mitigating the risk of prompt injections in browser use"](https://www.anthropic.com/research/prompt-injection-defenses) (2025-11). *Take:* layered defenses, and 1% adaptive attack success described as still meaningful risk. Later posts say the setup isn't comparable to current numbers.

## Containment
- Anthropic, ["How we contain Claude across products"](https://www.anthropic.com/engineering/how-we-contain-claude) (2026-05). *Take:* risk = likelihood × blast radius; allowlists as capability grants; credentials out of the sandbox; pre-trust code paths; "the weakest layer is the one you built yourself"; 24/25 phishing red-team result; Gray Swan numbers.
- Anthropic, ["Beyond permission prompts: making Claude Code more secure and autonomous"](https://www.anthropic.com/engineering/claude-code-sandboxing) (2025-10). *Take:* filesystem *and* network isolation; the proxy over a Unix socket; the git credential proxy; 84% fewer prompts.
- Anthropic, ["Scaling Managed Agents"](https://www.anthropic.com/engineering/managed-agents) (2026-04). *Take:* cattle sandboxes; tokens used only at clone time; OAuth tokens behind a vault and MCP proxy.
- Simon Willison, ["Designing agentic loops"](https://simonwillison.net/2025/Sep/30/designing-agentic-loops/) (2025-09). *Take:* sandbox YOLO runs; scoped staging credentials; budget-capped orgs for anything that can spend money.

## Permission classifiers
- Anthropic, ["How we built Claude Code auto mode"](https://www.anthropic.com/engineering/claude-code-auto-mode) (2026-03). *Take:* 93% approval fatigue; tiers; reasoning-blind transcript classifier; two-stage design; FPR 0.4% (n=10,000), FNR 17% (n=52), 5.7% synthetic exfil (n=1,000); stage-1-only numbers; escalation after 3 consecutive or 20 total denials. The Wilson intervals in [04](04-permission-classifiers.md) are our calculation, not Anthropic's.

## Agent supply chain and confused deputy
- Invariant Labs, ["MCP Security Notification: Tool Poisoning Attacks"](https://invariantlabs.ai/blog/mcp-security-notification-tool-poisoning-attacks) (2025-04-01). *Take:* poisoning, rug pulls, shadowing; pin and hash descriptions.
- Invariant Labs, ["GitHub MCP exploited"](https://invariantlabs.ai/blog/mcp-github-vulnerability) (2025-05-26). *Take:* the canonical cross-repo trifecta case; least privilege per session.
- Claude Code docs, [Agent teams](https://code.claude.com/docs/en/agent-teams) (living docs, checked 2026-10-19). *Take:* messages between agents are marked as not from the user; a teammate can't approve on your behalf.
- Claude Code docs, [Hooks guide](https://code.claude.com/docs/en/hooks-guide). *Take:* hooks are deterministic code; a plugin's hooks are code you're installing.
- Norm Hardy, "The Confused Deputy (or why capabilities might have been invented)", ACM SIGOPS Operating Systems Review, 1988. *Take:* the original framing; authority should travel with the request.

## Reward hacking, unintended actions, sycophancy
- Anthropic, ["From shortcuts to sabotage: natural emergent misalignment from reward hacking"](https://www.anthropic.com/research/emergent-misalignment-reward-hacking) (2025-11). *Take:* the `sys.exit(0)` hack; 12% sabotage; 50% alignment-faking reasoning; RLHF makes misalignment context-dependent; inoculation prompting.
- Anthropic, ["Investigating unintended model actions in evaluations and internal use"](https://www.anthropic.com/research/investigating-unintended-model-actions) (2026-10). *Take:* the four categories; root causes; live internet off for all internal evals for now.
- OpenAI, ["Expanding on what we missed with sycophancy"](https://openai.com/index/expanding-on-sycophancy/) (2025-05). *Take:* a reward-signal change, passing aggregate evals, and no targeted sycophancy eval.
- Andrej Karpathy, [autoresearch](https://github.com/karpathy/autoresearch) (2026-03). *Take:* freeze the evaluator outside the agent's write scope.

## Red-teaming and governance
- Hamel Husain and Shreya Shankar, [AI Evals for Engineers & PMs](https://maven.com/parlance-labs/evals), L7 Safety (syllabus as summarised in `research/curricula.md`; we did not re-fetch the syllabus document). *Take:* authorization must hold when the model is compromised; red-team findings become failing tests; NIST AI RMF governance record.
- promptfoo, [LLM red teaming docs](https://www.promptfoo.dev/docs/red-team/). *Take:* plugins per failure mode, CI integration, token-cost warning.
- OWASP GenAI Security Project, [Top 10 for Agentic Applications](https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/) (published 2025-12). *Take:* a category checklist for your suite. We did not verify the exact category names against OWASP's document.
- NIST, [AI Risk Management Framework](https://www.nist.gov/itl/ai-risk-management-framework) (AI RMF 1.0, NIST AI 100-1, Jan 2023), and the Generative AI Profile, [NIST AI 600-1](https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf) (Jul 2024). *Take:* Govern / Map / Measure / Manage; voluntary.
- [Regulation (EU) 2024/1689 (AI Act)](https://eur-lex.europa.eu/eli/reg/2024/1689/oj). *Take:* use-based obligations. The Digital Omnibus delay to high-risk dates was provisionally agreed in May 2026 according to secondary legal commentary, for example [Sidley, 2026-06-22](https://datamatters.sidley.com/2026/06/22/eu-lawmakers-reach-provisional-agreement-to-delay-key-eu-ai-act-obligations/). Final adoption is unverified.
- OpenAI, ["A practical guide to building agents"](https://cdn.openai.com/business-guides-and-resources/a-practical-guide-to-building-agents.pdf) (2025). *Take:* per-tool risk ratings by read/write, reversibility and financial impact.
