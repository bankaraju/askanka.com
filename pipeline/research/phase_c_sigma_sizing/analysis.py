"""Sigma-weighted sizing backtest for Phase C SHORT events.

Inputs (read-only):
- pipeline/data/research/mechanical_replay/v2/phase_c_roster.csv
- pipeline/data/fno_historical/<ticker>.csv  (PIT bars for ATR)

Output:
- pipeline/data/research/phase_c_sigma_sizing/<run_date>/
    - per_event.csv
    - sigma_buckets.csv
    - sizing_schemes.csv
    - report.md

Run:
    python -m pipeline.research.phase_c_sigma_sizing.analysis
"""
from __future__ import annotations

import csv
import math
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from pipeline.autoresearch.mechanical_replay.atr import _atr

_PIPELINE_DIR = Path(__file__).resolve().parents[2]
_DATA_DIR = _PIPELINE_DIR / "data"

ROSTER_CSV = _DATA_DIR / "research" / "mechanical_replay" / "v2" / "phase_c_roster.csv"
FNO_HIST_DIR = _DATA_DIR / "fno_historical"
OUT_BASE = _DATA_DIR / "research" / "phase_c_sigma_sizing"

FIXED_NOTIONAL_INR = 50_000.0

# |z| buckets — coarser at the bottom because most v2-roster events have |z|<1.
SIGMA_BUCKETS = [
    ("<1", 0.0, 1.0),
    ("1-2", 1.0, 2.0),
    ("2-3", 2.0, 3.0),
    ("3-4", 3.0, 4.0),
    (">=4", 4.0, math.inf),
]


def _load_pit_atr_pct(ticker: str, as_of: str) -> Optional[float]:
    """Compute ATR(14) / close * 100 from PIT daily bars up to as_of."""
    p = FNO_HIST_DIR / f"{ticker}.csv"
    if not p.exists():
        return None
    df = pd.read_csv(p)
    df.columns = [c.lower() for c in df.columns]
    needed = {"date", "high", "low", "close"}
    if not needed.issubset(df.columns):
        return None
    df["date"] = pd.to_datetime(df["date"])
    as_of_ts = pd.Timestamp(as_of)
    df = df[df["date"] <= as_of_ts].sort_values("date")
    a = _atr(df, window=14)
    if a is None or a <= 0:
        return None
    last_close = float(df["close"].iloc[-1])
    if last_close <= 0:
        return None
    return float(a / last_close * 100.0)


def _bucket_for(z_abs: float) -> str:
    for label, lo, hi in SIGMA_BUCKETS:
        if lo <= z_abs < hi:
            return label
    return ">=4"


def _max_drawdown(equity: pd.Series) -> float:
    if equity.empty:
        return 0.0
    peaks = equity.cummax()
    dd = (equity - peaks) / peaks.replace(0.0, np.nan)
    return float(dd.min()) if not dd.empty else 0.0


def _per_trade_sharpe(returns: pd.Series) -> float:
    """Per-trade Sharpe (no annualisation). Treat each trade as one observation."""
    if len(returns) < 2:
        return 0.0
    sd = float(returns.std(ddof=1))
    if sd <= 0:
        return 0.0
    return float(returns.mean() / sd)


