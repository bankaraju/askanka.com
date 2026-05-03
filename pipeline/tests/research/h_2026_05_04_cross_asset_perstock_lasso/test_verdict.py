import pytest
from pipeline.research.h_2026_05_04_cross_asset_perstock_lasso.verdict import (
    classify_n_qualifying_band,
    compute_basket_metrics,
)


def test_band_classifications():
    assert classify_n_qualifying_band(0) == "FAIL_NO_QUALIFIERS"
    assert classify_n_qualifying_band(3) == "FAIL_INSUFFICIENT_QUALIFIERS"
    assert classify_n_qualifying_band(15) == "EXPECTED_BAND"
    assert classify_n_qualifying_band(40) == "AMPLIFIED_AUDIT_REQUIRED"
    assert classify_n_qualifying_band(81) == "FAIL_LEAKAGE_SUSPECT"


def test_compute_basket_metrics_known_inputs():
    rows = [
        {"pnl_inr": 1000, "position_inr": 50000},  # +2.0%
        {"pnl_inr": -500, "position_inr": 50000},  # -1.0%
        {"pnl_inr": 750, "position_inr": 50000},   # +1.5%
        {"pnl_inr": 200, "position_inr": 50000},   # +0.4%
    ]
    m = compute_basket_metrics(rows)
    assert m["n_trades"] == 4
    assert m["hit_rate_pct"] == pytest.approx(75.0)  # 3 of 4 positive
    assert m["mean_pnl_pct"] == pytest.approx(0.725)  # mean of +2.0, -1.0, +1.5, +0.4
