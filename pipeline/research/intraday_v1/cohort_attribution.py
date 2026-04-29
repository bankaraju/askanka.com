"""V2 cohort attribution: which 6 features drive realized P&L on the
production engine's already-published longs/shorts?

User direction (2026-04-29): the regime+spread+z-score system already
publishes longs and shorts each day, and is mostly directionally right.
Don't run a fresh universe search (that overfits at n=17). Instead, take
the production cohort as given and ask: WITHIN those picks, which of the
6 features (delta_pcr_2d, orb_15min, volume_z, vwap_dev, rs_vs_sector,
trend_slope_15min) actually distinguishes the high-P&L trades from the
low-P&L ones?

Methodology:
- Cohort = closed rows from track_record/recommendations.csv (and
  optionally H-001 closed rows + Phase C closed live shadow). Drop OPENs.
- For each (date, ticker), recompute 6 features at the entry IST timestamp
  using features.compute_all (same code path V1 uses at 09:30).
- Drop rows where any feature is NaN OR the ticker is not in the V1
  cache (no silent imputation per feedback_no_hallucination_mandate.md).
- Continuous attribution: Spearman correlation of each feature with
  pnl_pct, overall and per side.
- Magnitude split: top-quartile vs bottom-quartile in pnl_pct, report
  per-feature mean separation.
- Production-engine z_score baseline: how does the engine's own z_score
  correlate with pnl_pct on the same cohort? Features should add
  explanatory power BEYOND the z_score; if any feature beats it, that's
  a candidate filter.

Caveats baked into output:
- n is small (typically 20-40 closed rows). Strong rank correlations
  (|rho| > 0.5) at this n are credible signal; weak (|rho| < 0.3) are
  noise.
- Coverage report: how many cohort rows had ticker in cache vs dropped.
- Per-side splits often have very few rows; use overall results as the
  primary read.
"""
from __future__ import annotations

import argparse
import json
import logging
import math
from datetime import date as date_cls, datetime, time, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from pipeline.research.intraday_v1 import (
    in_sample_panel, features, pcr_producer, volume_aggregator
)

PIPELINE_ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = PIPELINE_ROOT / "data" / "research" / "h_2026_04_29_intraday_v1" / "cache_1min"
OI_ARCHIVE_DIR = PIPELINE_ROOT / "data" / "oi_history_stocks"
TRACK_RECORD_CSV = PIPELINE_ROOT / "data" / "research" / "track_record" / "recommendations.csv"
H001_CSV = PIPELINE_ROOT / "data" / "research" / "h_2026_04_26_001" / "recommendations.csv"
PHASE_C_LEDGER = PIPELINE_ROOT / "data" / "research" / "phase_c" / "live_paper_ledger.json"
ATTRIB_DIR = (
    PIPELINE_ROOT / "data" / "research" / "h_2026_04_29_intraday_v1" / "cohort_attribution"
)
IST = timezone(timedelta(hours=5, minutes=30))

FEATURE_KEYS = (
    "delta_pcr_2d", "orb_15min", "volume_z",
    "vwap_dev", "rs_vs_sector", "trend_slope_15min",
)

log = logging.getLogger("intraday_v1.cohort_attribution")


def _load_track_record() -> pd.DataFrame:
    if not TRACK_RECORD_CSV.exists():
        return pd.DataFrame()
    df = pd.read_csv(TRACK_RECORD_CSV)
    keep = [
        "date", "ticker", "side", "regime", "sector",
        "z_score", "abs_z", "entry_time", "exit_time",
        "entry_price", "exit_price", "pnl_pct", "exit_reason",
    ]
    df = df[[c for c in keep if c in df.columns]].copy()
    df["source"] = "track_record"
    df["classification"] = "POSSIBLE_OPPORTUNITY"
    return df


