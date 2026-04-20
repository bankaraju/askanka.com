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


def test_simulate_trade_short_hits_target_when_price_falls():
    # Downtrend; SHORT target (below entry) should hit.
    bars = _trending_minute_bars("2026-04-18", slope_per_min=-0.02)
    trade = simulator_intraday.simulate_trade(
        bars=bars, signal_time="2026-04-18 09:30:00",
        side="SHORT", stop_pct=0.05, target_pct=0.005,
        notional_inr=50000, slippage_bps=5.0, exit_time="14:30:00",
    )
    assert trade["exit_reason"] == "TARGET"
    assert trade["pnl_gross_inr"] > 0


def test_simulate_trade_short_hits_stop_when_price_rises():
    # Uptrend; SHORT stop (above entry) should hit.
    bars = _trending_minute_bars("2026-04-18", slope_per_min=0.02)
    trade = simulator_intraday.simulate_trade(
        bars=bars, signal_time="2026-04-18 09:30:00",
        side="SHORT", stop_pct=0.005, target_pct=0.05,
        notional_inr=50000, slippage_bps=5.0, exit_time="14:30:00",
    )
    assert trade["exit_reason"] == "STOP"
    assert trade["pnl_gross_inr"] < 0


def test_simulate_trade_short_flat_exits_at_time_stop():
    bars = _flat_minute_bars("2026-04-18")
    trade = simulator_intraday.simulate_trade(
        bars=bars, signal_time="2026-04-18 09:30:00",
        side="SHORT", stop_pct=0.02, target_pct=0.01,
        notional_inr=50000, slippage_bps=5.0, exit_time="14:30:00",
    )
    assert "14:30" in trade["exit_time"]
    assert trade["exit_reason"] == "TIME_STOP"
    assert trade["pnl_gross_inr"] == pytest.approx(0.0, abs=0.5)


def test_simulate_trade_signal_equal_to_bar_time_does_not_enter_that_bar():
    # Strict > semantics: signal at exact bar timestamp enters the NEXT bar.
    bars = _flat_minute_bars("2026-04-18")
    # Pick bar at 09:31 to ensure entry is 09:32
    trade = simulator_intraday.simulate_trade(
        bars=bars, signal_time="2026-04-18 09:31:00",
        side="LONG", stop_pct=0.02, target_pct=0.01,
        notional_inr=50000, slippage_bps=5.0, exit_time="14:30:00",
    )
    assert trade["entry_time"] == "2026-04-18 09:32:00"


def test_simulate_trade_straddle_bar_takes_stop_first():
    # Volatile bar whose [low, high] contains BOTH stop and target.
    # Policy: stop wins (pessimistic first-touch assumption).
    start = pd.Timestamp("2026-04-18 09:15")
    minutes = pd.date_range(start=start, periods=10, freq="1min")
    bars = pd.DataFrame({
        "date": minutes,
        "open":  [100.0] * 10,
        "high":  [100.5, 100.5, 102.0, 100.5, 100.5, 100.5, 100.5, 100.5, 100.5, 100.5],  # index 2 spikes high
        "low":   [ 99.5,  99.5,  98.0,  99.5,  99.5,  99.5,  99.5,  99.5,  99.5,  99.5],  # index 2 spikes low
        "close": [100.0] * 10,
        "volume": 1000,
    })
    # Signal at 09:15 → enter at 09:16 open=100. Index 2 is 09:17.
    # stop_pct=0.005 -> stop=99.5 ; target_pct=0.005 -> target=100.5.
    # Bar 09:17: low=98, high=102 -> BOTH stop (99.5) and target (100.5) in range.
    trade = simulator_intraday.simulate_trade(
        bars=bars, signal_time="2026-04-18 09:15:00",
        side="LONG", stop_pct=0.005, target_pct=0.005,
        notional_inr=50000, slippage_bps=5.0, exit_time="14:30:00",
    )
    assert trade["exit_reason"] == "STOP"  # pessimistic policy


def test_run_simulation_gracefully_handles_loader_error():
    signals = pd.DataFrame([{
        "date": "2026-04-18", "signal_time": "2026-04-18 09:30:00",
        "symbol": "X", "side": "LONG", "stop_pct": 0.02, "target_pct": 0.01,
        "z_score": 2.0,
    }])

    def failing_loader(symbol, date):
        raise FileNotFoundError(f"no bars for {symbol}")

    ledger = simulator_intraday.run_simulation(
        signals=signals, minute_bars_loader=failing_loader,
    )
    assert ledger.empty
    # Should still have canonical columns
    for col in simulator_intraday._LEDGER_COLUMNS:
        assert col in ledger.columns


def test_simulate_trade_eod_fallback_when_minute_data_truncated(caplog):
    # Only 200 bars → ends around 12:35, no 14:30 bar present.
    bars = _flat_minute_bars("2026-04-18", n_bars=200)
    with caplog.at_level("WARNING", logger="pipeline.research.phase_c_backtest.simulator_intraday"):
        trade = simulator_intraday.simulate_trade(
            bars=bars, signal_time="2026-04-18 09:30:00",
            side="LONG", stop_pct=0.02, target_pct=0.01,
            notional_inr=50000, slippage_bps=5.0, exit_time="14:30:00",
        )
    assert trade["exit_reason"] == "EOD"
    assert any("EOD fallback" in rec.message for rec in caplog.records)
