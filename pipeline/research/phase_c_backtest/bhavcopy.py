"""Historical per-symbol PCR from NSE F&O bhavcopy.

NSE publishes daily F&O bhavcopy ZIP files at the archive URL

    https://nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_<YYYYMMDD>_F_0000.csv.zip

Each file contains every F&O instrument traded that session (stock options,
index options, stock futures, index futures). This module fetches the daily
CSV, keeps only stock options (``FinInstrmTp == 'STO'``, ``OptnTp in {CE, PE}``),
aggregates OpenInterest per symbol per option type, and writes a compact
parquet ``pcr_history/YYYY-MM-DD.parquet`` with columns
``[symbol, call_oi, put_oi, pcr]``.

PCR is defined as ``put_oi / call_oi`` (the classifier interprets PCR > 1 as
bullish, < 1 as bearish).
"""
from __future__ import annotations

import csv
import http.cookiejar
import io
import logging
import zipfile
from pathlib import Path
import urllib.error
import urllib.request

import pandas as pd

from . import paths

paths.ensure_cache()

_PCR_DIR = paths.CACHE_DIR / "pcr_history"
_PCR_DIR.mkdir(parents=True, exist_ok=True)

_NSE_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
_NSE_HEADERS = {
    "User-Agent": _NSE_UA,
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/all-reports",
}

log = logging.getLogger(__name__)


class BhavcopyUnavailable(Exception):
    """NSE archive unreachable or missing for a given date."""


def _bhavcopy_url(date_str: str) -> str:
    """'2024-10-15' -> archive URL."""
    d = pd.Timestamp(date_str)
    return (
        "https://nsearchives.nseindia.com/content/fo/"
        f"BhavCopy_NSE_FO_0_0_0_{d.strftime('%Y%m%d')}_F_0000.csv.zip"
    )


def _download_zip(url: str) -> bytes:
    """Fetch a ZIP from the NSE archive, warming the session cookie first."""
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    try:
        warm = urllib.request.Request("https://www.nseindia.com/", headers=_NSE_HEADERS)
        opener.open(warm, timeout=15).read()
    except Exception as exc:
        log.debug("NSE warm-up failed (proceeding anyway): %s", exc)
    req = urllib.request.Request(url, headers=_NSE_HEADERS)
    with opener.open(req, timeout=60) as resp:
        return resp.read()


def _parse_stock_options(csv_text: str) -> pd.DataFrame:
    """Return one row per (symbol, option_type) with aggregated OpenInterest.

    Filters: FinInstrmTp == 'STO' (Stock Options), OptnTp in {CE, PE}.
    """
    reader = csv.DictReader(io.StringIO(csv_text))
    rows: list[dict] = []
    for row in reader:
        if row.get("FinInstrmTp") != "STO":
            continue
        opt = row.get("OptnTp", "").strip()
        if opt not in ("CE", "PE"):
            continue
        sym = (row.get("TckrSymb") or "").strip().upper()
        if not sym:
            continue
        try:
            oi = float(row.get("OpnIntrst") or 0)
        except ValueError:
            continue
        rows.append({"symbol": sym, "option_type": opt, "oi": oi})
    if not rows:
        return pd.DataFrame(columns=["symbol", "call_oi", "put_oi", "pcr"])
    df = pd.DataFrame(rows)
    agg = df.groupby(["symbol", "option_type"], as_index=False)["oi"].sum()
    wide = agg.pivot(index="symbol", columns="option_type", values="oi").fillna(0.0)
    wide = wide.rename(columns={"CE": "call_oi", "PE": "put_oi"}).reset_index()
    for col in ("call_oi", "put_oi"):
        if col not in wide.columns:
            wide[col] = 0.0
    wide["pcr"] = wide.apply(
        lambda r: (r["put_oi"] / r["call_oi"]) if r["call_oi"] > 0 else float("nan"),
        axis=1,
    )
    return wide[["symbol", "call_oi", "put_oi", "pcr"]]


def fetch_pcr(date_str: str) -> pd.DataFrame:
    """Return per-symbol PCR for ``date_str``.

    Cached at ``pcr_history/<date>.parquet``. Re-download is triggered only
    by a missing cache entry. Raises :class:`BhavcopyUnavailable` if the NSE
    archive returns 404/403 or the file parses to an empty row set.
    """
    cache = _PCR_DIR / f"{date_str}.parquet"
    if cache.is_file():
        return pd.read_parquet(cache)
    url = _bhavcopy_url(date_str)
    try:
        blob = _download_zip(url)
    except urllib.error.HTTPError as exc:
        raise BhavcopyUnavailable(
            f"NSE bhavcopy HTTP {exc.code} for {date_str}: {exc.reason}"
        ) from exc
    except Exception as exc:
        raise BhavcopyUnavailable(
            f"NSE bhavcopy download failed for {date_str}: {exc}"
        ) from exc
    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            names = z.namelist()
            if not names:
                raise BhavcopyUnavailable(f"NSE bhavcopy zip empty for {date_str}")
            with z.open(names[0]) as fh:
                csv_text = fh.read().decode("utf-8", errors="replace")
    except zipfile.BadZipFile as exc:
        raise BhavcopyUnavailable(
            f"NSE bhavcopy not a valid zip for {date_str}: {exc}"
        ) from exc
    df = _parse_stock_options(csv_text)
    if df.empty:
        raise BhavcopyUnavailable(f"NSE bhavcopy parsed zero stock-option rows for {date_str}")
    df.to_parquet(cache, index=False)
    log.info("cached PCR for %s: %d symbols", date_str, len(df))
    return df


def pcr_by_symbol(date_str: str) -> dict[str, float]:
    """Convenience: ``{symbol: pcr}`` dict for use by classifier. Empty dict on failure."""
    try:
        df = fetch_pcr(date_str)
    except BhavcopyUnavailable as exc:
        log.warning("PCR unavailable for %s: %s", date_str, exc)
        return {}
    return {row["symbol"]: float(row["pcr"]) for _, row in df.iterrows() if pd.notna(row["pcr"])}


def backfill(start_date: str, end_date: str, sleep_s: float = 0.5) -> dict[str, int]:
    """Backfill daily PCR caches across a business-day window.

    Returns a summary ``{date: n_symbols}`` for successful days. Failed days
    are logged and skipped (not raised) so a single missing holiday doesn't
    abort a multi-month backfill.
    """
    import time
    dates = pd.bdate_range(start=start_date, end=end_date).strftime("%Y-%m-%d").tolist()
    out: dict[str, int] = {}
    for d in dates:
        cache = _PCR_DIR / f"{d}.parquet"
        if cache.is_file():
            try:
                out[d] = len(pd.read_parquet(cache))
            except Exception:
                cache.unlink(missing_ok=True)
            else:
                continue
        try:
            df = fetch_pcr(d)
            out[d] = len(df)
        except BhavcopyUnavailable as exc:
            log.warning("backfill skip %s: %s", d, exc)
            continue
        time.sleep(sleep_s)
    return out
