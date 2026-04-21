from __future__ import annotations
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent.parent.parent
CACHE_DIR = PIPELINE_DIR / "data" / "research" / "phase_c_v5"
LEDGERS_DIR = CACHE_DIR / "ledgers"
INDICES_DAILY_DIR = PIPELINE_DIR / "data" / "india_historical" / "indices"
INDICES_MINUTE_DIR = INDICES_DAILY_DIR / "intraday"
CONCENTRATION_FILE = PIPELINE_DIR / "config" / "sector_concentration.json"

REPO_DIR = PIPELINE_DIR.parent
DOCS_DIR = REPO_DIR / "docs" / "research" / "phase-c-v5-baskets"


def ensure_cache() -> None:
    """Create cache subdirectories if missing. Idempotent."""
    for d in (CACHE_DIR, LEDGERS_DIR, INDICES_DAILY_DIR, INDICES_MINUTE_DIR, DOCS_DIR):
        d.mkdir(parents=True, exist_ok=True)
