from pathlib import Path

import pytest

from prompt_lint import lint

PROMPTS = Path(__file__).parent / "prompts"


def rules(text, severity=None):
    return {f.rule for f in lint(text) if severity is None or f.severity == severity}


def test_missing_output_format():
    assert "PL001" in rules("Summarize the incident.")
    assert "PL001" not in rules("Summarize the incident. Respond with only a JSON object with a `summary` field.")
    assert "PL001" not in rules("<output_format>Three short paragraphs.</output_format>")


@pytest.mark.parametrize("text", [
    "Be thorough but concise. Respond in JSON.",
    "Keep it brief.\nInclude all relevant details.\nRespond in JSON.",
    "Be thorough. Only report high-severity issues. Respond in JSON.",
    "Always include stack traces in the summary.\nNever include stack traces in the summary. Respond in JSON.",
])
def test_contradictions_flagged(text):
    assert "PL002" in rules(text)


def test_unrelated_always_and_never_are_not_a_contradiction():
    text = "Always cite the log line you used. Never page for health checks. Respond in JSON."
    assert "PL002" not in rules(text)


def test_contradiction_reports_both_lines():
    f = next(f for f in lint("Keep it brief.\nRespond in JSON.\nBe comprehensive.") if f.rule == "PL002")
    assert "lines 1 and 3" in f.message


def test_unbounded_absolute_vs_scoped():
    assert "PL003" in rules("Always page for errors. Respond in JSON.")
    assert "PL003" not in rules("Always page when users are affected. Respond in JSON.")
    assert "PL003" not in rules("Never use ellipses, because a TTS engine reads the output. Respond in JSON.")
    assert "PL003" not in rules("The result must be valid JSON.")  # lowercase must in normal prose


def test_shouting_threshold():
    assert "PL004" in rules("IMPORTANT: you MUST do this. CRITICAL. Respond in JSON.")
    assert "PL004" not in rules("Important: respond in JSON.")


@pytest.mark.parametrize("phrase", ["Think step by step.", "You MUST plan extensively.", "Double-check your answer.",
                                    "Use the think tool before acting."])
def test_expired_techniques(phrase):
    assert "PL005" in rules(phrase + " Respond in JSON.")


def test_vague_terms_are_info_only():
    found = [f for f in lint("Handle errors appropriately. Respond in JSON.") if f.rule == "PL006"]
    assert found and all(f.severity == "info" for f in found)


def test_xml_balance():
    assert "PL007" in rules("<context>stuff\n<output_format>JSON</output_format>")
    assert "PL007" in rules("stuff</context> Respond in JSON.")
    assert "PL007" not in rules("<context>a</context>\n<output_format>JSON</output_format>")


def test_front_matter_is_skipped_and_line_numbers_are_file_lines():
    text = "---\nname: x\ndescription: be thorough but concise\n---\nAlways page for errors. Respond in JSON."
    found = lint(text)
    assert "PL002" not in {f.rule for f in found}  # the contradiction lives in front matter only
    assert next(f for f in found if f.rule == "PL003").line == 5


@pytest.mark.parametrize("path", sorted(PROMPTS.glob("*/v1.md")))
def test_legacy_prompts_fail_lint(path):
    assert rules(path.read_text(), "error"), f"{path} should have lint errors"


@pytest.mark.parametrize("path", sorted(PROMPTS.glob("*/v[23].md")))
def test_spec_prompts_are_clean(path):
    bad = [str(f) for f in lint(path.read_text()) if f.severity in ("error", "warning")]
    assert bad == [], f"{path}: {bad}"
