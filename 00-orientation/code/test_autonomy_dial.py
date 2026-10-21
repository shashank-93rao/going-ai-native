import pytest

from ainative_kit import FakeClient, text
from autonomy_dial import Task, extract_features, recommend


@pytest.mark.parametrize(
    "task, mode",
    [
        (Task(oracle="none"), "chat"),
        (Task(oracle="weak"), "pair"),
        (Task(oracle="partial", sandboxed=True), "supervised_agent"),
        (Task(oracle="strong", sandboxed=True), "supervised_agent"),
        (Task(oracle="strong", sandboxed=True, large_mechanical=True), "loop"),
        (Task(oracle="strong", sandboxed=True, recurring=True), "scheduled"),
    ],
)
def test_mode_scales_with_oracle(task, mode):
    assert recommend(task).mode == mode


def test_irreversible_caps_at_supervised():
    r = recommend(Task(oracle="strong", sandboxed=True, large_mechanical=True, reversible=False))
    assert r.mode == "supervised_agent"
    assert any("approval gate" in g for g in r.guards)


def test_no_sandbox_caps_unattended():
    assert recommend(Task(oracle="strong", large_mechanical=True, sandboxed=False)).mode == "supervised_agent"


def test_off_distribution_steps_down():
    assert recommend(Task(oracle="strong", sandboxed=True, large_mechanical=True, on_distribution=False)).mode == "supervised_agent"
    assert recommend(Task(oracle="weak", on_distribution=False)).mode == "chat"


def test_loops_always_get_governors():
    r = recommend(Task(oracle="strong", sandboxed=True, large_mechanical=True))
    assert {"iteration cap", "token/$ budget"} <= set(r.guards)


def test_bad_oracle_rejected():
    with pytest.raises(ValueError):
        recommend(Task(oracle="vibes"))


def test_extract_features_parses_model_json():
    fake = FakeClient([text('Sure: {"oracle": "strong", "reversible": true, "sandboxed": true, "on_distribution": true, '
                            '"large_mechanical": true, "recurring": false}')])
    t = extract_features("port the consumer", fake)
    assert t.oracle == "strong" and t.large_mechanical
    assert "autonomy policy" in fake.calls[0]["system"]


@pytest.mark.parametrize("reply", ["no json here", '{"oracle": "excellent"}', '{"oracle": "strong", "reversible": "yes"}'])
def test_extract_features_falls_back_conservatively(reply):
    t = extract_features("anything", FakeClient([text(reply)]))
    assert t == Task(oracle="none", reversible=False, sandboxed=False)
    assert recommend(t).mode == "chat"
