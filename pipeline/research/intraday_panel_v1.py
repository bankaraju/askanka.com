"""Panel-wide descriptive backtest — every F&O × every day × 09:30-09:45 TA features.

Question: across the entire F&O universe (not just H-001 trade triggers), what
do simple intraday-TA features at 09:45 say about the 09:45 -> 14:30 move?

This is descriptive research evidence — NOT a forward edge claim. Output is a
cells table compatible with the cohort_harness vocabulary (PUBLISH N>=30,
MONITOR 10<=N<30, INSUFFICIENT N<10).

Features at eval_t = 09:45 IST (close of the 09:30-09:45 ORB window):
  vwap_dev_pct       price vs cumulative VWAP from 09:15, signed
  orb_15min_pct      (09:45_close - 09:15_open) / 09:15_open  (= side proxy)
  volume_z           today's 09:15-09:45 volume vs trailing 20-day mean
  intraday_slope     simple linear slope of 30 1-min closes, normalized

Outcome (per row):
  hold_pct           (14:30_close / 09:45_close) - 1, in percent
  side_label         LONG if orb_15min_pct > 0 else SHORT
  win                follow rule: 1 if hold has same sign as orb_15min_pct
                     fade rule:   1 if hold has opposite sign

Caveats:
  - Regime is NOT conditioned per row (regime_history.csv is hindsight-tuned —
    contaminated for OOS use). The 60-day sample is dominated by NEUTRAL.
  - Cells are descriptive on the trailing 60-day Kite cache. Not pre-registered,
    so no edge claim — promote to a holdout if a cell looks real.

Outputs (data/research/intraday_panel_v1/):
  panel_<date>.parquet         every (ticker, day) row with features + outcome
  cells_<date>.csv             aggregated cells, follow + fade rules
  summary_<date>.json          baseline + PUBLISH/MONITOR cell summary
"""
from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

PIPELINE_ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = PIPELINE_ROOT / "data" / "research" / "h_2026_04_29_intraday_v1" / "cache_1min"
OUT_DIR = PIPELINE_ROOT / "data" / "research" / "intraday_panel_v1"
IST = timezone(timedelta(hours=5, minutes=30))

PUBLISH_THRESHOLD = 30
MONITOR_THRESHOLD = 10

OPEN_T = time(9, 15)
ORB_END_T = time(9, 45)
EXIT_T = time(14, 30)

log = logging.getLogger("intraday_panel_v1")


def _load_minute_bars(parquet_path: Path) -> pd.DataFrame | None:
    try:
        df = pd.read_parquet(parquet_path)
    except Exception as exc:
        log.debug("load failed %s: %s", parquet_path.name, exc)
        return None
    if df.empty or "timestamp" not in df.columns:
        return None
    df = df.sort_values("timestamp").reset_index(drop=True)
    return df


def _features_for_day(day_df: pd.DataFrame, open_row: pd.Series, orb_close_idx: int) -> dict | None:
    """Compute features at 09:45 close. Returns dict or None on insufficient data."""
    if orb_close_idx < 5 or orb_close_idx >= len(day_df):
        return None
    open_px = float(open_row["open"])
    if open_px <= 0:
        return None

    pre_orb = day_df.iloc[: orb_close_idx + 1]
    if len(pre_orb) < 10:
        return None

    typical = (pre_orb["high"] + pre_orb["low"] + pre_orb["close"]) / 3.0
    vol = pre_orb["volume"].astype(float).clip(lower=0)
    cumv = vol.sum()
    if cumv <= 0:
        return None
    vwap = (typical * vol).sum() / cumv

    orb_close_px = float(pre_orb.iloc[-1]["close"])
    orb_15min_pct = (orb_close_px - open_px) / open_px * 100.0
    vwap_dev_pct = (orb_close_px - vwap) / vwap * 100.0

    closes = pre_orb["close"].astype(float).values
    if len(closes) >= 5:
        x = np.arange(len(closes), dtype=float)
        slope, _ = np.polyfit(x, closes, 1)
        intraday_slope_pct = (slope * len(closes)) / closes[0] * 100.0
    else:
        intraday_slope_pct = float("nan")

    return {
        "open_px": open_px,
        "orb_close_px": orb_close_px,
        "orb_15min_pct": round(orb_15min_pct, 4),
        "vwap_dev_pct": round(vwap_dev_pct, 4),
        "intraday_slope_pct": round(intraday_slope_pct, 4),
        "orb_volume": float(cumv),
    }