def _load_h001_closed() -> pd.DataFrame:
    """Load H-001 ledger rows that have been CLOSED (status != OPEN)."""
    if not H001_CSV.exists():
        return pd.DataFrame()
    df = pd.read_csv(H001_CSV)
    if "status" in df.columns:
        df = df[df["status"].astype(str).str.upper() != "OPEN"].copy()
    if df.empty:
        return df
    rename_map = {
        "entry_px": "entry_price", "exit_px": "exit_price",
    }
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})
    keep = [
        "date", "ticker", "side", "regime", "z_score",
        "entry_time", "exit_time", "entry_price", "exit_price",
        "pnl_pct", "exit_reason", "classification",
    ]
    df = df[[c for c in keep if c in df.columns]].copy()
    df["source"] = "h001"
    return df


def _load_phase_c_closed() -> pd.DataFrame:
    if not PHASE_C_LEDGER.exists():
        return pd.DataFrame()
    with PHASE_C_LEDGER.open("r", encoding="utf-8") as f:
        rows = json.load(f)
    if not isinstance(rows, list) or not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    if "status" in df.columns:
        df = df[df["status"].astype(str).str.upper() != "OPEN"].copy()
    if df.empty:
        return df
    df = df.rename(columns={
        "symbol": "ticker", "signal_time": "entry_time",
        "entry_px": "entry_price", "exit_px": "exit_price",
    })
    if "pnl_net_inr" in df.columns and "notional_inr" in df.columns:
        df["pnl_pct"] = df["pnl_net_inr"] / df["notional_inr"] * 100.0
    keep = [
        "date", "ticker", "side", "z_score",
        "entry_time", "exit_time", "entry_price", "exit_price",
        "pnl_pct", "exit_reason",
    ]
    df = df[[c for c in keep if c in df.columns]].copy()
    df["source"] = "phase_c"
    df["regime"] = df.get("regime", "UNKNOWN")
    df["classification"] = df.get("classification", "PHASE_C")
    return df


def _build_cohort(use_h001: bool, use_phase_c: bool) -> pd.DataFrame:
    chunks = [_load_track_record()]
    if use_h001:
        chunks.append(_load_h001_closed())
    if use_phase_c:
        chunks.append(_load_phase_c_closed())
    chunks = [c for c in chunks if not c.empty]
    if not chunks:
        return pd.DataFrame()
    cohort = pd.concat(chunks, ignore_index=True, sort=False)
    cohort = cohort.dropna(subset=["pnl_pct", "ticker", "date"]).copy()
    return cohort


def _list_cached_tickers() -> set:
    return {p.stem for p in CACHE_DIR.glob("*.parquet")}


def _resolve_sector_symbol(ticker: str) -> str:
    """Return the Kite-naming sector index ticker for ``ticker``."""
    return in_sample_panel.SECTOR_INDEX_MAP_KITE.get(
        ticker, in_sample_panel.DEFAULT_SECTOR_FALLBACK
    )


def _bar_at(bars: pd.DataFrame, eval_t: datetime) -> Optional[pd.Series]:
    """Match in_sample_panel._bar_at semantics: <= eval_t."""
    mask = bars["timestamp"] <= eval_t
    if not mask.any():
        return None
    return bars.loc[mask].iloc[-1]


def _parse_entry_time(entry_time_str: str, eval_d: date_cls) -> datetime:
    """Parse the entry_time string to an IST datetime. Most rows are at
    09:30:00 IST; if parsing fails, default to 09:30 of eval_d."""
    try:
        ts = pd.to_datetime(entry_time_str)
        if ts.tzinfo is None:
            ts = ts.tz_localize(IST)
        else:
            ts = ts.tz_convert(IST)
        return ts.to_pydatetime()
    except Exception:
        return datetime.combine(eval_d, time(9, 30), tzinfo=IST)


