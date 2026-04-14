"""
Anka Research Pipeline — OI Scanner
Fetches options open interest data for all spread stocks, computes PCR, detects anomalies.

Key functions:
  compute_pcr(put_oi, call_oi)           → float
  classify_pcr(pcr)                       → str  (BULLISH/MILD_BULL/NEUTRAL/MILD_BEAR/BEARISH)
  detect_oi_anomaly(oi_change, avg)       → bool
  scan_oi()                               → dict  (full scan, live Kite)

Anomaly log:  data/oi_anomalies.json  (appended each run)
Positioning:  data/positioning.json   (overwritten each run)
"""

from __future__ import annotations

import csv
import json
import logging
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

# Ensure pipeline/ is importable when run as a script
_PIPELINE = Path(__file__).parent
if str(_PIPELINE) not in sys.path:
    sys.path.insert(0, str(_PIPELINE))

from dotenv import load_dotenv
load_dotenv(_PIPELINE / ".env")

log = logging.getLogger("anka.oi_scanner")

IST = timezone(timedelta(hours=5, minutes=30))

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_DATA_DIR        = _PIPELINE / "data"
_NFO_CACHE       = _PIPELINE / "data" / "kite_cache" / "instruments_nfo.csv"
_POSITIONING_FILE = _DATA_DIR / "positioning.json"
_ANOMALY_LOG      = _DATA_DIR / "oi_anomalies.json"

# ---------------------------------------------------------------------------
# Pure functions (tested in isolation — no external dependencies)
# ---------------------------------------------------------------------------

def compute_pcr(put_oi: int, call_oi: int) -> float:
    """Compute put-call ratio.

    Returns put_oi / call_oi. Returns 0 if call_oi is 0.
    """
    if call_oi == 0:
        return 0
    return put_oi / call_oi


def classify_pcr(pcr: float) -> str:
    """Classify a PCR value into a market sentiment bucket.

    Thresholds (options market convention: high PCR = bullish because put
    writers are bearish = contrarian bullish indicator):
      > 1.3  → BULLISH
      > 1.0  → MILD_BULL
      > 0.7  → NEUTRAL
      > 0.5  → MILD_BEAR
      else   → BEARISH
    """
    if pcr > 1.3:
        return "BULLISH"
    if pcr > 1.0:
        return "MILD_BULL"
    if pcr > 0.7:
        return "NEUTRAL"
    if pcr > 0.5:
        return "MILD_BEAR"
    return "BEARISH"


def detect_oi_anomaly(oi_change: float, avg_daily_change: float) -> bool:
    """Detect if an OI change is anomalous (> 2x average absolute daily change).

    Args:
        oi_change:        Current OI change (can be negative for unwinding).
        avg_daily_change: Average absolute daily OI change (baseline).

    Returns True only when avg_daily_change > 0 AND abs(oi_change) > 2 * avg_daily_change.
    """
    if avg_daily_change <= 0:
        return False
    return abs(oi_change) > 2 * avg_daily_change


# ---------------------------------------------------------------------------
# NFO instrument cache helpers
# ---------------------------------------------------------------------------

def _load_nfo_instruments() -> list[dict]:
    """Load NFO options instruments from cached CSV.

    Returns list of row dicts. Columns include: instrument_token, tradingsymbol,
    name, expiry, strike, instrument_type (CE/PE), lot_size, segment.
    """
    if not _NFO_CACHE.exists():
        log.warning("NFO instrument cache not found: %s", _NFO_CACHE)
        return []
    rows = []
    with _NFO_CACHE.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    log.debug("Loaded %d NFO instruments", len(rows))
    return rows


def _get_spread_symbols() -> list[str]:
    """Extract all unique stock symbols from INDIA_SPREAD_PAIRS config."""
    from config import INDIA_SPREAD_PAIRS
    symbols: set[str] = set()
    for pair in INDIA_SPREAD_PAIRS:
        symbols.update(pair.get("long", []))
        symbols.update(pair.get("short", []))
    return sorted(symbols)


