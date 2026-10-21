import re
import subprocess
import sys
from pathlib import Path

SKILL = Path(__file__).parent / "skills" / "investigate-kafka-consumer-lag"
DATA = Path(__file__).parent / "data"
SCRIPT = SKILL / "scripts" / "lag_summary.py"


def frontmatter(text: str) -> dict[str, str]:
    assert text.startswith("---\n"), "frontmatter must open on line 1"
    block = text.split("---\n", 2)[1]
    return {m.group(1): m.group(2).strip() for m in re.finditer(r"^([a-z-]+):\s*(.*)$", block, re.M)}


def test_frontmatter_follows_agent_skills_spec():
    fm = frontmatter((SKILL / "SKILL.md").read_text())
    name, desc = fm["name"], fm["description"]
    assert name == SKILL.name, "name must match the directory"
    assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", name) and len(name) <= 64
    assert 1 <= len(desc) <= 1024
    assert "Use when" in desc  # says *when*, which is what triggers loading


def test_body_is_lean_and_links_resolve():
    text = (SKILL / "SKILL.md").read_text()
    assert len(text.splitlines()) < 500
    links = re.findall(r"\]\(([^)]+)\)", text)
    assert links, "SKILL.md should point to its level-3 files"
    for rel in links:
        assert (SKILL / rel).is_file(), rel
        assert rel.count("/") <= 1, "keep references one level deep"
    assert "scripts/lag_summary.py" in text and "Execute the script" in text  # run it, don't load it


def run(path=None, stdin=None, *args):
    cmd = [sys.executable, "-I", str(SCRIPT), *([str(path)] if path else []), *args]
    return subprocess.run(cmd, input=stdin, capture_output=True, text=True, timeout=10)


def test_script_classifies_poison_partition():
    p = run(DATA / "describe_poison_partition.txt")
    assert p.returncode == 0
    assert "total_lag=48692" in p.stdout and "payments.events[3]=48211" in p.stdout
    assert p.stdout.strip().endswith("shape=single_partition")


def test_script_classifies_unassigned_from_stdin():
    p = run(stdin=(DATA / "describe_unassigned.txt").read_text())
    assert "unassigned_partitions=[0, 1]" in p.stdout and "shape=unassigned" in p.stdout


def test_script_threshold_and_bad_input():
    p = run(DATA / "describe_poison_partition.txt", None, "--threshold", "100000")
    assert "shape=none" in p.stdout
    bad = run(stdin="hello\n")
    assert bad.returncode == 1 and "no partition rows found" in bad.stderr
