"""Corp-action adjuster for unadjusted EODHD intraday bars.

The problem
-----------
EODHD daily history (`pipeline/data/fno_historical/<TICKER>.csv`) is **split-
adjusted**: every historical close is normalised to the *current* share-count
basis. EODHD intraday endpoints (1m, 5m, 1h) return **raw exchange prices** at
trade time. When Phase C minute-replay computes
``intraday_ret = (snap_px_1m - prev_close_daily) / prev_close_daily`` it is
comparing two different bases. After a 2:1 split, ratios appear at +100% for
every bar before the split — generating a flood of phantom OPPORTUNITY_OVERSHOOT
classifications.

The fix
-------
For each (ticker, date), compute the cumulative split-factor from `date` to
"now" (latest history). On read of 1m bars dated before any split events,
divide OHLC by that cumulative factor. After this, the 1m bars are on the
same split-adjusted basis as the daily history.

EODHD endpoints used
-------------------
- ``GET /api/splits/{TICKER}.NSE`` -> [{"date": "YYYY-MM-DD", "split": "post/pre"}, ...]

We deliberately do NOT adjust for dividends. EODHD's daily file in this repo
contains plain `Close` (not `Adjusted Close`), so dividends are NOT subtracted
in the daily series either. Both feeds are dividend-unadjusted, so percent
returns computed against either are dividend-consistent. Splits are the only
mismatch axis.

Caching
-------
Splits are immutable historical events. We cache the entire (ticker -> splits)
table to JSON and refresh on a long cadence (caller supplies refresh policy).
"""
from __future__ import annotations

import json
import logging
import sys
from bisect import bisect_left
from pathlib import Path

# Repo bundled lib (requests + dotenv) reachable
_REPO = Path(__file__).resolve().parents[3]
_LIB = _REPO / "pipeline" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

import requests  # noqa: E402

from pipeline.eodhd_client import _key  # noqa: E402

log = logging.getLogger("anka.phase_c_minute.corp_actions")

EODHD_BASE = "https://eodhd.com/api"
CACHE_PATH = _REPO / "pipeline" / "data" / "research" / "phase_c" / "corp_actions_cache.json"


def _parse_split_ratio(s: str) -> float:
    """`'2.000000/1.000000'` -> 2.0  (price-divisor for pre-split bars)."""
    post_str, _, pre_str = s.partition("/")
    if not pre_str:
        return 1.0
    try:
        return float(post_str) / float(pre_str)
    except (ValueError, ZeroDivisionError):
        return 1.0


def fetch_splits(ticker: str, *, timeout: int = 15) -> list[tuple[str, float]]:
    """Return chronological [(date, ratio)] for `ticker` from EODHD.

    `ratio` is the price divisor for bars on dates strictly < this split date.
    """
    api_key = _key()
    if not api_key or api_key == "YOUR_KEY_HERE":
        log.warning("EODHD_API_KEY not set; cannot fetch splits for %s", ticker)
        return []
    url = f"{EODHD_BASE}/splits/{ticker}.NSE"
    try:
        r = requests.get(
            url,
            params={"api_token": api_key, "fmt": "json"},
            timeout=timeout,
        )
        r.raise_for_status()
        data = r.json()
        if not isinstance(data, list):
            return []
        events: list[tuple[str, float]] = []
        for row in data:
            d = row.get("date")
            ratio = _parse_split_ratio(row.get("split", "1/1"))
            if d and ratio != 1.0:
                events.append((d, ratio))
        events.sort()
        return events
    except (requests.RequestException, ValueError) as exc:
        log.warning("splits fetch failed for %s: %s", ticker, exc)
        return []


def load_cache() -> dict[str, list[tuple[str, float]]]:
    """Read ticker -> [(date, ratio)] from the JSON cache. Empty dict if missing."""
    if not CACHE_PATH.is_file():
        return {}
    try:
        raw = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    out: dict[str, list[tuple[str, float]]] = {}
    for t, events in raw.items():
        if not isinstance(events, list):
            continue
        out[t] = [(e[0], float(e[1])) for e in events if isinstance(e, list) and len(e) == 2]
    return out


def save_cache(cache: dict[str, list[tuple[str, float]]]) -> None:
    """Persist ticker -> [(date, ratio)] to JSON. Atomic via tmp + rename."""
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {t: [list(e) for e in events] for t, events in sorted(cache.items())}
    tmp = CACHE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(CACHE_PATH)


