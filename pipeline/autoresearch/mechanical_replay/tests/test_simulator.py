"""TDD for simulator — 09:30 entry, 14:30 hard close, ATR_STOP / Z_CROSS / TRAIL / TIME_STOP."""
from __future__ import annotations

from datetime import datetime, time

import numpy as np
import pandas as pd
import pytest

from pipeline.autoresearch.mechanical_replay import simulator, constants as C


def _synth_minute_bars(
    *,
    date_str: str = "2026-03-10",
    open_price: float = 100.0,
    move_pct_per_min: float = 0.0,
    n_bars: int = 360,  # 09:15 → 15:14
    high_offset_pct: float = 0.05,
    low_offset_pct: float = 0.05,
    spike_at_min: int | None = None,
    spike_pct: float = 0.0,
) -> pd.DataFrame:
    """Generate predictable minute bars from 09:15 IST.

    move_pct_per_min: linear drift in close per minute.
    spike_at_min: minute index (0-based from 09:15) at which to inject an
      intra-bar spike — the bar's high/low are pushed by spike_pct in addition
      to the normal high/low offsets.
    """
    start = datetime.fromisoformat(f"{date_str}T09:15:00")
    rows = []
    for i in range(n_bars):
        ts = start + pd.Timedelta(minutes=i)
        close = open_price * (1 + move_pct_per_min / 100.0 * i)
        open_ = open_price * (1 + move_pct_per_min / 100.0 * (i - 1)) if i > 0 else open_price
        high = max(open_, close) * (1 + high_offset_pct / 100.0)
        low = min(open_, close) * (1 - low_offset_pct / 100.0)
        if spike_at_min == i and spike_pct != 0:
            if spike_pct > 0:
                high = max(high, open_ * (1 + spike_pct / 100.0))
            else:
                low = min(low, open_ * (1 + spike_pct / 100.0))
        rows.append({"timestamp_ist": ts, "open": open_, "high": high, "low": low, "close": close, "volume": 1000})
    return pd.DataFrame(rows)


def test_long_time_stop_flat_market():
    """Flat market, no triggers → TIME_STOP at 14:30 with ~0 pnl."""
    bars = _synth_minute_bars(open_price=100.0, move_pct_per_min=0.0)
    res = simulator.simulate_one_trade(
        bars=bars,
        side="LONG",
        stop_pct=-3.0,
        zcross_time=None,
    )
    assert res["exit_reason"] == "TIME_STOP"
    assert abs(res["pnl_pct"]) < 0.5
    assert res["exit_time"].time() == C.HARD_CLOSE


def test_long_atr_stop_trips_on_spike_low():
    """LONG: a -4% intra-bar low should fire ATR_STOP at -3.0% (configured)."""
    bars = _synth_minute_bars(
        open_price=100.0,
        move_pct_per_min=0.0,
        # spike at 11:00 (60 mins after 09:30 entry → bar index 105 since 09:15 start)
        spike_at_min=105,
        spike_pct=-4.0,
    )
    res = simulator.simulate_one_trade(
        bars=bars,
        side="LONG",
        stop_pct=-3.0,
        zcross_time=None,
        slippage_bps_roundtrip=0,
    )
    assert res["exit_reason"] == "ATR_STOP"
    assert res["pnl_pct"] == pytest.approx(-3.0, abs=0.01)


def test_short_atr_stop_trips_on_spike_high():
    """SHORT: a +4% intra-bar high → ATR_STOP at -3.0% (loss for short)."""
    bars = _synth_minute_bars(
        open_price=100.0,
        move_pct_per_min=0.0,
        spike_at_min=105,
        spike_pct=+4.0,
    )
    res = simulator.simulate_one_trade(
        bars=bars,
        side="SHORT",
        stop_pct=-3.0,
        zcross_time=None,
        slippage_bps_roundtrip=0,
    )
    assert res["exit_reason"] == "ATR_STOP"
    assert res["pnl_pct"] == pytest.approx(-3.0, abs=0.01)


