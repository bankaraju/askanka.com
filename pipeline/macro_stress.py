"""
Anka Research Pipeline — Macro Sentiment Index (MSI)
Scores India's macro stress daily on a 0-100 index.

MSI Inputs and Weights:
  FII net flow (₹ cr, 3-day rolling)  — 30%  (negative outflow = stress)
  India VIX vs 90-day average          — 25%  (VIX > avg = stress)
  USD/INR 5-day change %               — 20%  (INR weakening = stress)
  Nifty 50 30-day return %             — 15%  (declining = stress)
  Brent/MCX crude 5-day change %       — 10%  (rising = stress)

Regime thresholds:
  MSI >= 65  →  MACRO_STRESS   🔴
  MSI 35-64  →  MACRO_NEUTRAL  🟡
  MSI < 35   →  MACRO_EASY     🟢
"""

import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

_lib = str(Path(__file__).parent / "lib")
if _lib not in sys.path:
    sys.path.insert(0, _lib)

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

log = logging.getLogger("anka.macro_stress")

IST = timezone(timedelta(hours=5, minutes=30))
DATA_DIR = Path(__file__).parent / "data"
MSI_HISTORY_FILE = DATA_DIR / "msi_history.json"
MSI_BACKTEST_FILE = DATA_DIR / "msi_spread_backtest.json"

REGIME_STRESS   = "MACRO_STRESS"
REGIME_NEUTRAL  = "MACRO_NEUTRAL"
REGIME_EASY     = "MACRO_EASY"

STRESS_THRESHOLD = 65
EASY_THRESHOLD   = 35


# ---------------------------------------------------------------------------
# Data fetchers
# ---------------------------------------------------------------------------

def _fetch_institutional_flow() -> dict:
    """Fetch FII + DII net flows from NSE API (₹ crore).

    Returns dict:
        fii_net: float (3-day avg, negative = net sellers)
        dii_net: float (3-day avg, positive = net buyers typically)
        combined: float (fii_net + dii_net)
    Returns empty dict on failure.
    """
    url = "https://www.nseindia.com/api/fiidiiTradeReact"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "application/json",
        "Referer": "https://www.nseindia.com",
    }
    try:
        session = requests.Session()
        session.headers.update(headers)
        session.get("https://www.nseindia.com", timeout=10)
        resp = session.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        fii_flows = []
        dii_flows = []
        for row in data[:3]:
            # FII net
            fii_val = row.get("fiiNetDii") or row.get("fii_net") or row.get("netVal")
            if fii_val is not None:
                try:
                    fii_flows.append(float(str(fii_val).replace(",", "")))
                except ValueError:
                    pass
            # DII net
            dii_val = row.get("diiNetDii") or row.get("dii_net")
            if dii_val is not None:
                try:
                    dii_flows.append(float(str(dii_val).replace(",", "")))
                except ValueError:
                    pass

        fii_avg = sum(fii_flows) / len(fii_flows) if fii_flows else None
        dii_avg = sum(dii_flows) / len(dii_flows) if dii_flows else None

        if fii_avg is None:
            return {}

        combined = (fii_avg or 0) + (dii_avg or 0)
        return {
            "fii_net": round(fii_avg, 2),
            "dii_net": round(dii_avg, 2) if dii_avg is not None else 0.0,
            "combined": round(combined, 2),
        }
    except Exception as exc:
        log.warning("Institutional flow fetch failed: %s", exc)
        return {}


def _fetch_india_vix() -> Optional[float]:
    """Fetch India VIX as 3-day average of closing values from Kite Connect.
    Smooths out single-day expiry spikes.
    Fallback: single LTP if historical data unavailable.
    """
    try:
        from kite_client import fetch_historical
        candles = fetch_historical("INDIA VIX", interval="day", days=7)
        if len(candles) >= 3:
            last_3 = [c["close"] for c in candles[-3:] if c.get("close")]
            if last_3:
                return sum(last_3) / len(last_3)
    except Exception as exc:
        log.debug("VIX historical failed, falling back to LTP: %s", exc)

    # Fallback: single point LTP
    try:
        from kite_client import fetch_ltp
        prices = fetch_ltp(["INDIA VIX"])
        return prices.get("INDIA VIX")
    except Exception as exc:
        log.warning("India VIX fetch failed entirely: %s", exc)
        return None


