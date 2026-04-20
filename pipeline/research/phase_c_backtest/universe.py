"""Point-in-time F&O universe per historical month.

NSE publishes a monthly fo_mktlots.csv listing all derivatives-eligible
underlyings active for that month. We download it once per month and cache
the resulting symbol set as JSON.

URL pattern (subject to NSE archive layout changes):
  https://www1.nseindia.com/content/fo/fo_mktlots.csv
"""
from __future__ import annotations

import csv
import http.cookiejar
import io
import json
import logging
from pathlib import Path
import urllib.error
import urllib.request

from . import paths

paths.ensure_cache()

_UNIVERSE_DIR = paths.UNIVERSE_DIR
_NSE_MKTLOTS_URL = "https://www1.nseindia.com/content/fo/fo_mktlots.csv"
_NSE_HOME_URL = "https://www.nseindia.com/"
_NSE_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
_NSE_HEADERS = {
    "User-Agent": _NSE_UA,
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}

log = logging.getLogger(__name__)


class UniverseUnavailable(Exception):
    """NSE archive unreachable for a given month."""


def _month_key(date_str: str) -> str:
    """'YYYY-MM-DD' -> 'YYYY-MM'. Raises ValueError on malformed input."""
    if len(date_str) < 7 or date_str[4] != "-":
        raise ValueError(f"date_str must be YYYY-MM-DD, got: {date_str!r}")
    return date_str[:7]


def _download_mktlots_csv() -> str:
    """Fetch the current fo_mktlots.csv.

    Warms up an NSE session cookie first to avoid 403 on cold connection.
    Raises urllib.error.HTTPError on HTTP errors, ConnectionError on network
    failure.
    """
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    try:
        warm = urllib.request.Request(_NSE_HOME_URL, headers=_NSE_HEADERS)
        opener.open(warm, timeout=15).read()
    except Exception as exc:
        log.warning("NSE warm-up failed (proceeding anyway): %s", exc)
    req = urllib.request.Request(_NSE_MKTLOTS_URL, headers=_NSE_HEADERS)
    with opener.open(req, timeout=15) as resp:
        return resp.read().decode("utf-8-sig", errors="ignore")


def _parse_symbols(csv_text: str) -> set[str]:
    """Parse the first non-header column as the SYMBOL set."""
    reader = csv.reader(io.StringIO(csv_text))
    next(reader, None)  # skip header row
    syms: set[str] = set()
    for row in reader:
        if not row:
            continue
        sym = row[0].strip().upper()
        if sym and sym != "SYMBOL" and sym != "UNDERLYING" and not sym.startswith("#"):
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
    except urllib.error.HTTPError as exc:
        raise UniverseUnavailable(
            f"NSE F&O list unavailable for month {month}: HTTP {exc.code} ({exc.reason})"
        ) from exc
    except Exception as exc:
        raise UniverseUnavailable(
            f"NSE F&O list unavailable for month {month}: {exc}"
        ) from exc
    syms = _parse_symbols(csv_text)
    if not syms:
        raise UniverseUnavailable(f"NSE F&O list returned empty for month {month}")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(sorted(syms)), encoding="utf-8")
    log.info("cached F&O universe for %s: %d symbols", month, len(syms))
    return syms
