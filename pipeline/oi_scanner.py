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
_EOD_ARCHIVE_DIR  = _DATA_DIR / "oi_history_stocks"
_TRUST_SCORES_V2  = _PIPELINE.parent / "data" / "trust_scores_v2.json"

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


def _get_fno_universe() -> list[str]:
    """Full F&O universe — the 215 scorecard stocks in trust_scores_v2.json.

    This is the canonical "all stocks we care about" list. Used by scan_oi()
    to scan positioning across the whole universe, not just spread pairs.
    Falls back to spread symbols if the scorecard file is missing.
    """
    if not _TRUST_SCORES_V2.exists():
        log.warning("trust_scores_v2 not found at %s — falling back to spread symbols only", _TRUST_SCORES_V2)
        return _get_spread_symbols()
    try:
        data = json.loads(_TRUST_SCORES_V2.read_text(encoding="utf-8"))
        symbols = {s.get("symbol") for s in data.get("stocks", []) if s.get("symbol")}
        # Always include spread symbols so we don't regress that coverage
        symbols.update(_get_spread_symbols())
        return sorted(symbols)
    except Exception as exc:
        log.warning("Could not parse trust_scores_v2 (%s) — falling back to spread symbols", exc)
        return _get_spread_symbols()


def _compute_max_pain(options_with_oi: list[dict]) -> float | None:
    """Max pain: strike at which option writers lose the least money on expiry.

    options_with_oi: list of {strike, itype, oi}
    Returns the strike (float) or None if we can't compute.
    """
    if not options_with_oi:
        return None
    strikes = sorted({o["strike"] for o in options_with_oi})
    best_strike = None
    best_pain = None
    for k in strikes:
        pain = 0
        for o in options_with_oi:
            s, it, oi = o["strike"], o["itype"], o["oi"]
            if it == "CE" and k > s:
                pain += (k - s) * oi
            elif it == "PE" and k < s:
                pain += (s - k) * oi
        if best_pain is None or pain < best_pain:
            best_pain = pain
            best_strike = k
    return best_strike


def _top_oi_walls(options_with_oi: list[dict], itype: str, n: int = 3) -> list[dict]:
    """Return the top-N strikes by open interest for CE or PE options."""
    rows = [o for o in options_with_oi if o["itype"] == itype and o["oi"] > 0]
    rows.sort(key=lambda r: r["oi"], reverse=True)
    return [{"strike": r["strike"], "oi": r["oi"]} for r in rows[:n]]


def _compute_pinning(
    options_with_oi: list[dict],
    pin_strike: float | None,
    ltp: float,
    expiry: str | None,
) -> dict:
    """Quantify how strongly the stock is being pinned to the max-pain strike.

    Returns a dict with:
        pin_strike        — the gravitational centre (typically max_pain)
        pin_distance_pct  — (ltp - pin) / ltp * 100 (signed; negative = ltp below pin)
        days_to_expiry    — whole days between today and expiry (None if no expiry)
        pin_strength      — OI within ±1 strike of pin, as a fraction of total OI (0-1)
        pin_label         — human-readable tag: STRONG_PIN, MILD_PIN, FAR, UNRELIABLE
    """
    if pin_strike is None or not options_with_oi:
        return {
            "pin_strike": None,
            "pin_distance_pct": None,
            "days_to_expiry": None,
            "pin_strength": None,
            "pin_label": "UNRELIABLE",
        }

    # Distance as % of LTP (signed). Negative means spot is BELOW the pin.
    pin_distance_pct = round((ltp - pin_strike) / ltp * 100, 2) if ltp else None

    # Days to expiry
    dte = None
    if expiry:
        try:
            exp_date = datetime.strptime(expiry, "%Y-%m-%d").date()
            dte = max(0, (exp_date - datetime.now(IST).date()).days)
        except ValueError:
            dte = None

    # Pin strength: OI within ±1 strike of pin / total OI.
    strikes = sorted({o["strike"] for o in options_with_oi})
    if pin_strike in strikes:
        idx = strikes.index(pin_strike)
        neighbourhood = set(strikes[max(0, idx - 1): idx + 2])
    else:
        # Pin wasn't in the list — fall back to anything within the step distance
        step = (max(strikes) - min(strikes)) / max(1, len(strikes) - 1) if len(strikes) > 1 else 0
        neighbourhood = {s for s in strikes if abs(s - pin_strike) <= step}

    near_oi = sum(o["oi"] for o in options_with_oi if o["strike"] in neighbourhood)
    total_oi = sum(o["oi"] for o in options_with_oi)
    pin_strength = round(near_oi / total_oi, 4) if total_oi else 0

    # Label: combines distance + DTE + strength. Pinning only matters near expiry.
    if pin_distance_pct is None or dte is None:
        label = "UNRELIABLE"
    elif abs(pin_distance_pct) <= 1.5 and dte <= 5 and pin_strength >= 0.25:
        label = "STRONG_PIN"
    elif abs(pin_distance_pct) <= 3.0 and dte <= 10 and pin_strength >= 0.15:
        label = "MILD_PIN"
    else:
        label = "FAR"

    return {
        "pin_strike": pin_strike,
        "pin_distance_pct": pin_distance_pct,
        "days_to_expiry": dte,
        "pin_strength": pin_strength,
        "pin_label": label,
    }


