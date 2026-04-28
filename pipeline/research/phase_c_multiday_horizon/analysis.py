"""Multi-day holding-period descriptive for Phase C SHORT events.

Inputs (read-only):
- pipeline/data/research/mechanical_replay/v2/phase_c_roster.csv
- pipeline/data/fno_historical/<ticker>.csv  (PIT bars for T+1..T+5)

Output:
- pipeline/data/research/phase_c_multiday_horizon/<run_date>/
    - per_event.csv          — per-event T+1..T+5 SHORT P&L + MFE/MAE
    - horizon_summary.csv    — per-horizon aggregate
    - sigma_bucket_t1.csv    — per |z| bucket at T+1 only
    - report.md

Run:
    python -m pipeline.research.phase_c_multiday_horizon.analysis
"""
from __future__ import annotations

import csv
import math
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

_PIPELINE_DIR = Path(__file__).resolve().parents[2]
_DATA_DIR = _PIPELINE_DIR / "data"

ROSTER_CSV = _DATA_DIR / "research" / "mechanical_replay" / "v2" / "phase_c_roster.csv"
FNO_HIST_DIR = _DATA_DIR / "fno_historical"
OUT_BASE = _DATA_DIR / "research" / "phase_c_multiday_horizon"

HORIZONS = [1, 2, 3, 4, 5]

SIGMA_BUCKETS = [
    ("<1", 0.0, 1.0),
    ("1-2", 1.0, 2.0),
    ("2-3", 2.0, 3.0),
    ("3-4", 3.0, 4.0),
    (">=4", 4.0, math.inf),
]


def _bucket_for(z_abs: float) -> str:
    for label, lo, hi in SIGMA_BUCKETS:
        if lo <= z_abs < hi:
            return label
    return ">=4"


def _load_bars(ticker: str) -> Optional[pd.DataFrame]:
    p = FNO_HIST_DIR / f"{ticker}.csv"
    if not p.exists():
        return None
    df = pd.read_csv(p)
    df.columns = [c.lower() for c in df.columns]
    if "date" not in df.columns or "close" not in df.columns:
        return None
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date").reset_index(drop=True)


def _per_event_horizons(bars: pd.DataFrame, event_date: str) -> Optional[dict]:
    """Return SHORT P&L at T+1..T+5 + MFE/MAE within window. None if not enough bars."""
    as_of = pd.Timestamp(event_date)
    idx = bars.index[bars["date"] == as_of]
    if len(idx) == 0:
        # Fall back to last bar on or before event date
        on_or_before = bars[bars["date"] <= as_of]
        if on_or_before.empty:
            return None
        i0 = on_or_before.index[-1]
    else:
        i0 = int(idx[0])
    entry_close = float(bars["close"].iloc[i0])
    out = {"entry_close": entry_close, "entry_idx": i0}
    closes_after = bars["close"].iloc[i0 + 1:i0 + 1 + max(HORIZONS)].tolist()
    if len(closes_after) < max(HORIZONS):
        # Partial coverage — use what's available, NaN for missing horizons.
        for h in HORIZONS:
            if h <= len(closes_after):
                under = (closes_after[h - 1] - entry_close) / entry_close
                out[f"underlying_t{h}"] = under
                out[f"short_pnl_t{h}"] = -under
            else:
                out[f"underlying_t{h}"] = None
                out[f"short_pnl_t{h}"] = None
    else:
        for h in HORIZONS:
            under = (closes_after[h - 1] - entry_close) / entry_close
            out[f"underlying_t{h}"] = under
            out[f"short_pnl_t{h}"] = -under

    # MFE/MAE for SHORT side over window: highest favourable (most negative
    # underlying move) and worst adverse (most positive). Track from
    # high/low if available, else from close.
    if "high" in bars.columns and "low" in bars.columns and len(closes_after) > 0:
        win_h = bars["high"].iloc[i0 + 1:i0 + 1 + len(closes_after)]
        win_l = bars["low"].iloc[i0 + 1:i0 + 1 + len(closes_after)]
        # SHORT MFE = max favourable = entry/low (price drop)
        mfe_short = (entry_close - float(win_l.min())) / entry_close
        mae_short = (float(win_h.max()) - entry_close) / entry_close
    else:
        # Fallback to close-only
        if len(closes_after) > 0:
            mfe_short = (entry_close - float(min(closes_after))) / entry_close
            mae_short = (float(max(closes_after)) - entry_close) / entry_close
        else:
            mfe_short = mae_short = None
    out["short_mfe"] = mfe_short
    out["short_mae"] = mae_short
    out["bars_available"] = len(closes_after)
    return out


