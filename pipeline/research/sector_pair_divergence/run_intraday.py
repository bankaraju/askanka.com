"""Sector pair divergence-reversion — INTRADAY version on Kite 1-min cache.

Run with:  python -m pipeline.research.sector_pair_divergence.run_intraday

Tests the user hypothesis at the resolution it was originally posed:
when normally-tight sector pairs diverge during the morning session,
does the spread close by afternoon?

Reads from: pipeline/data/research/h_2026_04_29_intraday_v1/cache_1min/
~38 trading days × 375 min/day = ~14,250 minute bars per ticker.

Methodology
-----------
For each trading day:
  1. open  = first bar at-or-after 09:15 IST (close of that 1-min bar)
  2. T_sig = first bar at-or-after T (11:00 / 12:00 / 13:00 IST)
  3. close = first bar at-or-after 14:25 IST (last fully-tradeable bar
            under the 14:30 IST new-OPEN cutoff)
For each sector: equal-weighted mean of constituent log returns.
For each pair (A, B) × T × k:
  spread_AT = r_A_open_to_T - r_B_open_to_T
  σ_T = full-sample std of spread_AT across all (date, T) cells
  events where |spread_AT| > k·σ_T
  P&L = -sign(spread_AT) × (r_A_T_to_close - r_B_T_to_close)
  cost = 20 bps round-trip
  verdict: post-cost mean > 0, t > 1.7, n >= 5 (relaxed from daily — only
           ~38 trading days available)
"""
from __future__ import annotations

import logging
import sys
from datetime import date, time, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger("anka.sector_pair_divergence_intraday")

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
CACHE_DIR = REPO_ROOT / "pipeline" / "data" / "research" / "h_2026_04_29_intraday_v1" / "cache_1min"
OUT_DIR = REPO_ROOT / "pipeline" / "data" / "research" / "sector_pair_divergence"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ---- Locked design ---------------------------------------------------------
PAIRS = [
    ("Banks", "NBFC_HFC"),
    ("Capital_Goods", "Logistics_Transport"),
    ("Capital_Goods", "NBFC_HFC"),
    ("NBFC_HFC", "Infra_EPC"),
    ("Logistics_Transport", "NBFC_HFC"),
    ("Capital_Goods", "Infra_EPC"),
    ("Power_Utilities", "Oil_Gas"),
    ("Capital_Goods", "Power_Utilities"),
    ("Power_Utilities", "Logistics_Transport"),
    ("Logistics_Transport", "Infra_EPC"),
]
T_SIGNALS = {"t1100": time(11, 0), "t1200": time(12, 0), "t1300": time(13, 0)}
T_OPEN = time(9, 15)
T_CLOSE = time(14, 25)
THRESHOLDS_K = [1.0, 1.5, 2.0]
ROUND_TRIP_BPS = 20.0
T_STAT_BAR = 1.7   # relaxed (n_days ~38 in 60-day rolling window)
N_MIN = 5
MIN_CONSTITUENT_COVERAGE = 0.50
# ---------------------------------------------------------------------------


def _resolve_constituents() -> dict[str, list[str]]:
    """Map sectors → tickers present in the 1-min cache."""
    from pipeline.scorecard_v2.sector_mapper import SectorMapper
    m = SectorMapper().map_all()
    needed_sectors = {a for pair in PAIRS for a in pair}
    have = {p.stem for p in CACHE_DIR.glob("*.parquet")}
    by_sec: dict[str, list[str]] = {}
    for sym, info in m.items():
        sec = (info or {}).get("sector")
        if sec in needed_sectors and sym in have:
            by_sec.setdefault(sec, []).append(sym)
    return by_sec


