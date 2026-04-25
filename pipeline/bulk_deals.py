"""Anka Research — NSE bulk- and block-deals daily fetcher.

Pulls NSE's freely published rolling CSVs and archives one parquet per
trade-day under pipeline/data/bulk_deals/<YYYY-MM-DD>.parquet.

Endpoints (verified 2026-04-25, free, anonymous CSV — no session cookie
required for the CDN host):
    bulk : https://nsearchives.nseindia.com/content/equities/bulk.csv
    block: https://nsearchives.nseindia.com/content/equities/block.csv

Both files are *rolling-today* — NSE replaces them every trading day after
close. There is no free historical-range endpoint from NSE direct, so the
correct workflow is to pull EOD daily and archive forward. For dates
older than the daily-collection start, the bulk_deal_T column on a
forensic event will be NULL.

Output schema (parquet, one row per deal):
    date          datetime64[ns]   trade date
    symbol        str              NSE symbol
    security_name str              full company name
    client_name   str              FII / DII / promoter / fund (free-text)
    side          str              "BUY" or "SELL"
    quantity      int64            shares traded
    price         float64          weighted-avg trade price (₹)
    remarks       str              NSE remarks column (often "-")
    deal_type     str              "bulk" or "block"
    source        str              "nsearchives_csv"

Usage:
    python -m pipeline.bulk_deals                # fetch today
    python -m pipeline.bulk_deals --date 2026-04-24
"""

from __future__ import annotations

import argparse
import io
import logging
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

import pandas as pd
import requests

DATA_DIR = Path(__file__).parent / "data" / "bulk_deals"
LOG_DIR = Path(__file__).parent / "logs"
DATA_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "bulk_deals.log", delay=True, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("bulk_deals")

BULK_URL = "https://nsearchives.nseindia.com/content/equities/bulk.csv"
BLOCK_URL = "https://nsearchives.nseindia.com/content/equities/block.csv"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120 Safari/537.36"
)

# CSV header (bulk has 8 cols, block has 7 — block lacks Remarks)
BULK_COLS = [
    "Date", "Symbol", "Security Name", "Client Name",
    "Buy/Sell", "Quantity Traded", "Trade Price / Wght. Avg. Price", "Remarks",
]
BLOCK_COLS = BULK_COLS[:-1]

CLEAN = {
    "Date": "date",
    "Symbol": "symbol",
    "Security Name": "security_name",
    "Client Name": "client_name",
    "Buy/Sell": "side",
    "Quantity Traded": "quantity",
    "Trade Price / Wght. Avg. Price": "price",
    "Remarks": "remarks",
}


def _fetch_csv(url: str) -> str:
    r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
    r.raise_for_status()
    return r.text


def _parse(csv_text: str, deal_type: str) -> pd.DataFrame:
    df = pd.read_csv(io.StringIO(csv_text))
    if df.empty:
        return df
    df = df.rename(columns={c: CLEAN[c] for c in df.columns if c in CLEAN})
    if "remarks" not in df.columns:
        df["remarks"] = ""
    df["date"] = pd.to_datetime(df["date"], format="%d-%b-%Y", errors="coerce")
    df["symbol"] = df["symbol"].astype(str).str.strip().str.upper()
    df["side"] = df["side"].astype(str).str.strip().str.upper()
    df["quantity"] = (
        df["quantity"].astype(str).str.replace(",", "", regex=False)
        .pipe(pd.to_numeric, errors="coerce").astype("Int64")
    )
    df["price"] = (
        df["price"].astype(str).str.replace(",", "", regex=False)
        .pipe(pd.to_numeric, errors="coerce")
    )
    for col in ("client_name", "security_name", "remarks"):
        df[col] = df[col].astype(str).str.strip()
    df["deal_type"] = deal_type
    df["source"] = "nsearchives_csv"
    df = df.dropna(subset=["date", "symbol"])
    keep = [
        "date", "symbol", "security_name", "client_name",
        "side", "quantity", "price", "remarks", "deal_type", "source",
    ]
    return df[keep].copy()


def fetch_today() -> pd.DataFrame:
    parts: list[pd.DataFrame] = []
    for url, kind in ((BULK_URL, "bulk"), (BLOCK_URL, "block")):
        try:
            csv = _fetch_csv(url)
            df = _parse(csv, kind)
            log.info(f"{kind}: fetched {len(df)} rows")
            if not df.empty:
                parts.append(df)
        except Exception as e:
            log.warning(f"{kind} fetch failed: {e}")
    if not parts:
        return pd.DataFrame()
    out = pd.concat(parts, ignore_index=True)
    return out.sort_values(["date", "symbol", "deal_type", "side"]).reset_index(drop=True)


def archive(df: pd.DataFrame, target_date: date | None = None) -> list[Path]:
    """Write df partitioned by trade-date.

    The CSV usually carries only the most-recent trade-date, but we partition
    on the row's own date column to be safe against multi-day rollover.
    """
    if df.empty:
        log.warning("archive: empty df, nothing written")
        return []
    df = df.copy()
    df["_d"] = df["date"].dt.strftime("%Y-%m-%d")
    written: list[Path] = []
    for d, part in df.groupby("_d"):
        if target_date and d != target_date.isoformat():
            log.info(f"skipping rows dated {d} (asked for {target_date})")
            continue
        part = part.drop(columns="_d")
        path = DATA_DIR / f"{d}.parquet"
        if path.exists():
            existing = pd.read_parquet(path)
            combined = pd.concat([existing, part], ignore_index=True).drop_duplicates(
                subset=[
                    "date", "symbol", "client_name", "side",
                    "quantity", "price", "deal_type",
                ],
                keep="last",
            )
        else:
            combined = part
        combined = combined.sort_values(
            ["date", "symbol", "deal_type", "side"]
        ).reset_index(drop=True)
        combined.to_parquet(path, index=False)
        log.info(f"wrote {path.name}: {len(combined)} rows")
        written.append(path)
    return written


def run(target: date | None = None) -> int:
    df = fetch_today()
    if df.empty:
        log.error("no rows returned from NSE — nothing archived")
        return 0
    archive(df, target_date=target)
    return len(df)


def _parse_iso(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def main(argv: Iterable[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="NSE bulk/block deals daily fetcher")
    p.add_argument("--date", help="Target trade-date YYYY-MM-DD (default: whatever NSE currently serves)")
    args = p.parse_args(argv)
    target = _parse_iso(args.date) if args.date else None
    n = run(target)
    return 0 if n else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