def _fetch_india_vix_90d_avg() -> Optional[float]:
    """Fetch 90-day average of India VIX from Kite historical candles."""
    try:
        from kite_client import fetch_historical
        candles = fetch_historical("INDIA VIX", interval="day", days=100)
        if len(candles) >= 20:
            closes = [c["close"] for c in candles[-90:]]
            return sum(closes) / len(closes)
        return None
    except Exception as exc:
        log.warning("India VIX history fetch failed: %s", exc)
        return None


def _fetch_usdinr_change_5d() -> Optional[float]:
    """Fetch USD/INR 5-day percentage change from EODHD."""
    try:
        from eodhd_client import fetch_eod_series
        rows = fetch_eod_series("USDINR.FOREX", days=10)
        if len(rows) >= 6:
            old = rows[-6]["close"]
            new = rows[-1]["close"]
            if old and old > 0:
                return (new / old - 1) * 100
        return None
    except Exception as exc:
        log.warning("USD/INR change fetch failed: %s", exc)
        return None


def _fetch_nifty_30d_return() -> Optional[float]:
    """Fetch Nifty 50 30-day return % from Kite historical candles."""
    try:
        from kite_client import fetch_historical
        candles = fetch_historical("NIFTY 50", interval="day", days=35)
        if len(candles) >= 20:
            old = candles[-21]["close"]
            new = candles[-1]["close"]
            if old and old > 0:
                return (new / old - 1) * 100
        return None
    except Exception as exc:
        log.warning("Nifty 30d return fetch failed: %s", exc)
        return None


def _fetch_crude_change_5d() -> Optional[float]:
    """Fetch crude oil 5-day change % with 3-day smoothed closes.

    Data cascade:
      1. Kite Connect MCX CrudeOil historical
      2. MCX JSON endpoint scrape
      3. EODHD BZ.COMM
      4. yfinance BZ=F (cache disabled)

    3-day smoothing: compare avg of last 3 closes vs avg of 3 closes from 5 days earlier.
    """
    candles = _fetch_crude_candles(days=12)
    if len(candles) >= 8:
        recent_3 = [c["close"] for c in candles[-3:]]
        older_3 = [c["close"] for c in candles[-8:-5]]
        if recent_3 and older_3:
            avg_recent = sum(recent_3) / len(recent_3)
            avg_older = sum(older_3) / len(older_3)
            if avg_older > 0:
                return (avg_recent / avg_older - 1) * 100
    return None


def _fetch_crude_candles(days: int = 12) -> list[dict]:
    """Fetch crude oil daily candles from cascading sources.

    Returns list of dicts with at least 'close' key, sorted oldest-first.
    """
    # 1. Kite Connect (primary)
    try:
        from kite_client import fetch_historical
        candles = fetch_historical("CRUDEOIL", interval="day", days=days)
        if len(candles) >= 8:
            return candles
    except Exception as exc:
        log.debug("Kite crude failed: %s", exc)

    # 2. MCX JSON scrape
    try:
        mcx_candles = _fetch_mcx_crude_history(days)
        if len(mcx_candles) >= 8:
            return mcx_candles
    except Exception as exc:
        log.debug("MCX crude failed: %s", exc)

    # 3. EODHD BZ.COMM
    try:
        from eodhd_client import fetch_eod_series
        series = fetch_eod_series("BZ.COMM", days=days)
        if len(series) >= 8:
            return series
    except Exception as exc:
        log.debug("EODHD crude failed: %s", exc)

    # 4. yfinance (last resort, cache disabled)
    try:
        import os
        os.environ["YFINANCE_CACHE_DISABLED"] = "1"
        import yfinance as yf
        hist = yf.Ticker("BZ=F").history(period="1mo")
        if not hist.empty and len(hist) >= 8:
            return [{"close": float(row["Close"])} for _, row in hist.iterrows()]
    except Exception as exc:
        log.debug("yfinance crude fallback failed: %s", exc)

    return []


