from __future__ import annotations
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent.parent.parent
RESEARCH_DIR = PIPELINE_DIR / "research"
CACHE_DIR = PIPELINE_DIR / "data" / "research" / "phase_c"
MINUTE_BARS_DIR = CACHE_DIR / "minute_bars"
DAILY_BARS_DIR = CACHE_DIR / "daily_bars"
UNIVERSE_DIR = CACHE_DIR / "fno_universe_history"
PROFILES_DIR = CACHE_DIR / "phase_a_profiles"
REGIME_BACKFILL = CACHE_DIR / "regime_backfill.json"

REPO_DIR = PIPELINE_DIR.parent
DOCS_DIR = REPO_DIR / "docs" / "research" / "phase-c-validation"


def ensure_cache() -> None:
    """Create cache subdirectories if missing. Idempotent."""
    for d in (MINUTE_BARS_DIR, DAILY_BARS_DIR, UNIVERSE_DIR, PROFILES_DIR):
        d.mkdir(parents=True, exist_ok=True)
