"""Freshness contracts for the Feature Coincidence Scorer."""
from pathlib import Path

from pipeline.watchdog_inventory import load_inventory


_PROD_INVENTORY = Path(__file__).parent.parent / "config" / "anka_inventory.json"


def _find_task(inv, name):
    for t in inv["tasks"]:
        if t["task_name"] == name:
            return t
    return None


def test_fit_task_tracks_models_file():
    inv = load_inventory(_PROD_INVENTORY)
    task = _find_task(inv, "AnkaFeatureScorerFit")
    assert task is not None, "AnkaFeatureScorerFit must appear in anka_inventory.json"
    assert task["cadence_class"] == "weekly"
    assert task["tier"] == "warn"
    assert "pipeline/data/ticker_feature_models.json" in task["outputs"]


def test_intraday_task_tracks_scores_file():
    inv = load_inventory(_PROD_INVENTORY)
    task = _find_task(inv, "AnkaFeatureScorerIntraday")
    assert task is not None, "AnkaFeatureScorerIntraday must appear in anka_inventory.json"
    assert task["cadence_class"] == "intraday"
    assert task["tier"] == "warn"
    assert "pipeline/data/attractiveness_scores.json" in task["outputs"]


def test_no_duplicate_feature_scorer_entries():
    inv = load_inventory(_PROD_INVENTORY)
    names = [t["task_name"] for t in inv["tasks"]]
    assert names.count("AnkaFeatureScorerFit") == 1
    assert names.count("AnkaFeatureScorerIntraday") == 1
