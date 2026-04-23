import json
import subprocess
from pathlib import Path

from pipeline.autoresearch.overshoot_compliance import manifest as M


def _write(tmp_path: Path, name: str, content: bytes) -> Path:
    p = tmp_path / name
    p.write_bytes(content)
    return p


def test_sha256_stable(tmp_path):
    f = _write(tmp_path, "a.csv", b"abc\n")
    assert M.sha256_of(f) == M.sha256_of(f)
    g = _write(tmp_path, "b.csv", b"abc\n")
    assert M.sha256_of(f) == M.sha256_of(g)


def test_sha256_changes_with_content(tmp_path):
    f = _write(tmp_path, "a.csv", b"abc\n")
    g = _write(tmp_path, "b.csv", b"xyz\n")
    assert M.sha256_of(f) != M.sha256_of(g)


def test_build_manifest_has_all_required_fields(tmp_path):
    f1 = _write(tmp_path, "p1.csv", b"one\n")
    f2 = _write(tmp_path, "p2.csv", b"two\n")
    m = M.build_manifest(
        hypothesis_id="H-TEST",
        strategy_version="0.1.0",
        cost_model_version="zerodha-ssf-2025-04",
        random_seed=42,
        data_files=[f1, f2],
        config={"min_z": 3.0, "window": 20},
    )
    for field in (
        "run_id", "hypothesis_id", "strategy_version", "git_commit",
        "config_hash", "data_file_sha256_manifest",
        "cost_model_version", "random_seed", "report_generated_at",
    ):
        assert field in m, f"missing {field}"
    assert m["hypothesis_id"] == "H-TEST"
    assert m["random_seed"] == 42
    assert set(m["data_file_sha256_manifest"].keys()) == {str(f1), str(f2)}
    for sha in m["data_file_sha256_manifest"].values():
        assert len(sha) == 64  # hex sha256


def test_git_commit_matches_current_head():
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], text=True
    ).strip()
    m = M.build_manifest(
        hypothesis_id="H-TEST",
        strategy_version="0.1.0",
        cost_model_version="zerodha-ssf-2025-04",
        random_seed=0,
        data_files=[],
        config={},
    )
    assert m["git_commit"] == head


def test_config_hash_deterministic():
    m1 = M.build_manifest(
        hypothesis_id="X", strategy_version="1", cost_model_version="c",
        random_seed=0, data_files=[], config={"a": 1, "b": 2},
    )
    m2 = M.build_manifest(
        hypothesis_id="X", strategy_version="1", cost_model_version="c",
        random_seed=0, data_files=[], config={"b": 2, "a": 1},  # reordered
    )
    assert m1["config_hash"] == m2["config_hash"]


def test_write_manifest_round_trip(tmp_path):
    out_dir = tmp_path / "run_x"
    m = M.build_manifest(
        hypothesis_id="H-TEST", strategy_version="0.1.0",
        cost_model_version="c", random_seed=1, data_files=[], config={"k": "v"},
    )
    path = M.write_manifest(m, out_dir)
    assert path.exists()
    loaded = json.loads(path.read_text())
    assert loaded == m


def test_write_manifest_handles_non_ascii_config(tmp_path):
    out_dir = tmp_path / "run_utf8"
    m = M.build_manifest(
        hypothesis_id="H-TEST", strategy_version="0.1.0",
        cost_model_version="c", random_seed=1, data_files=[],
        config={"note": "σ=0.3 • holdout ≥ 20%"},  # Greek + bullet + ≥
    )
    path = M.write_manifest(m, out_dir)
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["config"]["note"] == "σ=0.3 • holdout ≥ 20%"
