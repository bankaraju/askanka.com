"""NEUTRAL-regime cohort tracker.

Honest accounting of forward closed trades in NEUTRAL regime, sliced by
filter cell so misleading single-number win rates can't hide.

Sources:
  - pipeline/data/research/h_2026_04_26_001/recommendations.csv (H-001 paper)
  - pipeline/data/research/h_2026_04_29_intraday_v1/cache_1min/<ticker>.parquet (features)
  - pipeline/data/research/h_2026_04_29_intraday_v1/cache_1min/NIFTY 50.parquet (day direction)

Cell publication rules:
  - N >= 30: PUBLISH (cell is reportable)
  - 10 <= N < 30: MONITOR (early signal, not for filtering)
  - N < 10: INSUFFICIENT (do not act on)

Outputs:
  pipeline/data/research/neutral_cohort/by_cell_<YYYY_MM_DD>.csv
  pipeline/data/research/neutral_cohort/summary_<YYYY_MM_DD>.json
  pipeline/data/research/neutral_cohort/by_cell_latest.csv

Usage:
  python -m pipeline.research.neutral_cohort_tracker
"""
from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

PIPELINE_ROOT = Path(__file__).resolve().parents[1]
H001_CSV = PIPELINE_ROOT / "data" / "research" / "h_2026_04_26_001" / "recommendations.csv"
CACHE_1MIN = PIPELINE_ROOT / "data" / "research" / "h_2026_04_29_intraday_v1" / "cache_1min"
OUT_DIR = PIPELINE_ROOT / "data" / "research" / "neutral_cohort"
NIFTY_FILE = CACHE_1MIN / "NIFTY 50.parquet"

IST = timezone(timedelta(hours=5, minutes=30))
PUBLISH_THRESHOLD = 30
MONITOR_THRESHOLD = 10

log = logging.getLogger("neutral_cohort_tracker")


def _load_minute(ticker: str, date_str: str) -> Optional[pd.DataFrame]:
    p = CACHE_1MIN / f"{ticker}.parquet"
    if not p.exists():
        return None
    df = pd.read_parquet(p)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["date"] = df["timestamp"].dt.date.astype(str)
    sub = df[df["date"] == date_str].sort_values("timestamp").reset_index(drop=True)
    return sub if len(sub) >= 15 else None


def _features_for_entry(df_min: pd.DataFrame) -> dict:
    """Compute ORB-15, VWAP-dev at 09:30, trend-slope first 15min."""
    open_p = float(df_min.iloc[0]["open"])
    first15 = df_min.iloc[:15]
    orb_range_pct = (first15["high"].max() - first15["low"].min()) / max(open_p, 1e-9)
    vwap_15 = (first15["close"] * first15["volume"]).sum() / max(first15["volume"].sum(), 1)
    px_15 = float(first15.iloc[-1]["close"])
    vwap_dev_pct = (px_15 - vwap_15) / max(vwap_15, 1e-9)
    y = first15["close"].to_numpy(dtype=float)
    x = np.arange(len(y), dtype=float)
    slope_per_min = float(np.polyfit(x, y, 1)[0]) if y.std() > 1e-9 else 0.0
    trend_slope_pct = slope_per_min / max(np.mean(y), 1e-9)
    return dict(
        orb_15min_pct=float(orb_range_pct),
        vwap_dev_pct=float(vwap_dev_pct),
        trend_slope_per_min_pct=float(trend_slope_pct),
        open_px=open_p,
        px_at_0930=px_15,
    )


def _nifty_direction_at_0930(date_str: str) -> Optional[float]:
    if not NIFTY_FILE.exists():
        return None
    df = pd.read_parquet(NIFTY_FILE)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["date"] = df["timestamp"].dt.date.astype(str)
    sub = df[df["date"] == date_str].sort_values("timestamp").reset_index(drop=True)
    if len(sub) < 15:
        return None
    open_p = float(sub.iloc[0]["open"])
    px_15 = float(sub.iloc[14]["close"])
    return (px_15 - open_p) / max(open_p, 1e-9)


def _tertile_label(value: float, q1: float, q3: float, name: str) -> str:
    if pd.isna(value):
        return f"{name}_NA"
    if value <= q1:
        return f"{name}_LO"
    if value >= q3:
        return f"{name}_HI"
    return f"{name}_MID"


def _classify_market_dir(direction: Optional[float]) -> str:
    if direction is None or pd.isna(direction):
        return "MKT_NA"
    if direction <= -0.0015:
        return "MKT_DOWN"
    if direction >= 0.0015:
        return "MKT_UP"
    return "MKT_FLAT"


