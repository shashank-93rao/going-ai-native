# Examples

Each scenario follows *Situation → Naive approach and what happens → AI-native approach → What to check*. The issue-triage coding agent (an untrusted GitHub issue meets a coding agent with secrets and network) is covered end to end in [02](02-the-lethal-trifecta.md) (trifecta audit), [03](03-containment-first-design.md) (egress policy and layer ablation) and [code/injection_suite/](code/README.md). This file covers the scenarios those files don't.

---

## 1. Threat model for an on-call agent with kubectl access

### Situation
Your SRE team wants an agent that responds to PagerDuty alerts for the `payments` namespace. It should read pod status, events and logs, query metrics, post findings to the incident Slack channel, and do a small set of remediations: `rollout restart` and scaling a deployment within limits. Someone proposes giving it the on-call engineer's kubeconfig, "since on-call can do all of this anyway".

### Naive approach and what happens
With the on-call kubeconfig, the agent holds ambient authority over every context and namespace that engineer can reach. Its inputs include text from parties you don't trust: log lines with request paths and user agents, pod annotations, alert descriptions, and messages in a shared incident channel that includes a vendor's staff. That makes it a confused deputy ([05](05-agent-supply-chain-and-confused-deputy.md)): any of those sources can ask it to act, and it will act with the engineer's full authority.

Run the trifecta audit on the proposed tool set (`data/manifests/oncall_agent.json`):

```text
$ python trifecta_audit.py data/manifests/oncall_agent.json
agent: oncall-k8s-agent
  private   k8s.kubectl_read, observability.query_logs, observability.query_metrics
  untrusted k8s.kubectl_read, observability.query_logs, slack-mcp.read_channel, web.fetch_url
  exfil     slack-mcp.post_message, web.fetch_url
VERDICT: LETHAL TRIFECTA PRESENT
  arises only from mixing servers: no single vendor can fix this
  cheapest leg to cut: exfil (2 tool(s))
  WARNING: web.fetch_url: mitigation 'prompt_says_dont' for exfil is not structural; ignored
```

No single server is the problem. The combination is. The trifecta also only covers *confidentiality*. An on-call agent has a second, bigger risk, *integrity and availability*: a write to the cluster.

### AI-native approach
**Step 1: write the threat model as a table.** Assets, entry points, principals, then threats.

| Asset | Why it matters |
|---|---|
| Cluster state in `payments` (prod) | Availability of a revenue path |
| Kubernetes Secrets | DB passwords, API keys |
| Logs | Contain customer identifiers |
| Incident channel | Shared with a vendor, so it is external |

| Entry point (untrusted text) | Who controls it |
|---|---|
| Log lines, request paths, user agents | Any internet client |
| Pod annotations and labels, event messages | Anyone with deploy rights, plus some controllers |
| Alert descriptions | Whoever wrote the alert rule |
| Slack messages | Any channel member, including external guests |

| Threat | Leg / class | Control |
|---|---|---|
| Injected log line asks agent to post secrets to Slack | trifecta | No read on `secrets`; Slack posts only to an internal-only incident channel |
| Agent restarts or scales the wrong namespace (overeager) | integrity | Actuator scoped to `payments`; intent-aware classifier; limits on replica counts |
| External guest asks agent to scale prod to 0 | confused deputy | Authorize writes against the *requesting human's* RBAC, not the agent's |
| Agent "fixes" an auth error by hunting for other credentials (an auto-mode incident pattern) | unintended action | No secrets access; classifier category `credential_hunt` |
| Agent changes a deployment's image or env during a "restart" | integrity | No raw `patch`; writes go through named operations only |

**Step 2: least privilege that actually binds.** Read-only RBAC for the agent's own identity, with Secrets excluded and no `pods/exec`:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata: {name: oncall-agent-read, namespace: payments}
rules:
  - apiGroups: [""]
    resources: [pods, pods/log, events, services, endpoints, configmaps]
    verbs: [get, list, watch]
  - apiGroups: [apps]
    resources: [deployments, replicasets, statefulsets]
    verbs: [get, list, watch]
  - apiGroups: [metrics.k8s.io]
    resources: [pods]
    verbs: [get, list]