def run(*, output_dir: Path | None = None) -> Path:
    if not ROSTER_CSV.exists():
        raise FileNotFoundError(f"phase_c_roster missing: {ROSTER_CSV}")

    roster = pd.read_csv(ROSTER_CSV)
    roster = roster[roster["trade_rec"].astype(str).str.upper() == "SHORT"].copy()
    roster = roster.sort_values("date").reset_index(drop=True)

    rows: list[dict] = []
    n_no_bars = 0
    n_partial = 0
    for _, ev in roster.iterrows():
        ticker = str(ev["ticker"]).upper()
        bars = _load_bars(ticker)
        if bars is None or len(bars) < 5:
            n_no_bars += 1
            continue
        h = _per_event_horizons(bars, str(ev["date"]))
        if h is None:
            n_no_bars += 1
            continue
        if h["bars_available"] < max(HORIZONS):
            n_partial += 1
        z_abs = abs(float(ev["z_score"]))
        row = {
            "date": str(ev["date"]),
            "ticker": ticker,
            "z_score": float(ev["z_score"]),
            "z_abs": z_abs,
            "regime": ev.get("regime"),
            "classification": ev.get("classification"),
            "event_geometry": ev.get("event_geometry"),
            "intraday_short_pnl": -float(ev["actual_return"]),
            "sigma_bucket": _bucket_for(z_abs),
            "bars_available": h["bars_available"],
        }
        for hzn in HORIZONS:
            row[f"short_pnl_t{hzn}"] = h[f"short_pnl_t{hzn}"]
            row[f"underlying_t{hzn}"] = h[f"underlying_t{hzn}"]
        row["short_mfe"] = h["short_mfe"]
        row["short_mae"] = h["short_mae"]
        rows.append(row)

    if not rows:
        raise RuntimeError("no events scored — investigate")

    df = pd.DataFrame(rows)
    out_dir = output_dir or (OUT_BASE / datetime.now().strftime("%Y-%m-%d"))
    out_dir.mkdir(parents=True, exist_ok=True)

    # per_event.csv
    df_round = df.copy()
    for c in df_round.columns:
        if c.startswith("short_pnl_") or c.startswith("underlying_") or c in (
                "intraday_short_pnl", "short_mfe", "short_mae", "z_abs"):
            df_round[c] = df_round[c].astype("float").round(6)
    df_round.to_csv(out_dir / "per_event.csv", index=False)

    # horizon_summary.csv
    horizon_rows: list[dict] = []
    for h in HORIZONS:
        col = f"short_pnl_t{h}"
        s = df[col].dropna()
        n = len(s)
        if n == 0:
            horizon_rows.append({
                "horizon": f"T+{h}", "n": 0, "wins": 0,
                "win_rate": None, "avg_short_pnl": None, "median_short_pnl": None,
            })
            continue
        wins = int((s > 0).sum())
        horizon_rows.append({
            "horizon": f"T+{h}",
            "n": n,
            "wins": wins,
            "win_rate": round(wins / n, 4),
            "avg_short_pnl": round(float(s.mean()), 6),
            "median_short_pnl": round(float(s.median()), 6),
        })
    pd.DataFrame(horizon_rows).to_csv(out_dir / "horizon_summary.csv", index=False)

    # sigma_bucket_t1.csv — focus on T+1 since that's Phase 1 user scope
    bucket_rows: list[dict] = []
    for label, _, _ in SIGMA_BUCKETS:
        g = df[df["sigma_bucket"] == label]
        s = g["short_pnl_t1"].dropna()
        n = len(s)
        if n == 0:
            bucket_rows.append({"sigma_bucket": label, "n_t1": 0, "wins_t1": 0,
                                "win_rate_t1": None, "avg_short_pnl_t1": None})
            continue
        wins = int((s > 0).sum())
        bucket_rows.append({
            "sigma_bucket": label,
            "n_t1": n,
            "wins_t1": wins,
            "win_rate_t1": round(wins / n, 4),
            "avg_short_pnl_t1": round(float(s.mean()), 6),
        })
    pd.DataFrame(bucket_rows).to_csv(out_dir / "sigma_bucket_t1.csv", index=False)

    (out_dir / "report.md").write_text(_render_report(
        n_events=int(len(roster)),
        n_scored=int(len(df)),
        n_no_bars=n_no_bars,
        n_partial=n_partial,
        horizon_rows=horizon_rows,
        bucket_rows=bucket_rows,
        df=df,
    ), encoding="utf-8")

    print(f"phase_c_multiday_horizon: scored {len(df)} of {len(roster)} SHORT events "
          f"(skipped: {n_no_bars} no bars, {n_partial} partial < T+5 coverage)")
    print(f"output: {out_dir}")
    return out_dir


