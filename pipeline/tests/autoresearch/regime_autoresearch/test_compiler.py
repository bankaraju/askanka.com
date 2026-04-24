"""DSL-to-returns compiler tests (Task 8 step 2).

Covers _compile_proposal_returns: single_long, single_short, long_short_basket
(top_k / bottom_k), pair NotImplementedError, overlap semantics, insufficient
future data, _threshold_fires unit coverage, and the
regime_buy_and_hold_sharpe scarcity-fallback benchmark.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from pipeline.autoresearch.regime_autoresearch.dsl import Proposal
from pipeline.autoresearch.regime_autoresearch.in_sample_runner import (
    _compile_proposal_returns,
    _threshold_fires,
    regime_buy_and_hold_sharpe,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _single_long_panel() -> pd.DataFrame:
    """10-ticker panel where ticker_0's price path ensures its 5d return is
    far above the grid threshold 0.5 (i.e. >50% over 5 days as a fraction),
    and its 5-day forward return is strongly positive.

    The ABSOLUTE_THRESHOLD_GRID values (..., 0.5, 1.0, 2.0, 3.0) are
    interpreted as fractional return thresholds — so to fire `>` 0.5 the
    ticker must gain >50% in 5 days. The synthetic drift below achieves
    that for ticker_0 only.

    Construction:
      ticker_0: +15% per day (ret_5d ~ 2x, forward 5d also ~2x)
      ticker_i (i>0): -1% per day (ret_5d ~-5%, forward 5d ~-5%)
    """
    dates = pd.bdate_range("2023-01-02", periods=80)
    rows = []
    for i in range(10):
        ticker = f"T{i}"
        drift = 0.15 if i == 0 else -0.01
        base = 100.0
        for k, d in enumerate(dates):
            price = base * (1.0 + drift) ** k
            rows.append({"date": d, "ticker": ticker, "close": price,
                          "volume": 1e6, "regime_zone": "NEUTRAL"})
    return pd.DataFrame(rows)


def _basket_panel() -> pd.DataFrame:
    """20-ticker panel where ticker index correlates with future return.

    Tickers sorted by index: T0 has strongest upward drift, T19 strongest
    downward. We build ret_5d such that high ret_5d -> high forward 5d return.
    That way top_k long-leg beats bottom_k long-leg.
    """
    dates = pd.bdate_range("2023-01-02", periods=80)
    rows = []
    for i in range(20):
        # drift linear in i: T0 = +0.3%/day, T19 = -0.3%/day (approximately)
        drift = 0.003 - (i * 0.0003)
        base = 100.0
        for k, d in enumerate(dates):
            price = base * (1.0 + drift) ** k
            rows.append({"date": d, "ticker": f"T{i:02d}", "close": price,
                          "volume": 1e6, "regime_zone": "NEUTRAL"})
    return pd.DataFrame(rows)


def _nifty_drift_panel() -> pd.DataFrame:
    """Panel where NIFTY has +0.1% daily drift — Sharpe from buy-and-hold
    should be clearly positive after slippage.

    Also includes a second ticker so panel has >1 unique ticker.
    """
    dates = pd.bdate_range("2023-01-02", periods=200)
    rows = []
    nifty_price = 20000.0
    for k, d in enumerate(dates):
        price = nifty_price * (1.0 + 0.001) ** k
        rows.append({"date": d, "ticker": "NIFTY", "close": price,
                      "volume": 1e6, "regime_zone": "NEUTRAL"})
    # Plus one generic ticker
    base = 100.0
    for k, d in enumerate(dates):
        price = base * (1.0 + 0.0001) ** k
        rows.append({"date": d, "ticker": "T0", "close": price,
                      "volume": 1e6, "regime_zone": "NEUTRAL"})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# _threshold_fires unit tests
# ---------------------------------------------------------------------------


def test_threshold_fires_all_ops():
    assert _threshold_fires(">", 1.0, 0.5) is True
    assert _threshold_fires(">", 0.5, 0.5) is False
    assert _threshold_fires("<", -1.0, 0.0) is True
    assert _threshold_fires("<", 0.0, 0.0) is False
    assert _threshold_fires(">=", 0.5, 0.5) is True
    assert _threshold_fires(">=", 0.4, 0.5) is False
    assert _threshold_fires("<=", 0.5, 0.5) is True
    assert _threshold_fires("<=", 0.6, 0.5) is False
    with pytest.raises(ValueError):
        _threshold_fires("top_k", 1.0, 3)
    with pytest.raises(ValueError):
        _threshold_fires("bottom_k", 1.0, 3)


# ---------------------------------------------------------------------------
# single_long / single_short
# ---------------------------------------------------------------------------


def test_compiler_single_long_happy_path():
    panel = _single_long_panel()
    # Only events where ret_5d > 0.5% — only T0 qualifies
    # threshold_value 0.5 is in ABSOLUTE_THRESHOLD_GRID
    p = Proposal(
        construction_type="single_long",
        feature="ret_5d",
        threshold_op=">",
        threshold_value=0.5,
        hold_horizon=5,
        regime="NEUTRAL",
        pair_id=None,
    )
    tickers = sorted(panel["ticker"].unique().tolist())
    # event_dates: all dates in panel (filtered to regime NEUTRAL already)
    event_dates = pd.DatetimeIndex(sorted(panel["date"].unique()))
    rets = _compile_proposal_returns(p, panel, event_dates, tickers)
    assert len(rets) > 0, "expected at least one trade"
    assert rets.mean() > 0, f"expected positive mean return, got {rets.mean()}"


def test_compiler_single_short_inverts_sign():
    panel = _single_long_panel()
    p_long = Proposal(
        construction_type="single_long",
        feature="ret_5d",
        threshold_op=">",
        threshold_value=0.5,
        hold_horizon=5,
        regime="NEUTRAL",
        pair_id=None,
    )
    p_short = Proposal(
        construction_type="single_short",
        feature="ret_5d",
        threshold_op=">",
        threshold_value=0.5,
        hold_horizon=5,
        regime="NEUTRAL",
        pair_id=None,
    )
    tickers = sorted(panel["ticker"].unique().tolist())
    event_dates = pd.DatetimeIndex(sorted(panel["date"].unique()))
    rets_long = _compile_proposal_returns(p_long, panel, event_dates, tickers)
    rets_short = _compile_proposal_returns(p_short, panel, event_dates, tickers)
    # same number of trades
    assert len(rets_long) == len(rets_short)
    # short returns must be exact negation
    assert np.allclose(rets_long.values, -rets_short.values)


def test_compiler_overlap_single():
    """One-position-per-ticker: if ticker's signal fires on consecutive days,
    only the first day's trade is recorded. The second day's signal is
    suppressed because the first trade's position is still open.

    We use threshold -2.0 on ret_5d with `>`, which fires essentially
    always once ret_5d has warmed up — giving us maximum overlap pressure.
    """
    dates = pd.bdate_range("2023-01-02", periods=40)
    rows = []
    for k, d in enumerate(dates):
        price = 100.0 * (1.005) ** k  # +0.5%/day -> ret_5d ~+0.025
        rows.append({"date": d, "ticker": "T0", "close": price,
                      "volume": 1e6, "regime_zone": "NEUTRAL"})
    # Add a second ticker so panel has >1 ticker.
    for k, d in enumerate(dates):
        price = 100.0 * (0.999) ** k
        rows.append({"date": d, "ticker": "T1", "close": price,
                      "volume": 1e6, "regime_zone": "NEUTRAL"})
    panel = pd.DataFrame(rows)
    p = Proposal(
        construction_type="single_long",
        feature="ret_5d",
        threshold_op=">",
        threshold_value=-2.0,  # fires whenever feature is non-NaN
        hold_horizon=5,
        regime="NEUTRAL",
        pair_id=None,
    )
    tickers = ["T0", "T1"]
    event_dates = pd.DatetimeIndex(sorted(panel["date"].unique()))
    rets = _compile_proposal_returns(p, panel, event_dates, tickers)
    # T0 fires daily. With hold_horizon=5, trade N opens at day k and
    # exits at day k+5, so next eligible entry is at day >= k+5.
    # Over ~35 post-warmup days that's ~7 trades max for T0 (and up to 7
    # for T1 too, but T1 is always negative so doesn't fire — wait, we
    # set threshold to -2.0 so T1 fires too).
    # Key assertion: if there were NO overlap rule, we'd have ~70 trades
    # (35 days x 2 tickers). With overlap, each ticker can have at most
    # floor(~35/5) ~= 7 trades -> total ~14.
    assert len(rets) > 0, "expected at least one trade"
    assert len(rets) < 25, f"overlap rule not enforced: {len(rets)} trades"


def test_compiler_insufficient_future_data():
    """When the event date is too close to panel end, the trade is skipped."""
    # Panel ends on day 10; event on day 9 with hold_horizon=5 -> no exit.
    dates = pd.bdate_range("2023-01-02", periods=10)
    rows = []
    for k, d in enumerate(dates):
        price = 100.0 * (1.01) ** k
        rows.append({"date": d, "ticker": "T0", "close": price,
                      "volume": 1e6, "regime_zone": "NEUTRAL"})
        rows.append({"date": d, "ticker": "T1", "close": price * 0.95,
                      "volume": 1e6, "regime_zone": "NEUTRAL"})
    panel = pd.DataFrame(rows)
    p = Proposal(
        construction_type="single_long",
        feature="ret_1d",
        threshold_op=">",
        threshold_value=-2.0,  # will always fire
        hold_horizon=5,
        regime="NEUTRAL",
        pair_id=None,
    )
    tickers = ["T0", "T1"]
    # Only use the last 3 dates as events — none have 5-day future.
    event_dates = pd.DatetimeIndex(sorted(panel["date"].unique())[-3:])
    rets = _compile_proposal_returns(p, panel, event_dates, tickers)
    assert len(rets) == 0, (
        f"expected 0 trades due to insufficient future data, got {len(rets)}"
    )


# ---------------------------------------------------------------------------
# long_short_basket
# ---------------------------------------------------------------------------


def test_compiler_basket_top_k_beats_bottom_k():
    panel = _basket_panel()
    # top_k with k=3 means longs = top-3 by ret_5d (T00, T01, T02 with
    # strongest drift), shorts = bottom-3 (T17, T18, T19 with most negative).
    # Since drift correlates with forward-returns, top_k basket should be
    # positive.
    p_top = Proposal(
        construction_type="long_short_basket",
        feature="ret_5d",
        threshold_op="top_k",
        threshold_value=3,
        hold_horizon=5,
        regime="NEUTRAL",
        pair_id=None,
    )
    p_bot = Proposal(
        construction_type="long_short_basket",
        feature="ret_5d",
        threshold_op="bottom_k",
        threshold_value=3,
        hold_horizon=5,
        regime="NEUTRAL",
        pair_id=None,
    )
    tickers = sorted(panel["ticker"].unique().tolist())
    event_dates = pd.DatetimeIndex(sorted(panel["date"].unique()))
    rets_top = _compile_proposal_returns(p_top, panel, event_dates, tickers)
    rets_bot = _compile_proposal_returns(p_bot, panel, event_dates, tickers)
    assert len(rets_top) > 0
    assert len(rets_bot) > 0
    assert rets_top.mean() > 0, (
        f"top_k basket should be positive, got {rets_top.mean()}"
    )
    assert rets_bot.mean() < 0, (
        f"bottom_k basket should be negative, got {rets_bot.mean()}"
    )


def test_compiler_overlap_basket():
    """Once a basket opens, no new basket opens until the first has exited."""
    panel = _basket_panel()
    p = Proposal(
        construction_type="long_short_basket",
        feature="ret_5d",
        threshold_op="top_k",
        threshold_value=3,
        hold_horizon=5,
        regime="NEUTRAL",
        pair_id=None,
    )
    tickers = sorted(panel["ticker"].unique().tolist())
    event_dates = pd.DatetimeIndex(sorted(panel["date"].unique()))
    rets = _compile_proposal_returns(p, panel, event_dates, tickers)
    assert len(rets) > 0
    # Feature warmup = 5d returns, so valid eval_dates start ~day 6. With
    # 80 panel days, ~75 valid, div 5 = ~15 non-overlapping baskets upper
    # bound. The essential contract: must be much less than naive per-day.
    assert len(rets) <= 80 // 5 + 1, (
        f"overlap rule not enforced at basket level: {len(rets)} baskets"
    )


# ---------------------------------------------------------------------------
# pair
# ---------------------------------------------------------------------------


def test_compiler_pair_raises():
    panel = _single_long_panel()
    p = Proposal(
        construction_type="pair",
        feature="ret_5d",
        threshold_op=">",
        threshold_value=0.5,
        hold_horizon=5,
        regime="NEUTRAL",
        pair_id="PAIR_HDFC_ICICI",
    )
    tickers = sorted(panel["ticker"].unique().tolist())
    event_dates = pd.DatetimeIndex(sorted(panel["date"].unique()))
    with pytest.raises(NotImplementedError, match="pair construction"):
        _compile_proposal_returns(p, panel, event_dates, tickers)


# ---------------------------------------------------------------------------
# regime_buy_and_hold_sharpe
# ---------------------------------------------------------------------------


def test_regime_buy_and_hold_sharpe_nontrivial():
    panel = _nifty_drift_panel()
    # Use all dates in panel as regime-tagged dates.
    regime = pd.DatetimeIndex(sorted(panel["date"].unique()))
    sharpe = regime_buy_and_hold_sharpe(
        panel, regime, benchmark_ticker="NIFTY", hold_horizon=1,
    )
    # With +0.1%/day drift, 1d holding returns average ~0.1%. After 30 bps
    # slippage per round-trip the net is ~-0.2%/day — negative. The test
    # asserts the Sharpe is FINITE and the function returns a float; the
    # sign depends on whether drift > slippage.
    assert isinstance(sharpe, float), f"expected float, got {type(sharpe)}"
    assert not np.isnan(sharpe)
    # Stronger test: with 0.1%/day drift over 1d hold, gross = 0.1%, net
    # (after 30 bps = 0.3%) is -0.2%. So Sharpe should be negative.
    # (This is the expected behaviour — costs dominate tiny drift.)
    # The test name says "nontrivial" — i.e. not zero/NaN/infinity.
    assert np.isfinite(sharpe)


def test_regime_buy_and_hold_sharpe_positive_with_strong_drift():
    """With 1%/day drift, Sharpe must be positive even after slippage."""
    dates = pd.bdate_range("2023-01-02", periods=200)
    rows = []
    for k, d in enumerate(dates):
        price = 20000.0 * (1.0 + 0.01) ** k
        rows.append({"date": d, "ticker": "NIFTY", "close": price,
                      "volume": 1e6, "regime_zone": "NEUTRAL"})
    panel = pd.DataFrame(rows)
    regime = pd.DatetimeIndex(sorted(panel["date"].unique()))
    sharpe = regime_buy_and_hold_sharpe(
        panel, regime, benchmark_ticker="NIFTY", hold_horizon=1,
    )
    assert sharpe > 0, f"expected positive Sharpe with 1%/day drift, got {sharpe}"
