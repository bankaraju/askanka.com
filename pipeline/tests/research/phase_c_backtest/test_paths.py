from pathlib import Path
from pipeline.research.phase_c_backtest import paths


def test_paths_are_under_repo():
    assert paths.PIPELINE_DIR.name == "pipeline"
    assert paths.RESEARCH_DIR == paths.PIPELINE_DIR / "research"
    assert paths.CACHE_DIR == paths.PIPELINE_DIR / "data" / "research" / "phase_c"
    assert paths.DOCS_DIR.name == "phase-c-validation"


def test_cache_subdirs_known():
    assert paths.MINUTE_BARS_DIR == paths.CACHE_DIR / "minute_bars"
    assert paths.DAILY_BARS_DIR == paths.CACHE_DIR / "daily_bars"
    assert paths.UNIVERSE_DIR == paths.CACHE_DIR / "fno_universe_history"
    assert paths.REGIME_BACKFILL == paths.CACHE_DIR / "regime_backfill.json"
    assert paths.PROFILES_DIR == paths.CACHE_DIR / "phase_a_profiles"


def test_ensure_cache_creates_dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(paths, "MINUTE_BARS_DIR", tmp_path / "cache" / "minute_bars")
    monkeypatch.setattr(paths, "DAILY_BARS_DIR", tmp_path / "cache" / "daily_bars")
    monkeypatch.setattr(paths, "UNIVERSE_DIR", tmp_path / "cache" / "fno_universe_history")
    monkeypatch.setattr(paths, "PROFILES_DIR", tmp_path / "cache" / "phase_a_profiles")
    paths.ensure_cache()
    assert paths.MINUTE_BARS_DIR.is_dir()
    assert paths.DAILY_BARS_DIR.is_dir()
    assert paths.UNIVERSE_DIR.is_dir()
    assert paths.PROFILES_DIR.is_dir()