def _build_panel_for_ticker(ticker: str, df: pd.DataFrame) -> pd.DataFrame:
    df["date"] = df["timestamp"].dt.date
    rows: list[dict] = []
    volume_history: list[float] = []  # rolling 20-day list of ORB volumes

    for day, day_df in df.groupby("date", sort=True):
        day_df = day_df.reset_index(drop=True)
        open_mask = day_df["timestamp"].dt.time == OPEN_T
        orb_end_mask = day_df["timestamp"].dt.time == ORB_END_T
        exit_mask = day_df["timestamp"].dt.time == EXIT_T
        if not (open_mask.any() and orb_end_mask.any() and exit_mask.any()):
            continue

        open_idx = int(np.where(open_mask)[0][0])
        orb_idx = int(np.where(orb_end_mask)[0][0])
        exit_idx = int(np.where(exit_mask)[0][0])
        if orb_idx <= open_idx or exit_idx <= orb_idx:
            continue

        feats = _features_for_day(day_df.iloc[open_idx:orb_idx + 1].reset_index(drop=True),
                                  day_df.iloc[open_idx], orb_idx - open_idx)
        if feats is None:
            continue

        exit_px = float(day_df.iloc[exit_idx]["close"])
        if exit_px <= 0:
            continue
        hold_pct = (exit_px / feats["orb_close_px"] - 1.0) * 100.0

        if volume_history:
            v_arr = np.array(volume_history[-20:])
            v_mean = v_arr.mean()
            v_std = v_arr.std(ddof=0)
            volume_z = (feats["orb_volume"] - v_mean) / v_std if v_std > 0 else float("nan")
        else:
            volume_z = float("nan")
        volume_history.append(feats["orb_volume"])

        rows.append({
            "ticker": ticker,
            "date": str(day),
            "open_px": feats["open_px"],
            "orb_close_px": feats["orb_close_px"],
            "exit_px": exit_px,
            "orb_15min_pct": feats["orb_15min_pct"],
            "vwap_dev_pct": feats["vwap_dev_pct"],
            "intraday_slope_pct": feats["intraday_slope_pct"],
            "volume_z": round(float(volume_z), 4) if pd.notna(volume_z) else None,
            "hold_pct": round(hold_pct, 4),
        })

    return pd.DataFrame(rows)


def build_panel(cache_dir: Path = CACHE_DIR, max_tickers: int | None = None) -> pd.DataFrame:
    parquets = sorted(cache_dir.glob("*.parquet"))
    if max_tickers:
        parquets = parquets[:max_tickers]
    log.info("scanning %d parquet files", len(parquets))
    all_rows: list[pd.DataFrame] = []
    for i, pq in enumerate(parquets):
        if i % 25 == 0:
            log.info("ticker %d/%d: %s", i, len(parquets), pq.stem)
        df = _load_minute_bars(pq)
        if df is None or df.empty:
            continue
        ticker_panel = _build_panel_for_ticker(pq.stem, df)
        if not ticker_panel.empty:
            all_rows.append(ticker_panel)
    if not all_rows:
        return pd.DataFrame()
    panel = pd.concat(all_rows, ignore_index=True)
    return panel


def _tertile_label(s: pd.Series, prefix: str) -> tuple[pd.Series, dict]:
    sub = s.dropna()
    if len(sub) < MONITOR_THRESHOLD:
        return pd.Series([None] * len(s), index=s.index), {}
    q1, q3 = sub.quantile([1 / 3, 2 / 3])

    def _lab(v):
        if pd.isna(v):
            return None
        if v <= q1:
            return f"{prefix}_LO"
        if v >= q3:
            return f"{prefix}_HI"
        return f"{prefix}_MID"

    return s.apply(_lab), {"q1": float(q1), "q3": float(q3)}