def _compute_features_for_row(
    row: pd.Series,
    archive_dir: Path,
    pcr_cache: Dict[date_cls, Optional[Tuple[Dict, Dict]]],
) -> Optional[Dict[str, float]]:
    """Return the 6-feature dict at row.entry_time, or None if any input
    is unavailable. Strict PIT: PCR uses prior archives only.

    pcr_cache memoizes per-date PCR resolution across rows on the same date,
    since _resolve_pcr_for_date materializes archives into a temp dir each
    call and that's expensive for repeated dates.
    """
    ticker = str(row["ticker"]).upper()
    eval_d = pd.to_datetime(row["date"]).date()
    eval_t = _parse_entry_time(row["entry_time"], eval_d)

    bars_p = CACHE_DIR / f"{ticker}.parquet"
    if not bars_p.exists():
        return None
    bars = pd.read_parquet(bars_p)

    sector_sym = _resolve_sector_symbol(ticker)
    sector_p = CACHE_DIR / f"{sector_sym}.parquet"
    if not sector_p.exists():
        return None
    sector_bars = pd.read_parquet(sector_p)

    if eval_d not in pcr_cache:
        pcr_cache[eval_d] = in_sample_panel._resolve_pcr_for_date(eval_d, archive_dir)
    pcr_pair = pcr_cache[eval_d]
    if pcr_pair is None:
        return None
    today_pcr_map, two_d_pcr_map = pcr_pair
    today_pcr = today_pcr_map.get(ticker)
    two_d_pcr = two_d_pcr_map.get(ticker)
    if today_pcr is None or two_d_pcr is None:
        return None

    try:
        vol_hist = volume_aggregator.build_volume_history(
            ticker, CACHE_DIR, eval_d, lookback_days=20
        )
    except volume_aggregator.VolumeAggregatorError:
        return None

    feats = features.compute_all(
        instrument_df=bars,
        sector_df=sector_bars,
        eval_t=eval_t,
        today_pcr=today_pcr,
        two_days_ago_pcr=two_d_pcr,
        volume_history=vol_hist,
    )
    if any(
        (v is None) or (isinstance(v, float) and not math.isfinite(v))
        for v in feats.values()
    ):
        return None
    return feats


def enrich_with_features(cohort: pd.DataFrame, archive_dir: Path) -> Tuple[pd.DataFrame, Dict]:
    """Compute 6 features per cohort row. Return enriched DF + coverage stats."""
    cached = _list_cached_tickers()
    cohort = cohort.copy()
    cohort["ticker"] = cohort["ticker"].astype(str).str.upper()
    cohort["in_cache"] = cohort["ticker"].isin(cached)

    rows: List[Dict] = []
    drop_reasons: Dict[str, int] = {
        "ticker_not_in_cache": 0, "feature_compute_failed": 0,
    }
    pcr_cache: Dict[date_cls, Optional[Tuple[Dict, Dict]]] = {}
    for _, row in cohort.iterrows():
        if not row["in_cache"]:
            drop_reasons["ticker_not_in_cache"] += 1
            continue
        feats = _compute_features_for_row(row, archive_dir, pcr_cache)
        if feats is None:
            drop_reasons["feature_compute_failed"] += 1
            continue
        merged = row.to_dict()
        for k in FEATURE_KEYS:
            merged[k] = feats[k]
        rows.append(merged)

    enriched = pd.DataFrame(rows)
    coverage = {
        "cohort_total": int(len(cohort)),
        "cohort_in_cache": int(cohort["in_cache"].sum()),
        "enriched_rows": int(len(enriched)),
        "drop_reasons": drop_reasons,
        "missing_tickers": sorted(cohort.loc[~cohort["in_cache"], "ticker"].unique().tolist()),
    }
    return enriched, coverage


