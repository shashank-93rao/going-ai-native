import json
from collections import Counter
from pathlib import Path

from ainative_kit import FakeClient, text

from calibrate import confusion
from compare_judges import LIKERT_PROMPT, best_threshold, likert, run
from judge_fakes import incident_keyword_judge, incident_rules_judge, likert_length_judge

DATA = Path(__file__).parent / "data"
ROWS = [json.loads(line) for line in (DATA / "incident_summaries.jsonl").read_text().splitlines()]
CODE_ROWS = [json.loads(line) for line in (DATA / "code_review_comments.jsonl").read_text().splitlines()]


def test_likert_prompt_is_the_bad_pattern():
    assert "1-5" in LIKERT_PROMPT and "Output only the number" in LIKERT_PROMPT


def test_likert_parse():
    assert likert(FakeClient([text("4")]), ROWS[0]) == 4
    assert likert(FakeClient([text("Score: 2/5")]), ROWS[0]) == 2


def test_best_threshold_maximises_youden():
    scores = [5, 4, 3, 2, 1, 5, 2, 1]
    human = [True, True, True, False, False, False, False, False]
    t, cm = best_threshold(scores, human)
    assert t == 3
    assert cm == confusion(human, [s >= 3 for s in scores])


def test_binary_v2_beats_likert_on_failures_and_dev_overstates_test():
    res = run(ROWS, FakeClient(likert_length_judge),
              {"v1": FakeClient(incident_keyword_judge), "v2": FakeClient(incident_rules_judge)})
    assert res["v2"]["test"].tnr > res["likert"]["test"].tnr
    assert res["v2"]["test"].kappa > res["likert"]["test"].kappa
    # The judge iterated on dev looks better on dev than on held-out test.
    assert res["v2"]["dev"].accuracy > res["v2"]["test"].accuracy
    # Many wrong summaries get the top Likert score.
    assert res["likert_hist"].get(("fail", 5), 0) >= res["likert_hist"].get(("pass", 5), 0)


def test_dataset_shape():
    assert len(ROWS) == 60 and len({r["id"] for r in ROWS}) == 60
    labels = Counter(r["human_label"] for r in ROWS)
    assert labels["pass"] == labels["fail"] == 30
    assert set(r["split"] for r in ROWS) == {"train", "dev", "test"}
    assert all("Customer impact:" in r["facts"] and r["human_critique"] for r in ROWS)
    assert len(CODE_ROWS) == 20 and {r["human_label"] for r in CODE_ROWS} == {"pass", "fail"}
