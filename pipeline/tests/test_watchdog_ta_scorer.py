import json
from pathlib import Path


def _load_inventory():
    p = Path("pipeline/config/anka_inventory.json")
    return json.loads(p.read_text(encoding="utf-8"))


def test_ta_scorer_fit_task_present():
    inv = _load_inventory()
    tasks = {t["task_name"]: t for t in inv["tasks"]}
    assert "AnkaTAScorerFit" in tasks
    e = tasks["AnkaTAScorerFit"]
    assert e["cadence_class"] == "weekly"
    assert e["tier"] == "warn"
    assert e["grace_multiplier"] >= 1.5
    assert any("ta_feature_models.json" in o for o in e["outputs"])


def test_ta_scorer_score_task_present():
    inv = _load_inventory()
    tasks = {t["task_name"]: t for t in inv["tasks"]}
    assert "AnkaTAScorerScore" in tasks
    e = tasks["AnkaTAScorerScore"]
    assert e["cadence_class"] == "daily"
    assert e["tier"] == "warn"
    assert any("ta_attractiveness_scores.json" in o for o in e["outputs"])


def test_no_duplicate_ta_entries():
    inv = _load_inventory()
    names = [t["task_name"] for t in inv["tasks"]]
    assert names.count("AnkaTAScorerFit") == 1
    assert names.count("AnkaTAScorerScore") == 1