def refresh_for_tickers(tickers: list[str]) -> dict[str, list[tuple[str, float]]]:
    """Fetch splits for each ticker and write to cache. Returns merged result."""
    cache = load_cache()
    for t in tickers:
        events = fetch_splits(t)
        cache[t] = events
        log.info("splits %s: %d event(s)", t, len(events))
    save_cache(cache)
    return cache


def cumulative_factor(splits: list[tuple[str, float]], date_str: str) -> float:
    """Cumulative split divisor applied to bars dated `date_str`.

    Convention: a split on `D` adjusts all bars dated **strictly before** `D`.
    Bars on or after `D` are already on the post-split basis.

    Examples
    --------
    splits = [("2025-08-26", 2.0)]
    cumulative_factor(splits, "2025-08-25") -> 2.0   # divide pre-split price
    cumulative_factor(splits, "2025-08-26") -> 1.0   # split day onwards: no adjust
    cumulative_factor(splits, "2026-01-01") -> 1.0
    """
    if not splits:
        return 1.0
    factor = 1.0
    for d, ratio in splits:
        if date_str < d:
            factor *= ratio
    return factor


def adjust_bars(
    bars_by_date: dict[str, list[dict]],
    splits: list[tuple[str, float]],
) -> dict[str, list[dict]]:
    """Return a new bar-dict with OHLC divided by the cumulative split factor.

    Volume is *multiplied* by the same factor so total notional is preserved
    (post-split shares were created from pre-split shares 1:N).

    Input bars are not mutated.
    """
    if not splits:
        return bars_by_date
    out: dict[str, list[dict]] = {}
    for d, bars in bars_by_date.items():
        f = cumulative_factor(splits, d)
        if f == 1.0:
            out[d] = bars
            continue
        adjusted: list[dict] = []
        for b in bars:
            nb = dict(b)
            for px_field in ("open", "high", "low", "close"):
                v = nb.get(px_field)
                if v is not None:
                    nb[px_field] = v / f
            vol = nb.get("volume")
            if vol is not None:
                nb["volume"] = vol * f
            adjusted.append(nb)
        out[d] = adjusted
    return out


# ---- Empirical adjustment (preferred) ---------------------------------------

def empirical_factor_table(
    bars_by_date: dict[str, list[dict]],
    daily_ohlc: list[dict],
    *,
    tolerance: float = 0.02,
) -> dict[str, float]:
    """Derive per-date adjustment factor from observed price disagreement.

    For each date D where both the 1m feed (raw) and the daily file (adjusted)
    have a close, compute ``factor(D) = daily_close(D) / raw_1m_last_close(D)``.
    Both prices are quoted at market close, so the only source of disagreement
    is the cumulative corp-action adjustment baked into the daily series.

    Robustness rules:
    - Skip days where either feed has 0/None.
    - Cluster factors that agree within `tolerance` and emit them; if a day's
      factor is an outlier (e.g. trading-halt artifacts) we still emit it
      verbatim — the factor table is per-date so a wrong factor on one day
      only damages that one day.

    Returns ``{date_str: factor}`` covering every date present in `bars_by_date`
    that has a matching daily row. Missing dates default to 1.0 at lookup.
    """
    daily_close: dict[str, float] = {}
    for row in daily_ohlc:
        d = row.get("date")
        c = row.get("close")
        if d and c:
            try:
                daily_close[d] = float(c)
            except (TypeError, ValueError):
                continue

    table: dict[str, float] = {}
    for d, bars in bars_by_date.items():
        if d not in daily_close:
            continue
        if not bars:
            continue
        last_bar = bars[-1]
        raw_close = last_bar.get("close")
        if raw_close is None or raw_close <= 0:
            continue
        adj = daily_close[d]
        if adj <= 0:
            continue
        table[d] = adj / raw_close
    return table


def adjust_bars_empirical(
    bars_by_date: dict[str, list[dict]],
    factor_table: dict[str, float],
) -> dict[str, list[dict]]:
    """Apply per-date factor from `factor_table` to all OHLC fields."""
    if not factor_table:
        return bars_by_date
    out: dict[str, list[dict]] = {}
    for d, bars in bars_by_date.items():
        f = factor_table.get(d, 1.0)
        if f == 1.0 or abs(f - 1.0) < 1e-6:
            out[d] = bars
            continue
        adjusted: list[dict] = []
        for b in bars:
            nb = dict(b)
            for px_field in ("open", "high", "low", "close"):
                v = nb.get(px_field)
                if v is not None:
                    nb[px_field] = v * f
            vol = nb.get("volume")
            if vol is not None and f > 0:
                nb["volume"] = vol / f
            adjusted.append(nb)
        out[d] = adjusted
    return out
