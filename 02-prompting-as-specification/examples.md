# Examples

Six scenarios from a backend and platform engineer's week. Each one follows: situation, the naive approach and what happens, the AI-native approach with artifacts, and what to check. Outputs marked *(illustrative output)* were not produced by a real model run.

---

## 1. The CI review bot that stopped finding bugs

**Situation.** Your team's PR review bot runs on every PR to `payments-api`. A double-charge bug shipped last week through a PR the bot had reviewed. It left three comments, all about naming.

**Naive approach.** Add "Focus on bugs, not style. Be thorough. Only report important stuff." to the prompt. The bot now leaves fewer comments, which looks like an improvement, and it still misses idempotency bugs. "Only report important stuff" is followed literally, and nothing defines "important" for this service.

**AI-native approach.**
1. Write the contract table (see [01-prompts-are-specs.md](01-prompts-are-specs.md)). The consumer is a CI step plus the PR author. The decision is block or don't block. The cost asymmetry is that a missed blocker costs money.
2. Split recall from precision. The model reports everything with a severity, and a deterministic filter decides what to post:

```python
# ci/review_filter.py
POST = {"blocker", "major"}
def to_comments(review: dict, diff_text: str) -> list[dict]:
    out = []
    for f in review["findings"]:
        if f["severity"] not in POST:
            continue
        if any(e not in diff_text for e in f["evidence"]):   # grounding check
            continue
        out.append({"path": f["file"], "line": f["line"], "body": f"[{f['severity']}] {f['claim']}"})
    return out
```

3. Inject `docs/INVARIANTS.md` into `{{invariants}}`, so the reviewer knows what INV-1 (idempotency keys stable across retries) means.
4. Publish `pr_review/v2.md` (see `code/prompts/pr_review/v2.md`), with a changelog entry citing the Opus 5 guidance on literal "high-severity only" instructions.
5. Build a 20-row eval from the last quarter's merged PRs that later needed fixes, with the escaped bug as the expected `blocker`. Mark the double-charge PR `must_pass`.

**What to check.** Recall on known-bad PRs, measured before and after. The share of findings dropped by the grounding check, since a high share means the model is citing lines that aren't in the diff. The blocker rate on PRs that later shipped cleanly, which is your false-positive cost.

---

## 2. A log-triage classifier from nothing

**Situation.** On-call gets 400 alerts a week from a log-pattern monitor, and about 70% are noise. You want an LLM step between the monitor and PagerDuty.

**Naive approach.** "You are an expert SRE. Classify these logs and rate severity." The output is prose with severities like `HIGH`, `P2` and "moderate". The router's regex parses some of them, and the rest fall through to "page", so noise volume goes up.

**AI-native approach.**
1. Define the schema first (`TRIAGE_SCHEMA` in `code/log_triage.py`): closed enums, `unknown` as a category, `needs_human` as a boolean, and `evidence` as verbatim lines.
2. Write the prompt from the schema's meanings (`code/prompts/log_triage/v2.md`): a definition per enum value, the cost asymmetry, settled signatures from past incident reviews, and three examples including an `unknown`.
3. Build `data/triage_eval.jsonl` from last month's alerts, labelled by the on-call engineers who handled them. Fifteen rows is enough to start. Each row looks like this:

```json
{"id": "pg-refused", "excerpt": "2026-10-03T02:31:12Z payments-api HikariPool-1 - Connection is not available: connection refused (pg-primary:5432)", "expected": {"category": "dependency", "severity": "page"}, "must_pass": false}
```

4. Ship it in **shadow mode** first: classify every alert, but route on the old rules, and log both decisions with `prompt_ref`.
5. After a week, compute agreement with what on-call actually did, then promote it to routing.

**What to check.** The schema-valid rate (should be about 100% with structured outputs), the abstain rate (if `unknown` is above 15%, the definitions need work), and above all **missed pages**: alerts the classifier said `ignore` that on-call later escalated. Make every one of those a `must_pass` row.

---

## 3. The summariser after a model upgrade

**Situation.** Your incident-summary prompt was tuned on `claude-sonnet-4-5` in mid-2025 (`code/prompts/incident_summary/v1.md`). Platform is moving the default to `claude-sonnet-5-5`.

**Naive approach.** Change the model ID in config and ship. Summaries get longer, open with a numbered list of every event, and state a single root cause with confidence even when the timeline is ambiguous. Nobody notices for two weeks, because the summaries read well.

**AI-native approach.** Run the upgrade drill from [03-outcome-first-and-expired-techniques.md](03-outcome-first-and-expired-techniques.md):

1. Freeze 25 past incidents with human-written summaries as references, and a binary rubric: impact stated, duration correct, cause hedged when the timeline is ambiguous, 150 words or fewer ([Module 11](../11-llm-as-judge/README.md) for the judge).
2. Run v1 on both models, and write v2 as a fresh baseline.
3. Ablate v1's legacy lines one at a time on the new model, and record each in a table like this one *(illustrative numbers)*:

