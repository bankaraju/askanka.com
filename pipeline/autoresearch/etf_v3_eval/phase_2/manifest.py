"""§13A.1 per-run manifest writer for Phase 2 backtest runs.

Extends pipeline/autoresearch/etf_v3_eval/manifest.py (Phase 1 dataset manifest)
with strategy_version, config_hash, lookback_days, n_iterations, universe.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class RunConfig:
    run_id: str
    strategy_version: str
    cost_model_version: str
    random_seed: int
    lookback_days: int
    refit_interval_days: int
    n_iterations: int
    universe: str
    feature_set: str


def _git_commit_hash() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return "unknown"


def _file_sha256(path: Path) -> str:
    if not path.exists():
        return "missing"
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _config_hash(cfg: RunConfig) -> str:
    blob = json.dumps(asdict(cfg), sort_keys=True).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def write_run_manifest(
    path: Path,
    cfg: RunConfig,
    input_files: Mapping[str, Path],
) -> None:
    manifest = {
        **asdict(cfg),
        "git_commit_hash": _git_commit_hash(),
        "config_hash": _config_hash(cfg),
        "data_file_sha256_manifest": {
            name: _file_sha256(p) for name, p in input_files.items()
        },
        "report_generated_at": datetime.now(timezone.utc).isoformat(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
