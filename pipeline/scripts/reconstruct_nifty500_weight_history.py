"""Reconstruct NIFTY 500 free-float weight history from today's ffmc anchor.

Idea (Bharat 2026-05-02):
  ffmc_i(d) = price_i(d) × shares_outstanding_i × free_float_factor_i

Within a window where shares-outstanding × free-float-factor is approximately
constant (corp actions are rare), this simplifies to:

  ffmc_i(d) ≈ ffmc_i(anchor) × close_i(d) / close_i(anchor)

We anchor to the latest live snapshot from
`fetch_nse_index_weights.py` (TRENDLYNE_ROOT/nifty500_weights/) and walk the
fno_historical/ + india_historical/ bar files backward.

Renormalization: weights are renormalized DAILY across the covered set so each
day's weights sum to 100% (instead of 89.97% — the missing 10% is small-cap
non-F&O constituents we have no bars for). This means weight_pct from the
reconstructed series and the live snapshot are comparable IFF you also
renormalize the live snapshot to the same covered set.

Caveats:
  1. Survivorship bias: uses today's constituents only — stocks that exited
     NIFTY 500 over the year (e.g. delisted, merged) are missing.
  2. Corp actions: fno_historical bars are split-adjusted (yfinance default)
     but bonuses/special dividends may not be; weight noise is highest at
     known corp-action dates.
  3. Free-float factor assumed constant — NSE re-classifies a few stocks per
     year. Magnitude small.

Output:
  pipeline/data/research/theme_detector/td_d1/
    nifty500_weights_reconstructed_<from>_<to>.csv
      schema: date, nse_symbol, ffmc_inr, weight_pct
    nifty500_weights_reconstructed_summary.json
      coverage stats per anchor date

Run:
  python -m pipeline.scripts.reconstruct_nifty500_weight_history
  python -m pipeline.scripts.reconstruct_nifty500_weight_history --start 2025-05-02 --end 2026-05-02
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
NIFTY500_WEIGHTS_DIR = REPO / "pipeline" / "data" / "trendlyne" / "raw_exports" / "nifty500_weights"
FNO_DIR = REPO / "pipeline" / "data" / "fno_historical"
IND_DIR = REPO / "pipeline" / "data" / "india_historical"
OUT_DIR = REPO / "pipeline" / "data" / "research" / "theme_detector" / "td_d1"


def _latest_anchor_csv() -> Path:
    cands = sorted(NIFTY500_WEIGHTS_DIR.glob("nifty_500_weights_*.csv"))
    if not cands:
        raise SystemExit(
            f"No NIFTY 500 anchor snapshot in {NIFTY500_WEIGHTS_DIR}. "
            "Run pipeline.scripts.fetch_nse_index_weights first."
        )
    return cands[-1]


def _load_bars(symbol: str) -> pd.DataFrame | None:
    """Load Close series for `symbol` from fno_historical or india_historical.

    Returns DataFrame indexed by date (datetime.date) with one column 'Close',
    or None when no bars exist.
    """
    for d in (FNO_DIR, IND_DIR):
        p = d / f"{symbol}.csv"
        if p.exists():
            df = pd.read_csv(p)
            # Handle both schemas: capitalized (yfinance) and lowercase (EODHD)
            if "Date" in df.columns:
                date_col, close_col = "Date", "Close"
            elif "date" in df.columns:
                date_col, close_col = "date", "close"
            else:
                return None
            df[date_col] = pd.to_datetime(df[date_col])
            df = df.set_index(df[date_col].dt.date)[[close_col]]
            df.columns = ["Close"]
            df = df[~df.index.duplicated(keep="last")]
            return df
    return None


def reconstruct(
    start: date, end: date, anchor_csv: Path | None = None
) -> tuple[pd.DataFrame, dict]:
    if anchor_csv is None:
        anchor_csv = _latest_anchor_csv()
    anchor = pd.read_csv(anchor_csv)
    anchor = anchor.dropna(subset=["nse_symbol", "ffmc_inr", "last_price"])
    anchor_date = pd.to_datetime(anchor["snapshot_date"].iloc[0]).date()

    print(
        f"anchor: {anchor_csv.name} ({anchor_date}, {len(anchor)} stocks, "
        f"sum_weight {anchor['weight_pct'].sum():.2f}%)"
    )

    # Load bars + anchor close for each stock
    bars: dict[str, pd.DataFrame] = {}
    anchor_close: dict[str, float] = {}
    anchor_ffmc: dict[str, float] = {}
    missing = []
    for _, row in anchor.iterrows():
        sym = row["nse_symbol"]
        b = _load_bars(sym)
        if b is None or b.empty:
            missing.append(sym)
            continue
        # Find anchor-date close (or latest available before anchor_date)
        before = b[b.index <= anchor_date]
        if before.empty:
            missing.append(sym)
            continue
        ac = float(before.iloc[-1]["Close"])
        if ac <= 0:
            missing.append(sym)
            continue
        bars[sym] = b
        anchor_close[sym] = ac
        anchor_ffmc[sym] = float(row["ffmc_inr"])

    covered_anchor_weight = sum(
        float(r["weight_pct"]) for _, r in anchor.iterrows()
        if r["nse_symbol"] in bars
    )
    print(
        f"covered: {len(bars)}/{len(anchor)} stocks "
        f"({covered_anchor_weight:.2f}% by weight); missing {len(missing)} small-caps"
    )

    # Build the universe of dates in the requested window from anchor's RELIANCE bars
    if "RELIANCE" not in bars:
        raise SystemExit("RELIANCE bars missing — anchor date pivot fails")
    all_dates = sorted(d for d in bars["RELIANCE"].index if start <= d <= end)
    print(f"reconstructing {len(all_dates)} dates from {start} to {end}")

    # Per-date reconstruction
    rows: list[dict] = []
    coverage_per_date: list[dict] = []
    for d in all_dates:
        ffmc_d: dict[str, float] = {}
        for sym, b in bars.items():
            sub = b[b.index <= d]
            if sub.empty:
                continue
            close_d = float(sub.iloc[-1]["Close"])
            if close_d <= 0:
                continue
            ffmc_d[sym] = anchor_ffmc[sym] * close_d / anchor_close[sym]
        total = sum(ffmc_d.values())
        if total <= 0:
            continue
        for sym, f in ffmc_d.items():
            rows.append({
                "date": d.isoformat(),
                "nse_symbol": sym,
                "ffmc_inr": round(f, 2),
                "weight_pct": round(100.0 * f / total, 6),
            })
        coverage_per_date.append({
            "date": d.isoformat(),
            "n_stocks": len(ffmc_d),
            "ffmc_total_inr": round(total, 0),
        })

    df = pd.DataFrame(rows)
    summary = {
        "anchor_csv": anchor_csv.name,
        "anchor_date": anchor_date.isoformat(),
        "anchor_constituents": int(len(anchor)),
        "anchor_covered_constituents": int(len(bars)),
        "anchor_covered_weight_pct": round(covered_anchor_weight, 4),
        "missing_stocks": sorted(missing),
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "n_dates": int(len(all_dates)),
        "rows_emitted": int(len(rows)),
        "coverage_per_date_first5": coverage_per_date[:5],
        "coverage_per_date_last5": coverage_per_date[-5:],
        "method": "ffmc_i(d) = ffmc_i(anchor) * close_i(d) / close_i(anchor); "
                  "weight_i(d) renormalised to covered set per date",
        "caveats": [
            "survivorship_bias: uses today's constituents only",
            "corp_actions: bars assumed split-adjusted; bonus/special-div noise",
            "free_float_factor_assumed_constant",
        ],
    }
    return df, summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--start", default=None, help="YYYY-MM-DD inclusive (default: 365d back)")
    ap.add_argument("--end", default=None, help="YYYY-MM-DD inclusive (default: anchor date)")
    args = ap.parse_args(argv)

    anchor_csv = _latest_anchor_csv()
    anchor = pd.read_csv(anchor_csv, nrows=1)
    anchor_date = pd.to_datetime(anchor["snapshot_date"].iloc[0]).date()
    end_d = date.fromisoformat(args.end) if args.end else anchor_date
    start_d = date.fromisoformat(args.start) if args.start else end_d - timedelta(days=365)

    df, summary = reconstruct(start_d, end_d, anchor_csv)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_csv = OUT_DIR / f"nifty500_weights_reconstructed_{start_d}_{end_d}.csv"
    df.to_csv(out_csv, index=False)
    out_json = OUT_DIR / "nifty500_weights_reconstructed_summary.json"
    out_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nwrote {out_csv.relative_to(REPO)}  ({len(df)} rows)")
    print(f"wrote {out_json.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