def test_long_trail_after_arm_then_giveback():
    """LONG: peak hits +3.0% (entry-relative), then close gives back 1% → TRAIL exit ≈ peak − giveback."""
    # Entry at 09:30 = bar index 15 (09:15 start). Build close path so that
    # entry_price (close at index 15) = 100, peak rises ~+3%, then gives back ~1.5%.
    n = 360
    start = datetime.fromisoformat("2026-03-10T09:15:00")
    rows = []
    for i in range(n):
        ts = start + pd.Timedelta(minutes=i)
        if i <= 15:
            close = 100.0  # flat through entry
        elif i < 75:
            close = 100.0 + 3.0 * (i - 15) / 60  # rise to 103 by minute 75
        else:
            # Plateau at 101.5 (giveback ≈ 1.5pp from peak 3pp = exits trail)
            close = max(103.0 - 1.5 * (i - 75) / 60, 101.5)
        open_ = close
        high = close * 1.0005
        low = close * 0.9995
        rows.append({"timestamp_ist": ts, "open": open_, "high": high, "low": low, "close": close, "volume": 1000})
    bars = pd.DataFrame(rows)

    res = simulator.simulate_one_trade(
        bars=bars,
        side="LONG",
        stop_pct=-3.0,
        zcross_time=None,
        slippage_bps_roundtrip=0,
    )
    assert res["exit_reason"] == "TRAIL"
    # peak ~3.05%, giveback = 1.0% → exit ≈ +2.05%
    assert res["pnl_pct"] == pytest.approx(3.0 - C.TRAIL_GIVEBACK_PCT, abs=0.4)
    assert res["mfe_pct"] >= C.TRAIL_ARM_PCT


def test_zcross_exits_at_provided_time():
    """When zcross_time is set, simulator exits at that bar's close."""
    bars = _synth_minute_bars(open_price=100.0, move_pct_per_min=0.005)  # gentle drift up
    zcross_at = pd.Timestamp("2026-03-10 11:00:00")
    res = simulator.simulate_one_trade(
        bars=bars,
        side="LONG",
        stop_pct=-3.0,
        zcross_time=zcross_at,
    )
    assert res["exit_reason"] == "Z_CROSS"
    assert res["exit_time"] == zcross_at


def test_no_entry_when_bars_after_entry_empty():
    """If there are no bars at/after 09:30, return NO_ENTRY."""
    # Generate bars only up to 09:25
    bars = _synth_minute_bars(n_bars=10)  # 09:15 → 09:24
    res = simulator.simulate_one_trade(
        bars=bars,
        side="LONG",
        stop_pct=-3.0,
        zcross_time=None,
    )
    assert res["exit_reason"] == "NO_ENTRY"


def test_invalid_side_raises():
    bars = _synth_minute_bars()
    with pytest.raises(ValueError):
        simulator.simulate_one_trade(bars=bars, side="FLAT", stop_pct=-3.0, zcross_time=None)


def test_slippage_subtracts_round_trip_in_bps():
    """A 20bps round-trip slippage should reduce the absolute pnl by 0.20pp on a TIME exit."""
    bars = _synth_minute_bars(open_price=100.0, move_pct_per_min=0.0)
    res_no_slip = simulator.simulate_one_trade(
        bars=bars, side="LONG", stop_pct=-3.0, zcross_time=None, slippage_bps_roundtrip=0
    )
    res_with_slip = simulator.simulate_one_trade(
        bars=bars, side="LONG", stop_pct=-3.0, zcross_time=None, slippage_bps_roundtrip=20
    )
    # Slippage hits both LONG and SHORT as a cost (subtracts from pnl).
    assert res_with_slip["pnl_pct"] == pytest.approx(res_no_slip["pnl_pct"] - 0.20, abs=0.01)
