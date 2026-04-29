"""V2 discovery: which names and sectors does the pooled-weight style work on?

Reuses the V1 in-sample panel + persisted weights/z-stats. Slices the daily
long-short basket P&L by individual instrument and by sector group, so the
question "where does this style belong?" is answered by data, not by a-priori
predicate.

Per the user direction (2026-04-29): the universe is a research RESULT, not
an input. We run the search wide and report which names / sectors carry the
style.

Caveat acknowledged in output: in-sample is currently 17 days (kickoff window).
Per-name Sharpe estimates have wide confidence intervals at this n; the report
flags this and pairs Sharpe with raw trade count and hit-rate so the user can
weigh the evidence honestly. Discovery passes per spec when (a) at least one
name has Sharpe >= 1.8 with n_trades >= 8 AND (b) the surviving subset is not
driven by a single name. Run again after the in-sample window grows.
"""
from __future__ import annotations

import argparse
import json
import logging
import math
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from pipeline.research.intraday_v1 import in_sample_panel, karpathy_fit

PIPELINE_ROOT = Path(__file__).resolve().parents[2]
WEIGHTS_PATH = (
    PIPELINE_ROOT / "data" / "research" / "h_2026_04_29_intraday_v1"
    / "weights" / "latest_stocks.json"
)
DISCOVERY_DIR = (
    PIPELINE_ROOT / "data" / "research" / "h_2026_04_29_intraday_v1" / "discovery"
)
IST = timezone(timedelta(hours=5, minutes=30))
LONG_QUANTILE = 0.7
SHORT_QUANTILE = 0.3
TRADING_DAYS_PER_YEAR = 252

# Sector groupings — NSE Nifty sector index conventions, matches what
# in_sample_panel uses for RS computation. Names not listed here fall under
# "Broad/Other" and are reported separately.
SECTOR_MAP: Dict[str, str] = {
    "HDFCBANK": "Banks", "ICICIBANK": "Banks", "AXISBANK": "Banks",
    "KOTAKBANK": "Banks", "SBIN": "Banks", "INDUSINDBK": "Banks",
    "INFY": "IT", "TCS": "IT", "HCLTECH": "IT", "TECHM": "IT", "WIPRO": "IT",
    "RELIANCE": "Energy", "ONGC": "Energy", "BPCL": "Energy",
    "GAIL": "Energy", "COALINDIA": "Energy", "NTPC": "Energy",
    "POWERGRID": "Energy",
    "SUNPHARMA": "Pharma", "CIPLA": "Pharma", "DRREDDY": "Pharma",
    "DIVISLAB": "Pharma", "APOLLOHOSP": "Pharma",
    "MARUTI": "Auto", "TMPV": "Auto", "BAJAJ-AUTO": "Auto",
    "EICHERMOT": "Auto", "HEROMOTOCO": "Auto", "M&M": "Auto",
    "HINDUNILVR": "FMCG", "ITC": "FMCG", "NESTLEIND": "FMCG",
    "BRITANNIA": "FMCG", "TATACONSUM": "FMCG",
    "TATASTEEL": "Metal", "JSWSTEEL": "Metal", "HINDALCO": "Metal",
    "BAJFINANCE": "Financials", "BAJAJFINSV": "Financials",
    "HDFCLIFE": "Financials", "SBILIFE": "Financials",
    "JIOFIN": "Financials", "SHRIRAMFIN": "Financials",
    "BHARTIARTL": "Telecom", "ASIANPAINT": "Materials", "ULTRACEMCO": "Materials",
    "GRASIM": "Materials", "TITAN": "Discretionary", "TRENT": "Discretionary",
    "ADANIENT": "Conglomerate", "ADANIPORTS": "Conglomerate", "LT": "Industrials",
    "BEL": "Defence", "TATAMOTORS": "Auto",
}

log = logging.getLogger("intraday_v1.discover_v2")


def _load_persisted_weights(path: Path) -> Dict:
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    required = {"weights", "feature_names", "feature_means", "feature_stds"}
    missing = required - set(payload)
    if missing:
        raise RuntimeError(
            f"weights file {path} missing required keys: {sorted(missing)}"
        )
    return payload