def _spearman_table(df: pd.DataFrame, group_label: str) -> List[Dict]:
    if df.empty:
        return []
    rows = []
    for feat in FEATURE_KEYS:
        sub = df.dropna(subset=[feat, "pnl_pct"])
        if len(sub) < 4:
            rows.append({
                "group": group_label, "feature": feat, "n": len(sub),
                "rho": None, "p": None,
            })
            continue
        rho, p = spearmanr(sub[feat], sub["pnl_pct"])
        rows.append({
            "group": group_label, "feature": feat, "n": int(len(sub)),
            "rho": float(rho), "p": float(p),
        })
    if "z_score" in df.columns:
        sub = df.dropna(subset=["z_score", "pnl_pct"])
        if len(sub) >= 4:
            rho, p = spearmanr(sub["z_score"], sub["pnl_pct"])
            rows.append({
                "group": group_label, "feature": "engine_z_score (baseline)",
                "n": int(len(sub)), "rho": float(rho), "p": float(p),
            })
    return rows


def _quartile_split(df: pd.DataFrame, group_label: str) -> List[Dict]:
    """Top-25% vs bottom-25% in pnl_pct, per-feature mean separation."""
    if len(df) < 8:
        return []
    sorted_df = df.sort_values("pnl_pct").reset_index(drop=True)
    q1 = max(1, len(sorted_df) // 4)
    bottom = sorted_df.head(q1)
    top = sorted_df.tail(q1)
    rows = []
    for feat in FEATURE_KEYS:
        b = bottom[feat].mean()
        t = top[feat].mean()
        if math.isnan(b) or math.isnan(t):
            continue
        # Pooled sd for crude effect size (no inference, just direction)
        pooled = pd.concat([bottom[feat], top[feat]]).std(ddof=1)
        std_diff = (t - b) / pooled if pooled > 0 else float("nan")
        rows.append({
            "group": group_label, "feature": feat,
            "n_bottom": len(bottom), "n_top": len(top),
            "mean_bottom": float(b), "mean_top": float(t),
            "diff_top_minus_bot": float(t - b), "std_diff": float(std_diff),
        })
    return rows


def attribute(use_h001: bool = True, use_phase_c: bool = True,
              archive_dir: Optional[Path] = None) -> Dict:
    archive_dir = archive_dir or OI_ARCHIVE_DIR
    cohort = _build_cohort(use_h001=use_h001, use_phase_c=use_phase_c)
    if cohort.empty:
        raise RuntimeError("cohort is empty — no closed production rows found")
    log.info(f"cohort built: {len(cohort)} closed rows from "
             f"{cohort['source'].value_counts().to_dict()}")

    enriched, coverage = enrich_with_features(cohort, archive_dir)
    log.info(f"enriched: {coverage['enriched_rows']} / {coverage['cohort_total']} rows "
             f"(in_cache={coverage['cohort_in_cache']}, "
             f"drops={coverage['drop_reasons']})")

    if enriched.empty:
        raise RuntimeError("zero rows survived feature enrichment")

    # ---- analyses ----
    spear_overall = _spearman_table(enriched, "ALL")
    spear_long = _spearman_table(enriched[enriched["side"] == "LONG"], "LONG")
    spear_short = _spearman_table(enriched[enriched["side"] == "SHORT"], "SHORT")
    quartile_overall = _quartile_split(enriched, "ALL")
    quartile_long = _quartile_split(enriched[enriched["side"] == "LONG"], "LONG")
    quartile_short = _quartile_split(enriched[enriched["side"] == "SHORT"], "SHORT")

    # ---- persist ----
    ATTRIB_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now(IST).strftime("%Y_%m_%d")
    enriched.to_csv(ATTRIB_DIR / f"enriched_cohort_{today}.csv",
                    index=False, float_format="%.4f")
    spear_df = pd.DataFrame(spear_overall + spear_long + spear_short)
    spear_df.to_csv(ATTRIB_DIR / f"spearman_{today}.csv", index=False, float_format="%.4f")
    quart_df = pd.DataFrame(quartile_overall + quartile_long + quartile_short)
    quart_df.to_csv(ATTRIB_DIR / f"quartile_split_{today}.csv", index=False, float_format="%.4f")

    summary = {
        "as_of": datetime.now(IST).isoformat(),
        "coverage": coverage,
        "enriched_n": int(len(enriched)),
        "win_rate_pct": float((enriched["pnl_pct"] > 0).mean() * 100),
        "mean_pnl_pct": float(enriched["pnl_pct"].mean()),
        "median_pnl_pct": float(enriched["pnl_pct"].median()),
        "side_counts": enriched["side"].value_counts().to_dict(),
        "regime_counts": enriched.get("regime", pd.Series(dtype=str)).value_counts().to_dict(),
        "spearman_overall": spear_overall,
        "spearman_long": spear_long,
        "spearman_short": spear_short,
        "quartile_overall": quartile_overall,
        "quartile_long": quartile_long,
        "quartile_short": quartile_short,
    }
    with (ATTRIB_DIR / f"summary_{today}.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)
    return summary


def _print_summary(s: Dict) -> None:
    cov = s["coverage"]
    print("=== Cohort Attribution — feature drivers on production cohort ===")
    print(f"cohort total: {cov['cohort_total']} closed rows  "
          f"in cache: {cov['cohort_in_cache']}  "
          f"enriched: {s['enriched_n']}")
    print(f"drops: {cov['drop_reasons']}")
    print(f"missing tickers (would unlock more rows if cached): "
          f"{cov['missing_tickers']}")
    print()
    print(f"side counts: {s['side_counts']}")
    print(f"regime counts: {s['regime_counts']}")
    print(f"win rate: {s['win_rate_pct']:.1f}%   "
          f"mean P&L: {s['mean_pnl_pct']:+.3f}%   "
          f"median P&L: {s['median_pnl_pct']:+.3f}%")
    print()

    def _print_spear(rows: List[Dict], label: str) -> None:
        if not rows:
            print(f"--- Spearman ({label}): no rows ---")
            return
        print(f"--- Spearman correlation: feature vs pnl_pct ({label}) ---")
        for r in rows:
            n = r["n"]
            rho = r["rho"]
            p = r["p"]
            if rho is None:
                print(f"  {r['feature']:<32} n={n:>2}  rho=  n/a    p=  n/a")
            else:
                marker = "  ***" if (p is not None and p < 0.05) else ("   *" if (p is not None and p < 0.10) else "")
                print(f"  {r['feature']:<32} n={n:>2}  rho={rho:+.3f}  p={p:.3f}{marker}")
        print()

    _print_spear(s["spearman_overall"], "ALL")
    _print_spear(s["spearman_long"], "LONG")
    _print_spear(s["spearman_short"], "SHORT")

    def _print_quart(rows: List[Dict], label: str) -> None:
        if not rows:
            print(f"--- Quartile split ({label}): n too small ---")
            return
        print(f"--- Top-quartile vs bottom-quartile P&L: per-feature mean separation ({label}) ---")
        for r in sorted(rows, key=lambda x: -abs(x.get("std_diff", 0) or 0)):
            print(f"  {r['feature']:<22} bot_mean={r['mean_bottom']:+.5f}  "
                  f"top_mean={r['mean_top']:+.5f}  "
                  f"diff={r['diff_top_minus_bot']:+.5f}  "
                  f"std_diff={r['std_diff']:+.2f}")
        print()

    _print_quart(s["quartile_overall"], "ALL")
    _print_quart(s["quartile_long"], "LONG")
    _print_quart(s["quartile_short"], "SHORT")

    print("Note: '***' p<0.05, '*' p<0.10. At small n, marginal p-values")
    print("are hypothesis candidates, not confirmed drivers. Strong rho")
    print("(|rho|>0.5) with p<0.05 is the credible signal threshold.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-h001", action="store_true")
    parser.add_argument("--no-phase-c", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    s = attribute(use_h001=not args.no_h001, use_phase_c=not args.no_phase_c)
    _print_summary(s)


if __name__ == "__main__":
    main()