def _find_atm_options(
    symbol: str,
    ltp: float,
    nfo_rows: list[dict],
    strike_pct: float = 5.0,
) -> list[dict]:
    """Find CE and PE options for a stock near its ATM strike.

    Selects the nearest active expiry, finds the ATM strike (closest to LTP),
    then returns all CE/PE rows within ±strike_pct% of the ATM strike.

    Args:
        symbol:     Stock ticker (e.g. "HAL").
        ltp:        Last traded price.
        nfo_rows:   Full NFO instrument list.
        strike_pct: Include strikes within this % of ATM (default 5%).

    Returns list of matching option rows (each a dict from the CSV).
    """
    today = datetime.now(IST).date()

    # Filter to options (CE/PE) for this stock name
    # NFO CSV "name" field matches the underlying (e.g. "HAL")
    candidate_rows = [
        r for r in nfo_rows
        if r.get("name", "").upper() == symbol.upper()
        and r.get("instrument_type", "") in ("CE", "PE")
        and r.get("expiry", "") >= str(today)  # active expiry only
    ]

    if not candidate_rows:
        log.debug("No NFO options found for %s", symbol)
        return []

    # Find nearest expiry
    expiries = sorted({r["expiry"] for r in candidate_rows})
    nearest_expiry = expiries[0]

    expiry_rows = [r for r in candidate_rows if r["expiry"] == nearest_expiry]

    # Find ATM strike
    try:
        strikes = sorted({float(r["strike"]) for r in expiry_rows})
    except (ValueError, KeyError):
        return []
    if not strikes:
        return []
    atm_strike = min(strikes, key=lambda s: abs(s - ltp))

    # Select strikes within ±strike_pct% of ATM
    pct = strike_pct / 100.0
    lower = atm_strike * (1 - pct)
    upper = atm_strike * (1 + pct)

    nearby = [
        r for r in expiry_rows
        if lower <= float(r["strike"]) <= upper
    ]
    return nearby


# ---------------------------------------------------------------------------
# Main scan function
# ---------------------------------------------------------------------------