def _load_ticker_anchors(symbol: str) -> pd.DataFrame:
    """For one ticker, return per-day open / 11:00 / 12:00 / 13:00 / close prices."""
    df = pd.read_parquet(CACHE_DIR / f"{symbol}.parquet")
    df["ts"] = pd.to_datetime(df["timestamp"])
    df["date"] = df["ts"].dt.date
    df["t"] = df["ts"].dt.time
    rows = []
    for d, sub in df.groupby("date"):
        if len(sub) < 200:           # need most of the day
            continue
        sub = sub.sort_values("ts")
        anchors: dict = {"date": d}
        for lbl, target in [("open", T_OPEN), ("t1100", T_SIGNALS["t1100"]),
                              ("t1200", T_SIGNALS["t1200"]),
                              ("t1300", T_SIGNALS["t1300"]),
                              ("close", T_CLOSE)]:
            row = sub[sub["t"] >= target]
            if row.empty:
                anchors[lbl] = float("nan")
            else:
                anchors[lbl] = float(row.iloc[0]["close"])
        rows.append(anchors)
    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.set_index("date").sort_index()
    return out


def _build_sector_returns(by_sec: dict[str, list[str]]) -> dict[str, pd.DataFrame]:
    """Per sector, return DataFrame indexed by date with columns:
       r_open_t1100, r_open_t1200, r_open_t1300, r_t1100_close, r_t1200_close, r_t1300_close
    """
    sec_returns: dict[str, pd.DataFrame] = {}
    for sec, syms in by_sec.items():
        log.info("  loading %s — %d constituents", sec, len(syms))
        per_ticker_returns: list[pd.DataFrame] = []
        for sym in syms:
            anchors = _load_ticker_anchors(sym)
            if anchors.empty:
                continue
            r = pd.DataFrame(index=anchors.index)
            for t_label in ("t1100", "t1200", "t1300"):
                r[f"r_open_{t_label}"] = np.log(anchors[t_label] / anchors["open"])
                r[f"r_{t_label}_close"] = np.log(anchors["close"] / anchors[t_label])
            per_ticker_returns.append(r.rename(columns=lambda c: f"{sym}__{c}"))
        if not per_ticker_returns:
            continue
        wide = pd.concat(per_ticker_returns, axis=1).sort_index()
        # Aggregate per (date, leg) across constituents, equal-weighted mean
        leg_cols = ["r_open_t1100", "r_open_t1200", "r_open_t1300",
                     "r_t1100_close", "r_t1200_close", "r_t1300_close"]
        aggregated = pd.DataFrame(index=wide.index)
        for leg in leg_cols:
            cols = [c for c in wide.columns if c.endswith(f"__{leg}")]
            if not cols:
                continue
            sub = wide[cols]
            present = sub.notna().sum(axis=1)
            min_present = max(1, int(np.ceil(MIN_CONSTITUENT_COVERAGE * len(cols))))
            aggregated[leg] = sub.mean(axis=1, skipna=True).where(present >= min_present)
        sec_returns[sec] = aggregated
    return sec_returns


def _t_stat(x: np.ndarray) -> float:
    if len(x) < 3:
        return 0.0
    sd = float(np.std(x, ddof=1))
    if sd == 0.0:
        return 0.0
    return float(np.mean(x)) / (sd / np.sqrt(len(x)))


def _two_sided_p(t: float) -> float:
    if abs(t) < 1e-9:
        return 1.0
    from math import erfc, sqrt
    return float(erfc(abs(t) / sqrt(2.0)))


