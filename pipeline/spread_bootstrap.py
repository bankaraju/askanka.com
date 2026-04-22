"""
Anka Research Pipeline — Spread Bootstrap
Same-day backfill for spreads that appear in eligible_spreads but have
no entry in spread_stats.json.

Public API
----------
tier_from_n(n: int) -> str
    "FULL" if n >= 30, "PROVISIONAL" if 15 <= n < 30, "DROPPED" otherwise.

ensure(name, long_legs, short_legs) -> dict
    Backfills spread_stats.json for the named spread if not already present.
    Returns a result dict with keys: status, name, tier (or reason).

_fetch_daily_data_for_spread(name, long_legs, short_legs, days) -> list
    Fetches regime-tagged daily observations for the spread legs.
    Each element: {date, regime, spread_return, long_avg, short_avg}.
    Exposed at module level so tests can monkeypatch it.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# Ensure pipeline/ root is importable when run directly
_HERE = Path(__file__).parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

_lib = str(_HERE / "lib")
if _lib not in sys.path:
    sys.path.insert(0, _lib)

log = logging.getLogger("anka.spread_bootstrap")

IST = timezone(timedelta(hours=5, minutes=30))

# =============================================================================
# Constants — single source of truth for sample thresholds
# =============================================================================

MIN_SAMPLES_FULL        = 30
MIN_SAMPLES_PROVISIONAL = 15

# Path to the canonical spread stats file (override in tests via monkeypatch)
_STATS_FILE = _HERE / "data" / "spread_stats.json"


# =============================================================================
# Public: tier_from_n
# =============================================================================


def tier_from_n(n_samples: int) -> str:
    """Return the tier label for a regime bucket with n_samples observations.

    FULL        — n >= 30   (statistically robust)
    PROVISIONAL — 15 <= n < 30 (flagged in UI, use with caution)
    DROPPED     — n < 15  (too thin, excluded from spread_stats)
    """
    if n_samples >= MIN_SAMPLES_FULL:
        return "FULL"
    if n_samples >= MIN_SAMPLES_PROVISIONAL:
        return "PROVISIONAL"
    return "DROPPED"


# =============================================================================
# Internal: data fetcher (extracted so tests can monkeypatch it)
# =============================================================================


def _fetch_daily_data_for_spread(
    name: str,
    long_legs: list[str],
    short_legs: list[str],
    days: int = 1825,
) -> list[dict]:
    """Fetch regime-tagged daily observations for a spread.

    Reuses logic from spread_statistics:
      - _fetch_price_series for each leg via EODHD
      - _load_regime_map for MSI history
      - compute_spread_return for daily returns

    Returns a list of dicts: {date, regime, spread_return, long_avg, short_avg}.
    May return an empty list (never raises).
    """
    from spread_statistics import (
        _fetch_price_series,
        _load_regime_map,
        _get_common_dates,
        compute_spread_return,
    )

    all_legs = long_legs + short_legs
    prices: dict[str, dict] = {}
    for sym in all_legs:
        try:
            prices[sym] = _fetch_price_series(sym, days=days)
        except Exception as exc:
            log.warning("Bootstrap: failed to fetch %s for %r: %s", sym, name, exc)
            prices[sym] = {}

    if not any(prices.values()):
        return []

    regime_map = _load_regime_map()
    if not regime_map:
        log.warning("Bootstrap: empty regime map — cannot tag observations for %r", name)
        return []

    all_dates = _get_common_dates(prices)
    if len(all_dates) < 2:
        return []

    daily_data: list[dict] = []
    for i in range(1, len(all_dates)):
        prev_date = all_dates[i - 1]
        curr_date = all_dates[i]
        regime = regime_map.get(curr_date)
        if not regime:
            continue

        long_prev  = {s: prices[s][prev_date] for s in long_legs  if prev_date in prices.get(s, {})}
        long_curr  = {s: prices[s][curr_date] for s in long_legs  if curr_date in prices.get(s, {})}
        short_prev = {s: prices[s][prev_date] for s in short_legs if prev_date in prices.get(s, {})}
        short_curr = {s: prices[s][curr_date] for s in short_legs if curr_date in prices.get(s, {})}

        if not long_prev or not short_prev:
            continue

        spread_ret = compute_spread_return(long_prev, long_curr, short_prev, short_curr)

        def _avg_ret(prev_d: dict, curr_d: dict) -> float:
            rets = []
            for sym, p in prev_d.items():
                if sym in curr_d and p > 0:
                    rets.append((curr_d[sym] - p) / p)
            return sum(rets) / len(rets) if rets else 0.0

        daily_data.append({
            "date":          curr_date,
            "regime":        regime,
            "spread_return": spread_ret,
            "long_avg":      _avg_ret(long_prev, long_curr),
            "short_avg":     _avg_ret(short_prev, short_curr),
        })

    return daily_data


# =============================================================================
# Internal: stats file I/O
# =============================================================================


def _load_stats() -> dict:
    """Load spread_stats.json; return {} on any failure."""
    if not _STATS_FILE.exists():
        return {}
    try:
        return json.loads(_STATS_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("Bootstrap: could not load spread_stats.json: %s", exc)
        return {}


def _save_stats(stats: dict) -> None:
    """Write spread_stats.json atomically."""
    _STATS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _STATS_FILE.write_text(json.dumps(stats, indent=2), encoding="utf-8")


# =============================================================================
# Public: ensure
# =============================================================================


def ensure(
    name: str,
    long_legs: list[str],
    short_legs: list[str],
) -> dict[str, Any]:
    """Ensure spread_stats.json has an entry for *name*.

    If an entry already exists (for any regime) returns immediately with
    status='already_present'.

    Otherwise fetches historical data, computes per-regime stats via
    spread_statistics.compute_regime_stats, filters buckets below
    MIN_SAMPLES_PROVISIONAL, writes the result, and returns status='bootstrapped'.

    On any fetch / compute failure returns status='skipped' with a reason.
    Never raises.

    On-disk schema is unchanged: each regime bucket stores
    {count, mean, std, …} — tier is derived via tier_from_n(count) on read.

    Parameters
    ----------
    name       : Human-readable spread name (key in spread_stats.json)
    long_legs  : List of NSE ticker symbols for the long basket
    short_legs : List of NSE ticker symbols for the short basket

    Returns
    -------
    dict with at minimum keys: status, name
    """
    try:
        stats = _load_stats()

        # Already present? (any regime bucket counts)
        if name in stats and stats[name]:
            # Derive existing tier from max count across regimes
            counts = [
                v.get("count", 0)
                for v in stats[name].values()
                if isinstance(v, dict)
            ]
            existing_tier = tier_from_n(max(counts)) if counts else "DROPPED"
            return {"status": "already_present", "tier": existing_tier, "name": name}

        # Fetch daily observations
        daily_data = _fetch_daily_data_for_spread(name, long_legs, short_legs)

        if not daily_data:
            return {
                "status": "skipped",
                "reason": "no regime-tagged observations returned from fetcher",
                "name": name,
            }

        # Count raw observations per regime (before stats floor) so we can
        # report which regimes were dropped due to insufficient samples.
        raw_counts: dict[str, int] = {}
        for row in daily_data:
            raw_counts[row["regime"]] = raw_counts.get(row["regime"], 0) + 1

        # Compute per-regime stats (compute_regime_stats applies the same floor
        # internally, so buckets below MIN_SAMPLES_PROVISIONAL are excluded).
        from spread_statistics import compute_regime_stats
        regime_stats = compute_regime_stats(daily_data)

        # Filter: drop buckets with count < MIN_SAMPLES_PROVISIONAL
        # compute_regime_stats returns all buckets regardless of count;
        # we apply the floor here so ensure() is the single enforcer of the threshold.
        dropped_buckets: list[str] = []
        kept: dict = {}
        for regime, bucket in regime_stats.items():
            n = bucket.get("count", 0)
            if n < MIN_SAMPLES_PROVISIONAL:
                dropped_buckets.append(regime)
            else:
                kept[regime] = bucket

        # Also flag any regime present in raw data but absent from regime_stats
        # (shouldn't happen but covers edge cases in compute_regime_stats).
        for r in raw_counts:
            if r not in regime_stats and r not in dropped_buckets:
                dropped_buckets.append(r)

        if not kept:
            return {
                "status": "skipped",
                "reason": f"all regime buckets below MIN_SAMPLES_PROVISIONAL ({MIN_SAMPLES_PROVISIONAL})",
                "name": name,
                "dropped_buckets": dropped_buckets,
            }

        # Derive tier from the kept bucket with the highest count
        max_kept_n = max(b.get("count", 0) for b in kept.values())
        tier = tier_from_n(max_kept_n)
        total_kept_n = sum(b.get("count", 0) for b in kept.values())

        # Merge into spread_stats.json (re-load to avoid clobbering concurrent writes)
        stats = _load_stats()
        stats[name] = kept
        _save_stats(stats)

        log.info(
            "Bootstrap: %r — tier=%s, %d kept regimes, %d dropped (%s)",
            name, tier, len(kept), len(dropped_buckets), dropped_buckets,
        )

        return {
            "status": "bootstrapped",
            "tier": tier,
            "name": name,
            "n_samples": total_kept_n,
            "dropped_buckets": dropped_buckets,
        }

    except Exception as exc:
        log.warning("Bootstrap: unexpected error for %r: %s", name, exc, exc_info=True)
        return {"status": "skipped", "reason": str(exc), "name": name}
