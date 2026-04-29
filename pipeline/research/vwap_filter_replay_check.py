"""Apply the frozen VWAP filter (KEEP/DROP cuts) to the 60-day mechanical replay.

The H-001 NEUTRAL forward sample (n=105, 3 days) showed: KEEP 64.7% wins,
DROP 35.0% wins, lift +10pp cumulative on 20 dropped trades. Question: does
the same KEEP-vs-DROP pattern hold on the 60-day replay (388 phase_c trades,
2026-03-04 -> 2026-04-23)?

The replay period DOES NOT OVERLAP with the H-001 forward window — that makes
this a quasi-out-of-sample test of the filter. Cuts are still derived after
seeing forward, so it's not strictly OOS for cut selection, but the trade
distribution under test is independent of the trades that built the cuts.

Caveats stated up front:
  - Replay uses Z_CROSS exits (early); H-001 uses TIME_STOP only. The replay's
    Z_CROSS variant is a known drag — see memory/project_mechanical_60day_replay.md.
  - 248 trades had FETCH_FAILED in the original replay run; those are excluded.
    With the now-clean cache they could be re-run, but that's a separate task.
  - VWAP cuts (LO=-0.0008, HI=+0.0036) were derived from the 105-row NEUTRAL
    forward sample. Applying to non-NEUTRAL regime replay rows is a stretch.

Method:
  - For each phase_c CLOSED replay row, open cache_1min/<TICKER>.parquet, find
    the entry date, take 09:15..09:30 minute bars, compute VWAP, take close
    at 09:30 (or last close before), sign by side, apply classify().
  - Aggregate (KEEP / DROP / WATCH) × (regime, all) cells.
  - Report.

Outputs (data/research/vwap_filter_replay/):
  cells_<date>.csv          aggregated cells with status
  summary_<date>.json       full state including the all-regime headline
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from pipeline.research.vwap_filter import (
    KEEP, DROP, WATCH,
    VWAP_DEV_SIGNED_HI_CUT,
    VWAP_DEV_SIGNED_LO_CUT,
    classify,
)

PIPELINE_ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = PIPELINE_ROOT / "data" / "research" / "h_2026_04_29_intraday_v1" / "cache_1min"
REPLAY_CSV = PIPELINE_ROOT / "data" / "research" / "mechanical_replay" / "v2" / "trades_with_exit.csv"
OUT_DIR = PIPELINE_ROOT / "data" / "research" / "vwap_filter_replay"
IST = timezone(timedelta(hours=5, minutes=30))

PUBLISH_THRESHOLD = 30
MONITOR_THRESHOLD = 10

OPEN_T = time(9, 15)
ENTRY_T = time(9, 30)

log = logging.getLogger("vwap_filter_replay")


def _vwap_dev_for_replay_row(ticker: str, trade_date: str, side: str) -> tuple[float | None, str]:
    """Compute vwap_dev_signed for a replay (ticker, date, side) row from cached bars."""
    if side not in ("LONG", "SHORT"):
        return None, "side_invalid"
    pq = CACHE_DIR / f"{ticker}.parquet"
    if not pq.exists():
        return None, "no_parquet"
    try:
        df = pd.read_parquet(pq)
    except Exception:
        return None, "load_error"
    if df.empty or "timestamp" not in df.columns:
        return None, "empty"
    df["date_str"] = df["timestamp"].dt.date.astype(str)
    day_df = df[df["date_str"] == trade_date]
    if len(day_df) < 16:
        return None, "insufficient_bars"
    open_idx = day_df["timestamp"].dt.time == OPEN_T
    entry_idx = day_df["timestamp"].dt.time == ENTRY_T
    if not open_idx.any() or not entry_idx.any():
        return None, "missing_anchor"

    pre = day_df[(day_df["timestamp"].dt.time >= OPEN_T) &
                 (day_df["timestamp"].dt.time <= ENTRY_T)].sort_values("timestamp")
    if len(pre) < 14:
        return None, "short_orb"
    typical = (pre["high"] + pre["low"] + pre["close"]) / 3.0
    vol = pre["volume"].astype(float).clip(lower=0)
    cumv = vol.sum()
    if cumv <= 0:
        return None, "zero_volume"
    vwap = float((typical * vol).sum() / cumv)
    if vwap <= 0:
        return None, "bad_vwap"
    entry_close = float(pre.iloc[-1]["close"])
    raw_dev = (entry_close - vwap) / vwap
    sign = 1.0 if side == "LONG" else -1.0
    return raw_dev * sign, "ok"


def build_replay_panel() -> pd.DataFrame:
    df = pd.read_csv(REPLAY_CSV)
    phase_c = df[(df["engine"] == "phase_c") & (df["exit_reason"] != "FETCH_FAILED")].copy()
    phase_c["pnl_pct"] = pd.to_numeric(phase_c["pnl_pct"], errors="coerce")
    phase_c = phase_c.dropna(subset=["pnl_pct"]).reset_index(drop=True)
    log.info("phase_c valid replay rows: %d", len(phase_c))

    devs: list[float | None] = []
    statuses: list[str] = []
    tags: list[str] = []
    for _, row in phase_c.iterrows():
        dev, status = _vwap_dev_for_replay_row(row["ticker"], row["date"], row["side"])
        devs.append(dev)
        statuses.append(status)
        tags.append(classify(dev))

    phase_c["vwap_dev_signed"] = devs
    phase_c["vwap_status"] = statuses
    phase_c["filter_tag"] = tags
    return phase_c


def aggregate(panel: pd.DataFrame) -> pd.DataFrame:
    """Cell stats by (scope, tag) where scope is ALL or per regime."""
    cells: list[dict] = []

    def _add(scope: str, sub: pd.DataFrame, tag: str) -> None:
        n = int(len(sub))
        if n == 0:
            return
        win = (sub["pnl_pct"] > 0).mean() * 100
        cells.append({
            "scope": scope,
            "tag": tag,
            "N": n,
            "win_pct": round(float(win), 2),
            "mean_pnl_pct": round(float(sub["pnl_pct"].mean()), 3),
            "median_pnl_pct": round(float(sub["pnl_pct"].median()), 3),
            "cumulative_pnl_pct": round(float(sub["pnl_pct"].sum()), 3),
            "status": ("PUBLISH" if n >= PUBLISH_THRESHOLD else
                       "MONITOR" if n >= MONITOR_THRESHOLD else "INSUFFICIENT"),
        })

    for tag in ("ALL", KEEP, DROP, WATCH):
        sub = panel if tag == "ALL" else panel[panel["filter_tag"] == tag]
        _add("ALL_REGIMES", sub, tag)

    for regime, regime_df in panel.groupby("regime"):
        for tag in ("ALL", KEEP, DROP, WATCH):
            sub = regime_df if tag == "ALL" else regime_df[regime_df["filter_tag"] == tag]
            _add(regime, sub, tag)

    return pd.DataFrame(cells)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    panel = build_replay_panel()
    if panel.empty:
        log.error("no replay rows produced")
        return

    log.info("VWAP cut points (frozen): LO=%+.4f HI=%+.4f",
             VWAP_DEV_SIGNED_LO_CUT, VWAP_DEV_SIGNED_HI_CUT)
    log.info("filter_tag distribution: %s", panel["filter_tag"].value_counts().to_dict())
    log.info("vwap_status distribution: %s", panel["vwap_status"].value_counts().to_dict())

    cells = aggregate(panel)
    today = datetime.now(IST).strftime("%Y_%m_%d")
    cells_csv = OUT_DIR / f"cells_{today}.csv"
    cells_latest = OUT_DIR / "cells_latest.csv"
    summary_json = OUT_DIR / f"summary_{today}.json"
    panel_csv = OUT_DIR / f"panel_{today}.csv"

    panel_out_cols = ["signal_id", "ticker", "date", "regime", "side",
                      "exit_reason", "pnl_pct", "vwap_dev_signed", "vwap_status", "filter_tag"]
    panel[panel_out_cols].to_csv(panel_csv, index=False, float_format="%.4f")
    cells.to_csv(cells_csv, index=False, float_format="%.3f")
    cells.to_csv(cells_latest, index=False, float_format="%.3f")

    summary = {
        "as_of": datetime.now(IST).isoformat(),
        "tracker": "vwap_filter_replay",
        "source": str(REPLAY_CSV.relative_to(PIPELINE_ROOT)),
        "n_replay_rows": int(len(panel)),
        "n_with_vwap": int((panel["vwap_status"] == "ok").sum()),
        "n_watch": int((panel["filter_tag"] == WATCH).sum()),
        "frozen_cuts": {
            "VWAP_DEV_SIGNED_LO_CUT": VWAP_DEV_SIGNED_LO_CUT,
            "VWAP_DEV_SIGNED_HI_CUT": VWAP_DEV_SIGNED_HI_CUT,
        },
        "filter_tag_distribution": panel["filter_tag"].value_counts().to_dict(),
        "vwap_status_distribution": panel["vwap_status"].value_counts().to_dict(),
        "cells": cells.to_dict(orient="records"),
        "panel_csv": str(panel_csv.relative_to(PIPELINE_ROOT)),
        "cells_csv": str(cells_csv.relative_to(PIPELINE_ROOT)),
    }
    summary_json.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    print(f"\n=== VWAP Filter — 60-day Replay Backtest ===")
    print(f"Source: {REPLAY_CSV.relative_to(PIPELINE_ROOT)}")
    print(f"Replay rows (phase_c, valid pnl): {len(panel)}")
    print(f"  with vwap data:  {(panel['vwap_status']=='ok').sum()}")
    print(f"  WATCH (no data): {(panel['filter_tag']==WATCH).sum()}")
    print(f"Cuts: LO={VWAP_DEV_SIGNED_LO_CUT:+.4f}  HI={VWAP_DEV_SIGNED_HI_CUT:+.4f}")
    print()
    for scope in ["ALL_REGIMES"] + sorted(panel["regime"].unique().tolist()):
        scope_cells = cells[cells["scope"] == scope]
        if scope_cells.empty:
            continue
        print(f"  --- {scope} ---")
        for _, c in scope_cells.iterrows():
            tag = c["tag"]
            print(f"    {tag:<5}  N={c['N']:>3}  win={c['win_pct']:>5.2f}%  "
                  f"per-trade={c['mean_pnl_pct']:>+6.3f}%  cum={c['cumulative_pnl_pct']:>+7.2f}%  "
                  f"[{c['status']}]")
        print()


if __name__ == "__main__":
    main()
