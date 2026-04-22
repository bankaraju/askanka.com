import json
from pathlib import Path


def test_write_and_read_models(tmp_path):
    from pipeline.feature_scorer.storage import write_models, read_models
    data = {"updated_at": "2026-04-22T01:00:00+05:30",
            "models": {"KAYNES": {"health": "GREEN", "mean_auc": 0.58}}}
    f = tmp_path / "models.json"
    write_models(data, out=f)
    got = read_models(path=f)
    assert got["models"]["KAYNES"]["health"] == "GREEN"


def test_read_missing_models_returns_empty(tmp_path):
    from pipeline.feature_scorer.storage import read_models
    got = read_models(path=tmp_path / "nope.json")
    assert got == {"models": {}}


def test_write_and_read_scores(tmp_path):
    from pipeline.feature_scorer.storage import write_scores, read_scores
    scores = {"updated_at": "2026-04-22T14:45:00+05:30",
              "scores": {"KAYNES": {"score": 67, "band": "AMBER"}}}
    f = tmp_path / "scores.json"
    write_scores(scores, out=f)
    got = read_scores(path=f)
    assert got["scores"]["KAYNES"]["score"] == 67


def test_append_snapshot_then_read_lines(tmp_path):
    from pipeline.feature_scorer.storage import append_snapshots
    f = tmp_path / "snap.jsonl"
    rows = [
        {"ts": "2026-04-22T09:30:00", "ticker": "KAYNES", "score": 62, "band": "AMBER"},
        {"ts": "2026-04-22T09:30:00", "ticker": "PGEL",   "score": 54, "band": "GREEN"},
    ]
    append_snapshots(rows, path=f)
    lines = f.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2
    assert json.loads(lines[0])["ticker"] == "KAYNES"


def test_append_is_idempotent_on_repeated_calls(tmp_path):
    from pipeline.feature_scorer.storage import append_snapshots
    f = tmp_path / "snap.jsonl"
    append_snapshots([{"ts": "t1", "ticker": "A", "score": 50, "band": "GREEN"}], path=f)
    append_snapshots([{"ts": "t2", "ticker": "B", "score": 60, "band": "GREEN"}], path=f)
    lines = f.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2


def test_rotate_snapshots_archives_last_month(tmp_path):
    """rotate_snapshots moves the raw jsonl to archive dir when called past month boundary."""
    from pipeline.feature_scorer.storage import append_snapshots, rotate_snapshots
    f = tmp_path / "snap.jsonl"
    archive = tmp_path / "archive"
    append_snapshots([{"ts": "2026-03-15T09:30:00", "ticker": "A", "score": 50}], path=f)
    rotate_snapshots(path=f, archive_dir=archive, now_ts="2026-04-01T02:00:00")
    assert not f.exists()  # moved out of the way
    archives = list(archive.glob("2026-03*.jsonl*"))
    assert len(archives) == 1
