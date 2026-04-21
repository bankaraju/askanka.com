"""Check whether a sectoral index has an F&O (derivatives) listing.

NSE's get-quotes-derivatives endpoint returns a non-empty ``info`` block for
indices with active futures; for non-tradeable indices it returns an empty
body or an error page.
"""
from __future__ import annotations

import http.cookiejar
import json
import logging
import urllib.error
import urllib.parse
import urllib.request

log = logging.getLogger(__name__)

_URL_TMPL = "https://www.nseindia.com/api/quote-derivative?symbol={symbol}"
_NSE_HOME = "https://www.nseindia.com/"
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
_HEADERS = {
    "User-Agent": _UA, "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9", "Referer": "https://www.nseindia.com/",
}


def _nse_get(symbol: str) -> dict:
    """Fetch NSE quote-derivative JSON. Warm cookies via homepage first."""
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    try:
        opener.open(urllib.request.Request(_NSE_HOME, headers=_HEADERS), timeout=10).read()
    except urllib.error.URLError as exc:
        log.warning("NSE homepage cookie warm failed: %s", exc)
        return {}
    url = _URL_TMPL.format(symbol=urllib.parse.quote(symbol))
    try:
        with opener.open(urllib.request.Request(url, headers=_HEADERS), timeout=10) as resp:
            raw = resp.read()
    except urllib.error.URLError as exc:
        log.warning("NSE quote fetch failed for %s: %s", symbol, exc)
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def is_tradeable_index(symbol: str) -> bool:
    """True if the NSE quote-derivative endpoint returns a usable record."""
    data = _nse_get(symbol)
    if not data:
        return False
    info = data.get("info") or {}
    return bool(info.get("symbol"))


def classify_universe(symbols: list[str]) -> tuple[list[str], list[str]]:
    """Split ``symbols`` into (tradeable, non_tradeable) lists."""
    tradeable, non_tradeable = [], []
    for sym in symbols:
        if is_tradeable_index(sym):
            tradeable.append(sym)
        else:
            non_tradeable.append(sym)
    return tradeable, non_tradeable
