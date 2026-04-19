"""
ATM Premium Capture — snapshots real ATM option premiums from Kite alongside
synthetic Black-Scholes prices for all F&O stocks.

Reads the NFO instrument master (downloaded by kite_client), finds the nearest
ATM strike per stock, fetches real CE/PE premiums from Kite, computes synthetic
straddle via the BS pricer + EWMA vol, and writes a timestamped JSON snapshot to
pipeline/data/atm_snapshots/YYYY-MM-DD-HHMM.json.

Run standalone: python -m pipeline.atm_premium_capture
"""

import json
import logging
import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))

_DATA = Path(__file__).resolve().parent / "data"
_NFO_CSV = _DATA / "kite_cache" / "instruments_nfo.csv"
_SNAPSHOT_DIR = _DATA / "atm_snapshots"

# Kite batch limit for quote()
_QUOTE_BATCH = 200

# Default vol when get_stock_vol returns None
_FALLBACK_VOL = 0.30


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def find_nearest_atm(spot: float, strikes: list[float]) -> Optional[float]:
    """Return the strike closest to *spot*. Ties broken by the lower strike.
    Returns None if *strikes* is empty.
    """
    if not strikes:
        return None
    return min(strikes, key=lambda k: (abs(k - spot), k))


def load_nfo_instruments(csv_path: Path = _NFO_CSV) -> dict:
    """Read the NFO instrument CSV in one pass and return a per-stock dict.

    Returns::

        {
            "HAL": {
                "expiry": "2026-04-28",
                "strikes": {
                    4300.0: {
                        "CE": {"token": 1001, "symbol": "HAL26APR4300CE"},
                        "PE": {"token": 1002, "symbol": "HAL26APR4300PE"},
                    },
                    ...
                },
            },
            ...
        }

    Only rows with segment == "NFO-OPT" and instrument_type in {"CE", "PE"} are
    included. For each stock the nearest future expiry (by calendar date) wins.
    """
    raw: dict[str, dict] = {}  # stock_name → {expiry: str, strikes: {...}}

    with open(csv_path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            if row.get("segment") != "NFO-OPT":
                continue
            itype = row.get("instrument_type", "").upper()
            if itype not in ("CE", "PE"):
                continue

            name = row.get("name", "").strip().strip('"')
            expiry_str = row.get("expiry", "").strip()
            strike_str = row.get("strike", "0").strip()
            token_str = row.get("instrument_token", "").strip()
            symbol = row.get("tradingsymbol", "").strip().strip('"')

            if not name or not expiry_str or not token_str:
                continue

            try:
                strike = float(strike_str)
                token = int(token_str)
            except ValueError:
                continue

            # Parse expiry for comparison
            try:
                expiry_date = datetime.strptime(expiry_str, "%Y-%m-%d").date()
            except ValueError:
                continue

            today = datetime.now(IST).date()
            if expiry_date < today:
                continue  # already expired

            if name not in raw:
                raw[name] = {"expiry": expiry_str, "expiry_date": expiry_date, "strikes": {}}

            existing_date = raw[name]["expiry_date"]
            # Keep nearest expiry; if this row's expiry is earlier, replace
            if expiry_date < existing_date:
                # Closer expiry — reset strikes
                raw[name] = {"expiry": expiry_str, "expiry_date": expiry_date, "strikes": {}}
            elif expiry_date > existing_date:
                # Further expiry — skip
                continue

            if strike not in raw[name]["strikes"]:
                raw[name]["strikes"][strike] = {}
            raw[name]["strikes"][strike][itype] = {"token": token, "symbol": symbol}

    # Strip internal expiry_date helper before returning
    result = {}
    for name, data in raw.items():
        result[name] = {
            "expiry": data["expiry"],
            "strikes": data["strikes"],
        }
    return result


def compute_comparison(
    spot: float,
    atm_strike: float,
    real_call: float,
    real_put: float,
    ewma_vol: float,
    days_to_expiry: int,
    vol_scalar: float = 1.0,
) -> dict:
    """Compare real vs synthetic ATM straddle.

    Args:
        spot:            Current spot price.
        atm_strike:      Nearest ATM strike.
        real_call:       Live CE premium from Kite.
        real_put:        Live PE premium from Kite.
        ewma_vol:        Annualised EWMA volatility (e.g. 0.31).
        days_to_expiry:  Calendar days to expiry (minimum 1 used in BS).
        vol_scalar:      Calibration scalar from vol backtest (default 1.0).

    Returns dict with keys:
        real_call, real_put, real_straddle,
        synthetic_call, synthetic_put, synthetic_straddle,
        error_pct (real - synthetic) / synthetic * 100
    """
    from pipeline.options_pricer import bs_call_price, bs_put_price

    T = max(days_to_expiry, 1) / 365.0
    adjusted_vol = ewma_vol * vol_scalar

    synthetic_call = bs_call_price(spot, atm_strike, T, adjusted_vol)
    synthetic_put = bs_put_price(spot, atm_strike, T, adjusted_vol)

    real_straddle = real_call + real_put
    synthetic_straddle = synthetic_call + synthetic_put

    if synthetic_straddle > 0:
        error_pct = (real_straddle - synthetic_straddle) / synthetic_straddle * 100.0
    else:
        error_pct = 0.0

    return {
        "real_call": round(real_call, 4),
        "real_put": round(real_put, 4),
        "real_straddle": round(real_straddle, 4),
        "synthetic_call": round(synthetic_call, 4),
        "synthetic_put": round(synthetic_put, 4),
        "synthetic_straddle": round(synthetic_straddle, 4),
        "error_pct": round(error_pct, 2),
    }


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def run(tickers: Optional[list[str]] = None) -> list[dict]:
    """Snapshot ATM premiums for all F&O stocks (or a subset).

    Steps:
    1. Load NFO instrument master.
    2. Fetch spots via kite.ltp().
    3. Resolve nearest ATM strike per stock.
    4. Batch-fetch CE/PE quotes via kite.quote().
    5. Compute real vs synthetic straddle comparison.
    6. Save to pipeline/data/atm_snapshots/YYYY-MM-DD-HHMM.json.

    Returns list of comparison dicts (one per stock).
    """
    from pipeline.kite_client import get_kite
    from pipeline.vol_engine import get_stock_vol

    try:
        kite = get_kite()
    except Exception as exc:
        log.error("Failed to get Kite client: %s", exc)
        return []

    # Load vol scalar from backtest results if available
    vol_scalar = _load_vol_scalar()

    # Load instrument master
    instruments = load_nfo_instruments(_NFO_CSV)
    if not instruments:
        log.error("No NFO instruments loaded from %s", _NFO_CSV)
        return []

    if tickers:
        instruments = {k: v for k, v in instruments.items() if k in tickers}

    stock_names = list(instruments.keys())
    log.info("Loaded %d F&O stocks from NFO master", len(stock_names))

    # --- Fetch spot prices via kite.ltp() ---
    # kite.ltp() expects "NSE:HAL" style keys
    ltp_keys = [f"NSE:{s}" for s in stock_names]
    spot_map: dict[str, float] = {}

    # Batch in chunks of _QUOTE_BATCH
    for i in range(0, len(ltp_keys), _QUOTE_BATCH):
        batch = ltp_keys[i: i + _QUOTE_BATCH]
        try:
            ltp_resp = kite.ltp(batch)
            for key, data in ltp_resp.items():
                ticker = key.split(":")[-1]
                spot_map[ticker] = float(data.get("last_price", 0.0))
        except Exception as exc:
            log.warning("LTP fetch failed for batch starting %s: %s", batch[0], exc)

    # --- Resolve ATM strikes and collect tokens ---
    atm_data: dict[str, dict] = {}  # stock → {spot, atm_strike, expiry, days_to_expiry,
    #                                             ce_token, pe_token, ce_symbol, pe_symbol}

    today = datetime.now(IST).date()
    token_to_stock: dict[int, tuple[str, str]] = {}  # token → (stock_name, "CE"/"PE")

    for stock, info in instruments.items():
        spot = spot_map.get(stock, 0.0)
        if spot <= 0:
            log.debug("No spot price for %s, skipping", stock)
            continue

        strikes_raw = list(info["strikes"].keys())
        if not strikes_raw:
            continue

        atm_strike = find_nearest_atm(spot, strikes_raw)
        if atm_strike is None:
            continue

        strike_data = info["strikes"][atm_strike]
        ce_info = strike_data.get("CE")
        pe_info = strike_data.get("PE")
        if not ce_info or not pe_info:
            log.debug("Missing CE or PE for %s @ %s", stock, atm_strike)
            continue

        try:
            expiry_date = datetime.strptime(info["expiry"], "%Y-%m-%d").date()
        except ValueError:
            continue
        days_to_expiry = max((expiry_date - today).days, 1)

        atm_data[stock] = {
            "spot": spot,
            "atm_strike": atm_strike,
            "expiry": info["expiry"],
            "days_to_expiry": days_to_expiry,
            "ce_token": ce_info["token"],
            "pe_token": pe_info["token"],
            "ce_symbol": ce_info["symbol"],
            "pe_symbol": pe_info["symbol"],
        }
        token_to_stock[ce_info["token"]] = (stock, "CE")
        token_to_stock[pe_info["token"]] = (stock, "PE")

    if not atm_data:
        log.warning("No ATM data resolved — are spots available?")
        return []

    # --- Batch-fetch real CE/PE premiums via kite.quote() ---
    # kite.quote() accepts "NFO:HAL26APR4300CE" style keys
    quote_keys = []
    for stock, d in atm_data.items():
        quote_keys.append(f"NFO:{d['ce_symbol']}")
        quote_keys.append(f"NFO:{d['pe_symbol']}")

    real_premiums: dict[str, float] = {}  # symbol → last_price

    for i in range(0, len(quote_keys), _QUOTE_BATCH):
        batch = quote_keys[i: i + _QUOTE_BATCH]
        try:
            quote_resp = kite.quote(batch)
            for key, data in quote_resp.items():
                symbol = key.split(":")[-1]
                real_premiums[symbol] = float(data.get("last_price", 0.0))
        except Exception as exc:
            log.warning("Quote fetch failed for batch: %s", exc)

    # --- Compute comparisons ---
    results = []
    snap_ts = datetime.now(IST).strftime("%Y-%m-%dT%H:%M:%S%z")

    for stock, d in atm_data.items():
        real_call = real_premiums.get(d["ce_symbol"], 0.0)
        real_put = real_premiums.get(d["pe_symbol"], 0.0)

        if real_call <= 0 and real_put <= 0:
            log.debug("Zero premiums for %s, skipping comparison", stock)
            continue

        ewma_vol = get_stock_vol(stock) or _FALLBACK_VOL

        comparison = compute_comparison(
            spot=d["spot"],
            atm_strike=d["atm_strike"],
            real_call=real_call,
            real_put=real_put,
            ewma_vol=ewma_vol,
            days_to_expiry=d["days_to_expiry"],
            vol_scalar=vol_scalar,
        )

        results.append({
            "stock": stock,
            "snapshot_ts": snap_ts,
            "spot": d["spot"],
            "atm_strike": d["atm_strike"],
            "expiry": d["expiry"],
            "days_to_expiry": d["days_to_expiry"],
            "ewma_vol": round(ewma_vol, 4),
            "vol_scalar": vol_scalar,
            "ce_symbol": d["ce_symbol"],
            "pe_symbol": d["pe_symbol"],
            **comparison,
        })

    # --- Save snapshot ---
    if results:
        _SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        ts_label = datetime.now(IST).strftime("%Y-%m-%d-%H%M")
        out_path = _SNAPSHOT_DIR / f"{ts_label}.json"
        try:
            out_path.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
            log.info("Saved ATM snapshot: %s (%d stocks)", out_path, len(results))
        except Exception as exc:
            log.error("Failed to write snapshot: %s", exc)

    return results


def _load_vol_scalar() -> float:
    backtest_path = _DATA / "vol_backtest_results.json"
    if not backtest_path.exists():
        return 1.0
    try:
        data = json.loads(backtest_path.read_text(encoding="utf-8"))
        return float(data.get("aggregate", {}).get("vol_scalar", 1.0))
    except Exception:
        return 1.0


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    records = run()
    print(f"Captured {len(records)} ATM snapshots")
    if records:
        sample = records[0]
        print(
            f"  Sample: {sample['stock']} spot={sample['spot']} "
            f"ATM={sample['atm_strike']} real_straddle={sample['real_straddle']} "
            f"synthetic_straddle={sample['synthetic_straddle']} "
            f"error_pct={sample['error_pct']}%"
        )
