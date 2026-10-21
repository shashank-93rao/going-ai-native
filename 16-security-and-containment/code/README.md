# Code: 16-security-and-containment

Everything runs offline. Scripts use `get_client(fake=...)`, so they call the real API only when `ANTHROPIC_API_KEY` is set and `AINATIVE_FAKE` is not.

From the course root:

```bash
.venv/bin/python -m pytest -q 16-security-and-containment/code      # all tests
cd 16-security-and-containment/code
export PYTHONPATH=../../shared                                       # for ainative_kit in scripts
```

| File | What it does | Run |
|---|---|---|
| `trifecta_audit.py` | Reads a tool manifest (JSON), unions the legs across servers, flags the trifecta, single-tool trifectas and cross-server trifectas, ignores non-structural mitigations, and fails closed on unlabeled tools. Exit 1 if a trifecta is present, so CI can gate on it. | `python trifecta_audit.py data/manifests/coding_agent.json` |
| `egress_proxy_policy.py` | `decide(request, policy)`: default-deny egress with capability rules (host, methods, path prefixes with boundaries, credential injection, size caps). Rejects IP literals (including decimal and hex), userinfo, odd ports, lookalike hosts and caller-supplied auth on credentialed hosts. | `python egress_proxy_policy.py` |
| `injection_suite/cases.jsonl` | 11 benign attack cases plus 1 control. Payloads target a canary and reserved `*.example` domains. | |
| `injection_suite/triage_agent.py` | A plain tool-use loop and a simulated world, plus two harnesses: `NAIVE` and `CONTAINED` (credential proxy, egress proxy, least privilege, approval queue). | |
| `injection_suite/injection_runner.py` | Runs every case against a **compromised** FakeClient that always obeys the injection, then checks that the canary never left (egress, comments, PRs, final answer), forbidden tools never executed, the payload was actually delivered, and control work still ran. | `python injection_suite/injection_runner.py` |
| `permission_classifier_eval.py` | FNR/FPR with Wilson intervals for a deny-list, a strict read-only stage 1, a reasoning-blind LLM classifier, and a two-stage pipeline, over `data/labeled_commands.jsonl` (44 rows). Offline, the LLM is a label-oracle fake with two planted errors, so its numbers are a demo. | `python permission_classifier_eval.py` |

Tests:
- `test_trifecta_audit.py`: verdicts on the three manifests, fail-closed behavior, CLI exit codes.
- `test_egress_proxy_policy.py`: legitimate requests, 19 bypass attempts, method and path scoping, the credential rule, size caps, and a Hypothesis fuzz.
- `test_injection_suite.py`: contained harness passes every case; naive fails every attack case; **layer ablation**, where removing each layer causes a specific set of cases to fail; and checks that the canary never enters context, that unoffered tools are rejected and traced, and that PRs are queued.
- `test_permission_classifier_eval.py`: metric definitions, Wilson values, the rules-miss-intent property, the stage-1 trade-off, reasoning-blind input and fail-closed parsing, and two-stage behavior.

No extra packages are needed beyond the course venv (`hypothesis` is already there).