def _fetch_mcx_crude_history(days: int = 12) -> list[dict]:
    """Fetch MCX Crude Oil prices from MCX public API.

    MCX serves JSON from their quote endpoint. We extract closing prices.
    Since MCX only provides current quote (not history), we return single
    data point and rely on daily dump files for history.
    """
    try:
        url = "https://www.mcxindia.com/backpage.aspx/GetQuote"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        payload = {"Ession": "CRUDEOIL"}
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            # MCX returns current quote — supplement with daily dumps
            close_price = None
            if isinstance(data, dict) and "d" in data:
                rows = json.loads(data["d"]) if isinstance(data["d"], str) else data["d"]
                if rows and isinstance(rows, list):
                    close_price = float(rows[0].get("PrevClose") or rows[0].get("LastTradedPrice", 0))

            if close_price and close_price > 0:
                # Read daily dumps to build history
                candles = _read_crude_from_daily_dumps(days)
                if candles:
                    candles.append({"close": close_price})
                    return candles
                return [{"close": close_price}]
    except Exception as exc:
        log.debug("MCX scrape failed: %s", exc)
    return []


def _read_crude_from_daily_dumps(days: int = 12) -> list[dict]:
    """Read crude close prices from saved daily dump files."""
    from datetime import date
    candles = []
    today = date.today()
    for i in range(days + 5, 0, -1):
        d = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        dump_file = DATA_DIR / "daily" / f"{d}.json"
        if dump_file.exists():
            try:
                dump = json.loads(dump_file.read_text(encoding="utf-8"))
                crude_val = dump.get("indices", {}).get("crude") or dump.get("crude_close")
                if crude_val:
                    candles.append({"close": float(crude_val)})
            except Exception:
                pass
    return candles


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------

def _norm_institutional(combined_flow: Optional[float], vix: Optional[float] = None, vix_avg: Optional[float] = None) -> float:
    """Normalise combined institutional flow (FII+DII) to 0-1 stress score.

    Uses percentile-based lookup from last 90 days of MSI history.
    Special case: combined flow in bottom 10th percentile AND VIX > 90d avg → stress = 1.0.
    Fallback: linear scale with hardcoded range if < 10 days of history.
    """
    if combined_flow is None:
        return 0.5  # unknown → neutral

    # Try percentile-based normalisation from history
    try:
        history = _load_msi_history_flows(days=90)
        if len(history) >= 10:
            sorted_flows = sorted(history)
            n = len(sorted_flows)
            # Find percentile of current combined_flow
            rank = sum(1 for f in sorted_flows if f <= combined_flow)
            percentile = rank / n

            # Special case: bottom 10th percentile + high VIX = max stress
            if percentile <= 0.10 and vix is not None and vix_avg is not None and vix > vix_avg:
                return 1.0

            # Map percentile to stress: 0th percentile = 1.0 (max stress), 100th = 0.0
            return max(0.0, min(1.0, 1.0 - percentile))
    except Exception as exc:
        log.debug("Percentile normalisation failed, using linear fallback: %s", exc)

    # Fallback: linear scale (same range as old _norm_fii but on combined flow)
    # -8000 (max stress) to +4000 (benign)
    clamped = max(-8000, min(4000, combined_flow))
    return (4000 - clamped) / 12000


