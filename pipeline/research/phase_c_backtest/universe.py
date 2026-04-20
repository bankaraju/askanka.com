"""Point-in-time F&O universe per historical month.

NSE publishes a monthly fo_mktlots.csv listing all derivatives-eligible
underlyings active for that month. We download it once per month and cache
the resulting symbol set as JSON.

URL pattern (subject to NSE archive layout changes):
  https://www1.nseindia.com/content/fo/fo_mktlots.csv
"""
from __future__ import annotations

import csv
import io
import json
import logging
from pathlib import Path
import urllib.request

from . import paths

paths.ensure_cache()

_UNIVERSE_DIR = paths.UNIVERSE_DIR
_NSE_MKTLOTS_URL = "https://www1.nseindia.com/content/fo/fo_mktlots.csv"

log = logging.getLogger(__name__)


class UniverseUnavailable(Exception):
    """NSE archive unreachable for a given month."""


def _month_key(date_str: str) -> str:
    """'2026-04-15' -> '2026-04'."""
    return date_str[:7]


def _download_mktlots_csv() -> str:
    """Fetch the current fo_mktlots.csv. Raises ConnectionError on failure."""
    req = urllib.request.Request(_NSE_MKTLOTS_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def _parse_symbols(csv_text: str) -> set[str]:
    """Parse the first non-header column as the SYMBOL set."""
    reader = csv.reader(io.StringIO(csv_text))
    next(reader, None)  # skip header row
    syms: set[str] = set()
    for row in reader:
        if not row:
            continue
        sym = row[0].strip().upper()
        if sym and sym != "SYMBOL" and not sym.startswith("#"):
            syms.add(sym)
    return syms


def universe_for_date(date_str: str) -> set[str]:
    """Return the F&O underlying set active for the month of `date_str`.

    Cached per month at fno_universe_history/YYYY-MM.json. On cache miss
    and download failure, raises UniverseUnavailable.
    """
    month = _month_key(date_str)
    cache_path = Path(_UNIVERSE_DIR) / f"{month}.json"
    if cache_path.is_file():
        return set(json.loads(cache_path.read_text(encoding="utf-8")))
    try:
        csv_text = _download_mktlots_csv()
    except Exception as exc:
        raise UniverseUnavailable(f"NSE F&O list unavailable for month {month}: {exc}") from exc
    syms = _parse_symbols(csv_text)
    if not syms:
        raise UniverseUnavailable(f"NSE F&O list returned empty for month {month}")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(sorted(syms)), encoding="utf-8")
    log.info("cached F&O universe for %s: %d symbols", month, len(syms))
    return syms
