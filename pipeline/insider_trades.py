"""Anka Research — NSE PIT (Prohibition of Insider Trading) disclosures fetcher.

Pulls SEBI-mandated insider-trading disclosures from NSE's corporate-filings
endpoint and archives parquet partitions under
pipeline/data/insider_trades/<YYYY-MM>.parquet.

Endpoint (verified 2026-04-25, free, session-cookie auth — no API key):
    https://www.nseindia.com/api/corporates-pit
    params: index=equities, from_date=DD-MM-YYYY, to_date=DD-MM-YYYY

Historical reach: 2016+ (2015 returns empty). Density:
    2018 / 14d ≈ 1745 filings    2021 / 14d ≈ 860
    2023 / 14d ≈ 325             2025 / 14d ≈ 290

Output schema (parquet, one row per disclosure):
    symbol            str         NSE symbol
    company           str         company name
    acq_name          str         acquirer name (free-text)
    person_category   str         Promoter / Director / KMP / Employee / etc.
    transaction_type  str         "Buy" or "Sell"
    securities_type   str         "Equity Shares" / derivative / etc.
    shares_traded     Int64       count
    value_inr         float64     ₹
    shares_before     Int64       holdings before
    shares_after      Int64       holdings after
    acq_from_date     datetime64  trade-date start (use this for forensic join)
    acq_to_date       datetime64  trade-date end
    intimation_date   datetime64  date company was informed
    filing_date       datetime64  NSE disclosure timestamp (date part)
    acq_mode          str         Market Purchase / ESOP / Off-Market / etc.
    annexure          str         "7(2)" / "7(3)" / etc.
    pid               str         filing ID
    source            str         "nse_corporates_pit"

Usage:
    python -m pipeline.insider_trades --backfill 2021-04-25 2026-04-25
    python -m pipeline.insider_trades --date 2026-04-24
    python -m pipeline.insider_trades                                  # last 7 days
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable

import pandas as pd
import requests

DATA_DIR = Path(__file__).parent / "data" / "insider_trades"
LOG_DIR = Path(__file__).parent / "logs"
DATA_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "insider_trades.log", delay=True, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("insider_trades")

NSE_HOME = "https://www.nseindia.com/"
NSE_PIT_REFERER = "https://www.nseindia.com/companies-listing/corporate-filings-insider-trading"
NSE_PIT_URL = "https://www.nseindia.com/api/corporates-pit"

# NSE raw field → our clean column
RAW_TO_CLEAN = {
    "symbol": "symbol",
    "company": "company",
    "acqName": "acq_name",
    "personCategory": "person_category",
    "tdpTransactionType": "transaction_type",
    "secType": "securities_type",
    "secAcq": "shares_traded",
    "secVal": "value_inr",
    "befAcqSharesNo": "shares_before",
    "afterAcqSharesNo": "shares_after",
    "acqfromDt": "acq_from_date",
    "acqtoDt": "acq_to_date",
    "intimDt": "intimation_date",
    "date": "filing_date",
    "acqMode": "acq_mode",
    "anex": "annexure",
    "pid": "pid",
}


def _make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": NSE_PIT_REFERER,
    })
    s.get(NSE_HOME, timeout=10)
    return s


def _fetch_chunk(s: requests.Session, frm: date, to: date) -> list[dict]:
    params = {
        "index": "equities",
        "from_date": frm.strftime("%d-%m-%Y"),
        "to_date": to.strftime("%d-%m-%Y"),
    }
    r = s.get(NSE_PIT_URL, params=params, timeout=30)
    r.raise_for_status()
    j = r.json()
    return j.get("data", []) or []


def _to_int(x) -> int | None:
    if x is None:
        return None
    s = str(x).strip().replace(",", "")
    if s in {"", "-", "Nil", "NIL", "nil", "N.A.", "NA"}:
        return None
    try:
        return int(float(s))
    except ValueError:
        return None


def _to_float(x) -> float | None:
    if x is None:
        return None
    s = str(x).strip().replace(",", "")
    if s in {"", "-", "Nil", "NIL", "nil"}:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _to_date(x) -> pd.Timestamp | None:
    if not x or str(x).strip() in {"-", "Nil", "NIL", ""}:
        return pd.NaT
    s = str(x).strip()
    # NSE serves "DD-MMM-YYYY" or "DD-MMM-YYYY HH:MM"
    for fmt in ("%d-%b-%Y %H:%M", "%d-%b-%Y"):
        try:
            return pd.to_datetime(datetime.strptime(s, fmt)).normalize()
        except ValueError:
            continue
    parsed = pd.to_datetime(s, errors="coerce")
    return parsed.normalize() if pd.notna(parsed) else pd.NaT


def normalise(rows: list[dict]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    keep = {raw: clean for raw, clean in RAW_TO_CLEAN.items() if raw in df.columns}
    df = df.rename(columns=keep)[list(keep.values())].copy()
    df["symbol"] = df["symbol"].astype(str).str.strip().str.upper()
    df["transaction_type"] = df["transaction_type"].astype(str).str.strip().str.title()
    for col in ("acq_name", "company", "person_category", "securities_type",
                "acq_mode", "annexure", "pid"):
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()
    for col in ("shares_traded", "shares_before", "shares_after"):
        if col in df.columns:
            df[col] = df[col].apply(_to_int).astype("Int64")
    if "value_inr" in df.columns:
        df["value_inr"] = df["value_inr"].apply(_to_float)
    for col in ("acq_from_date", "acq_to_date", "intimation_date", "filing_date"):
        if col in df.columns:
            df[col] = df[col].apply(_to_date)
    df["source"] = "nse_corporates_pit"
    df = df.dropna(subset=["symbol"])
    return df


def fetch_range(frm: date, to: date, *, chunk_days: int = 14, sleep_s: float = 0.7) -> pd.DataFrame:
    """Fetch PIT filings between two dates inclusive, chunked to be polite."""
    s = _make_session()
    parts: list[pd.DataFrame] = []
    cur = frm
    while cur <= to:
        chunk_end = min(cur + timedelta(days=chunk_days - 1), to)
        try:
            rows = _fetch_chunk(s, cur, chunk_end)
            df = normalise(rows)
            if not df.empty:
                parts.append(df)
            log.info(f"{cur} → {chunk_end}: {len(rows):4d} raw, {len(df):4d} kept")
        except Exception as e:
            log.warning(f"{cur} → {chunk_end} failed: {e}")
        time.sleep(sleep_s)
        cur = chunk_end + timedelta(days=1)
    if not parts:
        return pd.DataFrame()
    out = pd.concat(parts, ignore_index=True)
    return out.sort_values(["acq_from_date", "symbol", "pid"], na_position="last").reset_index(drop=True)


def archive(df: pd.DataFrame) -> list[Path]:
    if df.empty:
        return []
    df = df.copy()
    bucket_date = df["acq_from_date"].fillna(df["filing_date"]).fillna(df["intimation_date"])
    df["_yyyymm"] = bucket_date.dt.strftime("%Y-%m")
    written: list[Path] = []
    for ym, part in df.groupby("_yyyymm"):
        part = part.drop(columns="_yyyymm")
        path = DATA_DIR / f"{ym}.parquet"
        if path.exists():
            existing = pd.read_parquet(path)
            combined = pd.concat([existing, part], ignore_index=True)
            combined = combined.drop_duplicates(subset=["pid"], keep="last")
        else:
            combined = part
        combined = combined.sort_values(
            ["acq_from_date", "symbol", "pid"], na_position="last"
        ).reset_index(drop=True)
        combined.to_parquet(path, index=False)
        log.info(f"wrote {path.name}: {len(combined)} rows")
        written.append(path)
    return written


def run_backfill(start: date, end: date) -> int:
    log.info(f"backfill {start} → {end}")
    df = fetch_range(start, end)
    if df.empty:
        log.warning("no rows returned")
        return 0
    archive(df)
    log.info(f"backfill complete — {len(df)} rows")
    return len(df)


def run_daily(target: date | None = None, lookback_days: int = 7) -> int:
    """Daily fetch — pulls last `lookback_days` because PIT filings often
    arrive 1-3 days after the trade date (filing lag)."""
    end = target or date.today()
    start = end - timedelta(days=lookback_days)
    df = fetch_range(start, end)
    if df.empty:
        log.warning(f"no rows for {start} → {end}")
        return 0
    archive(df)
    return len(df)


def _parse_iso(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def main(argv: Iterable[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="NSE PIT insider-trades fetcher")
    p.add_argument("--backfill", nargs=2, metavar=("FROM", "TO"),
                   help="Backfill range, ISO dates (YYYY-MM-DD)")
    p.add_argument("--date", help="Single ISO date YYYY-MM-DD (default today)")
    p.add_argument("--lookback", type=int, default=7,
                   help="Days back from --date for daily mode (default 7)")
    args = p.parse_args(argv)
    if args.backfill:
        n = run_backfill(_parse_iso(args.backfill[0]), _parse_iso(args.backfill[1]))
        return 0 if n else 1
    target = _parse_iso(args.date) if args.date else None
    n = run_daily(target, lookback_days=args.lookback)
    return 0 if n else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