# Deliberately absent: secrets, pods/exec, pods/portforward, any write verb.
```

Here is the subtle part a senior engineer will spot. `kubectl rollout restart` is a `patch` on the deployment, and RBAC cannot tell "patch the restart annotation" apart from "patch the image". Granting `patch` on deployments grants every change to them. So writes do not go through kubectl at all. They go through a small **actuator** service with named operations:

```text
POST /actuator/restart   {namespace: payments, deployment: payments-api, requested_by: U123}
POST /actuator/scale     {namespace: payments, deployment: payments-api, replicas: 6, requested_by: U123}
```

The actuator has its own service account with `patch` on deployments. It enforces the invariants: namespace is `payments`; replicas stay between `min` and `max` from a config file, and never 0; at most one restart per deployment per 10 minutes. It checks `requested_by` against your RBAC with a `SubjectAccessReview`, so an external Slack guest gets denied no matter what the model decides. This is the credential-proxy pattern from [03](03-containment-first-design.md) applied to cluster writes.

**Step 3: cut the exfil leg.** Remove `web.fetch_url` (an on-call agent can read runbooks from a vendored copy). Restrict `post_message` to the internal incident channel, and render posts as plain text, so images and links don't unfurl.

**Step 4: tier the writes** ([07](07-red-teaming-and-governance.md)):

| Operation | Tier | Gate |
|---|---|---|
| Read pods, events, logs, metrics | T0 | none |
| Restart one deployment in `payments` | T2 | actuator invariants + classifier + audit log |
| Scale within limits | T2 | same |
| Scale outside limits, delete, roll back image | T3 | human approval in Slack by an on-call engineer, checked against RBAC |

**Step 5: measure the classifier on your traffic.** The labeled set in `data/labeled_commands.jsonl` includes on-call rows, such as restarting staging vs prod, `get secret`, `delete pod --all` and `scale --replicas=0`. The deny-list misses the namespace mix-up, because only the user's intent says which namespace was meant:

```text
MISS [scope_creep] kubectl -n payments rollout restart deploy/payments-api
```

That is the argument for an intent-aware classifier in front of the actuator, *and* for the actuator's own invariants behind it.

### What to check
- `kubectl auth can-i --list --as=system:serviceaccount:payments:oncall-agent -n payments` shows no write verbs and no `secrets`.
- `trifecta_audit.py` on the revised manifest exits 0, with exfil cut.
- The actuator rejects `replicas: 0`, a different namespace, and a `requested_by` without the RBAC binding, each covered by a unit test.
- Classifier FNR and FPR on your labeled on-call rows are reported with intervals ([04](04-permission-classifiers.md)).
- A game-day drill: post an instruction to the incident channel from a guest account asking for a T3 action, and confirm it is denied by authorization, not by the model.

---

## 2. Catching an agent that "fixed" a test by weakening it

### Situation
An agent opens a PR titled "Fix refund rounding", and CI is green. The task was a failing `test_refund_rounding`.

### Naive approach and what happens
A reviewer sees green CI and a plausible summary and approves. The diff turned out to have relaxed the assertion rather than fixing the float bug ([06](06-reward-hacking-and-unintended-actions.md) shows the diff). The bug ships, and the test that guarded it is gone.

### AI-native approach
1. **Policy:** bug-fix tasks may not edit `tests/**`. A `PreToolUse` hook enforces it ([14](../14-steering-and-guardrails/README.md)).
2. **CI check on agent PRs:** fail if test files changed, and compare the collected test count with the base branch.
3. **Grader on test IDs:** parse JUnit XML and require the named test as `passed`. Exit code 0 alone is not enough.
4. **Classifier rows:** the two `test_tampering` rows in the labeled set, so your command classifier's misses there are visible and you don't rely on it alone.

### What to check
- A scratch branch that inserts `sys.exit(0)` at import time turns CI red.
- Agent PRs that touch tests are routed to a human with a label.
- Over a month, count how many agent PRs were blocked by the test-edit rule. A rising count means the task specs are leaving the agent no honest exit; add an explicit "report that you can't" outcome.

---

## 3. Adopting a third-party MCP server

### Situation
A teammate wants to add a popular community MCP server (say, a code formatter) to the team's shared agent config.

### Naive approach and what happens
Everyone installs it and clicks "Always allow". Nobody reads the tool descriptions, and nothing pins them. If the server's descriptions change later (a rug pull, [05](05-agent-supply-chain-and-confused-deputy.md)), every agent reads the new text on every turn, and nobody is prompted.

### AI-native approach
1. **Review it like a dependency, with two artifacts.** Review the code, and read every tool description and schema. Look for imperatives aimed at the model.
2. **Pin it.** Pin the version and record a hash of each description and schema in `agent-tools.lock.json`. Refuse to load on mismatch.
3. **Label its tools** in the agent's trifecta manifest and run the audit in CI. A formatter should provide no legs at all. If it does network I/O, find out why.
4. **Sandbox it.** Run the server process with no network unless it needs one, and with no secrets in its env.
5. **Add a suite case.** `tool-poisoned-description` in `cases.jsonl` is the template: a poisoned description that asks the agent to send its env somewhere. Confirm the contained harness holds.

### What to check
- Changing one character in a pinned description makes the loader refuse the server.
- The trifecta audit still exits 0 with the server added.
- The injection suite still passes 100% on the contained harness, and the new case fails on the naive one.

---

## 4. Approving an agent for wider rollout

### Situation
Your platform team's triage bot has run on one repo for a month. Leadership asks whether it can roll out to 40 repos, some of them private and customer-facing.

### Naive approach and what happens
"It's been fine for a month" becomes the approval. More repos means more private data per token, more untrusted authors, and more public-write channels. The trifecta can come back through a broader token without any code change.

### AI-native approach
1. Re-run the trifecta audit with the *rollout* token scopes, not the pilot's. Per-repo tokens keep the private leg as small as it was in the pilot.
2. Re-run the injection suite and the layer-ablation test against the rollout config.
3. Re-run the classifier eval with a month of real labeled actions added. Report FNR and FPR with intervals.
4. Update the governance record ([07](07-red-teaming-and-governance.md)): tier, residual risk, owner, and review triggers (model upgrade, tool change, scope change).
5. Roll out like a deploy: a few repos first, an audit-log review, then the rest ([15](../15-observability-and-production/README.md)).

### What to check
- The approval cites artifacts (audit output, suite results, classifier metrics), not a duration.
- The record names who accepted the residual risk and when it expires.