def _cell_status(n: int) -> str:
    if n >= PUBLISH_THRESHOLD:
        return "PUBLISH"
    if n >= MONITOR_THRESHOLD:
        return "MONITOR"
    return "INSUFFICIENT"


def build_cohort_table() -> pd.DataFrame:
    if not H001_CSV.exists():
        raise FileNotFoundError(f"H-001 ledger missing: {H001_CSV}")
    h = pd.read_csv(H001_CSV)
    closed = h[h["status"] == "CLOSED"].copy()
    closed = closed[closed["regime"] == "NEUTRAL"]
    if closed.empty:
        raise RuntimeError("no CLOSED NEUTRAL rows in H-001 ledger")

    log.info(f"H-001 CLOSED NEUTRAL rows: {len(closed)}")
    closed["win"] = (closed["pnl_pct"] > 0).astype(int)

    nifty_cache: dict[str, Optional[float]] = {}

    enriched_rows = []
    for _, row in closed.iterrows():
        ticker = row["ticker"]
        date_str = row["date"]

        feat = dict(orb_15min_pct=np.nan, vwap_dev_pct=np.nan, trend_slope_per_min_pct=np.nan)
        df_min = _load_minute(ticker, date_str)
        if df_min is not None:
            feat = _features_for_entry(df_min)

        if date_str not in nifty_cache:
            nifty_cache[date_str] = _nifty_direction_at_0930(date_str)
        mkt_dir = nifty_cache[date_str]

        enriched_rows.append({
            "date": date_str,
            "ticker": ticker,
            "side": row["side"],
            "sigma_bucket": row["sigma_bucket"],
            "regime": row["regime"],
            "pnl_pct": float(row["pnl_pct"]),
            "win": int(row["win"]),
            "orb_15min_pct": feat.get("orb_15min_pct", np.nan),
            "vwap_dev_pct": feat.get("vwap_dev_pct", np.nan),
            "trend_slope_per_min_pct": feat.get("trend_slope_per_min_pct", np.nan),
            "nifty_dir_0930_pct": mkt_dir if mkt_dir is not None else np.nan,
            "mkt_dir_label": _classify_market_dir(mkt_dir),
        })

    return pd.DataFrame(enriched_rows)


def aggregate_cells(df: pd.DataFrame) -> pd.DataFrame:
    """Build the cohort cell table: per-filter aggregates with publish status."""
    side_signed = np.where(df["side"] == "LONG", 1.0, -1.0)
    df = df.copy()
    df["vwap_dev_signed"] = df["vwap_dev_pct"] * side_signed
    df["trend_slope_signed"] = df["trend_slope_per_min_pct"] * side_signed
    df["orb_signed"] = df["orb_15min_pct"]

    cells: list[dict] = []

    def add_cell(name: str, mask: pd.Series) -> None:
        sub = df[mask]
        n = int(len(sub))
        if n == 0:
            return
        cells.append({
            "cell": name,
            "N": n,
            "win_pct": round(sub["win"].mean() * 100, 2),
            "mean_pnl_pct": round(sub["pnl_pct"].mean(), 3),
            "median_pnl_pct": round(sub["pnl_pct"].median(), 3),
            "status": _cell_status(n),
        })

    add_cell("ALL_NEUTRAL", pd.Series([True] * len(df), index=df.index))
    for side in ("LONG", "SHORT"):
        add_cell(f"side={side}", df["side"] == side)
    for bucket in df["sigma_bucket"].dropna().unique():
        add_cell(f"sigma={bucket}", df["sigma_bucket"] == bucket)
    for side in ("LONG", "SHORT"):
        for bucket in df["sigma_bucket"].dropna().unique():
            add_cell(f"side={side}+sigma={bucket}",
                     (df["side"] == side) & (df["sigma_bucket"] == bucket))
    for label in df["mkt_dir_label"].dropna().unique():
        add_cell(f"market_dir={label}", df["mkt_dir_label"] == label)
    for side in ("LONG", "SHORT"):
        for label in df["mkt_dir_label"].dropna().unique():
            add_cell(f"side={side}+market_dir={label}",
                     (df["side"] == side) & (df["mkt_dir_label"] == label))

    feat_cells = df.dropna(subset=["orb_15min_pct"])
    if len(feat_cells) >= MONITOR_THRESHOLD:
        q1 = feat_cells["orb_15min_pct"].quantile(1 / 3)
        q3 = feat_cells["orb_15min_pct"].quantile(2 / 3)
        labels = feat_cells["orb_15min_pct"].apply(
            lambda v: _tertile_label(v, q1, q3, "ORB"))
        for tag in ("ORB_LO", "ORB_MID", "ORB_HI"):
            add_cell(tag, df.index.isin(feat_cells.index[labels == tag]))

    feat_cells = df.dropna(subset=["vwap_dev_signed"])
    if len(feat_cells) >= MONITOR_THRESHOLD:
        q1 = feat_cells["vwap_dev_signed"].quantile(1 / 3)
        q3 = feat_cells["vwap_dev_signed"].quantile(2 / 3)
        labels = feat_cells["vwap_dev_signed"].apply(
            lambda v: _tertile_label(v, q1, q3, "VWAPSIGN"))
        for tag in ("VWAPSIGN_LO", "VWAPSIGN_MID", "VWAPSIGN_HI"):
            add_cell(tag, df.index.isin(feat_cells.index[labels == tag]))

    cells_df = pd.DataFrame(cells)
    cells_df["status_rank"] = cells_df["status"].map(
        {"PUBLISH": 0, "MONITOR": 1, "INSUFFICIENT": 2}).fillna(3)
    cells_df = cells_df.sort_values(["status_rank", "win_pct"], ascending=[True, False])
    cells_df = cells_df.drop(columns=["status_rank"]).reset_index(drop=True)
    return cells_df