def _study_pair(sec_returns: dict[str, pd.DataFrame], a_name: str, b_name: str) -> list[dict]:
    """For one pair, run all (T_signal × k) combos. Returns a list of summary rows."""
    if a_name not in sec_returns or b_name not in sec_returns:
        return []
    df_a = sec_returns[a_name]
    df_b = sec_returns[b_name]
    common = df_a.index.intersection(df_b.index)
    if len(common) < 10:
        return []
    a_df = df_a.loc[common]
    b_df = df_b.loc[common]

    rows: list[dict] = []
    cost = ROUND_TRIP_BPS / 1e4
    pair_label = f"{a_name}__{b_name}"

    for t_lbl in ("t1100", "t1200", "t1300"):
        spread_open_T = a_df[f"r_open_{t_lbl}"] - b_df[f"r_open_{t_lbl}"]
        afternoon_a = a_df[f"r_{t_lbl}_close"]
        afternoon_b = b_df[f"r_{t_lbl}_close"]
        revert = -np.sign(spread_open_T) * (afternoon_a - afternoon_b)

        sigma = float(spread_open_T.dropna().std(ddof=1))
        if not np.isfinite(sigma) or sigma == 0.0:
            continue

        for k in THRESHOLDS_K:
            mask = spread_open_T.abs() > k * sigma
            events = revert[mask].dropna()
            n = len(events)
            if n < N_MIN:
                rows.append({
                    "pair_label": pair_label,
                    "t_signal": t_lbl, "k": k, "n_events": n,
                    "verdict": "INSUFFICIENT_N",
                })
                continue
            pre = events.values
            post = pre - cost
            t_stat = _t_stat(post)
            mean_pre = float(np.mean(pre)) * 1e4
            mean_post = float(np.mean(post)) * 1e4
            win_post = float(np.mean(post > 0))
            p_val = _two_sided_p(t_stat)

            verdict = "PASS"
            if mean_post <= 0:
                verdict = "FAIL_POSTCOST"
            elif t_stat < T_STAT_BAR:
                verdict = "FAIL_TSTAT"

            rows.append({
                "pair_label": pair_label,
                "t_signal": t_lbl,
                "k": k,
                "n_events": n,
                "sigma_T": sigma,
                "threshold_pct": k * sigma * 100,
                "mean_pnl_pre_bps": mean_pre,
                "mean_pnl_post_bps": mean_post,
                "median_pnl_post_bps": float(np.median(post)) * 1e4,
                "win_rate_post": win_post,
                "t_stat_post": t_stat,
                "p_value_post": p_val,
                "verdict": verdict,
            })
    return rows