def _load_msi_history_flows(days: int = 90) -> list[float]:
    """Load combined_flow values from last N days of msi_history.json."""
    if not MSI_HISTORY_FILE.exists():
        return []
    try:
        history = json.loads(MSI_HISTORY_FILE.read_text(encoding="utf-8"))
        cutoff = (datetime.now(IST) - timedelta(days=days)).strftime("%Y-%m-%d")
        flows = []
        for entry in history:
            if entry.get("date", "") >= cutoff:
                cf = entry.get("combined_flow")
                if cf is not None:
                    flows.append(float(cf))
        return flows
    except Exception:
        return []


def _norm_vix(vix: Optional[float], vix_avg: Optional[float]) -> float:
    """Normalise VIX vs 90-day avg.
    0 = VIX 50% below avg (very calm), 1 = VIX 100% above avg (extreme fear).
    """
    if vix is None:
        return 0.5
    if vix_avg is None or vix_avg == 0:
        # No history: use absolute level (VIX 12 = benign, 40 = extreme)
        return max(0.0, min(1.0, (vix - 12) / 28))
    ratio = (vix / vix_avg - 1)  # positive = VIX above avg
    # -0.5 (50% below) → 0, +1.0 (100% above) → 1
    return max(0.0, min(1.0, (ratio + 0.5) / 1.5))


def _norm_usdinr(change_5d: Optional[float]) -> float:
    """Normalise USD/INR 5-day change.
    INR weakening (positive change) = stress.
    Scale: -2% (strong INR) → 0, +3% (weak INR) → 1.
    """
    if change_5d is None:
        return 0.5
    return max(0.0, min(1.0, (change_5d + 2) / 5))


def _norm_nifty(return_30d: Optional[float]) -> float:
    """Normalise Nifty 30-day return.
    Declining = stress. Scale: +15% → 0, -15% → 1.
    """
    if return_30d is None:
        return 0.5
    return max(0.0, min(1.0, (-return_30d + 15) / 30))


def _norm_crude(change_5d: Optional[float]) -> float:
    """Normalise crude 5-day change.
    Rising = stress. Scale: -10% → 0, +10% → 1.
    """
    if change_5d is None:
        return 0.5
    return max(0.0, min(1.0, (change_5d + 10) / 20))


# ---------------------------------------------------------------------------
# MSI computation
# ---------------------------------------------------------------------------

def compute_msi(*, cached_fii: dict | None = None) -> dict:
    """Compute today's Macro Sentiment Index.

    Args:
        cached_fii: Optional dict with keys {fii_net, dii_net, combined_flow}.
            If provided, skip the NSE HTTP fetch and use these values. Used by
            the intraday refresh because NSE publishes FII flows EOD only.

    Returns dict:
      msi_score: float 0-100
      regime: MACRO_STRESS | MACRO_NEUTRAL | MACRO_EASY
      components: {input: {raw_value, normalised, weight, contribution}}
      timestamp: ISO string (IST)
    """
    inst      = cached_fii if cached_fii is not None else _fetch_institutional_flow()
    fii_net   = inst.get("fii_net")
    dii_net   = inst.get("dii_net", 0.0)
    combined  = inst.get("combined_flow") if cached_fii is not None else inst.get("combined")
    vix       = _fetch_india_vix()
    vix_avg   = _fetch_india_vix_90d_avg()
    usdinr    = _fetch_usdinr_change_5d()
    nifty_ret = _fetch_nifty_30d_return()
    crude     = _fetch_crude_change_5d()

    components = {
        "inst_flow":   {"raw": combined,  "norm": _norm_institutional(combined, vix, vix_avg), "weight": 0.30},
        "india_vix":   {"raw": vix,       "norm": _norm_vix(vix, vix_avg), "weight": 0.25},
        "usdinr":      {"raw": usdinr,    "norm": _norm_usdinr(usdinr),    "weight": 0.20},
        "nifty_30d":   {"raw": nifty_ret, "norm": _norm_nifty(nifty_ret),  "weight": 0.15},
        "crude_5d":    {"raw": crude,     "norm": _norm_crude(crude),      "weight": 0.10},
    }

    msi_score = sum(
        c["norm"] * c["weight"] for c in components.values()
    ) * 100

    for name, c in components.items():
        c["contribution"] = round(c["norm"] * c["weight"] * 100, 1)
        if c["raw"] is not None:
            c["raw"] = round(c["raw"], 2)
        c["norm"] = round(c["norm"], 3)

    if msi_score >= STRESS_THRESHOLD:
        regime = REGIME_STRESS
    elif msi_score < EASY_THRESHOLD:
        regime = REGIME_EASY
    else:
        regime = REGIME_NEUTRAL

    result = {
        "msi_score":  round(msi_score, 1),
        "regime":     regime,
        "components": components,
        "vix_90d_avg": round(vix_avg, 2) if vix_avg else None,
        "fii_net":    fii_net,
        "dii_net":    dii_net,
        "combined_flow": combined,
        "timestamp":  datetime.now(IST).isoformat(),
    }

    log.info("MSI: %.1f -> %s", msi_score, regime)
    return result


