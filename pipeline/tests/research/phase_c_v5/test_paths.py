from pipeline.research.phase_c_v5 import paths


def test_paths_module_exports_expected_constants():
    assert paths.PIPELINE_DIR.name == "pipeline"
    assert paths.CACHE_DIR.parts[-3:] == ("pipeline", "data", "research") or \
           paths.CACHE_DIR.parts[-2:] == ("research", "phase_c_v5")
    assert paths.LEDGERS_DIR.name == "ledgers"
    assert paths.INDICES_DAILY_DIR.name == "indices"
    assert paths.DOCS_DIR.parts[-2:] == ("research", "phase-c-v5-baskets")


def test_ensure_cache_creates_directories(tmp_path, monkeypatch):
    """ensure_cache() must create all subdirs; idempotent on re-call."""
    monkeypatch.setattr(paths, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(paths, "LEDGERS_DIR", tmp_path / "cache" / "ledgers")
    monkeypatch.setattr(paths, "INDICES_DAILY_DIR", tmp_path / "cache" / "indices" / "daily")
    monkeypatch.setattr(paths, "INDICES_MINUTE_DIR", tmp_path / "cache" / "indices" / "minute")
    paths.ensure_cache()
    assert (tmp_path / "cache" / "ledgers").is_dir()
    assert (tmp_path / "cache" / "indices" / "daily").is_dir()
    assert (tmp_path / "cache" / "indices" / "minute").is_dir()
    # idempotent
    paths.ensure_cache()