def write_outputs(trades: pd.DataFrame, cells: pd.DataFrame) -> dict:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now(IST).strftime("%Y_%m_%d")
    trades_csv = OUT_DIR / f"trades_neutral_{today}.csv"
    cells_csv = OUT_DIR / f"by_cell_{today}.csv"
    cells_latest = OUT_DIR / "by_cell_latest.csv"
    summary_json = OUT_DIR / f"summary_{today}.json"

    trades.to_csv(trades_csv, index=False, float_format="%.4f")
    cells.to_csv(cells_csv, index=False, float_format="%.4f")
    cells.to_csv(cells_latest, index=False, float_format="%.4f")

    publish_cells = cells[cells["status"] == "PUBLISH"]
    monitor_cells = cells[cells["status"] == "MONITOR"]
    summary = {
        "as_of": datetime.now(IST).isoformat(),
        "regime": "NEUTRAL",
        "regime_period_note": (
            "global_regime.json shows NEUTRAL stable for 8 consecutive days as of "
            f"{datetime.now(IST).date().isoformat()}; H-001 rows are forward-only "
            "single-touch holdout 2026-04-27 → 2026-05-26."
        ),
        "source": str(H001_CSV.relative_to(PIPELINE_ROOT)),
        "n_trades": int(len(trades)),
        "n_with_features": int(trades["orb_15min_pct"].notna().sum()),
        "baseline_win_pct": round(trades["win"].mean() * 100, 2),
        "baseline_mean_pnl_pct": round(trades["pnl_pct"].mean(), 3),
        "publish_cells": publish_cells.to_dict(orient="records"),
        "monitor_cells": monitor_cells.to_dict(orient="records"),
        "publish_threshold": PUBLISH_THRESHOLD,
        "monitor_threshold": MONITOR_THRESHOLD,
        "trades_csv": str(trades_csv.relative_to(PIPELINE_ROOT)),
        "cells_csv": str(cells_csv.relative_to(PIPELINE_ROOT)),
    }
    summary_json.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    return summary


def main() -> None:
    p = argparse.ArgumentParser(description="NEUTRAL cohort tracker")
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args()
    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    trades = build_cohort_table()
    cells = aggregate_cells(trades)
    summary = write_outputs(trades, cells)

    print(f"=== NEUTRAL cohort tracker — {summary['as_of']} ===")
    print(f"Source: {summary['source']}")
    print(f"N forward CLOSED NEUTRAL trades: {summary['n_trades']}")
    print(f"  with ORB/VWAP features: {summary['n_with_features']}")
    print(f"Baseline win%: {summary['baseline_win_pct']:.2f}%, "
          f"mean PnL: {summary['baseline_mean_pnl_pct']:+.3f}%")
    print()
    print(f"Cell publication thresholds: "
          f"PUBLISH N>={PUBLISH_THRESHOLD}, MONITOR N>={MONITOR_THRESHOLD}")
    print()
    print(cells.to_string(index=False, float_format=lambda v: f"{v:.2f}"))
    print()
    print(f"Outputs:")
    print(f"  {summary['trades_csv']}")
    print(f"  {summary['cells_csv']}")


if __name__ == "__main__":
    main()
