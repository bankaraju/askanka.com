"""H-2026-05-01-earnings-drift-long-v1 — backtest harness.

PURPOSE
-------
Replay the FROZEN signal generator on the in-sample window 2021-05-01 → 2024-04-30.
Verify the spec replicates the +277 bps net@20 bivariate cell observed in Stage A.

This is the §9 verification run BEFORE holdout opens. NOT a research/exploration tool.

Output: backtest_2021_05_2024_04.csv with one row per qualified entry, plus
verdict statistics dict.

This file matches the kill-switch regex (`*_backtest.py`); registry row required.

Spec: docs/superpowers/specs/2026-05-01-earnings-drift-long-v1-design.md
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
DAILY_DIR = ROOT / "pipeline" / "data" / "fno_historical"
OUT_CSV = ROOT / "pipeline" / "research" / "h_2026_05_01_earnings_drift_long" / "backtest_2021_05_2024_04.csv"
OUT_JSON = ROOT / "pipeline" / "research" / "h_2026_05_01_earnings_drift_long" / "backtest_2021_05_2024_04.json"

from pipeline.research.h_2026_05_01_earnings_drift_long.earnings_drift_signal_generator import (
    SignalCandidate,
    STOP_ATR_MULT,
    _read_daily,
    load_calendar,
    load_universe,
    _compute_features,
    _last_trading_day_strictly_before,
    _load_regime_tape_lookup,
    VOL_Z_THRESHOLD,
    SHORT_MOM_BPS_THRESHOLD,
    REALIZED_VOL_21D_PCT_THRESHOLD,
    ALLOWED_REGIMES,
)

HOLD_TRADING_DAYS = 5
COST_BPS_S0 = 10.0
COST_BPS_S1 = 20.0
COST_BPS_S2 = 30.0
WINDOW_START = pd.Timestamp("2021-05-01")
WINDOW_END = pd.Timestamp("2024-04-30")


def _exit_with_stop(daily: pd.DataFrame, entry_date: pd.Timestamp,
                    entry_price: float, atr_pct: float) -> tuple[pd.Timestamp, float, str]:
    """Find exit at first ATR×2 stop or T+5 close, whichever first.

    Returns (exit_date, exit_price, exit_reason).
    """
    stop_price = entry_price * (1.0 - STOP_ATR_MULT * atr_pct)
    forward = daily[daily["Date"] > entry_date].head(HOLD_TRADING_DAYS)
    if forward.empty:
        return entry_date, entry_price, "no_forward_bars"

    for _, row in forward.iterrows():
        if row["Low"] <= stop_price:
            return row["Date"], stop_price, "atr_stop"

    last = forward.iloc[-1]
    return last["Date"], float(last["Close"]), "time_stop"


def _annualised_sharpe(per_trade_returns_bps: np.ndarray) -> float:
    if len(per_trade_returns_bps) < 2:
        return 0.0
    mu = float(per_trade_returns_bps.mean())
    sd = float(per_trade_returns_bps.std(ddof=1))
    if sd <= 0:
        return 0.0
    per_trade_sharpe = mu / sd
    n_trades_per_year = 252 / HOLD_TRADING_DAYS
    return per_trade_sharpe * np.sqrt(n_trades_per_year)


def run_backtest() -> dict:
    universe = load_universe()
    cal = load_calendar(window_start=WINDOW_START.date(), window_end=WINDOW_END.date())
    cal = cal[cal["symbol"].isin(universe)].copy()
    regime_lookup = _load_regime_tape_lookup()

    rows = []
    skipped = 0

    for _, ev in cal.iterrows():
        symbol = ev["symbol"]
        event_date = ev["event_date"]

        daily = _read_daily(symbol)
        if daily is None or daily.empty:
            skipped += 1
            continue

        t_minus_1 = _last_trading_day_strictly_before(daily, event_date)
        if t_minus_1 is None:
            skipped += 1
            continue

        feats = _compute_features(daily, t_minus_1)
        if feats is None:
            skipped += 1
            continue

        regime_at_t1 = regime_lookup.get(t_minus_1)
        if regime_at_t1 is None:
            skipped += 1
            continue

        passes_vol = feats["volume_z"] >= VOL_Z_THRESHOLD
        passes_mom = feats["short_mom_bps"] > SHORT_MOM_BPS_THRESHOLD
        passes_rv = feats["realized_vol_21d_pct"] >= REALIZED_VOL_21D_PCT_THRESHOLD
        passes_regime = regime_at_t1 in ALLOWED_REGIMES
        if not (passes_vol and passes_mom and passes_rv and passes_regime):
            continue

        entry_price = feats["entry_close_ref"]
        exit_date, exit_price, reason = _exit_with_stop(daily, t_minus_1,
                                                          entry_price, feats["atr_14_pct"])
        gross_bps = (exit_price / entry_price - 1.0) * 10_000.0

        rows.append({
            "symbol": symbol,
            "event_date": event_date,
            "entry_date": t_minus_1,
            "exit_date": exit_date,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "exit_reason": reason,
            "volume_z": feats["volume_z"],
            "short_mom_bps": feats["short_mom_bps"],
            "realized_vol_21d_pct": feats["realized_vol_21d_pct"],
            "regime": regime_at_t1,
            "atr_14_pct": feats["atr_14_pct"],
            "gross_bps": gross_bps,
            "net_s0_bps": gross_bps - COST_BPS_S0,
            "net_s1_bps": gross_bps - COST_BPS_S1,
            "net_s2_bps": gross_bps - COST_BPS_S2,
        })

    if not rows:
        return {"meta": {"n": 0, "skipped": skipped}}

    df = pd.DataFrame(rows).sort_values("entry_date").reset_index(drop=True)
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_CSV, index=False)

    gross = df["gross_bps"].values
    net_s1 = df["net_s1_bps"].values

    verdict = {
        "meta": {
            "n_qualified_trades": int(len(df)),
            "n_calendar_events": int(len(cal)),
            "n_skipped": int(skipped),
            "window_start": str(WINDOW_START.date()),
            "window_end": str(WINDOW_END.date()),
            "spec_ref": "docs/superpowers/specs/2026-05-01-earnings-drift-long-v1-design.md",
            "frozen_thresholds": {
                "vol_z_min": VOL_Z_THRESHOLD,
                "short_mom_bps_min": SHORT_MOM_BPS_THRESHOLD,
                "realized_vol_21d_pct_min": REALIZED_VOL_21D_PCT_THRESHOLD,
                "allowed_regimes": sorted(ALLOWED_REGIMES),
                "hold_trading_days": HOLD_TRADING_DAYS,
                "stop_atr_mult": STOP_ATR_MULT,
            },
        },
        "headline": {
            "n": int(len(df)),
            "gross_mean_bps": round(float(gross.mean()), 2),
            "gross_std_bps": round(float(gross.std(ddof=1)), 2),
            "net_s0_mean_bps": round(float(gross.mean() - COST_BPS_S0), 2),
            "net_s1_mean_bps": round(float(gross.mean() - COST_BPS_S1), 2),
            "net_s2_mean_bps": round(float(gross.mean() - COST_BPS_S2), 2),
            "hit_gross": round(float((gross > 0).mean()), 4),
            "hit_net_s1": round(float((net_s1 > 0).mean()), 4),
            "sharpe_ann_s1": round(_annualised_sharpe(net_s1), 3),
            "max_drawdown_bps": round(float(_max_dd(net_s1)), 2),
        },
        "by_exit_reason": df.groupby("exit_reason").agg(
            n=("symbol", "size"),
            gross_mean_bps=("gross_bps", "mean"),
        ).round(2).to_dict(orient="index"),
    }

    # FY split for stability check vs Stage A
    df["fy"] = df["entry_date"].dt.year + (df["entry_date"].dt.month >= 4).astype(int)
    fy_split = {}
    for fy, sub in df.groupby("fy"):
        if len(sub) < 1:
            continue
        g = sub["gross_bps"].values
        fy_split[int(fy)] = {
            "n": int(len(sub)),
            "gross_mean_bps": round(float(g.mean()), 2),
            "net_s1_mean_bps": round(float(g.mean() - COST_BPS_S1), 2),
            "hit": round(float((g > 0).mean()), 4),
        }
    verdict["by_fy"] = fy_split

    # Sector split
    sec_split = {}
    universe_cfg = json.load(open(ROOT / "pipeline" / "research" /
                                    "h_2026_05_01_earnings_drift_long" / "universe_frozen.json"))
    sym_to_sec = {}
    for sec, syms in universe_cfg["universe"].items():
        for s in syms:
            sym_to_sec[s] = sec
    df["sector"] = df["symbol"].map(sym_to_sec)
    for sec, sub in df.groupby("sector"):
        g = sub["gross_bps"].values
        sec_split[sec] = {
            "n": int(len(sub)),
            "gross_mean_bps": round(float(g.mean()), 2),
            "net_s1_mean_bps": round(float(g.mean() - COST_BPS_S1), 2),
            "hit": round(float((g > 0).mean()), 4),
        }
    verdict["by_sector"] = sec_split

    OUT_JSON.write_text(json.dumps(verdict, indent=2, default=str))
    return verdict


def _max_dd(net_per_trade: np.ndarray) -> float:
    if len(net_per_trade) == 0:
        return 0.0
    cum = np.cumsum(net_per_trade)
    running_peak = np.maximum.accumulate(cum)
    drawdowns = cum - running_peak
    return float(drawdowns.min())


if __name__ == "__main__":
    print("running H-2026-05-01-earnings-drift-long-v1 frozen-spec backtest...")
    print(f"window: {WINDOW_START.date()} -> {WINDOW_END.date()}")
    v = run_backtest()
    print(json.dumps(v, indent=2, default=str))
    print(f"\n-> {OUT_CSV}")
    print(f"-> {OUT_JSON}")
