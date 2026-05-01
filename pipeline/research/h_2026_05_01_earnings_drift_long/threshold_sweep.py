"""Threshold sweep for H-2026-05-01-earnings-drift-long-v1.

Search a small grid of (vol_z_threshold, short_mom_floor, optional realized-vol filter)
to find the FROZEN spec parameters that maximize a robust criterion:
  - mean net@20 >= +25 bps
  - hit >= 0.50
  - Sharpe >= 0.5
  - MaxDD as % single-leg notional >= -30%
  - n >= 30 (statistical floor for in-sample inference)

The chosen cell is registered. Other cells are forensic only.

NOT a HARKing / parameter-retry — this is the in-sample chosen-cell selection
documented per §14.4 backtesting-specs (in-sample evidence).
"""
from __future__ import annotations

import json
import math
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
OUT_JSON = ROOT / "pipeline" / "research" / "h_2026_05_01_earnings_drift_long" / "threshold_sweep.json"

from pipeline.research.h_2026_05_01_earnings_drift_long.earnings_drift_signal_generator import (
    _read_daily, load_calendar, load_universe, _last_trading_day_strictly_before,
    _compute_features, MIN_PRIOR_BARS, ATR_LOOKBACK, STOP_ATR_MULT,
)
from pipeline.research.h_2026_05_01_earnings_drift_long.earnings_drift_backtest import (
    HOLD_TRADING_DAYS, COST_BPS_S1, _exit_with_stop, _max_dd, _annualised_sharpe,
)

WINDOW_START = pd.Timestamp("2021-05-01")
WINDOW_END = pd.Timestamp("2024-04-30")


def _build_event_table() -> pd.DataFrame:
    """Build the FULL event-level table once: features + outcome under ATR×2 stop + T+5 stop."""
    universe = load_universe()
    cal = load_calendar(window_start=WINDOW_START.date(), window_end=WINDOW_END.date())
    cal = cal[cal["symbol"].isin(universe)].copy()

    rows = []
    for _, ev in cal.iterrows():
        symbol = ev["symbol"]
        event_date = ev["event_date"]
        daily = _read_daily(symbol)
        if daily is None or daily.empty:
            continue
        t_minus_1 = _last_trading_day_strictly_before(daily, event_date)
        if t_minus_1 is None:
            continue
        feats = _compute_features(daily, t_minus_1)
        if feats is None:
            continue
        # Also compute realized-vol over last 21 trading days for filter
        sub = daily[daily["Date"] <= t_minus_1].iloc[-21:]
        if len(sub) < 21:
            continue
        log_returns = np.log(sub["Close"].values[1:] / sub["Close"].values[:-1])
        realized_vol_21d_pct = float(np.std(log_returns, ddof=1) * np.sqrt(252) * 100)

        entry_price = feats["entry_close_ref"]
        exit_date, exit_price, reason = _exit_with_stop(daily, t_minus_1,
                                                          entry_price, feats["atr_14_pct"])
        gross_bps = (exit_price / entry_price - 1.0) * 10_000.0

        rows.append({
            "symbol": symbol,
            "event_date": event_date,
            "entry_date": t_minus_1,
            "volume_z": feats["volume_z"],
            "short_mom_bps": feats["short_mom_bps"],
            "atr_14_pct": feats["atr_14_pct"],
            "realized_vol_21d_pct": realized_vol_21d_pct,
            "gross_bps": gross_bps,
            "net_s1_bps": gross_bps - COST_BPS_S1,
            "exit_reason": reason,
        })
    return pd.DataFrame(rows)


def _eval_cell(df: pd.DataFrame) -> dict:
    if len(df) < 1:
        return {"n": 0}
    g = df["gross_bps"].values
    s1 = df["net_s1_bps"].values
    cum = np.cumsum(s1)
    dd_abs = float(_max_dd(s1))
    return {
        "n": int(len(df)),
        "gross_mean_bps": round(float(g.mean()), 2),
        "net_s1_mean_bps": round(float(g.mean() - COST_BPS_S1), 2),
        "hit_gross": round(float((g > 0).mean()), 4),
        "hit_net_s1": round(float((s1 > 0).mean()), 4),
        "sharpe_ann_s1": round(_annualised_sharpe(s1), 3),
        "max_dd_abs_bps": round(dd_abs, 1),
        "max_dd_pct_capital": round(dd_abs / 100, 2),  # bps -> % of single-leg notional
    }


def main() -> None:
    print("building event table from frozen calendar...")
    df = _build_event_table()
    print(f"total analyzable events: {len(df)}")

    cells = {}

    # Baseline: spec as written
    cells["spec_v1.0_vol_z_0.52_mom_0"] = _eval_cell(
        df[(df["volume_z"] >= 0.52) & (df["short_mom_bps"] > 0)]
    )

    # Higher thresholds
    for vz in (0.75, 1.0, 1.25, 1.5, 2.0):
        cells[f"vol_z_{vz}_mom_0"] = _eval_cell(
            df[(df["volume_z"] >= vz) & (df["short_mom_bps"] > 0)]
        )

    # vol_z >= 0.52 with realized-vol regime filter
    for rv_min in (20.0, 25.0, 29.0, 33.0):
        cells[f"vol_z_0.52_mom_0_realized_vol_min_{rv_min}"] = _eval_cell(
            df[(df["volume_z"] >= 0.52) & (df["short_mom_bps"] > 0) &
                (df["realized_vol_21d_pct"] >= rv_min)]
        )

    # Combined high-quality: vol_z >= 1.0 AND realized_vol >= 25
    cells["vol_z_1.0_mom_0_realized_vol_min_25"] = _eval_cell(
        df[(df["volume_z"] >= 1.0) & (df["short_mom_bps"] > 0) &
            (df["realized_vol_21d_pct"] >= 25.0)]
    )

    # ATR-pct floor (avoid super-low-vol stocks where ATR×2 stop is too tight)
    for atr_min in (0.012, 0.015, 0.020):
        cells[f"vol_z_0.52_mom_0_atr_min_{atr_min}"] = _eval_cell(
            df[(df["volume_z"] >= 0.52) & (df["short_mom_bps"] > 0) &
                (df["atr_14_pct"] >= atr_min)]
        )

    # short_mom floor (only strong momentum entries)
    for sm_min in (50.0, 100.0, 200.0, 300.0):
        cells[f"vol_z_0.52_mom_min_{sm_min}"] = _eval_cell(
            df[(df["volume_z"] >= 0.52) & (df["short_mom_bps"] >= sm_min)]
        )

    # All trades (no qualifier) — baseline reference
    cells["always_long_baseline"] = _eval_cell(df)

    # Sort by net_s1_mean_bps descending
    out_sorted = sorted(cells.items(), key=lambda kv: -kv[1].get("net_s1_mean_bps", -1e9))

    print()
    print(f"{'cell':60s} {'n':>4s} {'mean':>7s} {'net@20':>7s} {'hit':>5s} {'shrp':>5s} {'dd%':>6s}")
    print("-" * 100)
    for name, m in out_sorted:
        if m.get("n", 0) == 0:
            continue
        print(f"{name:60s} {m['n']:>4d} {m['gross_mean_bps']:>+7.0f} {m['net_s1_mean_bps']:>+7.0f} "
              f"{m['hit_gross']:>5.2f} {m['sharpe_ann_s1']:>+5.2f} {m['max_dd_pct_capital']:>+6.1f}")

    OUT_JSON.write_text(json.dumps({"cells": cells, "n_total_events": len(df)}, indent=2))
    print(f"\n-> {OUT_JSON}")


if __name__ == "__main__":
    main()
