"""VIX history (India VIX close) via yfinance primary + NSE archive fallback.

Forward-fill policy: gap <= 2 bars (for holidays), longer gaps left NaN so
the downstream feature builder can flag them.
"""
from __future__ import annotations

import sys

import pandas as pd

from pipeline.autoresearch.regime_autoresearch._yfinance_util import download_ohlcv
from pipeline.autoresearch.regime_autoresearch.constants import REPO_ROOT

OUT_CSV = REPO_ROOT / "pipeline/data/vix_history.csv"
NSE_FALLBACK = REPO_ROOT / "pipeline/data/india_historical/indices/INDIAVIX.csv"
START = "2021-04-01"
END = "2026-05-01"


def _from_yfinance() -> pd.DataFrame:
    df = download_ohlcv("^INDIAVIX", start=START, end=END)
    if df.empty:
        return pd.DataFrame(columns=["date", "vix_close"])
    return df[["date", "close"]].rename(columns={"close": "vix_close"})


def _from_nse_archive() -> pd.DataFrame:
    if not NSE_FALLBACK.exists():
        return pd.DataFrame(columns=["date", "vix_close"])
    df = pd.read_csv(NSE_FALLBACK, parse_dates=["date"])
    col = "close" if "close" in df.columns else df.columns[-1]
    return df.rename(columns={col: "vix_close"})[["date", "vix_close"]]


def main() -> int:
    df_yf = _from_yfinance()
    df_nse = _from_nse_archive()
    if df_yf.empty and df_nse.empty:
        print("error: both yfinance and NSE archive empty", file=sys.stderr)
        return 1
    if df_yf.empty:
        combined = df_nse
    elif df_nse.empty:
        combined = df_yf
    else:
        # yfinance is primary; NSE fills only gaps
        combined = pd.concat([df_yf, df_nse], ignore_index=True)
        combined = combined.drop_duplicates(subset="date", keep="first")

    combined = combined.dropna().sort_values("date")
    # Forward-fill gaps of <= 2 bars only
    combined = combined.set_index("date").asfreq("B")
    combined["vix_close"] = combined["vix_close"].ffill(limit=2)
    combined = combined.reset_index().dropna()

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(OUT_CSV, index=False)
    print(f"wrote {len(combined)} rows to {OUT_CSV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