def run(*, output_dir: Path | None = None) -> Path:
    if not ROSTER_CSV.exists():
        raise FileNotFoundError(f"phase_c_roster missing: {ROSTER_CSV}")

    roster = pd.read_csv(ROSTER_CSV)
    roster = roster[roster["trade_rec"].astype(str).str.upper() == "SHORT"].copy()
    roster = roster.sort_values("date").reset_index(drop=True)

    rows: list[dict] = []
    n_skipped_no_atr = 0
    for _, ev in roster.iterrows():
        ticker = str(ev["ticker"]).upper()
        as_of = str(ev["date"])
        atr_pct = _load_pit_atr_pct(ticker, as_of)
        if atr_pct is None or atr_pct <= 0:
            n_skipped_no_atr += 1
            continue
        z_abs = abs(float(ev["z_score"]))
        actual_return = float(ev["actual_return"])
        short_pnl_pct = -actual_return  # SHORT P&L sign-flipped vs underlying
        rows.append({
            "date": as_of,
            "ticker": ticker,
            "z_score": float(ev["z_score"]),
            "z_abs": z_abs,
            "regime": ev.get("regime"),
            "classification": ev.get("classification"),
            "event_geometry": ev.get("event_geometry"),
            "atr_pct": atr_pct,
            "actual_return": actual_return,
            "short_pnl_pct": short_pnl_pct,
            "win": int(short_pnl_pct > 0),
            "sigma_bucket": _bucket_for(z_abs),
        })

    if not rows:
        raise RuntimeError("no events scored — investigate skip counts")

    df = pd.DataFrame(rows)
    n = len(df)
    z_mean = float(df["z_abs"].mean())
    z_over_atr = df["z_abs"] / df["atr_pct"]
    parity_mean = float(z_over_atr.mean())

    # Three sizing schemes — all normalised to the same total notional
    # (n * FIXED_NOTIONAL_INR) so results compare like-for-like.
    df["notional_fixed"] = FIXED_NOTIONAL_INR
    df["notional_sigma"] = FIXED_NOTIONAL_INR * (df["z_abs"] / z_mean)
    df["notional_parity"] = FIXED_NOTIONAL_INR * (z_over_atr / parity_mean)

    # Per-trade INR P&L
    df["pnl_fixed"] = df["notional_fixed"] * (df["short_pnl_pct"])
    df["pnl_sigma"] = df["notional_sigma"] * (df["short_pnl_pct"])
    df["pnl_parity"] = df["notional_parity"] * (df["short_pnl_pct"])

    out_dir = output_dir or (OUT_BASE / datetime.now().strftime("%Y-%m-%d"))
    out_dir.mkdir(parents=True, exist_ok=True)

    keep_cols = ["date", "ticker", "z_score", "z_abs", "regime",
                 "classification", "event_geometry", "atr_pct",
                 "actual_return", "short_pnl_pct", "win", "sigma_bucket",
                 "notional_fixed", "notional_sigma", "notional_parity",
                 "pnl_fixed", "pnl_sigma", "pnl_parity"]
    df_out = df[keep_cols].copy()
    for c in ("z_abs", "atr_pct", "actual_return", "short_pnl_pct",
              "notional_sigma", "notional_parity",
              "pnl_fixed", "pnl_sigma", "pnl_parity"):
        df_out[c] = df_out[c].round(6)
    df_out.to_csv(out_dir / "per_event.csv", index=False)

    # Sigma-bucket aggregates
    bucket_rows: list[dict] = []
    for label, lo, hi in SIGMA_BUCKETS:
        g = df[df["sigma_bucket"] == label]
        n_b = len(g)
        if n_b == 0:
            bucket_rows.append({
                "sigma_bucket": label, "n": 0, "wins": 0,
                "win_rate": None, "avg_short_pnl_pct": None,
                "avg_underlying_return": None,
            })
            continue
        bucket_rows.append({
            "sigma_bucket": label,
            "n": n_b,
            "wins": int(g["win"].sum()),
            "win_rate": round(float(g["win"].mean()), 4),
            "avg_short_pnl_pct": round(float(g["short_pnl_pct"].mean()), 6),
            "avg_underlying_return": round(float(g["actual_return"].mean()), 6),
        })
    pd.DataFrame(bucket_rows).to_csv(out_dir / "sigma_buckets.csv", index=False)

    # Per-scheme aggregates: trades sorted by date so equity / drawdown are sequential.
    df_seq = df.sort_values("date").reset_index(drop=True)
    sizing_rows: list[dict] = []
    for scheme, pnl_col, notional_col in [
        ("fixed", "pnl_fixed", "notional_fixed"),
        ("sigma", "pnl_sigma", "notional_sigma"),
        ("parity", "pnl_parity", "notional_parity"),
    ]:
        pnl = df_seq[pnl_col]
        # Per-trade return on that trade's own notional — comparable across schemes.
        ret = pnl / df_seq[notional_col]
        # Equity curve in INR — starts at total deployed notional; cumulative P&L on top.
        starting_capital = float(df_seq[notional_col].sum())
        equity = starting_capital + pnl.cumsum()
        sizing_rows.append({
            "scheme": scheme,
            "n": int(len(df_seq)),
            "total_pnl_inr": round(float(pnl.sum()), 2),
            "total_notional_inr": round(starting_capital, 2),
            "total_return_pct": round(
                float(pnl.sum()) / starting_capital * 100.0
                if starting_capital > 0 else 0.0, 4),
            "avg_pnl_inr_per_trade": round(float(pnl.mean()), 2),
            "hit_rate": round(float((pnl > 0).mean()), 4),
            "per_trade_sharpe": round(_per_trade_sharpe(ret), 4),
            "max_drawdown_pct": round(_max_drawdown(equity) * 100.0, 4),
        })
    pd.DataFrame(sizing_rows).to_csv(out_dir / "sizing_schemes.csv", index=False)

    (out_dir / "report.md").write_text(_render_report(
        n_events=int(len(roster)),
        n_scored=n,
        n_skipped_no_atr=n_skipped_no_atr,
        bucket_rows=bucket_rows,
        sizing_rows=sizing_rows,
        df=df,
    ), encoding="utf-8")

    print(f"phase_c_sigma_sizing: scored {n} of {len(roster)} SHORT events "
          f"(skipped: {n_skipped_no_atr} no ATR)")
    print(f"output: {out_dir}")
    return out_dir


