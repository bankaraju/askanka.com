import json
from pathlib import Path
from pipeline.ta_scorer import storage


def test_models_roundtrip(tmp_path: Path):
    p = tmp_path / "models.json"
    payload = {"version": "1.0", "models": {"RELIANCE": {"health": "GREEN"}}}
    storage.write_models(payload, out=p)
    data = storage.read_models(path=p)
    assert data["models"]["RELIANCE"]["health"] == "GREEN"


def test_scores_roundtrip(tmp_path: Path):
    p = tmp_path / "scores.json"
    storage.write_scores({"updated_at": "x", "scores": {}}, out=p)
    data = storage.read_scores(path=p)
    assert data["scores"] == {}


def test_read_models_missing_file_returns_empty(tmp_path: Path):
    missing = tmp_path / "nope.json"
    assert storage.read_models(path=missing) == {"version": "1.0", "models": {}}


def test_read_scores_missing_returns_empty(tmp_path: Path):
    missing = tmp_path / "nope.json"
    data = storage.read_scores(path=missing)
    assert data["scores"] == {}