def _per_day_baskets(scored: pd.DataFrame) -> pd.DataFrame:
    """Tag each row with whether it's in the long/short/neutral basket that day.

    Long: score >= per-day 0.7 quantile. Short: score <= per-day 0.3 quantile.
    Per-row contribution = +next_return_pct if long, -next_return_pct if short,
    NaN if neutral (not traded that day).
    """
    out_chunks = []
    for date, group in scored.groupby("date", sort=True):
        long_thresh = group["score"].quantile(LONG_QUANTILE)
        short_thresh = group["score"].quantile(SHORT_QUANTILE)
        g = group.copy()
        g["basket"] = "neutral"
        g.loc[g["score"] >= long_thresh, "basket"] = "long"
        g.loc[g["score"] <= short_thresh, "basket"] = "short"
        # Degenerate day (long_thresh == short_thresh): tie goes to short via
        # the order above; force to neutral so per-name P&L isn't whipsawed.
        if long_thresh == short_thresh:
            g["basket"] = "neutral"
        g["contribution_pct"] = np.where(
            g["basket"] == "long", g["next_return_pct"],
            np.where(g["basket"] == "short", -g["next_return_pct"], np.nan)
        )
        out_chunks.append(g)
    return pd.concat(out_chunks, ignore_index=True)


def _per_name_metrics(tagged: pd.DataFrame) -> pd.DataFrame:
    """Aggregate per-instrument: n_trades, hit_rate, sum_return, mean, std,
    annualized Sharpe (with the n=small caveat surfaced via n_trades column)."""
    rows = []
    for instrument, group in tagged.groupby("instrument", sort=True):
        traded = group.dropna(subset=["contribution_pct"])
        n_trades = len(traded)
        n_long = int((traded["basket"] == "long").sum())
        n_short = int((traded["basket"] == "short").sum())
        if n_trades == 0:
            rows.append({
                "instrument": instrument, "sector": SECTOR_MAP.get(instrument, "Broad/Other"),
                "n_trades": 0, "n_long": 0, "n_short": 0,
                "sum_return_pct": 0.0, "mean_pct": 0.0, "std_pct": 0.0,
                "hit_rate": float("nan"), "sharpe_ann": float("nan"),
            })
            continue
        contribs = traded["contribution_pct"].to_numpy()
        mean = float(contribs.mean())
        std = float(contribs.std(ddof=1)) if n_trades >= 2 else 0.0
        hit_rate = float((contribs > 0).mean())
        sharpe_ann = (
            (mean / std * math.sqrt(TRADING_DAYS_PER_YEAR))
            if std > 0 else float("nan")
        )
        rows.append({
            "instrument": instrument,
            "sector": SECTOR_MAP.get(instrument, "Broad/Other"),
            "n_trades": n_trades, "n_long": n_long, "n_short": n_short,
            "sum_return_pct": float(contribs.sum()),
            "mean_pct": mean, "std_pct": std,
            "hit_rate": hit_rate, "sharpe_ann": sharpe_ann,
        })
    return pd.DataFrame(rows).sort_values(
        ["sharpe_ann", "sum_return_pct"], ascending=[False, False],
        na_position="last"
    )


def _per_sector_metrics(tagged: pd.DataFrame) -> pd.DataFrame:
    """Aggregate per-sector by pooling all instrument-day contributions in
    the sector. Equal-weight across names within sector."""
    tagged = tagged.copy()
    tagged["sector"] = tagged["instrument"].map(SECTOR_MAP).fillna("Broad/Other")
    rows = []
    for sector, group in tagged.groupby("sector", sort=True):
        traded = group.dropna(subset=["contribution_pct"])
        n_trades = len(traded)
        n_names = group["instrument"].nunique()
        if n_trades == 0:
            rows.append({
                "sector": sector, "n_names": n_names,
                "n_trades": 0, "sum_return_pct": 0.0,
                "mean_pct": 0.0, "hit_rate": float("nan"),
                "sharpe_ann": float("nan"),
            })
            continue
        contribs = traded["contribution_pct"].to_numpy()
        mean = float(contribs.mean())
        std = float(contribs.std(ddof=1)) if n_trades >= 2 else 0.0
        hit_rate = float((contribs > 0).mean())
        sharpe_ann = (
            (mean / std * math.sqrt(TRADING_DAYS_PER_YEAR))
            if std > 0 else float("nan")
        )
        rows.append({
            "sector": sector, "n_names": n_names, "n_trades": n_trades,
            "sum_return_pct": float(contribs.sum()),
            "mean_pct": mean, "hit_rate": hit_rate,
            "sharpe_ann": sharpe_ann,
        })
    return pd.DataFrame(rows).sort_values(
        ["sharpe_ann", "sum_return_pct"], ascending=[False, False],
        na_position="last"
    )


