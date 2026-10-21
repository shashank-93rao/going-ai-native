import json
import shutil

import pytest

from prompt_registry import DEFAULT_ROOT, PromptError, Registry, content_hash, parse_prompt_file


@pytest.fixture
def reg_copy(tmp_path):
    root = tmp_path / "prompts"
    shutil.copytree(DEFAULT_ROOT, root)
    return root


def test_repo_registry_is_clean():
    """The committed lock file matches the committed prompts (this is the CI check)."""
    assert Registry.load().verify() == []


def test_hash_ignores_whitespace_noise_but_not_content():
    a = "---\nname: x\n---\nhello world\n"
    assert content_hash(a) == content_hash(a.replace("\n", "\r\n") + "\n\n")
    assert content_hash(a) == content_hash("---\nname: x   \n---\nhello world   \n")
    assert content_hash(a) != content_hash(a.replace("hello", "Hello"))


def test_front_matter_required_fields():
    with pytest.raises(PromptError, match="owner"):
        parse_prompt_file("---\nname: x\nversion: 1\nmodel: m\n---\nbody\n")
    with pytest.raises(PromptError, match="front matter"):
        parse_prompt_file("no front matter here")


def test_get_latest_and_specific_version():
    reg = Registry.load()
    assert reg.get("log_triage").version == 3
    pv = reg.get("log_triage", 2)
    assert pv.ref.startswith("log_triage@v2#") and len(pv.ref.split("#")[1]) == 12
    with pytest.raises(PromptError, match="no v9"):
        reg.get("log_triage", 9)


def test_render_is_strict_about_variables():
    pv = Registry.load().get("log_triage", 2)
    out = pv.render(services="orders-api")
    assert "Known services: orders-api" in out and "{{" not in out
    with pytest.raises(PromptError, match="missing"):
        pv.render()
    with pytest.raises(PromptError, match="unexpected"):
        pv.render(services="a", typo="b")


def test_body_and_declared_variables_must_agree(reg_copy):
    f = reg_copy / "pr_review" / "v3.md"
    f.write_text("---\nname: pr_review\nversion: 3\nmodel: m\nowner: o\nvariables: diff\n---\n{{diff}} {{extra}}\n")
    pv = Registry.load(reg_copy).get("pr_review", 3)
    with pytest.raises(PromptError, match="declares"):
        pv.render(diff="x")


def test_editing_a_published_version_is_detected(reg_copy):
    f = reg_copy / "log_triage" / "v2.md"
    f.write_text(f.read_text().replace("3am", "4am"))
    problems = Registry.load(reg_copy).verify()
    assert any("content changed after publish" in p and "create v4" in p for p in problems)


def test_new_version_needs_lock_and_changelog(reg_copy):
    src = (reg_copy / "log_triage" / "v3.md").read_text().replace("version: 3", "version: 4")
    (reg_copy / "log_triage" / "v4.md").write_text(src)
    problems = Registry.load(reg_copy).verify()
    assert any("v4" in p and "not in lock file" in p for p in problems)
    assert any("no '## v4' entry" in p for p in problems)


def test_deleting_a_version_is_detected(reg_copy):
    (reg_copy / "log_triage" / "v1.md").unlink()
    problems = Registry.load(reg_copy).verify()
    assert any("missing versions [1]" in p for p in problems)
    assert any("file is gone" in p for p in problems)


def test_channels_resolve_and_rollback(reg_copy):
    reg = Registry.load(reg_copy)
    assert reg.resolve("log_triage", "stable").version == 2
    chans = json.loads((reg_copy / "channels.json").read_text())
    chans["log_triage"]["stable"] = 1  # rollback is a pointer move, not a file edit
    (reg_copy / "channels.json").write_text(json.dumps(chans))
    assert Registry.load(reg_copy).resolve("log_triage", "stable").version == 1
    chans["log_triage"]["stable"] = 7
    (reg_copy / "channels.json").write_text(json.dumps(chans))
    assert any("missing v7" in p for p in Registry.load(reg_copy).verify())


def test_name_and_version_must_match_path(reg_copy):
    f = reg_copy / "log_triage" / "v2.md"
    f.write_text(f.read_text().replace("version: 2", "version: 5"))
    with pytest.raises(PromptError, match="front matter says"):
        Registry.load(reg_copy)
