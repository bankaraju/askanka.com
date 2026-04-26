"""Run manifest writer per Backtest Spec §13A.1."""
from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _git_commit_hash() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True, timeout=10,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return "unknown"


def _pip_freeze_sha256() -> str:
    try:
        result = subprocess.run(
            ["pip", "freeze"],
            capture_output=True, text=True, check=True, timeout=30,
        )
        return hashlib.sha256(result.stdout.encode("utf-8")).hexdigest()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return "unknown"


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def write_manifest(
    out_path: Path,
    run_id: str,
    config: dict[str, Any],
    seed: int,
    artifact_paths: list[Path],
) -> None:
    """Write a §13A.1-compliant run manifest."""
    manifest = {
        "run_id": run_id,
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "git_commit": _git_commit_hash(),
        "pip_freeze_sha256": _pip_freeze_sha256(),
        "seed": seed,
        "config": config,
        "artifacts": {str(p): _file_sha256(p) for p in artifact_paths if Path(p).exists()},
    }
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