# ---------------------------------------------------------------------------
# History & backtest
# ---------------------------------------------------------------------------

def append_msi_history(msi_result: dict) -> None:
    """Append today's MSI result to msi_history.json."""
    DATA_DIR.mkdir(exist_ok=True)
    history = []
    if MSI_HISTORY_FILE.exists():
        try:
            history = json.loads(MSI_HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass

    today = datetime.now(IST).strftime("%Y-%m-%d")
    # Replace today's entry if already exists
    history = [h for h in history if h.get("date") != today]
    history.append({
        "date":      today,
        "msi_score": msi_result["msi_score"],
        "regime":    msi_result["regime"],
        "combined_flow": msi_result.get("combined_flow"),
    })
    # Keep last 365 days
    history = history[-365:]
    MSI_HISTORY_FILE.write_text(
        json.dumps(history, indent=2), encoding="utf-8"
    )


def get_previous_regime() -> Optional[str]:
    """Return yesterday's MSI regime from history, or None."""
    if not MSI_HISTORY_FILE.exists():
        return None
    try:
        history = json.loads(MSI_HISTORY_FILE.read_text(encoding="utf-8"))
        today = datetime.now(IST).strftime("%Y-%m-%d")
        past = [h for h in history if h.get("date") != today]
        if past:
            return past[-1].get("regime")
    except Exception:
        pass
    return None


def detect_regime_crossing(current_regime: str) -> Optional[str]:
    """Detect if the regime just crossed into MACRO_STRESS.

    Returns 'NEUTRAL_TO_STRESS' if crossing occurred, else None.
    """
    prev = get_previous_regime()
    if prev and prev != REGIME_STRESS and current_regime == REGIME_STRESS:
        log.info("Regime crossing: %s → %s", prev, current_regime)
        return "NEUTRAL_TO_STRESS"
    return None


# ---------------------------------------------------------------------------
# INR weakness and FII outflow triggers
# ---------------------------------------------------------------------------

INR_WEAKNESS_THRESHOLD = 1.5   # USD/INR 5-day change % above this = INR_WEAKNESS signal
FII_OUTFLOW_THRESHOLD  = -5000  # 3-day avg FII flow below this (₹ cr) = fii_outflow signal

# File to track whether we've already fired these triggers today (avoid repeats)
_TRIGGER_STATE_FILE = DATA_DIR / "macro_trigger_state.json"


def _load_trigger_state() -> dict:
    if _TRIGGER_STATE_FILE.exists():
        try:
            return json.loads(_TRIGGER_STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_trigger_state(state: dict) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    _TRIGGER_STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def detect_inr_weakness() -> Optional[str]:
    """Return 'INR_WEAKNESS' if USD/INR 5-day change exceeds threshold and hasn't fired today."""
    today = datetime.now(IST).strftime("%Y-%m-%d")
    state = _load_trigger_state()
    if state.get("inr_weakness_date") == today:
        return None  # already fired today

    change = _fetch_usdinr_change_5d()
    if change is None:
        return None
    log.info("USD/INR 5d change: %.2f%%", change)
    if change >= INR_WEAKNESS_THRESHOLD:
        state["inr_weakness_date"] = today
        state["inr_weakness_change"] = round(change, 2)
        _save_trigger_state(state)
        log.info("INR_WEAKNESS trigger fired: USD/INR +%.2f%% over 5 days", change)
        return "INR_WEAKNESS"
    return None


def detect_fii_outflow() -> Optional[str]:
    """Return 'fii_outflow' if 3-day avg FII flow is below threshold and hasn't fired today."""
    today = datetime.now(IST).strftime("%Y-%m-%d")
    state = _load_trigger_state()
    if state.get("fii_outflow_date") == today:
        return None  # already fired today

    inst = _fetch_institutional_flow()
    fii = inst.get("fii_net")
    if fii is None:
        return None
    fii_avg = fii
    log.info("FII 3-day avg: Rs%.0f cr", fii_avg)
    if fii_avg <= FII_OUTFLOW_THRESHOLD:
        state["fii_outflow_date"] = today
        state["fii_outflow_avg"] = round(fii_avg, 0)
        _save_trigger_state(state)
        log.info("fii_outflow trigger fired: Rs%.0f cr 3-day avg", fii_avg)
        return "fii_outflow"
    return None


def get_inr_change() -> Optional[float]:
    """Return current USD/INR 5-day change % (for card display)."""
    state = _load_trigger_state()
    return state.get("inr_weakness_change")


def get_fii_outflow_avg() -> Optional[float]:
    """Return current FII 3-day average flow (for display in trigger cards)."""
    result = _fetch_institutional_flow()
    return result.get("fii_net")


def compute_spread_backtest() -> dict:
    """Compute average spread return by MSI regime from daily dump files.

    For each spread pair in INDIA_SPREAD_PAIRS:
      - Looks at each day in msi_history.json
      - Computes next-day spread move in the long direction
      - Aggregates by regime

    Returns {spread_name: {MACRO_STRESS: {avg_return, win_rate, n}, ...}}
    """
    from config import INDIA_SPREAD_PAIRS
    DATA_DIR.mkdir(exist_ok=True)

    if not MSI_HISTORY_FILE.exists():
        return {}

    try:
        history = json.loads(MSI_HISTORY_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}

    daily_dir = DATA_DIR / "daily"
    backtest: dict = {}

    for pair in INDIA_SPREAD_PAIRS:
        name = pair["name"]
        backtest[name] = {
            REGIME_STRESS:  {"returns": [], "wins": 0, "n": 0},
            REGIME_NEUTRAL: {"returns": [], "wins": 0, "n": 0},
            REGIME_EASY:    {"returns": [], "wins": 0, "n": 0},
        }

        for i, day in enumerate(history[:-1]):
            regime = day.get("regime")
            next_date = history[i + 1].get("date")
            curr_date = day.get("date")
            if not regime or not next_date:
                continue

            # Load closes for curr_date and next_date from daily dump files
            curr_file = daily_dir / f"{curr_date}.json"
            next_file = daily_dir / f"{next_date}.json"
            if not curr_file.exists() or not next_file.exists():
                continue

            try:
                curr_dump = json.loads(curr_file.read_text(encoding="utf-8"))
                next_dump = json.loads(next_file.read_text(encoding="utf-8"))
            except Exception:
                continue

            all_tickers = pair["long"] + pair["short"]
            curr_prices = {}
            next_prices = {}
            for t in all_tickers:
                c = curr_dump.get("stocks", {}).get(t, {})
                n = next_dump.get("stocks", {}).get(t, {})
                cp = c.get("close") or c.get("adjusted_close")
                np_ = n.get("close") or n.get("adjusted_close")
                if cp and np_:
                    curr_prices[t] = float(cp)
                    next_prices[t] = float(np_)

            if len(curr_prices) < len(all_tickers):
                continue

            long_ret = sum(
                (next_prices[t] / curr_prices[t] - 1) * 100
                for t in pair["long"] if t in curr_prices and t in next_prices
            ) / len(pair["long"])

            short_ret = sum(
                (1 - next_prices[t] / curr_prices[t]) * 100
                for t in pair["short"] if t in curr_prices and t in next_prices
            ) / len(pair["short"])

            spread_ret = long_ret + short_ret
            reg_data = backtest[name][regime]
            reg_data["returns"].append(spread_ret)
            reg_data["n"] += 1
            if spread_ret > 0:
                reg_data["wins"] += 1

    # Summarise
    summary: dict = {}
    for pair_name, reg_data in backtest.items():
        summary[pair_name] = {}
        for regime, data in reg_data.items():
            n = data["n"]
            returns = data["returns"]
            summary[pair_name][regime] = {
                "n":         n,
                "avg_return": round(sum(returns) / n, 2) if n else 0.0,
                "win_rate":  round(data["wins"] / n, 3) if n else 0.0,
            }

    MSI_BACKTEST_FILE.write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    return summary


def get_top_stress_spreads(n: int = 2) -> list[dict]:
    """Return top N spreads by historical STRESS-regime win rate (min 5 data points).

    Used to select spreads for macro signal cards.
    """
    if not MSI_BACKTEST_FILE.exists():
        return []
    try:
        backtest = json.loads(MSI_BACKTEST_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []

    candidates = []
    for spread_name, regimes in backtest.items():
        stress_data = regimes.get(REGIME_STRESS, {})
        if stress_data.get("n", 0) >= 5:
            candidates.append({
                "spread_name": spread_name,
                "win_rate":    stress_data["win_rate"],
                "avg_return":  stress_data["avg_return"],
                "n":           stress_data["n"],
            })

    candidates.sort(key=lambda x: x["win_rate"], reverse=True)
    return candidates[:n]


# ---------------------------------------------------------------------------
# Telegram visual helpers
# ---------------------------------------------------------------------------

def msi_bar(score: float, regime: str) -> str:
    """Generate 10-block MSI visual bar for Telegram.

    Example: MSI: 73/100  🟥🟥🟥🟥🟥🟥🟥🟨⬜⬜  STRESS
    """
    filled = min(10, int(score / 10))
    if regime == REGIME_STRESS:
        filled_block = "🟥"
        caution_block = "🟨"
    elif regime == REGIME_NEUTRAL:
        filled_block = "🟨"
        caution_block = "🟧"
    else:
        filled_block = "🟩"
        caution_block = "🟨"

    # Last filled block is caution, rest are filled_block
    blocks = []
    for i in range(10):
        if i < filled - 1:
            blocks.append(filled_block)
        elif i == filled - 1 and filled > 0:
            blocks.append(caution_block)
        else:
            blocks.append("⬜")

    regime_label = {"MACRO_STRESS": "STRESS", "MACRO_NEUTRAL": "NEUTRAL", "MACRO_EASY": "EASY"}[regime]
    return f"MSI: {score:.0f}/100  {''.join(blocks)}  {regime_label}"


def regime_emoji(regime: str) -> str:
    return {"MACRO_STRESS": "🔴", "MACRO_NEUTRAL": "🟡", "MACRO_EASY": "🟢"}.get(regime, "⚪")


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    result = compute_msi()
    print(f"\n{msi_bar(result['msi_score'], result['regime'])}")
    print(f"\nComponents:")
    for name, c in result["components"].items():
        print(f"  {name:15s}  raw={c['raw']}  norm={c['norm']}  contrib={c['contribution']}")
    print(f"\nRegime: {regime_emoji(result['regime'])} {result['regime']}")
    print(f"Timestamp: {result['timestamp']}")
