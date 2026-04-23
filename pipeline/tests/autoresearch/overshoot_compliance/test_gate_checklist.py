import json
from pathlib import Path

import pytest

from pipeline.autoresearch.overshoot_compliance import gate_checklist as GC


def _minimal_inputs():
    return {
        "slippage_s0_s1": {"s0_sharpe": 1.1, "s0_hit": 0.58, "s0_max_dd": 0.12,
                            "s1_sharpe": 0.9, "s1_max_dd": 0.18, "s1_cum_pnl_pct": 35.0},
        "metrics_present": True,
        "data_audit": {"classification": "CLEAN", "impaired_pct": 0.4},
        "universe_snapshot": {"status": "SURVIVORSHIP-UNCORRECTED-WAIVED",
                              "waiver_path": "docs/superpowers/waivers/..."},
        "execution_mode": "MODE_A",
        "direction_audit": {"conflicts": 3, "n_survivors": 20},
        "power_analysis": {"min_n_per_regime_met": True, "underpowered_count": 0},
        "fragility": {"verdict": "STABLE"},
        "comparators": {"beaten_strongest": True, "strongest_name": "momentum_follow"},
        "permutations": {"n_shuffles": 100_000, "floor_required": 100_000},
        "holdout": {"pct": 0.06, "target": 0.20},
        "beta_regression": {"residual_sharpe": 0.8, "gross_sharpe": 1.0},
    }


def test_gate_emits_all_sections():
    report = GC.build(_minimal_inputs(), hypothesis_id="H-TEST")
    sections = {r["section"] for r in report["rows"]}
    for needed in {"1/3", "2", "5A", "6", "7", "8", "9", "9A", "9B.1", "9B.2", "10", "11B"}:
        assert needed in sections


def test_gate_pass_when_every_row_passes():
    inp = _minimal_inputs()
    inp["holdout"]["pct"] = 0.25
    report = GC.build(inp, hypothesis_id="H-TEST")
    assert report["decision"] == "PASS"


def test_gate_partial_when_waivered_sections_present():
    inp = _minimal_inputs()
    report = GC.build(inp, hypothesis_id="H-TEST")
    assert report["decision"] in {"PARTIAL", "FAIL"}


def test_gate_fail_when_slippage_s0_missed():
    inp = _minimal_inputs()
    inp["slippage_s0_s1"]["s0_sharpe"] = 0.3
    report = GC.build(inp, hypothesis_id="H-TEST")
    assert report["decision"] == "FAIL"


def test_write_to_disk_round_trips(tmp_path):
    report = GC.build(_minimal_inputs(), hypothesis_id="H-TEST")
    out = GC.write(report, tmp_path)
    assert out.exists()
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded == report