def discover(pool: str = "stocks") -> Dict:
    payload = _load_persisted_weights(WEIGHTS_PATH)
    weights = np.array(payload["weights"], dtype=float)
    feature_names = list(payload["feature_names"])
    means = dict(payload["feature_means"])
    stds = dict(payload["feature_stds"])
    if list(karpathy_fit.FEATURE_NAMES) != feature_names:
        raise RuntimeError(
            "Feature ordering drift between fit-time and discover-time. "
            f"fit-time: {feature_names}, current: {list(karpathy_fit.FEATURE_NAMES)}"
        )

    df = in_sample_panel.assemble_for_pool(pool)
    if df.empty:
        raise RuntimeError(f"in_sample_panel for pool={pool} is EMPTY")
    n_days = df["date"].nunique()
    n_rows = len(df)
    n_inst = df["instrument"].nunique()

    df_z = karpathy_fit.apply_zscore(df, means, stds)
    feat = df_z[list(karpathy_fit.FEATURE_COLS)].to_numpy()
    df_z = df_z.copy()
    df_z["score"] = feat @ weights

    tagged = _per_day_baskets(df_z)
    name_metrics = _per_name_metrics(tagged)
    sector_metrics = _per_sector_metrics(tagged)

    DISCOVERY_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now(IST).strftime("%Y_%m_%d")
    name_csv = DISCOVERY_DIR / f"per_name_{pool}_{today}.csv"
    sector_csv = DISCOVERY_DIR / f"per_sector_{pool}_{today}.csv"
    name_metrics.to_csv(name_csv, index=False, float_format="%.4f")
    sector_metrics.to_csv(sector_csv, index=False, float_format="%.4f")

    survivors = name_metrics[
        (name_metrics["sharpe_ann"] >= 1.8) & (name_metrics["n_trades"] >= 8)
    ]
    summary = {
        "pool": pool, "n_days": int(n_days), "n_rows": int(n_rows),
        "n_instruments": int(n_inst),
        "n_survivors_sharpe_ge_1p8_and_n_ge_8": int(len(survivors)),
        "survivor_names": survivors["instrument"].tolist(),
        "top5_names": name_metrics.head(5).to_dict(orient="records"),
        "top5_sectors": sector_metrics.head(5).to_dict(orient="records"),
        "bottom5_names": name_metrics.dropna(subset=["sharpe_ann"]).tail(5).to_dict(orient="records"),
        "weights_path": str(WEIGHTS_PATH),
        "name_csv": str(name_csv),
        "sector_csv": str(sector_csv),
        "as_of": datetime.now(IST).isoformat(),
    }
    summary_json = DISCOVERY_DIR / f"summary_{pool}_{today}.json"
    with summary_json.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)
    return summary


def _print_summary(s: Dict) -> None:
    print(f"=== V2 Discovery — pool={s['pool']} ===")
    print(f"in-sample: {s['n_days']} days x {s['n_instruments']} instruments = {s['n_rows']} rows")
    print(f"weights: {s['weights_path']}")
    print()
    print(f"survivors (Sharpe >= 1.8 AND n_trades >= 8): {s['n_survivors_sharpe_ge_1p8_and_n_ge_8']}")
    if s["survivor_names"]:
        print(f"  -> {s['survivor_names']}")
    print()
    print("=== Top 5 names by annualized Sharpe ===")
    for r in s["top5_names"]:
        print(f"  {r['instrument']:<14} sector={r['sector']:<14} "
              f"n_trades={r['n_trades']:>2}  hit={r['hit_rate']:.0%}  "
              f"mean={r['mean_pct']:+.3f}%  Sharpe_ann={r['sharpe_ann']:>6.2f}  "
              f"sum={r['sum_return_pct']:+.2f}%")
    print()
    print("=== Bottom 5 names ===")
    for r in s["bottom5_names"]:
        print(f"  {r['instrument']:<14} sector={r['sector']:<14} "
              f"n_trades={r['n_trades']:>2}  hit={r['hit_rate']:.0%}  "
              f"mean={r['mean_pct']:+.3f}%  Sharpe_ann={r['sharpe_ann']:>6.2f}  "
              f"sum={r['sum_return_pct']:+.2f}%")
    print()
    print("=== Top 5 sectors ===")
    for r in s["top5_sectors"]:
        print(f"  {r['sector']:<16} n_names={r['n_names']:>2}  n_trades={r['n_trades']:>3}  "
              f"hit={r['hit_rate']:.0%}  mean={r['mean_pct']:+.3f}%  "
              f"Sharpe_ann={r['sharpe_ann']:>6.2f}  sum={r['sum_return_pct']:+.2f}%")
    print()
    print(f"per-name CSV:   {s['name_csv']}")
    print(f"per-sector CSV: {s['sector_csv']}")
    print()
    print("CAVEAT: in-sample n=17 days. Per-name Sharpe estimates are noisy")
    print("(95% CI half-width ~ 1/sqrt(n) ~ 24%). Treat survivors as candidates")
    print("for refit-then-walk-forward, not as accepted strategies.")


def main() -> None:
    parser = argparse.ArgumentParser(description="V2 discovery — slice pooled-weight P&L by name + sector")
    parser.add_argument("--pool", default="stocks", choices=("stocks", "indices"))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    s = discover(pool=args.pool)
    _print_summary(s)


if __name__ == "__main__":
    main()