def _find_atm_options(
    symbol: str,
    ltp: float,
    nfo_rows: list[dict],
    strike_pct: float = 5.0,
    expiry_offset: int = 0,
) -> list[dict]:
    """Find CE and PE options for a stock near its ATM strike.

    Selects the Nth future expiry (``expiry_offset``: 0 = nearest, 1 = next-month,
    …), finds the ATM strike (closest to LTP), then returns all CE/PE rows within
    ±strike_pct% of the ATM strike.

    Args:
        symbol:        Stock ticker (e.g. "HAL").
        ltp:           Last traded price.
        nfo_rows:      Full NFO instrument list.
        strike_pct:    Include strikes within this % of ATM (default 5%).
        expiry_offset: Which expiry to pick (0 = near, 1 = next, …).

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

    # Pick the requested expiry by offset (0 = nearest, 1 = next, …)
    expiries = sorted({r["expiry"] for r in candidate_rows})
    if expiry_offset >= len(expiries):
        return []
    target_expiry = expiries[expiry_offset]

    expiry_rows = [r for r in candidate_rows if r["expiry"] == target_expiry]

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

def scan_oi(universe: str = "full") -> dict:
    """OI scan across the stock universe.

    Args:
        universe: "full"   — all 215 F&O stocks from trust_scores_v2.json (default)
                  "spread" — only INDIA_SPREAD_PAIRS symbols (legacy behaviour)

    Workflow:
      1. Resolve symbols from the requested universe
      2. Fetch live LTP from Kite
      3. Load NFO options cache
      4. For each stock: find ATM options, batch-query Kite for OI
      5. Compute PCR, max pain, top walls, classify, detect anomalies
      6. Save positioning.json, append anomalies to oi_anomalies.json

    Returns: dict keyed by symbol, with OI summary and signals.
    """
    from kite_client import get_kite, fetch_ltp

    if universe == "spread":
        symbols = _get_spread_symbols()
    else:
        symbols = _get_fno_universe()
    log.info("OI scan started (%s universe): %d symbols", universe, len(symbols))

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

    # 4. Build batch instrument key list for all stocks — BOTH near and next expiries
    # Keyed by (symbol, expiry_slot) where expiry_slot is "near" or "next"
    instrument_meta: dict[str, dict] = {}
    stock_option_rows: dict[tuple[str, str], list[dict]] = {}

    for sym in symbols:
        ltp = ltp_map.get(sym)
        if ltp is None:
            log.warning("No LTP for %s — skipping OI scan", sym)
            continue
        # Use a ±10% window so we capture the full wall structure, not just ATM.
        for slot, offset in (("near", 0), ("next", 1)):
            options = _find_atm_options(sym, ltp, nfo_rows, strike_pct=10.0, expiry_offset=offset)
            if not options:
                log.debug("No %s-expiry options for %s (LTP=%.2f)", slot, sym, ltp)
                continue
            stock_option_rows[(sym, slot)] = options
            for row in options:
                ts = row.get("tradingsymbol", "")
                if ts:
                    key = f"NFO:{ts}"
                    instrument_meta[key] = {
                        "symbol": sym,
                        "slot": slot,
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

    # 6. Aggregate OI per (stock, expiry-slot) and compute metrics
    timestamp = datetime.now(IST).strftime("%Y-%m-%dT%H:%M:%S%z")
    results: dict[str, dict] = {}
    anomalies: list[dict] = []

    # Collect by symbol first so we can nest near/next under each stock
    per_symbol: dict[str, dict] = {}

    for (sym, slot), options in stock_option_rows.items():
        call_oi = 0
        put_oi = 0
        strike_oi: list[dict] = []

        for row in options:
            ts = row.get("tradingsymbol", "")
            key = f"NFO:{ts}"
            oi = oi_data.get(key, 0)
            itype = row.get("instrument_type", "")
            try:
                strike = float(row.get("strike", 0))
            except (TypeError, ValueError):
                strike = 0.0
            strike_oi.append({"strike": strike, "itype": itype, "oi": oi})
            if itype == "CE":
                call_oi += oi
            elif itype == "PE":
                put_oi += oi

        total_oi = call_oi + put_oi
        pcr = compute_pcr(put_oi, call_oi)
        sentiment = classify_pcr(pcr)
        max_pain = _compute_max_pain(strike_oi)
        call_walls = _top_oi_walls(strike_oi, "CE", n=3)
        put_walls = _top_oi_walls(strike_oi, "PE", n=3)
        expiry = options[0].get("expiry") if options else None
        ltp = ltp_map.get(sym, 0)
        pinning = _compute_pinning(strike_oi, max_pain, ltp, expiry)

        per_symbol.setdefault(sym, {})[slot] = {
            "expiry": expiry,
            "call_oi": call_oi,
            "put_oi": put_oi,
            "total_oi": total_oi,
            "pcr": round(pcr, 4),
            "sentiment": sentiment,
            "max_pain": max_pain,
            "call_walls": call_walls,
            "put_walls": put_walls,
            "pinning": pinning,
        }

    # Build final entries (anomaly logic applies to the NEAR expiry — the one
    # that moves the most intraday).
    for sym, expiries in per_symbol.items():
        near = expiries.get("near") or {}
        nxt  = expiries.get("next") or {}

        ltp = ltp_map.get(sym, 0)
        total_oi_near = near.get("total_oi", 0)
        pcr_near = near.get("pcr", 0)

        # Anomaly detection vs previous scan (near expiry)
        prev = prev_positioning.get(sym, {})
        # Backward-compat: old flat schema or new nested 'near' schema
        prev_total = (prev.get("near") or {}).get("total_oi", prev.get("total_oi", 0))
        oi_change = total_oi_near - prev_total
        avg_daily_change = prev_total * 0.10 if prev_total > 0 else 0
        oi_anomaly = detect_oi_anomaly(oi_change, avg_daily_change)

        prev_pcr = (prev.get("near") or {}).get("pcr", prev.get("pcr", None))
        pcr_flip = False
        if prev_pcr is not None:
            was_bearish = prev_pcr < 0.7
            was_bullish = prev_pcr > 1.2
            now_bullish = pcr_near > 1.2
            now_bearish = pcr_near < 0.7
            if (was_bearish and now_bullish) or (was_bullish and now_bearish):
                pcr_flip = True

        # Rollover signal: if next-expiry OI growing faster than near-expiry OI,
        # traders are rolling positions forward (common in the final week).
        rollover = None
        if nxt and near:
            near_total = near.get("total_oi", 0)
            next_total = nxt.get("total_oi", 0)
            if near_total > 0:
                rollover = round(next_total / near_total, 3)

        entry: dict = {
            "symbol": sym,
            "timestamp": timestamp,
            "ltp": ltp,
            "near": near,
            "next": nxt,
            "rollover_ratio": rollover,
            # Top-level shortcuts to NEAR expiry (back-compat for existing consumers)
            "expiry": near.get("expiry"),
            "call_oi": near.get("call_oi", 0),
            "put_oi": near.get("put_oi", 0),
            "total_oi": total_oi_near,
            "pcr": pcr_near,
            "sentiment": near.get("sentiment"),
            "max_pain": near.get("max_pain"),
            "call_walls": near.get("call_walls", []),
            "put_walls": near.get("put_walls", []),
            "pinning": near.get("pinning"),
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
            log.warning("ANOMALY %s — %s: PCR=%.2f (%s), OI change=%+d", flag, sym, pcr_near, near.get("sentiment"), oi_change)

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


def archive_eod_snapshot() -> Path | None:
    """Copy the current positioning.json to data/oi_history_stocks/YYYY-MM-DD.json.

    Meant to be called from the EOD close-capture task so we keep a permanent
    per-stock OI record for future computations (PCR trend, OI velocity, etc.).
    Returns the archive path, or None if positioning.json is missing.
    """
    if not _POSITIONING_FILE.exists():
        log.warning("positioning.json missing — nothing to archive")
        return None
    _EOD_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now(IST).strftime("%Y-%m-%d")
    archive = _EOD_ARCHIVE_DIR / f"{today}.json"
    try:
        archive.write_text(
            _POSITIONING_FILE.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        log.info("EOD archive written: %s", archive)
        return archive
    except Exception as exc:
        log.warning("Failed to write EOD archive %s: %s", archive, exc)
        return None


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Anka OI Scanner")
    parser.add_argument(
        "--universe", choices=["full", "spread"], default="full",
        help="full = 215 F&O stocks (default). spread = INDIA_SPREAD_PAIRS only.",
    )
    parser.add_argument(
        "--eod", action="store_true",
        help="Archive positioning.json → data/oi_history_stocks/YYYY-MM-DD.json after scan.",
    )
    parser.add_argument(
        "--archive-only", action="store_true",
        help="Skip the Kite scan — just archive the existing positioning.json (use post-close).",
    )
    args = parser.parse_args()

    # Archive-only mode: no scan, just copy the latest positioning snapshot to the EOD folder.
    if args.archive_only:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
            datefmt="%H:%M:%S",
        )
        archive = archive_eod_snapshot()
        if archive:
            print(f"EOD archive written: {archive}")
            sys.exit(0)
        print("Archive failed (no positioning.json)")
        sys.exit(1)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )
    print(f"=== OI Scanner ({args.universe} universe) ===")
    results = scan_oi(universe=args.universe)
    if not results:
        print("No results returned (no live Kite or empty NFO cache).")
        sys.exit(0)

    print(f"\n{'Symbol':<15} {'LTP':>8} {'PCR':>6} {'Sentiment':<12} {'Put OI':>12} {'Call OI':>12} {'MaxPain':>8} {'Pin':<12}")
    print("-" * 105)
    for sym, row in sorted(results.items()):
        flag = ""
        if row["oi_anomaly"]:
            flag += " [OI_SPIKE]"
        if row["pcr_flip"]:
            flag += " [PCR_FLIP]"
        pin = row.get("pinning") or {}
        mp = row.get("max_pain")
        pin_label = pin.get("pin_label", "—")
        print(
            f"{sym:<15} {row['ltp']:>8.2f} {row['pcr']:>6.3f} {row['sentiment']:<12} "
            f"{row['put_oi']:>12,} {row['call_oi']:>12,} "
            f"{mp if mp else '—':>8} {pin_label:<12}{flag}"
        )
    print(f"\nTotal: {len(results)} stocks scanned")
    anomalies_count = sum(1 for r in results.values() if r["oi_anomaly"] or r["pcr_flip"])
    if anomalies_count:
        print(f"Anomalies detected: {anomalies_count}")
    pins = sum(1 for r in results.values() if (r.get("pinning") or {}).get("pin_label") in ("STRONG_PIN", "MILD_PIN"))
    if pins:
        print(f"Pinning candidates: {pins}")

    if args.eod:
        archive = archive_eod_snapshot()
        if archive:
            print(f"EOD archive: {archive}")

    print("\nOI Scanner: OK")
