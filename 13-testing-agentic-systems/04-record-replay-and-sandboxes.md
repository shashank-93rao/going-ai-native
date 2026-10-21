# 04: Record/replay, and the environment ladder up to sandboxes

## The idea
A simulated world fakes the *environment*. **Record/replay** fakes the *model*. You run the agent once against the real API with a `RecordingClient`, which writes each request hash and response to a JSONL **cassette**. Later runs use a `ReplayClient`, which serves the recorded response for each request and fails loudly on any request it hasn't seen. You get the real model's behavior, offline, deterministically, for free. It's VCR.py for LLM calls, and it's in `ainative_kit`.

The catch is in what the request hash covers. In `ainative_kit` it is `sha256(messages + kwargs)`: the full message list (tool results included) plus whatever keyword arguments the caller passed. Anything that changes the request misses the cassette. That is the honest case. Anything that changes behavior *without* changing the request replays green. That is the lie.

Replay is one rung on an **environment ladder**: scripted fake → seeded simulation → cassette replay → hermetic sandbox with real tools → staging → production. Each rung up buys fidelity and costs determinism, money, and blast radius. Sandboxes are the rung where the agent runs real commands against real software, contained so that a bad action can't reach anything that matters.

## Why it matters
Cassettes make agent tests cheap enough to run on every commit. A 20-step run costs 20 model calls once and zero after that. They also make a test that was flaky because of model sampling reproducible: you froze one sample.

That second point is the danger. A frozen sample says nothing about the distribution it came from. If the recorded run happened to be one of the 35 out of 40 that pass, replay passes forever, while the live agent fails 1 run in 8.

