"""Trader's one-pager + per-engine attribution + §10 sanity checks.

Inputs (from runner):
  trades: DataFrame with columns
    [signal_id, ticker, date, source, regime, engine, side, exit_reason,
     pnl_pct, mfe_pct, actual_pnl_pct, entry_time, exit_time]

Outputs:
  - per-engine summary JSON
  - regime cube (engine × regime)
  - sanity checks dict
  - markdown one-pager committed to docs/research/mechanical_replay/
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import numpy as np
import pandas as pd

from pipeline.autoresearch.mechanical_replay import constants as C


# ---------------------------------------------------------------------------
# Per-engine summary
# ---------------------------------------------------------------------------

def build_engine_summary(trades: pd.DataFrame) -> Dict[str, Dict[str, Any]]:
    """{engine: {n, hit_rate, mean_pnl_pct, total_pnl_pct, exit_reasons: {reason: count}}}."""
    out: Dict[str, Dict[str, Any]] = {}
    if trades.empty:
        return out
    for engine, grp in trades.groupby("engine"):
        n = len(grp)
        winners = (grp["pnl_pct"] > 0).sum()
        out[engine] = {
            "n": int(n),
            "hit_rate": round(float(winners / n) if n else 0.0, 4),
            "mean_pnl_pct": round(float(grp["pnl_pct"].mean()), 4),
            "total_pnl_pct": round(float(grp["pnl_pct"].sum()), 4),
            "median_pnl_pct": round(float(grp["pnl_pct"].median()), 4),
            "exit_reasons": grp["exit_reason"].value_counts().to_dict(),
        }
    return out


# ---------------------------------------------------------------------------
# Regime cube (engine × regime)
# ---------------------------------------------------------------------------

def build_regime_cube(trades: pd.DataFrame) -> pd.DataFrame:
    """MultiIndex (engine, regime) → n, hit_rate, mean_pnl_pct, total_pnl_pct."""
    if trades.empty:
        return pd.DataFrame()
    grouped = trades.groupby(["engine", "regime"])
    rows = []
    for (engine, regime), grp in grouped:
        n = len(grp)
        winners = (grp["pnl_pct"] > 0).sum()
        rows.append({
            "engine": engine,
            "regime": regime,
            "n": int(n),
            "hit_rate": round(float(winners / n) if n else 0.0, 4),
            "mean_pnl_pct": round(float(grp["pnl_pct"].mean()), 4),
            "total_pnl_pct": round(float(grp["pnl_pct"].sum()), 4),
        })
    if not rows:
        return pd.DataFrame()
    cube = pd.DataFrame(rows).set_index(["engine", "regime"])
    return cube


# ---------------------------------------------------------------------------
# Sanity checks (spec §10)
# ---------------------------------------------------------------------------

def run_sanity_checks(
    *,
    trades: pd.DataFrame,
    total_signals_in_window: int,
    coverage_threshold_pct: float = C.COVERAGE_THRESHOLD_PCT,
    pnl_tolerance_pp: float = C.LIVE_CROSSCHECK_PNL_TOL_PP,
    agreement_threshold_pct: float = C.LIVE_CROSSCHECK_AGREE_PCT,
) -> Dict[str, Dict[str, Any]]:
    """Run §10 acceptance gates. Returns a dict with one block per check."""
    n_processed = len(trades)
    coverage_pct = (100.0 * n_processed / total_signals_in_window) if total_signals_in_window > 0 else 0.0
    coverage_block = {
        "n_processed": int(n_processed),
        "n_total": int(total_signals_in_window),
        "coverage_pct": round(coverage_pct, 2),
        "threshold_pct": coverage_threshold_pct,
        "pass": coverage_pct >= coverage_threshold_pct,
    }

    # Live cross-check: rows where actual_pnl_pct is set (i.e. source == "actual")
    cross = trades.dropna(subset=["actual_pnl_pct"]).copy() if "actual_pnl_pct" in trades.columns else pd.DataFrame()
    if cross.empty:
        cross_block = {
            "n_overlap": 0,
            "agree_pct": None,
            "threshold_pct": agreement_threshold_pct,
            "pnl_tolerance_pp": pnl_tolerance_pp,
            "pass": None,
            "note": "no live actual rows in window — cross-check skipped",
        }
    else:
        diff = (cross["pnl_pct"].astype(float) - cross["actual_pnl_pct"].astype(float)).abs()
        agree_n = int((diff <= pnl_tolerance_pp).sum())
        agree_pct = 100.0 * agree_n / len(cross)
        cross_block = {
            "n_overlap": int(len(cross)),
            "agree_pct": round(agree_pct, 2),
            "threshold_pct": agreement_threshold_pct,
            "pnl_tolerance_pp": pnl_tolerance_pp,
            "pass": agree_pct >= agreement_threshold_pct,
        }

    # Regime balance: every regime present in trades has ≥1 row.
    regimes_seen = sorted(set(trades["regime"].dropna().unique())) if "regime" in trades.columns else []
    regime_block = {
        "regimes_seen": regimes_seen,
        "n_regimes": len(regimes_seen),
        "pass": len(regimes_seen) >= 1,
    }

    return {
        "coverage": coverage_block,
        "live_cross_check": cross_block,
        "regime_balance": regime_block,
    }


# ---------------------------------------------------------------------------
# Per-trade narration (the desk-facing story for each trade)
# ---------------------------------------------------------------------------

def _fmt_time(t: Any) -> str:
    if t is None or pd.isna(t):
        return "—"
    ts = pd.Timestamp(t)
    return ts.strftime("%H:%M")


def _fmt_pp(x: Any, sign: bool = True) -> str:
    if x is None or pd.isna(x):
        return "—"
    return (f"{x:+.2f}" if sign else f"{x:.2f}") + "pp"


def narrate_trade(row: pd.Series) -> str:
    """One trader-facing paragraph per simulated trade.

    Tells the entry-time story, what happened intraday, why we exited, and
    (when present) how the live ledger compared. Designed to be quotable
    in a desk summary or a client-facing recap.
    """
    ticker = row.get("ticker", "?")
    date = pd.Timestamp(row.get("date")).date().isoformat() if not pd.isna(row.get("date")) else "?"
    side = row.get("side") or "?"
    regime = row.get("regime") or "?"
    classification = row.get("classification") or "?"
    entry_t = _fmt_time(row.get("entry_time"))
    exit_t = _fmt_time(row.get("exit_time"))
    entry_px = row.get("entry_price")
    exit_px = row.get("exit_price")
    pnl = row.get("pnl_pct")
    mfe = row.get("mfe_pct")
    exit_reason = row.get("exit_reason") or "?"
    stop_pct = row.get("stop_pct")
    atr = row.get("atr_14")
    actual_pnl = row.get("actual_pnl_pct")

    headline = f"**{ticker} {date} · {side} · {regime}**"
    setup = (
        f"Phase C `{classification}` event. Entered at {entry_t} IST at "
        f"{entry_px:.2f}." if entry_px is not None and not pd.isna(entry_px)
        else f"Phase C `{classification}` event."
    )
    risk = (
        f" Pre-trade ATR-14 was {atr:.2f}; mechanical stop set at {stop_pct:.2f}pp."
        if atr is not None and not pd.isna(atr) and stop_pct is not None and not pd.isna(stop_pct)
        else ""
    )

    # Intraday story
    if exit_reason == "TRAIL":
        story = (
            f" Trade ran to a peak of {_fmt_pp(mfe)} (trail armed once peak crossed +2.0%), "
            f"then gave back ~1.0pp into the close. Trail exit at {exit_t} IST at "
            f"{(f'{exit_px:.2f}' if exit_px is not None and not pd.isna(exit_px) else '—')} → **{_fmt_pp(pnl)}**."
        )
    elif exit_reason == "TIME_STOP":
        story = (
            f" Held to the 14:30 hard close. Peak intraday move was {_fmt_pp(mfe)}, "
            f"closed at {(f'{exit_px:.2f}' if exit_px is not None and not pd.isna(exit_px) else '—')} → **{_fmt_pp(pnl)}**."
        )
    elif exit_reason == "ATR_STOP":
        story = (
            f" Move ran against us; intra-bar drawdown breached the {_fmt_pp(stop_pct)} ATR stop "
            f"at {exit_t} IST. Exit {(f'{exit_px:.2f}' if exit_px is not None and not pd.isna(exit_px) else '—')} → **{_fmt_pp(pnl)}**. "
            f"Best intraday run before the stop: {_fmt_pp(mfe)}."
        )
    elif exit_reason == "Z_CROSS":
        story = (
            f" Phase C peer-relative z-score crossed back through zero at {exit_t} IST — "
            f"the dislocation that drove the entry had closed. Exit {(f'{exit_px:.2f}' if exit_px is not None and not pd.isna(exit_px) else '—')} → **{_fmt_pp(pnl)}**."
        )
    elif exit_reason == "NO_SIDE":
        return (
            f"{headline} — POSSIBLE_OPPORTUNITY event without a directional read in the live ledger; "
            f"replay cannot simulate without a side."
        )
    elif exit_reason == "FETCH_FAILED":
        return (
            f"{headline} — minute bars unavailable from Kite cache for this date; "
            f"trade not simulated."
        )
    else:
        story = f" Exit reason `{exit_reason}` at {exit_t} IST → **{_fmt_pp(pnl)}**."

    # Live cross-check (when present)
    if actual_pnl is not None and not pd.isna(actual_pnl):
        diff = float(pnl) - float(actual_pnl) if pnl is not None and not pd.isna(pnl) else None
        if diff is not None:
            tail = (
                f" Live ledger booked **{_fmt_pp(actual_pnl)}** (replay vs live diff: "
                f"{_fmt_pp(diff)}). Gap reflects entry-time difference: replay enters at 09:30, "
                f"live entered at the signal-fire moment intraday."
            )
        else:
            tail = ""
    else:
        tail = ""

    return headline + " — " + setup + risk + story + tail


def build_per_trade_narrations(trades: pd.DataFrame) -> list[str]:
    """One narration string per row, in chronological order."""
    if trades.empty:
        return []
    df = trades.sort_values(["date", "ticker"])
    return [narrate_trade(row) for _, row in df.iterrows()]


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------

def write_engine_summary(summary: Dict[str, Dict[str, Any]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")


def write_one_pager(
    *,
    summary: Dict[str, Dict[str, Any]],
    cube: pd.DataFrame,
    checks: Dict[str, Dict[str, Any]],
    trades: pd.DataFrame,
    window_start: pd.Timestamp,
    window_end: pd.Timestamp,
    out_path: Path,
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Mechanical 60-Day Replay — Trader One-Pager (v1)",
        "",
        f"**Window:** {window_start.date().isoformat()} → {window_end.date().isoformat()}",
        f"**Universe:** canonical_fno_research_v1 (154 tickers)",
        f"**Rules:** entry 09:30 IST · hard close 14:30 IST · ATR stop · ratchet trail · 20bps slippage",
        f"**Total trades simulated:** {len(trades)}",
        "",
        "> **⚠ v1 scope reality:** Phase C roster read from the live engine's stored "
        "`correlation_break_history.json`; regime tag read from `regime_history.csv`. "
        "Phase B + spread engines are NOT replayed in v1. Z_CROSS exit channel wired in the "
        "simulator but not populated by the runner. Only the intraday 09:30→14:30 minute-bar "
        "walk is fully deterministic. v2 spec at "
        "`docs/superpowers/specs/2026-04-25-mechanical-60day-replay-v2-design.md` closes the gap.",
        "",
        "## Per-Engine Attribution",
        "",
        "| Engine | n | Hit-rate | Mean P&L (%) | Total P&L (%) | Top Exit |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for engine, e in sorted(summary.items()):
        top_exit = max(e["exit_reasons"].items(), key=lambda kv: kv[1])[0] if e["exit_reasons"] else "-"
        lines.append(
            f"| {engine} | {e['n']} | {e['hit_rate']*100:.1f}% | "
            f"{e['mean_pnl_pct']:+.2f} | {e['total_pnl_pct']:+.2f} | {top_exit} |"
        )

    lines.extend(["", "## Regime × Engine Cube", ""])
    if cube.empty:
        lines.append("_no rows_")
    else:
        lines.append("| Engine | Regime | n | Hit-rate | Mean P&L (%) | Total P&L (%) |")
        lines.append("|---|---|---:|---:|---:|---:|")
        for (engine, regime), row in cube.iterrows():
            lines.append(
                f"| {engine} | {regime} | {int(row['n'])} | "
                f"{row['hit_rate']*100:.1f}% | {row['mean_pnl_pct']:+.2f} | {row['total_pnl_pct']:+.2f} |"
            )

    lines.extend(["", "## Exit Reason Breakdown", ""])
    if not trades.empty:
        ex = trades.groupby(["engine", "exit_reason"]).size().unstack(fill_value=0)
        lines.append("| Engine | " + " | ".join(ex.columns) + " |")
        lines.append("|---|" + "|".join([":---:"] * len(ex.columns)) + "|")
        for engine, row in ex.iterrows():
            lines.append(f"| {engine} | " + " | ".join(str(int(v)) for v in row) + " |")
    else:
        lines.append("_no rows_")

    lines.extend(["", "## Sanity Checks (spec §10)", ""])
    cov = checks["coverage"]
    lines.append(
        f"- **Coverage:** {cov['n_processed']}/{cov['n_total']} = "
        f"{cov['coverage_pct']:.1f}% (threshold {cov['threshold_pct']:.0f}%) — "
        f"{'PASS' if cov['pass'] else 'FAIL'}"
    )
    cross = checks["live_cross_check"]
    if cross["pass"] is None:
        lines.append(f"- **Live cross-check:** skipped — {cross.get('note', '')}")
    else:
        lines.append(
            f"- **Live cross-check:** {cross['agree_pct']:.1f}% agree within "
            f"±{cross['pnl_tolerance_pp']:.1f}pp on {cross['n_overlap']} overlapping rows "
            f"(threshold {cross['threshold_pct']:.0f}%) — "
            f"{'PASS' if cross['pass'] else 'FAIL'}"
        )
    rb = checks["regime_balance"]
    lines.append(f"- **Regime balance:** {rb['n_regimes']} regimes seen ({', '.join(rb['regimes_seen'])}) — "
                 f"{'PASS' if rb['pass'] else 'FAIL'}")

    # Per-trade narration — the desk-facing story for each simulated trade.
    narrations = build_per_trade_narrations(trades)
    lines.extend(["", "## Per-Trade Story", ""])
    if not narrations:
        lines.append("_no rows_")
    else:
        for n in narrations:
            lines.append("- " + n)
            lines.append("")  # blank line between trades

    lines.extend([
        "## Trader's read",
        "",
        "Descriptive forensics: this table tells you which engine made or lost money "
        "under the live rules over the 60-day window. There is **no edge claim** here — "
        "this run does not promote, register, or otherwise gate any deployment decision.",
        "",
        "If an engine column shows a positive Total P&L with hit-rate above 50% and "
        "the dominant exit is `TIME_STOP` or `TRAIL`, the live system is working as designed. "
        "If `ATR_STOP` dominates and Total P&L is negative, the engine is being run in a "
        "regime its rules don't fit — investigate before scaling.",
        "",
        "_Generated by `pipeline/autoresearch/mechanical_replay/runner.py`._",
    ])
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
