"""Read/write TA scorer models + scores JSON. Mirrors feature_scorer.storage.
Default paths are repo-relative; callers can override via `out=`/`path=`."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any

_DATA = Path(__file__).resolve().parent.parent / "data"
_MODELS = _DATA / "ta_feature_models.json"
_SCORES = _DATA / "ta_attractiveness_scores.json"


def _empty_models() -> dict[str, Any]:
    return {"version": "1.0", "models": {}}


def _empty_scores() -> dict[str, Any]:
    return {"updated_at": None, "scores": {}}


def write_models(data: dict[str, Any], out: Path | None = None) -> None:
    p = Path(out) if out else _MODELS
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")


def read_models(path: Path | None = None) -> dict[str, Any]:
    p = Path(path) if path else _MODELS
    if not p.exists():
        return _empty_models()
    return json.loads(p.read_text(encoding="utf-8"))


def write_scores(data: dict[str, Any], out: Path | None = None) -> None:
    p = Path(out) if out else _SCORES
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")


def read_scores(path: Path | None = None) -> dict[str, Any]:
    p = Path(path) if path else _SCORES
    if not p.exists():
        return _empty_scores()
    return json.loads(p.read_text(encoding="utf-8"))