Sandboxes matter because the top rungs are where agents cause real damage. Anthropic reports that sandboxing Claude Code cut permission prompts by 84%, and that in the cloud version git credentials stay outside the sandbox while a proxy checks the push target before attaching the token ([Anthropic, "Claude Code sandboxing"](https://www.anthropic.com/engineering/claude-code-sandboxing)). Stripe runs its coding agents in isolated, pre-warmed devboxes that are cut off from production and the internet, which is what lets them run without per-action prompts ([Stripe, "Minions"](https://stripe.dev/blog/minions-stripes-one-shot-end-to-end-coding-agents)). Anthropic also found that an unisolated eval harness leaks between trials: Claude once used git history left by earlier trials, and shared memory limits caused correlated failures ([Anthropic, "Demystifying evals"](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)).

## How it works

### Recording and replaying (`replay_demo.py`)
```python
def record(cassette, *, system=SYSTEM, seed=7):
    inner = get_client(fake=FakeClient(promote_policy()))   # real API when a key is set
    rec = RecordingClient(inner, cassette)
    run = run_agent(rec, OpsWorld(seed=seed), TASK, system=system)
    Path(f"{cassette}.meta.json").write_text(json.dumps(meta_for(system, world_seed=seed)))
    return run

def replay(cassette, *, system=SYSTEM, seed=7, faults=None):
    return run_agent(ReplayClient(cassette), OpsWorld(seed=seed, faults=faults), TASK, system=system)
```

Notice that replay re-executes the tools against a fresh simulated world. The model is replayed and the environment is live. That's the useful combination. If someone changes `world.py` so that `deploy` returns a different payload, the next request contains a different tool result, the cassette misses, and you learn that your agent test depends on that payload.

### When replay lies
Running `python replay_demo.py` prints:

```text
recorded 5 model calls -> /tmp/.../deploy.jsonl
1. replay, nothing changed: identical trajectory = True
2. replay after a prompt edit: cassette miss, as it should be ('No recorded response for request 24b03cf09df788a3; re-record the cassette')
3. replay after the world changed (tool now returns 503): cassette miss, as it should be
4. replay after a model upgrade: replays GREEN (4 steps) but meta says stale: ["model: recorded 'claude-sonnet-5-5', now 'claude-opus-5-5'"]
```

Cases 2 and 3 are honest misses. Case 4 is the lie. `run_agent` doesn't pass `model=` to `complete()`, because the client holds the model ID, so the model is not in the hash. Upgrade the model and every cassette still replays. Your CI is green, and none of that green says anything about the new model. The fix is a **sidecar metadata file** with the prompt hash, tool-schema hash and model ID, plus a staleness check that fails CI or forces a re-record:

```python
def cassette_staleness(cassette, *, system=SYSTEM, model=DEFAULT_MODEL) -> list[str]:
    meta = json.loads(Path(f"{cassette}.meta.json").read_text())
    now = meta_for(system, model=model, world_seed=meta["world_seed"])
    return [f"{k}: recorded {meta[k]!r}, now {now[k]!r}"
            for k in ("system_sha", "tools_sha", "model") if meta[k] != now[k]]
```

The full list of ways replay lies (*course synthesis*):

| Lie | Why it happens | Guard |
|---|---|---|
| Model upgraded, replay still green | Model ID not in the request hash | Model ID in the metadata, plus a staleness check |
| Sampling settings changed | `temperature` or effort set on the client, not passed per call | Put them in the metadata too |
| One sample frozen | The cassette holds 1 draw from a distribution | Use replay for regression *plumbing*. Use N live runs for *behavior* ([05](05-statistical-testing-under-nondeterminism.md)) |
| Prompt edited "cosmetically" | Any byte change misses, so people re-record without looking | Diff the old and new trajectories when re-recording, and review the diff like a snapshot test |
| Recorded against a buggy world | The cassette encodes the model's reaction to a bug | Re-record when world fixtures change, and keep the world seed in the metadata |

**Decision rule.** Use cassettes to test *your code around the model*: parsers, tool dispatch, state handling, trace schema, check functions. Don't use them as evidence about *model behavior* after any change to the prompt, the model, or the tools. That needs live runs.

### The environment ladder
| Rung | Determinism | Fidelity | Blast radius | Use for |
|---|---|---|---|---|
| Scripted fake (FakeClient + policy) | Total | Low | None | Unit tests of harness code, negative controls |
| Seeded simulated world (`world.py`) | Total for the world | Medium | None | Fault injection, invariants, property search |
| Cassette replay | Total | Real model, one sample | None | Regression tests of plumbing, cheap CI |
| Hermetic sandbox (container, network off) | Low | High: real tools, real binaries | The container | Coding agents, real CLIs, live N-run evals |
| Staging | Low | Higher | Shared staging | Pre-release soak, canaries |
| Production | None | Full | Users | Online evals and monitoring only ([Module 15](../15-observability-and-production/README.md)) |

### What makes a sandbox safe for tests
Built from the sources above and [Module 16](../16-security-and-containment/README.md):
- **Fresh per trial.** A new container or worktree from a clean image, with no git history or caches from earlier trials. That isolation is what keeps trials independent, which pass^k assumes.
- **Network off by default**, with an allowlist when the task needs a registry. Egress is a capability you grant, not a default. OpenAI describes the same default for Codex: writes limited to the workspace, network off, because of prompt-injection risk ([OpenAI, "Introducing upgrades to Codex"](https://openai.com/index/introducing-upgrades-to-codex/)).
- **No real credentials inside.** Use a proxy that holds tokens and enforces policy (which branch, which namespace), or scoped staging-only keys with hard spend caps ([Willison, "Designing agentic loops"](https://simonwillison.net/2025/Sep/30/designing-agentic-loops/) suggests a dedicated org with a small budget for any credential that can spend money).
- **Resource limits written down and reported.** Anthropic found that strict 1x resource enforcement produced 5.8% infra errors versus 0.5% uncapped, and recommends a guaranteed allocation plus a separate, higher kill threshold. Above about 3x headroom, the eval starts measuring something different ([Anthropic, infra noise](https://www.anthropic.com/engineering/infrastructure-noise)).
- **Infra failures surfaced as infra.** A container OOM must reach the harness as `infra_error`, not as a tool result the agent tries to "fix".

## Worked example: the cassette that survived a model upgrade
Here is a team's setup. They recorded 60 cassettes for their incident-triage agent in March. CI replays them on every PR. In September they bumped `AINATIVE_MODEL` to a new model. CI stayed green, and a week later on-call noticed the agent paging the wrong team.

**Bad setup:** cassettes only.
```text
tests/cassettes/triage_*.jsonl     # request-hash -> response
```
Nothing in the request changed, so every cassette replayed the old model's answers.

**Good setup:** cassettes with metadata, a staleness gate, and a live tier.
```text
tests/cassettes/triage_017.jsonl
tests/cassettes/triage_017.jsonl.meta.json
  {"system_sha": "9f2c...", "tools_sha": "41ab...", "model": "claude-sonnet-5-5", "world_seed": 17}
```
```python
@pytest.fixture(autouse=True)
def fresh_cassettes(cassette_path):
    stale = cassette_staleness(cassette_path, system=SYSTEM, model=current_model())
    if stale:
        pytest.fail(f"stale cassette, re-record and review the trajectory diff: {stale}")
```
The model bump now fails CI with `model: recorded 'claude-sonnet-5-5', now 'claude-opus-5-5'`. Re-recording produces a trajectory diff for review. The nightly live tier runs each task N=10 times against the sandbox and reports pass^k for the new model ([05](05-statistical-testing-under-nondeterminism.md)).

## Pitfalls
- **Cassettes as behavior evidence.** *Detect:* a PR that changes the prompt and only re-records cassettes, with no live-run report attached.
- **Secrets in cassettes.** Requests contain tool results, and those can contain tokens, customer data, or log lines. *Detect:* run your secret scanner over `cassettes/` in CI.
- **Unbounded re-recording.** Re-recording on every miss turns the cassette into a rubber stamp. *Detect:* require a reviewed trajectory diff (tools, args, final claim) for each re-record.
- **A shared sandbox across trials.** *Detect:* look for files, branches or processes from trial *i* visible in trial *i+1*. Start each trial by asserting the workspace is pristine.
- **A sandbox with production reach.** *Detect:* from inside the sandbox, try to resolve and connect to a prod hostname. The test passes only if that fails.

## In your day job
- Wrap your agent's model client in `RecordingClient` for one day of staging runs. You now have a regression suite for the harness code.
- Add a `.meta.json` next to every cassette, and a CI check that fails on a prompt, tool or model mismatch.
- Write down your agent test environment's rung for each test tier (PR, nightly, pre-release) so that nobody mistakes a replay pass for a behavior pass.
- Check your sandbox for isolation per trial, network-off by default, no raw credentials, and reported resource limits. Fix the first one missing.
