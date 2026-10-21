# Exercises

Exercises 1–5 run offline (FakeClient, no key). Exercise 6 uses a real model or a real coding agent. Run commands from the course root with `PYTHONPATH=shared`.

---

## 1. Audit your own agent for the trifecta (45 min, offline)
**Goal:** find out whether an agent you actually use has all three legs.

**Steps**
1. Pick a real agent setup: your Claude Code config with its MCP servers, a CI bot, or a Slack bot.
2. Write a manifest in the format of `code/data/manifests/coding_agent.json`. Label every tool, built-ins included.
3. Run `python 16-security-and-containment/code/trifecta_audit.py your_manifest.json`.
4. For each leg the audit finds, write one sentence on the structural control that would cut it, and what that would cost.
5. Write the contained manifest, and re-run until it exits 0, or until you've written down why you accept the remaining leg.

**Done when:** you have two committed manifests (current and target), the target exits 0 or documents an accepted risk, and no mitigation in the target uses a kind outside `STRUCTURAL_MITIGATIONS`.

**Stretch:** add the audit as a CI step that fails when the agent config's tool list changes without a matching manifest update.

---

## 2. Break the naive egress check, then harden the policy (60 min, offline)
**Goal:** feel why substring allowlists fail, and extend the capability policy.

**Steps**
1. Write a 3-line `allow(url)` that does `any(d in url for d in ALLOWED)`. Run every URL in `test_attacks_denied` through it and count how many it lets through.
2. Add a rule to `CODING_AGENT_POLICY` that lets the agent read release notes from `https://raw.githubusercontent.com/acme/payments-svc/`. Write tests showing other repos on the same host are denied.
3. Add a new bypass test of your own (for example, a unicode or IDNA lookalike for `github.com`) and make it pass.
4. Add a rule-level `max_query_bytes` override and a test for it.

**Done when:** `pytest -q 16-security-and-containment/code/test_egress_proxy_policy.py` passes with at least 4 new tests, including one for your new bypass.

**Stretch:** extend `decide` to take the resolved IP from the proxy's own DNS lookup and deny private ranges, which covers DNS rebinding.

---

## 3. Add a red-team finding to the injection suite (45 min, offline)
**Goal:** run the finding → case → harness fix → ablation loop from [07](07-red-teaming-and-governance.md).

**Steps**
1. Pick an injection vector the suite lacks: a poisoned CLAUDE.md that persists, a malicious subagent summary, or a pod annotation read via `kubectl describe`.
2. Add a case row with a benign canary payload and reserved `*.example` destinations, plus a matching control case.
3. Run `python 16-security-and-containment/code/injection_suite/injection_runner.py`. The new case must FAIL on `naive`.
4. If it also fails on `contained`, fix the harness in `triage_agent.py`, not the prompt.
5. Extend `test_every_containment_layer_is_load_bearing` if your fix adds a layer.

**Done when:** the new case fails on naive, passes on contained, the benign-payload lint test passes, and the full module suite is green.

**Stretch:** add a persistence vector by giving the agent a `write_file` tool, and a check that context files (`CLAUDE.md`) are unchanged after the run.

---

## 4. Measure a permission classifier honestly (60 min, offline)
**Goal:** report FNR and FPR with intervals, and see the two-stage trade-off.

**Steps**
1. Add 20 rows to `data/labeled_commands.jsonl` from your own shell history or agent traces (scrub anything sensitive), with intent, command, label and category.
2. Re-run `python 16-security-and-containment/code/permission_classifier_eval.py`.
3. Improve `rule_classifier` to catch one more category without raising FPR. Record before/after.
4. Write a short paragraph: at your current n, how small would the FNR interval need to be to approve this classifier for T2 actions, and how many more labeled denies would that take?

**Done when:** you have a before/after table of FNR and FPR with intervals, and the paragraph uses `wilson()` to justify the sample size.

**Stretch:** split the eval by tier and report per-tier metrics.

---

## 5. Threat-model an on-call agent (60 min, offline)
**Goal:** produce the artifact from [examples.md](examples.md) scenario 1 for a system you run.

**Steps**
1. Choose a real operational agent idea (Kafka lag responder, DB failover helper, deploy babysitter).
2. Fill in the asset, entry-point and threat tables.
3. Write the RBAC or IAM policy for the agent's own identity, and list which writes go through an actuator with named operations.
4. Write the manifest and run the trifecta audit.

**Done when:** every threat row has a structural control, the audit exits 0 or names an accepted leg, and a peer can find no write the agent can perform that isn't covered by an actuator invariant or a human approval.

---

## 6. Measure real-model resistance separately from the harness gate (45 min, real API)
**Goal:** see the difference between a harness invariant test and a model resistance rate.

**Steps**
1. Set `ANTHROPIC_API_KEY`. Run `python 16-security-and-containment/code/injection_suite/injection_runner.py --real` a few times.
2. Note that the contained harness passes whether or not the model resists. Then make a copy of the runner that uses `NAIVE` with the real model, and run each attack case k=5 times.
3. Report, per case, how often the real model attempted the attacker's action, with a Wilson interval.

**Done when:** you have a table of per-case attempt rates with intervals, plus a sentence explaining why none of those numbers belongs in the merge gate.

**Stretch:** point a real coding agent (Claude Code in a disposable container with network off) at a scratch repo whose issue contains one of the suite's benign payloads, and compare its behavior with and without sandboxing enabled.