def _render_report(*, n_events, n_scored, n_no_bars, n_partial,
                   horizon_rows, bucket_rows, df) -> str:
    intra = df["intraday_short_pnl"]
    intra_hr = float((intra > 0).mean())
    intra_avg = float(intra.mean())
    mfe = df["short_mfe"].dropna()
    mae = df["short_mae"].dropna()

    lines = [
        "# Phase C multi-day holding-period descriptive",
        "",
        f"**Run:** {datetime.now().isoformat(timespec='seconds')}",
        f"**Events:** {n_scored} of {n_events} SHORT events scored "
        f"(skipped: {n_no_bars} no bars, {n_partial} partial < T+5 coverage)",
        f"**Source:** mechanical_replay v2 phase_c_roster.csv",
        "",
        "## User intent",
        "",
        "Backlog #119 — Phase 1 = T+1 overnight only (\"for now it is overnight",
        "risk\"). Phase 2 (T+2..T+5 with MFE/MAE) was deferred until forward",
        "shadow confirms T+1 edge is real. This run produces both as descriptive",
        "input — no production change.",
        "",
        "## Intraday baseline (mechanical replay 09:30→14:30)",
        "",
        f"- N: {n_scored}",
        f"- Intraday hit rate: {intra_hr:.2%}",
        f"- Intraday avg SHORT P&L: {intra_avg:+.4%}",
        "",
        "## Holding-period extension (entry close → +N close)",
        "",
        "| Horizon | N | Wins | Win rate | Avg SHORT P&L | Median |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for r in horizon_rows:
        wr = f"{r['win_rate']:.2%}" if r["win_rate"] is not None else "—"
        avg = f"{r['avg_short_pnl']:+.4%}" if r["avg_short_pnl"] is not None else "—"
        med = f"{r['median_short_pnl']:+.4%}" if r["median_short_pnl"] is not None else "—"
        lines.append(f"| {r['horizon']} | {r['n']} | {r['wins']} | {wr} | {avg} | {med} |")

    lines += [
        "",
        "## T+1 by |z| bucket (Phase 1 focus)",
        "",
        "| |z| bucket | N | Wins | Win rate | Avg SHORT P&L |",
        "|---|---:|---:|---:|---:|",
    ]
    for r in bucket_rows:
        wr = f"{r['win_rate_t1']:.2%}" if r["win_rate_t1"] is not None else "—"
        avg = f"{r['avg_short_pnl_t1']:+.4%}" if r["avg_short_pnl_t1"] is not None else "—"
        lines.append(f"| {r['sigma_bucket']} | {r['n_t1']} | {r['wins_t1']} | {wr} | {avg} |")

    lines += [
        "",
        "## MFE / MAE in [+1, +5] window (SHORT side)",
        "",
        f"- Avg MFE (best favourable move): {float(mfe.mean()):+.4%}",
        f"- Avg MAE (worst adverse move): -{float(mae.mean()):.4%}",
        f"- p75 MFE: {float(mfe.quantile(0.75)):+.4%}",
        f"- p75 MAE: -{float(mae.quantile(0.75)):.4%}",
        "",
        "## Reading the table",
        "",
        "- All P&L numbers are SHORT-side: positive when underlying fell.",
        "- T+N P&L is close[event_date] → close[event_date + N trading days].",
        "  Different event tickers may share underlying T+N moves on overlapping",
        "  dates, so events are not strictly independent observations.",
        "- MFE/MAE use intraday high/low when available, else daily close.",
        "  SHORT MFE = (entry - lowest_low) / entry; MAE = (highest_high - entry) / entry.",
        "",
        "## Verdict logic",
        "",
        "- T+1 hit rate above intraday baseline -> overnight risk has positive",
        "  expected value (Phase 1 trigger).",
        "- T+N degrades monotonically as N grows -> intraday is the regime;",
        "  multi-day extension dilutes edge.",
        "- T+N improves as N grows -> the event signal works on a slower clock;",
        "  reconsider exit timing.",
        "",
        "## Caveats",
        "",
        "- T+N close-to-close ignores intraday slippage on the entry bar.",
        "- Roster is mechanical replay v2 with v3.2 reclassification overrep.",
        "  Treat absolute hit rates as anchored to the roster, not the universe.",
        "- |z| in this roster is regime-adjusted residual z, not the raw 2σ break.",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    run()
