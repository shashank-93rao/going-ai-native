# 07: Eval integrity and benchmark literacy

## The idea
An eval score means something only if the system under test could not get the answer any way other than by doing the task. **Eval integrity** is the set of properties that make this true. Each one has a familiar failure:

| Property | Failure | Systems analogy |
|---|---|---|
| The answers are not in the model's training data | **Contamination** | Testing a cache with the keys it was warmed with |
| The system cannot read the answer key | **Answer-key leakage** | Integration test that reads the expected value from the same DB it writes |
| Trials cannot see each other | **Cross-trial leakage** (git history, shared files, shared memory) | Test pollution from shared fixtures |
| The system does not treat the eval differently from real work | **Eval awareness** | Code that detects the benchmark harness and takes a fast path |
| The environment is the same across runs and across systems compared | **Infra and scaffold effects** | Comparing p99s measured on different hardware |
| You did not tune on what you report | **Overfitting to the test split** | Tuning a load test until it passes |

**Benchmark literacy** is the same set of properties applied to *other people's* numbers. A public benchmark goes through creation, saturation, contamination and, eventually, retirement. A leaderboard gap of a few points often says more about scaffolds and resource limits than about models. That is why the evals that should drive your decisions are **private** ones built from your own traces.

## Why it matters
- **Eval awareness.** On BrowseComp, Claude Opus 4.6 in 2 of 1,266 problems inferred it was being evaluated, identified the benchmark, found the decryption code on GitHub and a mirror of the data on Hugging Face, and decrypted the answer key. Nine more problems were ordinary contamination. The eval-aware run used 40.5M tokens, 38 times the median. Multi-agent configurations produced unintended solutions at 3.7 times the single-agent rate (0.87% vs 0.24%). URL blocklists were not enough; blocking search results that mentioned the benchmark's name worked ([Anthropic, "Eval awareness in Claude Opus 4.6's BrowseComp performance"](https://www.anthropic.com/engineering/eval-awareness-browsecomp)). Anthropic's conclusion: "treat eval integrity as an ongoing adversarial problem rather than a design-time concern."
- **Cross-trial leakage.** In Anthropic's internal evals, Claude gained an unfair advantage on some tasks by examining git history left by earlier trials ([Anthropic, "Demystifying evals"](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)).
- **Actions with real effects.** A transcript review that Anthropic published in October 2026 found models in evals exploiting injection flaws on third-party servers, submitting real web forms, and bypassing access controls. Anthropic turned off live internet access for all internal evals ([Anthropic, "Investigating unintended model actions"](https://www.anthropic.com/research/investigating-unintended-model-actions)). An eval environment with network access is a production environment.
- **Infrastructure.** On Terminal-Bench 2.0, infrastructure configuration alone moved scores by 6 points (p < 0.01). Anthropic suggests distrusting leaderboard gaps under about 3 points unless configurations are matched ([Anthropic, "Quantifying infrastructure noise in agentic coding evals"](https://www.anthropic.com/engineering/infrastructure-noise)).
- **Scaffolds.** A minimal scaffold (prompt, bash tool, edit tool) took Claude 3.5 Sonnet to 49% on SWE-bench Verified, past the previous state of the art of 45% ([Anthropic, "Raising the bar on SWE-bench Verified"](https://www.anthropic.com/engineering/swe-bench-sonnet)). LangChain reported +13.7 points on Terminal-Bench by changing only the harness, with the model fixed (from the course research notes; see [Module 08](../08-harness-engineering/README.md)). CORE-Bench went from 42% to 95% for one model after grader and scaffold fixes ([Anthropic, "Demystifying evals"](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)). A benchmark number is a number for a model *plus* a harness *plus* an environment.

### The retirement of SWE-bench Verified (as reported)
SWE-bench launched in 2023 with 2,294 real GitHub issues from 12 Python repositories, graded by hidden tests. At launch the best model solved "a mere 1.96% of the issues" ([Jimenez et al.](https://arxiv.org/abs/2310.06770)). SWE-bench Verified, a human-validated subset, became the standard coding-agent benchmark.

In February 2026 OpenAI published "Why we no longer evaluate SWE-bench Verified" ([OpenAI](https://openai.com/index/why-we-no-longer-evaluate-swe-bench-verified/)). The page returned 403 when this module was written, so what follows is **as reported** by search snippets and secondary coverage, not read from the post itself:

- An audit of a subset of problems that models often failed reportedly found that most had tests that reject correct solutions (a figure of 59.4% is reported).
- Frontier models reportedly could reproduce gold patches for some tasks, a sign of contamination.
- Progress had reportedly flattened near the top of the scale, which is saturation.
- OpenAI reportedly recommended SWE-bench Pro instead. A later third-party audit reportedly questioned Pro's grading too. Treat that as unverified.

You do not need the exact figures to take the lesson. A benchmark that was hard in 2023 became saturated, contaminated and partly broken within about three years, and the people who maintained it said so. Your private eval will go through the same life cycle, only faster, unless you refresh it.

## How it works: an integrity checklist
Run this on every suite before trusting its numbers, and again whenever the harness changes.

**Isolation**
- A fresh environment per trial: new temp dir, no git history from earlier trials, no shared caches or memory. Resource limits are specified and recorded (a guaranteed allocation and a separate kill threshold, per Anthropic's infra-noise post).
- No live network access unless the task needs it, and then an allowlist. Log every outbound request.

**The answer key**
- Expected outputs, reference solutions and hidden tests live outside anything the system under test can read. Hidden tests are written into the workdir only after the agent stops.
- If coding agents work on the system in the same repository (for example Claude Code tuning the router prompt), the **test split must not be readable by them**. Keep it outside the repo or behind a deny rule, and check that it stays that way ([Module 05](../05-tools-mcp-skills-hooks/README.md) covers permission rules).
- Few-shot examples in the prompt are not drawn from the eval set. Lance Martin's rule for automated hill-climbing: "If the hillclimber reads the failing transcripts, it should never paste the failure content into the prompt" ([Lance Martin](https://claude.dev/blog/automating-eval-design-and-hillclimbing/)).

**Contamination**
- Never publish your private eval set. Some public benchmarks embed a unique canary string in their files so that contamination of a training corpus can be detected. Doing the same in yours is cheap.
- Prefer tasks from your own incidents and traces, which cannot be in anyone's training data unless they leaked.
- Refresh: add recent cases every quarter, and watch for a sudden jump on the oldest cases after a model upgrade.

**Awareness and gaming**
- Read transcripts of the highest-token and highest-scoring trials. The BrowseComp case was found because the run used 38 times the median tokens.
- Search transcripts for the benchmark's name, the dataset file name, or attempts to read grader files.
- Make graders robust to the hacks you have already seen: hidden tests, file hashes, graders that run outside the agent's process ([05-graders.md](05-graders.md)).

**Reporting**
- Record the model ID, prompt hash, harness version, dataset hash, resource configuration and date with every result.
- Report n, trials per task and an interval ([Module 12](../12-hill-climbing/README.md)). Don't act on gaps smaller than your measured noise.

### Reading a public benchmark claim
Before a public number changes your model choice, ask:

1. **Which harness and scaffold?** If the vendor's scaffold differs from yours, the number may not transfer.
2. **Which configuration?** Reasoning effort, context limit, tools, resource limits, number of attempts. Is it pass@1 or best-of-k?
3. **How many trials, and what interval?** A 2-point gap with no interval is not a result.
4. **Contamination status?** How old is the benchmark? Has its maintainer retired or revised it?
5. **Does the task distribution resemble yours?** Python GitHub issues are not your Go monorepo, and a QA benchmark is not your router.
6. **Who ran it?** A vendor on its own model, or an independent party with matched configurations?

Karpathy has argued for not choosing models from public leaderboards, because public numbers become optimization targets, and for building a private eval that matches your workload instead (summarized in the course research notes). The checklist above is why.

## Worked example: auditing the coding eval

**Bad harness.** A first version of the coding eval looked like this:

```python
WORKDIR = Path("/tmp/ratelimit-eval")          # reused across trials
subprocess.run(["git", "init"], cwd=WORKDIR)
for trial in range(10):
    reset_files(WORKDIR)                        # rewrites ratelimit.py and both test files
    run_agent(client, WORKDIR)                  # agent tools: read_file, write_file, run_shell
    subprocess.run(["git", "commit", "-am", f"trial {trial}"], cwd=WORKDIR)
    passed = run_pytest(WORKDIR, "test_hidden_ratelimit.py")
```

The audit finds four leaks:

| Leak | How the agent could exploit it | How you'd notice |
|---|---|---|
| Reused directory with git history | `git log -p` shows the previous trial's fix | Later trials pass more often than early ones; transcripts contain `git log` |
| Hidden test written before the run | `cat test_hidden_ratelimit.py` reveals both bugs | Agents never fail the "hidden" test; transcripts show reads of it |
| `run_shell` with network | Search the web for the task text, or `pip install` a fixed version | Outbound requests in the logs; token spikes |
| Results depend on trial order | Trial 0 is always the worst | Shuffle trial order and compare |

**Good harness** (`coding_task.py`):

```python
def run_fn(case, trial):
    with tempfile.TemporaryDirectory(prefix=f"trial{trial}_") as d:   # fresh, no git, deleted after
        root = Path(d)
        shas = setup_workdir(root)                                     # only ratelimit.py + visible test
        run = run_agent(get_client(fake=fake_coding_client(trial)), root, tracer)
        run["graded"] = grade_coding_trial(root, run, shas)            # hidden test written here, after
    return run
```

The agent's tools are `read_file`, `write_file` and `run_tests`, with no shell and no network. `_safe` rejects any path that resolves outside the trial directory, and `test_tools_cannot_escape_the_repo` checks it. The reference solution (`FIXED_SRC`) lives in the harness module, which the agent cannot read because it is outside the trial directory.

**The router audit.** Its prompt has no few-shot examples, so nothing from the dataset can leak through the prompt. The obvious remaining risk is the course itself: `router_cases.jsonl` is in a repository that a coding agent working on `ticket_router.py` can read. For this teaching module that is acceptable. For your production router, move the test split out of the repo the agent works in.

## Pitfalls
| Pitfall | How to detect it |
|---|---|
| Reusing environments across trials | Pass rate rises with trial index. Shuffle order, or diff the environment before each trial against a clean image. |
| Answer key readable by the system | Grep transcripts for reads of expected-output, reference or hidden-test files. |
| Failure content pasted into prompts during tuning | Diff the prompt against the dataset: long shared substrings mean leakage. Test score jumps while new production traffic doesn't improve. |
| Eval with live internet | Outbound requests from eval runs. Default to no network; allowlist what the task needs. |
| Trusting a sub-3-point public gap | No matched configuration or interval given. Re-run on your own suite before acting. |
| Private set gets stale | New production failure modes don't appear in it. Refresh from error analysis every sprint. |
| Assuming integrity is a one-time setup | Nobody has read the highest-token transcripts since the suite was built. Schedule it. |

## In your day job
- Audit your agent evals this week against the isolation and answer-key checklist above, starting with "is the environment fresh per trial?".
- Keep the test split of every private eval out of the repositories your coding agents work in.
- Record model, prompt hash, harness version, dataset hash and resource configuration with every eval result, and refuse to compare results that differ in more than the variable under test.
- Before a public benchmark changes your model choice, run both models on your private suite with matched configurations.
