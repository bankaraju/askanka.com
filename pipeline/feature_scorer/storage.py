"""I/O for the Feature Coincidence Scorer artifacts.

- ticker_feature_models.json (weekly; read every intraday cycle)
- attractiveness_scores.json  (rewritten every 15-min cycle)
- attractiveness_snapshots.jsonl (append-only intraday history)
"""
from __future__ import annotations
import gzip
import json
import shutil
from pathlib import Path
from typing import Any

_PIPELINE_DIR = Path(__file__).parent.parent
_DATA_DIR = _PIPELINE_DIR / "data"

_MODELS_FILE = _DATA_DIR / "ticker_feature_models.json"
_SCORES_FILE = _DATA_DIR / "attractiveness_scores.json"
_SNAPSHOTS_FILE = _DATA_DIR / "attractiveness_snapshots.jsonl"
_SNAPSHOTS_ARCHIVE = _DATA_DIR / "attractiveness_snapshots"


def write_models(data: dict, *, out: Path | None = None) -> None:
    out = out or _MODELS_FILE
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2, default=str, ensure_ascii=False),
                   encoding="utf-8")


def read_models(*, path: Path | None = None) -> dict[str, Any]:
    path = path or _MODELS_FILE
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"models": {}}


def write_scores(data: dict, *, out: Path | None = None) -> None:
    out = out or _SCORES_FILE
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2, default=str, ensure_ascii=False),
                   encoding="utf-8")


def read_scores(*, path: Path | None = None) -> dict[str, Any]:
    path = path or _SCORES_FILE
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"scores": {}}


def append_snapshots(rows: list[dict], *, path: Path | None = None) -> int:
    path = path or _SNAPSHOTS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, default=str, ensure_ascii=False) + "\n")
    return len(rows)


def rotate_snapshots(*, path: Path | None = None,
                      archive_dir: Path | None = None,
                      now_ts: str | None = None) -> Path | None:
    """If the current snapshot file has lines from a previous month, archive it.

    now_ts defaults to today; passing an ISO string makes this testable.
    """
    from datetime import datetime
    path = path or _SNAPSHOTS_FILE
    archive_dir = archive_dir or _SNAPSHOTS_ARCHIVE
    if not path.exists() or path.stat().st_size == 0:
        return None
    first_line = path.read_text(encoding="utf-8").splitlines()[0]
    first_row = json.loads(first_line)
    file_month = first_row["ts"][:7]  # YYYY-MM

    now = datetime.fromisoformat(now_ts) if now_ts else datetime.now()
    now_month = now.isoformat()[:7]

    if file_month >= now_month:
        return None

    archive_dir.mkdir(parents=True, exist_ok=True)
    dest = archive_dir / f"{file_month}.jsonl.gz"
    with path.open("rb") as src, gzip.open(dest, "wb") as gz:
        shutil.copyfileobj(src, gz)
    path.unlink()
    return dest
