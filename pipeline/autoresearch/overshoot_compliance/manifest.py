"""Reproducibility manifest per §13A.1 of backtesting-specs.txt v1.0."""
from __future__ import annotations

import hashlib
import json
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True,
            cwd=Path(__file__).resolve().parents[3],
        ).strip()
    except Exception:
        return "unknown"


def _config_hash(config: dict) -> str:
    canonical = json.dumps(config, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_manifest(
    *,
    hypothesis_id: str,
    strategy_version: str,
    cost_model_version: str,
    random_seed: int,
    data_files: Iterable[Path],
    config: dict,
) -> dict:
    data_files = list(data_files)
    return {
        "run_id": uuid.uuid4().hex,
        "hypothesis_id": hypothesis_id,
        "strategy_version": strategy_version,
        "git_commit": _git_commit(),
        "config_hash": _config_hash(config),
        "config": config,
        "data_file_sha256_manifest": {
            str(p): sha256_of(p) for p in data_files
        },
        "cost_model_version": cost_model_version,
        "random_seed": random_seed,
        "report_generated_at": datetime.now(timezone.utc).isoformat(),
    }


def write_manifest(manifest: dict, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2, default=str))
    return path
