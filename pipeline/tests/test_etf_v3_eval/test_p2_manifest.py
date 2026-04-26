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
