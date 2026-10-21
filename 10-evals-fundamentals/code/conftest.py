"""Force the offline fake for every test, even if ANTHROPIC_API_KEY is set in your shell."""
import pytest


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    monkeypatch.setenv("AINATIVE_FAKE", "1")