def scan_oi() -> dict:
    """Full OI scan for all spread stocks.

    Workflow:
      1. Get symbols from INDIA_SPREAD_PAIRS
      2. Fetch live LTP from Kite
      3. Load NFO options cache
      4. For each stock: find ATM options, batch-query Kite for OI
      5. Compute PCR, classify, detect anomalies vs previous scan
      6. Save positioning.json, append anomalies to oi_anomalies.json

    Returns: dict keyed by symbol, with OI summary and signals.
    """
    from kite_client import get_kite, fetch_ltp

    symbols = _get_spread_symbols()
    log.info("OI scan started for %d symbols: %s", len(symbols), symbols)

    # 1. Fetch live prices
    ltp_map = fetch_ltp(symbols)
    log.info("LTP fetched: %d/%d symbols", len(ltp_map), len(symbols))

    # 2. Load NFO options
    nfo_rows = _load_nfo_instruments()
    if not nfo_rows:
        log.warning("NFO cache empty — cannot scan OI")
        return {}

    # 3. Load previous positioning for anomaly detection
    prev_positioning: dict = {}
    if _POSITIONING_FILE.exists():
        try:
            prev_positioning = json.loads(_POSITIONING_FILE.read_text(encoding="utf-8"))
        except Exception as exc:
            log.warning("Could not load previous positioning: %s", exc)

    kite = get_kite()

    # 4. Build batch instrument key list for all stocks
    # Map: "NFO:HAL26APR540CE" → (symbol, strike, instrument_type)
    instrument_meta: dict[str, dict] = {}
    stock_option_rows: dict[str, list[dict]] = {}

    for sym in symbols:
        ltp = ltp_map.get(sym)
        if ltp is None:
            log.warning("No LTP for %s — skipping OI scan", sym)
            continue
        options = _find_atm_options(sym, ltp, nfo_rows)
        if not options:
            log.debug("No ATM options found for %s (LTP=%.2f)", sym, ltp)
            continue
        stock_option_rows[sym] = options
        for row in options:
            ts = row.get("tradingsymbol", "")
            if ts:
                key = f"NFO:{ts}"
                instrument_meta[key] = {
                    "symbol": sym,
                    "strike": float(row.get("strike", 0)),
                    "itype": row.get("instrument_type", ""),
                }

    if not instrument_meta:
        log.warning("No NFO option instruments resolved — OI scan empty")
        return {}

    # 5. Batch-query Kite OI (up to ~500 per call)
    all_keys = list(instrument_meta.keys())
    oi_data: dict[str, int] = {}

    BATCH = 450
    for start in range(0, len(all_keys), BATCH):
        batch = all_keys[start : start + BATCH]
        try:
            raw = kite.quote(batch)
            for key, val in raw.items():
                oi_data[key] = int(val.get("oi", 0))
            log.debug("Kite quote batch (%d keys): OK", len(batch))
        except Exception as exc:
            log.warning("Kite quote batch failed: %s", exc)

    # 6. Aggregate OI per stock and compute PCR
    timestamp = datetime.now(IST).strftime("%Y-%m-%dT%H:%M:%S%z")
    results: dict[str, dict] = {}
    anomalies: list[dict] = []

    for sym, options in stock_option_rows.items():
        call_oi = 0
        put_oi = 0

        for row in options:
            ts = row.get("tradingsymbol", "")
            key = f"NFO:{ts}"
            oi = oi_data.get(key, 0)
            if row.get("instrument_type") == "CE":
                call_oi += oi
            elif row.get("instrument_type") == "PE":
                put_oi += oi

        total_oi = call_oi + put_oi
        pcr = compute_pcr(put_oi, call_oi)
        sentiment = classify_pcr(pcr)

        # Anomaly detection vs previous scan
        prev = prev_positioning.get(sym, {})
        prev_total = prev.get("total_oi", 0)
        oi_change = total_oi - prev_total

        # Average daily change: 10% of previous total as baseline
        avg_daily_change = prev_total * 0.10 if prev_total > 0 else 0
        oi_anomaly = detect_oi_anomaly(oi_change, avg_daily_change)

        # PCR flip detection
        prev_pcr = prev.get("pcr", None)
        pcr_flip = False
        if prev_pcr is not None:
            was_bearish = prev_pcr < 0.7
            was_bullish = prev_pcr > 1.2
            now_bullish = pcr > 1.2
            now_bearish = pcr < 0.7
            if (was_bearish and now_bullish) or (was_bullish and now_bearish):
                pcr_flip = True

        entry: dict = {
            "symbol": sym,
            "timestamp": timestamp,
            "ltp": ltp_map.get(sym, 0),
            "call_oi": call_oi,
            "put_oi": put_oi,
            "total_oi": total_oi,
            "pcr": round(pcr, 4),
            "sentiment": sentiment,
            "oi_change": oi_change,
            "prev_total_oi": prev_total,
            "oi_anomaly": oi_anomaly,
            "pcr_flip": pcr_flip,
        }
        results[sym] = entry

        if oi_anomaly or pcr_flip:
            flag = "OI_SPIKE" if oi_anomaly else "PCR_FLIP"
            if oi_anomaly and pcr_flip:
                flag = "OI_SPIKE+PCR_FLIP"
            anomaly_rec = {**entry, "anomaly_type": flag}
            anomalies.append(anomaly_rec)
            log.warning("ANOMALY %s — %s: PCR=%.2f (%s), OI change=%+d", flag, sym, pcr, sentiment, oi_change)

    # 7. Persist positioning
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    _POSITIONING_FILE.write_text(
        json.dumps(results, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    log.info("Positioning saved: %s", _POSITIONING_FILE)

    # 8. Append anomalies to log
    if anomalies:
        existing: list = []
        if _ANOMALY_LOG.exists():
            try:
                existing = json.loads(_ANOMALY_LOG.read_text(encoding="utf-8"))
            except Exception:
                existing = []
        existing.extend(anomalies)
        _ANOMALY_LOG.write_text(
            json.dumps(existing, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        log.info("Anomalies appended: %d new → %d total in log", len(anomalies), len(existing))

    return results


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )
    print("=== OI Scanner ===")
    results = scan_oi()
    if not results:
        print("No results returned (no live Kite or empty NFO cache).")
        sys.exit(0)

    print(f"\n{'Symbol':<15} {'LTP':>8} {'PCR':>6} {'Sentiment':<12} {'Put OI':>12} {'Call OI':>12} {'OI Chg':>10} {'Anomaly'}")
    print("-" * 95)
    for sym, row in sorted(results.items()):
        flag = ""
        if row["oi_anomaly"]:
            flag += " [OI_SPIKE]"
        if row["pcr_flip"]:
            flag += " [PCR_FLIP]"
        print(
            f"{sym:<15} {row['ltp']:>8.2f} {row['pcr']:>6.3f} {row['sentiment']:<12} "
            f"{row['put_oi']:>12,} {row['call_oi']:>12,} {row['oi_change']:>+10,}{flag}"
        )
    print(f"\nTotal: {len(results)} stocks scanned")
    anomalies_count = sum(1 for r in results.values() if r["oi_anomaly"] or r["pcr_flip"])
    if anomalies_count:
        print(f"Anomalies detected: {anomalies_count}")
    print("\nOI Scanner: OK")