def _aggregate_cells(panel: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    panel = panel.copy()
    panel["side_label"] = np.where(panel["orb_15min_pct"] > 0, "LONG",
                                   np.where(panel["orb_15min_pct"] < 0, "SHORT", "FLAT"))

    panel["follow_win"] = ((panel["orb_15min_pct"] > 0) & (panel["hold_pct"] > 0)) | \
                         ((panel["orb_15min_pct"] < 0) & (panel["hold_pct"] < 0))
    panel["follow_pnl_pct"] = np.where(panel["orb_15min_pct"] > 0,
                                       panel["hold_pct"],
                                       -panel["hold_pct"])
    panel["fade_win"] = ((panel["orb_15min_pct"] > 0) & (panel["hold_pct"] < 0)) | \
                       ((panel["orb_15min_pct"] < 0) & (panel["hold_pct"] > 0))
    panel["fade_pnl_pct"] = -panel["follow_pnl_pct"]

    panel["vwap_dev_signed_pct"] = np.where(
        panel["orb_15min_pct"] >= 0,
        panel["vwap_dev_pct"],
        -panel["vwap_dev_pct"],
    )

    cells: list[dict] = []
    cuts: dict = {}

    def _row(name: str, mask: pd.Series, pnl_col: str, win_col: str) -> dict | None:
        sub = panel[mask]
        n = int(len(sub))
        if n == 0:
            return None
        return {
            "cell": name,
            "N": n,
            "win_pct": round(sub[win_col].mean() * 100, 2),
            "mean_pnl_pct": round(sub[pnl_col].mean(), 3),
            "median_pnl_pct": round(sub[pnl_col].median(), 3),
            "status": ("PUBLISH" if n >= PUBLISH_THRESHOLD else
                       "MONITOR" if n >= MONITOR_THRESHOLD else "INSUFFICIENT"),
        }

    full_mask = pd.Series([True] * len(panel), index=panel.index)
    for rule in ("follow", "fade"):
        win_col = f"{rule}_win"
        pnl_col = f"{rule}_pnl_pct"
        cells.append({**_row(f"ALL/{rule}", full_mask, pnl_col, win_col), "rule": rule})

        for side in ("LONG", "SHORT"):
            r = _row(f"side={side}/{rule}", panel["side_label"] == side, pnl_col, win_col)
            if r:
                cells.append({**r, "rule": rule})

        for feat in ("orb_15min_pct", "vwap_dev_signed_pct", "intraday_slope_pct", "volume_z"):
            labels, cut = _tertile_label(panel[feat], feat)
            cuts[feat] = cut
            for tag in (f"{feat}_LO", f"{feat}_MID", f"{feat}_HI"):
                r = _row(f"{tag}/{rule}", labels == tag, pnl_col, win_col)
                if r:
                    cells.append({**r, "rule": rule})

        # Combined VWAP_dev_signed × side
        for side in ("LONG", "SHORT"):
            labels, _ = _tertile_label(panel.loc[panel["side_label"] == side, "vwap_dev_signed_pct"],
                                       f"vwap_dev_signed_pct_{side}")
            for tag in (f"vwap_dev_signed_pct_{side}_LO",
                        f"vwap_dev_signed_pct_{side}_HI"):
                mask = (panel["side_label"] == side) & (labels.reindex(panel.index) == tag)
                r = _row(f"side={side}+{tag}/{rule}", mask, pnl_col, win_col)
                if r:
                    cells.append({**r, "rule": rule})

    cells_df = pd.DataFrame(cells)
    if not cells_df.empty:
        cells_df["status_rank"] = cells_df["status"].map(
            {"PUBLISH": 0, "MONITOR": 1, "INSUFFICIENT": 2}).fillna(3)
        cells_df = cells_df.sort_values(
            ["rule", "status_rank", "win_pct"], ascending=[True, True, False]
        ).drop(columns=["status_rank"]).reset_index(drop=True)

    return cells_df, cuts


def write_outputs(panel: pd.DataFrame, cells: pd.DataFrame, cuts: dict) -> dict:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now(IST).strftime("%Y_%m_%d")
    panel_path = OUT_DIR / f"panel_{today}.parquet"
    cells_path = OUT_DIR / f"cells_{today}.csv"
    cells_latest = OUT_DIR / "cells_latest.csv"
    summary_path = OUT_DIR / f"summary_{today}.json"

    panel.to_parquet(panel_path, index=False)
    cells.to_csv(cells_path, index=False, float_format="%.4f")
    cells.to_csv(cells_latest, index=False, float_format="%.4f")

    pub = cells[cells["status"] == "PUBLISH"] if not cells.empty else pd.DataFrame()
    mon = cells[cells["status"] == "MONITOR"] if not cells.empty else pd.DataFrame()
    summary = {
        "as_of": datetime.now(IST).isoformat(),
        "tracker": "intraday_panel_v1",
        "n_rows": int(len(panel)),
        "n_tickers": int(panel["ticker"].nunique()),
        "n_dates": int(panel["date"].nunique()),
        "date_range": [panel["date"].min(), panel["date"].max()] if not panel.empty else None,
        "tertile_cuts": cuts,
        "n_publish": int(len(pub)),
        "n_monitor": int(len(mon)),
        "publish_cells": pub.to_dict(orient="records"),
        "monitor_cells": mon.head(50).to_dict(orient="records"),
        "panel_parquet": str(panel_path.relative_to(PIPELINE_ROOT)),
        "cells_csv": str(cells_path.relative_to(PIPELINE_ROOT)),
    }
    summary_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    return summary


def main() -> None:
    p = argparse.ArgumentParser(description="Panel-wide intraday TA descriptive backtest")
    p.add_argument("--max-tickers", type=int, default=None)
    p.add_argument("--print", action="store_true")
    args = p.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    panel = build_panel(max_tickers=args.max_tickers)
    if panel.empty:
        log.error("panel is empty — no rows produced")
        return
    log.info("panel: %d rows, %d tickers, %d dates",
             len(panel), panel["ticker"].nunique(), panel["date"].nunique())
    cells, cuts = _aggregate_cells(panel)
    summary = write_outputs(panel, cells, cuts)

    print(f"=== Intraday Panel v1 — {summary['as_of']} ===")
    print(f"Rows: {summary['n_rows']}  Tickers: {summary['n_tickers']}  Dates: {summary['n_dates']}")
    print(f"Date range: {summary['date_range']}")
    print(f"PUBLISH cells: {summary['n_publish']}, MONITOR cells: {summary['n_monitor']}")
    print()
    if args.print:
        for cell in summary["publish_cells"][:30]:
            print(f"  PUB  {cell['rule']:<6}  {cell['cell']:<48}  N={cell['N']:>5}  "
                  f"win={cell['win_pct']:>6.2f}%  mean={cell['mean_pnl_pct']:>+7.3f}%")


if __name__ == "__main__":
    main()