def _render_report(*, n_events, n_scored, n_skipped_no_atr,
                   bucket_rows, sizing_rows, df) -> str:
    lines = [
        "# Phase C sigma-weighted sizing backtest",
        "",
        f"**Run:** {datetime.now().isoformat(timespec='seconds')}",
        f"**Events:** {n_scored} of {n_events} SHORT events scored "
        f"(skipped: {n_skipped_no_atr} no PIT ATR)",
        f"**Source:** mechanical_replay v2 phase_c_roster.csv",
        "",
        "## Hypothesis",
        "",
        "User (2026-04-23): position sizing scaled by `|z|` would have",
        "materially helped 3σ/4σ cases (e.g. TECHM 4.6σ short, +3.07%).",
        "",
        "## Sizing schemes",
        "",
        "All three schemes deploy the **same total notional**",
        f"(n × ₹{int(FIXED_NOTIONAL_INR)}) so comparison is like-for-like:",
        "",
        "1. **fixed** — ₹50k per trade (status quo)",
        "2. **sigma** — notional ∝ `|z|` (normalised by mean |z|)",
        "3. **parity** — notional ∝ `|z| / ATR_pct` (vol-parity)",
        "",
        "## Scheme aggregates",
        "",
        "| Scheme | N | Total return | Avg ₹/trade | Hit rate | Per-trade Sharpe | Max DD |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for r in sizing_rows:
        lines.append(
            f"| {r['scheme']} | {r['n']} | {r['total_return_pct']:+.2f}% | "
            f"₹{r['avg_pnl_inr_per_trade']:,.0f} | {r['hit_rate']:.2%} | "
            f"{r['per_trade_sharpe']:+.4f} | {r['max_drawdown_pct']:.2f}% |"
        )

    lines += [
        "",
        "## Per |z| bucket",
        "",
        "| |z| bucket | N | Wins | Win rate | Avg SHORT P&L | Avg underlying return |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for r in bucket_rows:
        wr = f"{r['win_rate']:.2%}" if r["win_rate"] is not None else "—"
        sp = f"{r['avg_short_pnl_pct']:+.4%}" if r["avg_short_pnl_pct"] is not None else "—"
        ar = f"{r['avg_underlying_return']:+.4%}" if r["avg_underlying_return"] is not None else "—"
        lines.append(
            f"| {r['sigma_bucket']} | {r['n']} | {r['wins']} | {wr} | {sp} | {ar} |"
        )

    high_z = df[df["z_abs"] >= 2.0]
    lines += [
        "",
        f"## High-conviction (|z| ≥ 2.0) detail — n={len(high_z)}",
        "",
    ]
    if len(high_z):
        lines += [
            f"- Hit rate: {float(high_z['win'].mean()):.2%}",
            f"- Avg SHORT P&L: {float(high_z['short_pnl_pct'].mean()):+.4%}",
            f"- Avg underlying return: {float(high_z['actual_return'].mean()):+.4%}",
            f"- Avg |z|: {float(high_z['z_abs'].mean()):.2f}",
            f"- Avg ATR%: {float(high_z['atr_pct'].mean()):.2f}",
        ]

    lines += [
        "",
        "## Verdict logic",
        "",
        "- **Sigma helps** if `sigma` total return > `fixed` AND per-trade Sharpe",
        "  improves — implies the high-|z| edge is real.",
        "- **Parity helps additionally** if `parity` > `sigma` — implies the edge",
        "  is normalisation-stable (high-|z| but high-vol names don't drag it down).",
        "- **No improvement** -> the |z| ranking inside this universe is not a",
        "  conviction signal; keep status-quo fixed sizing.",
        "",
        "## Caveats",
        "",
        "- This roster's `z_score` is the regime-adjusted residual z, not the",
        "  raw 2σ break threshold the live engine uses. Most |z| values are <1.",
        "- ATR is computed PIT from `pipeline/data/fno_historical/<ticker>.csv`",
        "  bars up to and including the event date.",
        "- Per-trade Sharpe is unannualised (treats each trade as one obs).",
        "- Max drawdown is computed on the running INR equity curve, sequential",
        "  by event date — re-orderings would change it.",
        "- Roster classification overall has overrepresented winners (mechanical",
        "  replay v2 with v3.2 reclassification). Verdict reads relative",
        "  performance, not absolute hit rate.",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    run()
