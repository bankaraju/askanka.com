"""Tests for the §5 DIRECTION-SUSPECT classifier."""
from pipeline.autoresearch.overshoot_compliance.direction_suspect import (
    classify_direction_verdict,
    CellResult,
)


class TestClassifyDirectionVerdict:
    def test_clean_when_lag_clears_bonferroni(self):
        lag = CellResult(ticker="RELIANCE", direction="UP", slice_name="LAG",
                          n_events=30, bonferroni_pass=True, edge_net_pct=0.6, p_value=1e-5)
        overshoot = CellResult(ticker="RELIANCE", direction="UP", slice_name="OVERSHOOT",
                                n_events=15, bonferroni_pass=False, edge_net_pct=-0.2, p_value=0.5)
        assert classify_direction_verdict(lag, overshoot) == "CLEAN"

    def test_direction_suspect_when_overshoot_clears_but_lag_does_not(self):
        lag = CellResult(ticker="TORNTPOWER", direction="UP", slice_name="LAG",
                          n_events=20, bonferroni_pass=False, edge_net_pct=0.1, p_value=0.4)
        overshoot = CellResult(ticker="TORNTPOWER", direction="UP", slice_name="OVERSHOOT",
                                n_events=12, bonferroni_pass=True, edge_net_pct=1.4, p_value=1e-5)
        assert classify_direction_verdict(lag, overshoot) == "DIRECTION_SUSPECT"

    def test_parameter_fragile_when_both_pass(self):
        lag = CellResult(ticker="SBIN", direction="UP", slice_name="LAG",
                          n_events=25, bonferroni_pass=True, edge_net_pct=0.7, p_value=1e-5)
        overshoot = CellResult(ticker="SBIN", direction="UP", slice_name="OVERSHOOT",
                                n_events=20, bonferroni_pass=True, edge_net_pct=1.2, p_value=1e-6)
        assert classify_direction_verdict(lag, overshoot) == "PARAMETER_FRAGILE_DIRECTION"

    def test_insufficient_power_when_either_slice_too_few_events(self):
        lag = CellResult(ticker="RARE", direction="UP", slice_name="LAG",
                          n_events=5, bonferroni_pass=False, edge_net_pct=None, p_value=None)
        overshoot = CellResult(ticker="RARE", direction="UP", slice_name="OVERSHOOT",
                                n_events=8, bonferroni_pass=False, edge_net_pct=None, p_value=None)
        assert classify_direction_verdict(lag, overshoot) == "INSUFFICIENT_POWER"

    def test_clean_when_neither_slice_passes(self):
        lag = CellResult(ticker="NOISE", direction="UP", slice_name="LAG",
                          n_events=20, bonferroni_pass=False, edge_net_pct=0.1, p_value=0.3)
        overshoot = CellResult(ticker="NOISE", direction="UP", slice_name="OVERSHOOT",
                                n_events=15, bonferroni_pass=False, edge_net_pct=-0.05, p_value=0.6)
        assert classify_direction_verdict(lag, overshoot) == "CLEAN"


class TestMismatchedPair:
    def test_ticker_mismatch_raises(self):
        import pytest
        lag = CellResult(ticker="A", direction="UP", slice_name="LAG",
                          n_events=20, bonferroni_pass=False, edge_net_pct=0.1, p_value=0.3)
        overshoot = CellResult(ticker="B", direction="UP", slice_name="OVERSHOOT",
                                n_events=15, bonferroni_pass=False, edge_net_pct=-0.05, p_value=0.6)
        with pytest.raises(ValueError):
            classify_direction_verdict(lag, overshoot)


class TestLoadCells:
    """Adapting the real compliance artifact schema (permutations_100k.json)."""

    def test_load_cells_from_permutations_json(self, tmp_path):
        import json
        from pipeline.autoresearch.overshoot_compliance.direction_suspect import load_cells
        artifact = tmp_path / "permutations_100k.json"
        artifact.write_text(json.dumps({
            "n_shuffles": 100000,
            "floor_required": 100000,
            "rows": [
                {"ticker": "A", "direction": "UP", "n_events": 30, "edge_net_pct": 0.8, "p_value": 1e-5},
                {"ticker": "B", "direction": "DOWN", "n_events": 5, "edge_net_pct": -0.1, "p_value": 0.8},
            ],
        }))
        cells = list(load_cells(artifact, slice_name="LAG", bonferroni_alpha=1.0e-4))
        assert len(cells) == 2
        a = [c for c in cells if c.ticker == "A"][0]
        assert a.bonferroni_pass is True  # p=1e-5 < 1e-4 AND edge > 0
        assert a.n_events == 30
        b = [c for c in cells if c.ticker == "B"][0]
        assert b.bonferroni_pass is False  # edge < 0 and p > alpha

    def test_bonferroni_pass_requires_positive_edge(self, tmp_path):
        import json
        from pipeline.autoresearch.overshoot_compliance.direction_suspect import load_cells
        artifact = tmp_path / "perms.json"
        artifact.write_text(json.dumps({
            "rows": [
                {"ticker": "X", "direction": "UP", "n_events": 30, "edge_net_pct": -0.5, "p_value": 1e-10},
            ],
        }))
        cells = list(load_cells(artifact, slice_name="LAG", bonferroni_alpha=1e-4))
        # Very significant p-value but negative edge → not a pass
        assert cells[0].bonferroni_pass is False


class TestClassifyAllCells:
    def test_writes_summary_and_returns_dict(self, tmp_path):
        import json
        from pipeline.autoresearch.overshoot_compliance.direction_suspect import classify_all_cells

        lag_art = tmp_path / "lag_perms.json"
        lag_art.write_text(json.dumps({"rows": [
            {"ticker": "A", "direction": "UP", "n_events": 30, "edge_net_pct": 0.6, "p_value": 1e-5},
        ]}))
        lag_manifest = tmp_path / "lag_manifest.json"
        lag_manifest.write_text(json.dumps({"config": {"family_size": 100}}))

        ovs_art = tmp_path / "ovs_perms.json"
        ovs_art.write_text(json.dumps({"rows": [
            {"ticker": "A", "direction": "UP", "n_events": 15, "edge_net_pct": -0.2, "p_value": 0.5},
        ]}))
        ovs_manifest = tmp_path / "ovs_manifest.json"
        ovs_manifest.write_text(json.dumps({"config": {"family_size": 100}}))

        out = tmp_path / "verdicts.json"
        result = classify_all_cells(
            lag_artifact_path=lag_art, lag_manifest_path=lag_manifest,
            overshoot_artifact_path=ovs_art, overshoot_manifest_path=ovs_manifest,
            output_path=out,
        )

        assert out.is_file()
        assert result["summary"]["verdict_counts"].get("CLEAN", 0) == 1
        assert result["summary"]["n_cells"] == 1
        v0 = result["verdicts"][0]
        assert v0["ticker"] == "A" and v0["direction"] == "UP" and v0["verdict"] == "CLEAN"
