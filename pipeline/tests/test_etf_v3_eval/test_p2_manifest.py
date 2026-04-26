import json
from pathlib import Path

import pytest

from pipeline.autoresearch.etf_v3_eval.phase_2.manifest import (
    write_run_manifest,
    RunConfig,
)


def test_write_run_manifest_emits_required_fields(tmp_path):
    cfg = RunConfig(
        run_id="wf_lb756_u126_seed0",
        strategy_version="v3-CURATED-30",
        cost_model_version="cm_2026-04-26_v1",
        random_seed=0,
        lookback_days=756,
        refit_interval_days=5,
        n_iterations=2000,
        universe="126",
        feature_set="curated",
    )
    inputs = {"replay_parquet": tmp_path / "x.parquet"}
    (tmp_path / "x.parquet").write_bytes(b"hello")
    out_path = tmp_path / "manifest.json"
    write_run_manifest(out_path, cfg, input_files=inputs)
    m = json.loads(out_path.read_text(encoding="utf-8"))
    for required in (
        "run_id","strategy_version","git_commit_hash","config_hash",
        "data_file_sha256_manifest","random_seed","cost_model_version",
        "report_generated_at","lookback_days","refit_interval_days","n_iterations",
        "universe","feature_set",
    ):
        assert required in m, f"missing {required}"
    assert m["data_file_sha256_manifest"]["replay_parquet"].startswith(
        "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"  # sha256("hello")
    )


def test_write_run_manifest_raises_for_missing_input_file(tmp_path):
    """A manifest claiming a missing file is provenance-grade dangerous."""
    cfg = RunConfig(
        run_id="x", strategy_version="v", cost_model_version="cm",
        random_seed=0, lookback_days=1, refit_interval_days=1,
        n_iterations=1, universe="u", feature_set="f",
    )
    out_path = tmp_path / "manifest.json"
    with pytest.raises(FileNotFoundError, match="Manifest input not found"):
        write_run_manifest(out_path, cfg, input_files={"missing": tmp_path / "nope.parquet"})


def test_write_run_manifest_handles_empty_input_files(tmp_path):
    cfg = RunConfig(
        run_id="x", strategy_version="v", cost_model_version="cm",
        random_seed=0, lookback_days=1, refit_interval_days=1,
        n_iterations=1, universe="u", feature_set="f",
    )
    out_path = tmp_path / "manifest.json"
    write_run_manifest(out_path, cfg, input_files={})
    m = json.loads(out_path.read_text(encoding="utf-8"))
    assert m["data_file_sha256_manifest"] == {}


def test_write_run_manifest_hashes_multiple_input_files(tmp_path):
    cfg = RunConfig(
        run_id="x", strategy_version="v", cost_model_version="cm",
        random_seed=0, lookback_days=1, refit_interval_days=1,
        n_iterations=1, universe="u", feature_set="f",
    )
    a = tmp_path / "a.parquet"; a.write_bytes(b"alpha")
    b = tmp_path / "b.parquet"; b.write_bytes(b"beta")
    out_path = tmp_path / "manifest.json"
    write_run_manifest(out_path, cfg, input_files={"a": a, "b": b})
    m = json.loads(out_path.read_text(encoding="utf-8"))
    assert set(m["data_file_sha256_manifest"].keys()) == {"a", "b"}
    assert m["data_file_sha256_manifest"]["a"] != m["data_file_sha256_manifest"]["b"]
    assert len(m["data_file_sha256_manifest"]["a"]) == 64


def test_git_commit_hash_unknown_when_git_missing(monkeypatch):
    """If git isn't on PATH, manifest should record 'unknown' not crash."""
    import subprocess as _sp
    from pipeline.autoresearch.etf_v3_eval.phase_2 import manifest as m

    def _raise(*_a, **_kw):
        raise FileNotFoundError("git")

    monkeypatch.setattr(_sp, "check_output", _raise)
    assert m._git_commit_hash() == "unknown"
