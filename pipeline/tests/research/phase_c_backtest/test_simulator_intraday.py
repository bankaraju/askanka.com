"""Tests for the intraday 1-minute simulator with mechanical 14:30 IST exit."""
from __future__ import annotations

import pandas as pd
import pytest

from pipeline.research.phase_c_backtest import simulator_intraday


def _flat_minute_bars(date: str, n_bars: int = 375) -> pd.DataFrame:
    """Trading day with 375 1-min bars (09:15 to 15:30 IST). All bars at price 100."""
    start = pd.Timestamp(f"{date} 09:15")
    minutes = pd.date_range(start=start, periods=n_bars, freq="1min")
    return pd.DataFrame({
        "date": minutes,
        "open": 100.0,
        "high": 100.0,
        "low": 100.0,
        "close": 100.0,
        "volume": 1000,
    })


def _trending_minute_bars(date: str, slope_per_min: float, n_bars: int = 375) -> pd.DataFrame:
    start = pd.Timestamp(f"{date} 09:15")
    minutes = pd.date_range(start=start, periods=n_bars, freq="1min")
    closes = [100.0 + i * slope_per_min for i in range(n_bars)]
    opens = [100.0] + closes[:-1]
    return pd.DataFrame({
        "date": minutes,
        "open": opens,
        "high": [max(o, c) + 0.05 for o, c in zip(opens, closes)],
        "low": [min(o, c) - 0.05 for o, c in zip(opens, closes)],
        "close": closes,
        "volume": [1000] * n_bars,
    })


def test_simulate_trade_enters_at_next_bar_open():
    bars = _flat_minute_bars("2026-04-18")
    trade = simulator_intraday.simulate_trade(
        bars=bars,
        signal_time="2026-04-18 09:30:00",
        side="LONG",
        stop_pct=0.02,
        target_pct=0.01,
        notional_inr=50000,
        slippage_bps=5.0,
        exit_time="14:30:00",
    )
    # Signal at 09:30:00, entry at next bar (09:31) open
    assert trade["entry_time"] == "2026-04-18 09:31:00"
    assert trade["entry_px"] == 100.0


def test_simulate_trade_exits_at_1430_if_no_stop_or_target_hit():
    bars = _flat_minute_bars("2026-04-18")
    trade = simulator_intraday.simulate_trade(
        bars=bars,
        signal_time="2026-04-18 09:30:00",
        side="LONG",
        stop_pct=0.02,
        target_pct=0.01,
        notional_inr=50000,
        slippage_bps=5.0,
        exit_time="14:30:00",
    )
    assert "14:30" in trade["exit_time"]
    assert trade["exit_reason"] == "TIME_STOP"
    assert trade["pnl_gross_inr"] == pytest.approx(0.0, abs=0.5)


def test_simulate_trade_long_hits_target_early():
    # +0.02 per minute uptrend. Entry at 09:31 bar open = closes[15] = 100 + 15*0.02 = 100.30
    # target = 100.30 * 1.005 = ~100.80, hit a few minutes later via bar high.
    bars = _trending_minute_bars("2026-04-18", slope_per_min=0.02)
    trade = simulator_intraday.simulate_trade(
        bars=bars,
        signal_time="2026-04-18 09:30:00",
        side="LONG",
        stop_pct=0.05,
        target_pct=0.005,
        notional_inr=50000,
        slippage_bps=5.0,
        exit_time="14:30:00",
    )
    assert trade["exit_reason"] == "TARGET"
    assert trade["pnl_gross_inr"] > 0


def test_simulate_trade_long_hits_stop_when_price_falls():
    bars = _trending_minute_bars("2026-04-18", slope_per_min=-0.02)
    trade = simulator_intraday.simulate_trade(
        bars=bars,
        signal_time="2026-04-18 09:30:00",
        side="LONG",
        stop_pct=0.005,
        target_pct=0.05,
        notional_inr=50000,
        slippage_bps=5.0,
        exit_time="14:30:00",
    )
    assert trade["exit_reason"] == "STOP"
    assert trade["pnl_gross_inr"] < 0


def test_simulate_trade_returns_none_when_signal_after_exit_time():
    bars = _flat_minute_bars("2026-04-18")
    trade = simulator_intraday.simulate_trade(
        bars=bars,
        signal_time="2026-04-18 14:35:00",
        side="LONG",
        stop_pct=0.02,
        target_pct=0.01,
        notional_inr=50000,
        slippage_bps=5.0,
        exit_time="14:30:00",
    )
    assert trade is None
