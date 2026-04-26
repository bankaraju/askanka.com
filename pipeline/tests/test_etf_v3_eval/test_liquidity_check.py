# pipeline/tests/test_etf_v3_eval/test_liquidity_check.py
import pandas as pd
import pytest

from pipeline.autoresearch.etf_v3_eval.phase_2.liquidity_check import (
    compute_60d_adv,
    impact_penalty_bps,
)


def test_compute_60d_adv():
    df = pd.DataFrame({
        "ticker": ["A"]*5,
        "trade_date": pd.date_range("2026-01-01", periods=5),
        "close": [100.0]*5,
        "volume": [100_000, 200_000, 150_000, 250_000, 100_000],
    })
    out = compute_60d_adv(df, window=5)
    # mean(volume) * mean(close) = 160000 * 100
    assert out["A"] == pytest.approx(160_000 * 100.0)


def test_impact_penalty_scales_linearly_with_position_over_adv():
    p = impact_penalty_bps(position_size=2_000_000, adv=10_000_000)
    # base = 0; penalty = 5 * (2e6 / 1e7) = 1.0 bps
    assert p == pytest.approx(1.0)


def test_compute_60d_adv_raises_on_missing_columns():
    df = pd.DataFrame({"ticker": ["A"], "close": [100.0]})  # missing volume
    with pytest.raises(ValueError, match="volume"):
        compute_60d_adv(df)


def test_impact_penalty_raises_on_zero_adv():
    with pytest.raises(ValueError, match="adv must be > 0"):
        impact_penalty_bps(position_size=1_000_000, adv=0)


def test_impact_penalty_raises_on_negative_position():
    with pytest.raises(ValueError, match="position_size"):
        impact_penalty_bps(position_size=-1, adv=1_000_000)