| Variant on sonnet-5-5 | Rubric pass | Mean output tokens |
|---|---|---|
| v1 as-is | 15/25 | 610 |
| v1 minus "Think step by step" | 15/25 | 540 |
| v1 minus steps 1 to 3 | 17/25 | 330 |
| v1 minus "exactly one root cause" | 19/25 | 600 |
| v2 (fresh baseline) | 22/25 | 210 |

4. Run the paired gate between v1 on the old model (the reference) and v2 on the new model, then publish v2 with `model: claude-sonnet-5-5`.

**What to check.** The paired wins and losses, not two rubric scores side by side. Rows where v2 loses are your next examples or constraints. Also check that v1 stays pinned to the old model ID in its front matter, so a rollback restores the old pair exactly.

---

## 4. A monorepo where three files disagree

**Situation.** Root `AGENTS.md` says "Build with `make build`". `services/payments/AGENTS.md` says "Use `./gradlew build`; never use make here". A `release` skill says "Always run `make release-check` first". An agent asked to "cut a release of payments" runs `make release-check`, which fails because make isn't wired up for payments. It then tries `./gradlew` and spends 20 minutes rebuilding.

**Naive approach.** Add "IMPORTANT: in services/payments, NEVER use make" to the root file as well. Now the rule exists in two files, and the skill still says "Always".

**AI-native approach.**
1. Classify each instruction (see [04-instruction-hierarchy.md](04-instruction-hierarchy.md)). All three are defaults, and none is an invariant.
2. Give each rule one owner. The build command for payments lives *only* in `services/payments/AGENTS.md`. The root file says "Each service's AGENTS.md defines its build and test commands; it overrides this file." The skill says "Run the service's release check (see that service's AGENTS.md)" instead of naming a command.
3. Add the precedence block and the deviation sentence to the root file.
4. Run `/doctor prompt-audit` and check that it reports no conflicts.

**What to check.** Re-run the same "cut a release of payments" task three times in fresh sessions. All three should run the gradle check first, with no failed make call in the trace.

---

## 5. A prompt deploy that only fails on weekends

**Situation.** An invoice-extraction step in your data pipeline uses a prompt to pull `vendor`, `amount_minor`, `currency` and `due_date` from PDFs. Version 7 adds a rule for European date formats. It passes the offline gate: 6 wins, 0 losses, p = 0.031.

**Naive approach.** Promote it to 100% on Friday. On Saturday the batch of scanned invoices from a new vendor comes through. v7's date rule makes the model return `null` for `due_date` whenever the format is ambiguous, and the downstream `NOT NULL` constraint rejects 18% of the batch.

**AI-native approach.**
1. Canary at 10% with metrics grouped by `prompt_ref`, and soak through the weekend batch, since the input mix changes then.
2. The canary panel shows the `due_date` null rate at 0.4% for `invoice_extract@v6#...` and 17% for `invoice_extract@v7#...`.
3. Roll back by setting `"stable": 6` in `channels.json`. Because v6 was never edited, the rollback is exact.
4. Add three of Saturday's invoices to the eval set as rows, and mark one `must_pass`.
5. Decide whether the right behaviour for an ambiguous date is `null` plus `needs_human`, or a best guess. That's a product decision, so write it into the prompt and the schema, as v8.

**What to check.** Every field-level null rate, per `prompt_ref`, through at least one full input cycle. Also confirm the offline eval set now contains the input class that broke.

---

## 6. The 400 after the SDK bump

**Situation.** A service built in early 2025 classifies support tickets. It ends `messages` with `{"role": "assistant", "content": "{"}` to force JSON. After moving to `claude-sonnet-5-5`, every call returns a 400.

**Naive approach.** Pin the old model. That postpones the problem and blocks every other upgrade.

**AI-native approach.** Migrate as the Anthropic docs recommend ([migrating away from prefilled responses](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices#migrating-away-from-prefilled-responses)):

```diff
 resp = client.messages.create(
     model="claude-sonnet-5-5",
     system=SYSTEM,
-    messages=[{"role": "user", "content": ticket}, {"role": "assistant", "content": "{"}],
+    messages=[{"role": "user", "content": ticket}],
+    output_config={"format": {"type": "json_schema", "schema": TICKET_SCHEMA}},
 )
-data = json.loads("{" + resp.content[0].text)
+if resp.stop_reason in ("refusal", "max_tokens"):
+    return route_to_human(ticket, reason=resp.stop_reason)
+data = json.loads(next(b.text for b in resp.content if b.type == "text"))
```

Note the last line. On current models, thinking can be on by default, so the first content block may be a `thinking` block. Select blocks by `type`, not by position, as the Anthropic guide advises.

**What to check.** Run the old and new paths on the same 50 tickets with the old model (which still accepts prefill), and diff the labels. Then switch models and re-run the gate. Also grep the codebase for other `"role": "assistant"` final turns.
