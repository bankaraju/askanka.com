import numpy as np
import pandas as pd
import pytest

from pipeline.autoresearch.overshoot_compliance import portfolio_gate as PG


def test_pairwise_correlation_below_threshold_passes():
    rng = np.random.default_rng(0)
    dates = pd.bdate_range("2024-01-01", periods=252)
    pnl = pd.DataFrame({
        "A-UP": rng.normal(0.0, 1.0, size=252),
        "B-UP": rng.normal(0.0, 1.0, size=252),
        "C-DOWN": rng.normal(0.0, 1.0, size=252),
    }, index=dates)
    report = PG.evaluate(pnl, sectors={"A-UP": "IT", "B-UP": "Pharma", "C-DOWN": "Banks"},
                         corr_threshold=0.60, concentration_cap=0.40)
    assert report["max_pairwise_correlation"] < 0.60
    assert report["corr_verdict"] == "PASS"


def test_high_correlation_fails():
    dates = pd.bdate_range("2024-01-01", periods=252)
    rng = np.random.default_rng(1)
    a = rng.normal(0.0, 1.0, size=252)
    b = a + rng.normal(0.0, 0.05, size=252)
    pnl = pd.DataFrame({"A-UP": a, "B-UP": b}, index=dates)
    report = PG.evaluate(pnl, sectors={"A-UP": "IT", "B-UP": "Pharma"},
                         corr_threshold=0.60, concentration_cap=0.40)
    assert report["max_pairwise_correlation"] > 0.60
    assert report["corr_verdict"] == "FAIL"


def test_concentration_fails_when_single_sector_over_cap():
    dates = pd.bdate_range("2024-01-01", periods=50)
    rng = np.random.default_rng(2)
    cols = {f"T{i}-UP": rng.normal(0, 1, size=50) for i in range(10)}
    pnl = pd.DataFrame(cols, index=dates)
    sectors = {c: ("IT" if i < 5 else f"S{i}") for i, c in enumerate(pnl.columns)}
    report = PG.evaluate(pnl, sectors=sectors, corr_threshold=0.60, concentration_cap=0.40)
    assert report["max_sector_share"] >= 0.4
    assert report["concentration_verdict"] == "FAIL"
