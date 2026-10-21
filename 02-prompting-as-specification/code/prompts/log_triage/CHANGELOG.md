# log_triage changelog

## v3 (2026-10-14)
- Add rule: `consumer lag`, `timeout` map to `dependency`/`page` (from INC-2291, where broker lag was triaged as `unknown`).
- Status: candidate. The A/B on triage_eval.jsonl rejected it: `timeout` is too broad and pages on an app_bug row marked must_pass. See ab_harness output.

## v2 (2026-10-09)
- Rewrite as a spec: purpose and cost of errors, closed category and severity enums with definitions, settled signatures, abstention via `unknown`, verbatim evidence, JSON-only output, three examples.
- Remove "Always page for errors" (unbounded rule) and "Be thorough but concise" (contradiction).

## v1 (2026-09-30)
- Initial version.