def main() -> int:
    logging.basicConfig(level=logging.INFO,
                         format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    today = date.today().isoformat()

    log.info("Phase 1 — resolve sector constituents")
    by_sec = _resolve_constituents()
    for sec, syms in sorted(by_sec.items()):
        log.info("  %s: %d in cache", sec, len(syms))

    log.info("Phase 2 — build per-sector intraday return panel")
    sec_returns = _build_sector_returns(by_sec)
    if not sec_returns:
        log.error("no sector returns built")
        return 2

    sample_sec = next(iter(sec_returns))
    n_days = len(sec_returns[sample_sec])
    log.info("  panel: %d sectors × %d trading days", len(sec_returns), n_days)

    log.info("Phase 3 — run divergence study × %d pairs × %d T-points × %d thresholds",
              len(PAIRS), len(T_SIGNALS), len(THRESHOLDS_K))
    all_rows: list[dict] = []
    for a, b in PAIRS:
        if a not in sec_returns or b not in sec_returns:
            log.warning("  missing %s/%s, skipping", a, b)
            continue
        all_rows.extend(_study_pair(sec_returns, a, b))

    summary = pd.DataFrame(all_rows)
    if summary.empty:
        log.error("no rows produced")
        return 3

    summary = summary.sort_values(["verdict", "mean_pnl_post_bps"],
                                    ascending=[True, False])
    summary_path = OUT_DIR / f"intraday_summary_{today}.csv"
    summary.to_csv(summary_path, index=False)
    log.info("wrote %s", summary_path)

    _write_findings(summary, n_days, today)
    return 0


def _fmt_bps(v) -> str:
    return f"{v:+.1f} bps" if pd.notna(v) else "—"


def _fmt_pct(v) -> str:
    return f"{v*100:.0f}%" if pd.notna(v) else "—"


def _write_findings(summary: pd.DataFrame, n_days: int, today: str) -> None:
    lines = [
        f"# Sector pair divergence-reversion — INTRADAY findings {today}",
        "",
        "_Discovery-only. No edge claim, no hypothesis-registry entry. "
        "Spec: `docs/research/sector_pair_divergence/2026-04-30-design.md` (intraday extension)._",
        "",
        "## What this tests",
        "",
        "When sector pair (A, B) diverges by >k·σ between OPEN (09:15 IST) "
        "and T_signal (11:00 / 12:00 / 13:00 IST), buying the laggard and "
        "shorting the leader at T_signal and holding to 14:25 IST close: "
        "does the trade earn positive post-cost return?",
        "",
        "## Setup",
        f"- Source: Kite 1-min cache, `pipeline/data/research/h_2026_04_29_intraday_v1/cache_1min/`",
        f"- Trading days available: {n_days}",
        f"- Pairs: {len(PAIRS)}, T-points: {list(T_SIGNALS)}, k-grid: {THRESHOLDS_K}",
        f"- Round-trip cost: {ROUND_TRIP_BPS:.0f} bps",
        f"- Verdict bar: post-cost mean > 0, t > {T_STAT_BAR}, n ≥ {N_MIN}",
        "",
    ]

    vc = summary["verdict"].value_counts()
    lines += ["## Verdict counts", ""]
    for v, n in vc.items():
        lines.append(f"- {v}: {n}")
    lines.append("")

    passes = summary[summary["verdict"] == "PASS"]
    if not passes.empty:
        lines += [
            f"## PASSING ({len(passes)} combos cleared the bar)",
            "",
            "| Pair | T_sig | k | n | mean post | win % | t |",
            "|---|---|---|---|---|---|---|",
        ]
        for _, r in passes.iterrows():
            lines.append(
                f"| {r['pair_label'].replace('__', ' × ')} "
                f"| {r['t_signal']} | {r['k']:.1f} | {int(r['n_events'])} "
                f"| {_fmt_bps(r['mean_pnl_post_bps'])} "
                f"| {_fmt_pct(r['win_rate_post'])} "
                f"| {r['t_stat_post']:+.2f} |"
            )
        lines.append("")

    powered = summary[summary["verdict"] != "INSUFFICIENT_N"]
    if not powered.empty:
        lines += [
            "## All powered combos (sorted by post-cost mean)",
            "",
            "| Pair | T_sig | k | n | mean pre | mean post | win % | t | verdict |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
        for _, r in powered.sort_values("mean_pnl_post_bps", ascending=False).iterrows():
            lines.append(
                f"| {r['pair_label'].replace('__', ' × ')} "
                f"| {r['t_signal']} | {r['k']:.1f} | {int(r['n_events'])} "
                f"| {_fmt_bps(r.get('mean_pnl_pre_bps'))} "
                f"| {_fmt_bps(r['mean_pnl_post_bps'])} "
                f"| {_fmt_pct(r['win_rate_post'])} "
                f"| {r['t_stat_post']:+.2f} "
                f"| **{r['verdict']}** |"
            )
        lines.append("")

    lines += [
        "## Sample-size caveat",
        "",
        f"Kite 1-min cache rolls 60 calendar days ≈ {n_days} trading days. "
        "Per (pair, T, k) cell n_events is bounded by that. "
        "A passing result here is suggestive, NOT decisive — re-check "
        "monthly as the rolling window advances, and require a fresh "
        "single-touch holdout under backtesting-specs.txt §10.4 before "
        "any live shadow.",
        "",
        "## Cross-reference",
        "",
        "Daily-frequency version: `findings_2026-04-30.md` — 0/40 combos "
        "passed; reversion fails at d→d+1 horizon. The intraday result is "
        "what tests the original user hypothesis.",
    ]

    out = OUT_DIR / f"intraday_findings_{today}.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    log.info("wrote %s", out)


if __name__ == "__main__":
    sys.exit(main())
