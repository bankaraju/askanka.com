"""Build pipeline/data/fno_universe_history.json from NSE bhavcopy archives.

Strategy: download one bhavcopy per calendar month-end; extract the unique set
of symbols whose instrument is a stock future or stock option; persist as one
snapshot.

NSE has TWO archive URL patterns over our backtest window:

1. Old (legacy)  — `https://archives.nseindia.com/products/content/derivatives/equities/fo<DDMonYYYY>bhav.csv.zip`
   - Schema: columns INSTRUMENT, SYMBOL (FUTSTK/OPTSTK)
   - Status as of 2026-04-25 probe: returns HTTP 404 for ALL probed dates
     (2021-05 through 2024-04). Effectively dead.

2. New UDiFF  — `https://archives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_<YYYYMMDD>_F_0000.csv.zip`
   - Schema: columns FinInstrmTp (STO/STF/IDO/IDF) and TckrSymb
   - Live from 2024-01-02 onward.

Pre-2024 months are not recoverable via NSE public archives at the moment.
Coverage therefore starts at 2024-01-31. The H-2026-04-25-001 backtest
window (2024-10-25 → 2026-04-25) is fully covered.
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import logging
import zipfile
from pathlib import Path

import pandas as pd
import requests

REPO = Path(__file__).resolve().parents[2]
OUT_PATH = REPO / "pipeline" / "data" / "fno_universe_history.json"

LEGACY_URL = "https://archives.nseindia.com/products/content/derivatives/equities/fo{ddmonyyyy}bhav.csv.zip"
UDIFF_URL = "https://archives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_{yyyymmdd}_F_0000.csv.zip"

UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip",
    "Referer": "https://www.nseindia.com/",
}


def _last_business_day(year: int, month: int) -> dt.date:
    if month == 12:
        nxt = dt.date(year + 1, 1, 1)
    else:
        nxt = dt.date(year, month + 1, 1)
    d = nxt - dt.timedelta(days=1)
    while d.weekday() >= 5:
        d -= dt.timedelta(days=1)
    return d


def _try_url(url: str, retries: int = 3, sleep_seconds: float = 1.5) -> pd.DataFrame | None:
    import time
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=UA, timeout=30)
            if r.status_code != 200:
                if r.status_code in (401, 403):
                    logging.warning(
                        "HTTP %d for %s — auth required, check headers",
                        r.status_code,
                        url,
                    )
                    return None
                if r.status_code in (429, 503):
                    logging.warning("HTTP %d for %s, backing off", r.status_code, url)
                    time.sleep(sleep_seconds * (attempt + 1))
                    continue
                return None
            with zipfile.ZipFile(io.BytesIO(r.content)) as z:
                inner = z.namelist()[0]
                with z.open(inner) as fh:
                    return pd.read_csv(fh)
        except zipfile.BadZipFile:
            return None
        except Exception as exc:
            logging.warning("attempt %d for %s failed: %s", attempt, url, exc)
            time.sleep(sleep_seconds * (attempt + 1))
    return None


def _fetch_bhavcopy(d: dt.date) -> tuple[pd.DataFrame, str] | None:
    """Try UDiFF first (live 2024+), fall back to legacy. Returns (df, format)."""
    udiff_url = UDIFF_URL.format(yyyymmdd=d.strftime("%Y%m%d"))
    df = _try_url(udiff_url)
    if df is not None:
        return df, "udiff"
    legacy_url = LEGACY_URL.format(ddmonyyyy=d.strftime("%d%b%Y").upper())
    df = _try_url(legacy_url)
    if df is not None:
        return df, "legacy"
    return None


def _extract_fno_symbols(df: pd.DataFrame, fmt: str) -> list[str]:
    if fmt == "udiff":
        # FinInstrmTp values: STO (stock options), STF (stock futures),
        # IDO (index options), IDF (index futures). We want stock-level only.
        mask = df["FinInstrmTp"].isin({"STO", "STF"})
        col = "TckrSymb"
    else:
        mask = df["INSTRUMENT"].isin({"FUTSTK", "OPTSTK"})
        col = "SYMBOL"
    return sorted(df.loc[mask, col].dropna().astype(str).str.strip().unique().tolist())


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--years", type=int, default=5)
    args = parser.parse_args()

    today = dt.date.today()
    snapshots: list[dict] = []
    failed: list[str] = []
    fmt_counts = {"udiff": 0, "legacy": 0}
    for years_back in range(args.years, -1, -1):
        for month in range(1, 13):
            year = today.year - years_back
            if year > today.year or (year == today.year and month > today.month):
                continue
            d = _last_business_day(year, month)
            if d > today:
                continue
            result = None
            probe = d
            while result is None and probe > d - dt.timedelta(days=7):
                result = _fetch_bhavcopy(probe)
                if result is None:
                    probe -= dt.timedelta(days=1)
            if result is None:
                logging.warning("no bhavcopy in week ending %s", d)
                failed.append(d.isoformat())
                continue
            df, fmt = result
            fmt_counts[fmt] += 1
            symbols = _extract_fno_symbols(df, fmt)
            if not symbols:
                logging.warning("%s parsed but produced 0 symbols (fmt=%s)", probe, fmt)
                failed.append(d.isoformat())
                continue
            snapshots.append({"date": probe.isoformat(), "symbols": symbols})
            logging.info("%s: %d symbols (fmt=%s)", probe, len(symbols), fmt)

    payload = {
        "snapshots": snapshots,
        "source": "nseindia.com archives (UDiFF + legacy bhavcopy)",
        "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "format_counts": fmt_counts,
        "failed_months": failed,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, indent=2))
    logging.info(
        "wrote %d snapshots to %s (udiff=%d legacy=%d failed=%d)",
        len(snapshots),
        OUT_PATH,
        fmt_counts["udiff"],
        fmt_counts["legacy"],
        len(failed),
    )

    # I-1: fail loudly on UDiFF-window misses. Pre-2024 gaps are documented
    # in the audit doc §20 known-issue, but any miss on/after 2024-01-02
    # (UDiFF cutover) means NSE archives are unreachable — exit non-zero so
    # reruns don't silently produce stale output.
    udiff_misses = [m for m in failed if m >= "2024-01-02"]
    if udiff_misses:
        logging.error("UDiFF-window months unexpectedly missing: %s", udiff_misses)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
