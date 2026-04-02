"""
Anka Research Pipeline -- Pre-Market Scanner
Asian market cascade scanner that runs at 8:30 AM IST.
Detects overnight moves in Asian indices, defence stocks, commodities,
and FX to generate India pre-market spread signals.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd
import yfinance as yf

from config import (
    ASIA_DEFENCE_STOCKS,
    ASIA_INDIA_CASCADE,
    ASIA_INDICES,
    INDIA_SIGNAL_STOCKS,
    REGIME_RISK_ON,
    REGIME_RISK_OFF,
    REGIME_MIXED,
    REGIME_WEIGHT_POLITICAL,
    REGIME_WEIGHT_OIL,
    REGIME_WEIGHT_ASIAN,
    REGIME_THRESHOLD,
    REGIME_SPREADS,
    EVENT_TAXONOMY,
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logger = logging.getLogger("anka.premarket_scanner")
logger.setLevel(logging.DEBUG)
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter(
        "%(asctime)s | %(name)s | %(levelname)s | %(message)s"
    ))
    logger.addHandler(_handler)

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# yfinance helper
# ---------------------------------------------------------------------------
YF_TIMEOUT = 15  # seconds


def _safe_day_change(ticker_symbol: str) -> dict[str, Optional[float]]:
    """Fetch current price and day-change % for a single ticker.

    Returns {"price": float|None, "change_pct": float|None}.
    """
    try:
        tkr = yf.Ticker(ticker_symbol)
        info = tkr.fast_info
        price = info.get("lastPrice") or info.get("previousClose")
        prev = info.get("previousClose")
        if price and prev and prev != 0:
            change_pct = round(((price - prev) / prev) * 100, 2)
        else:
            change_pct = None
        return {
            "price": round(float(price), 2) if price else None,
            "change_pct": change_pct,
        }
    except Exception as exc:
        logger.warning("Failed to fetch %s: %s", ticker_symbol, exc)
        return {"price": None, "change_pct": None}


# ---------------------------------------------------------------------------
# Core data fetch
# ---------------------------------------------------------------------------

def fetch_asian_session_data() -> dict[str, Any]:
    """Pull live/recent data for Asian markets, commodities, and FX.

    Designed to run at 8:30 AM IST when Asian sessions are active.

    Returns a dict with keys:
        timestamp, indices, defence_stocks, commodities, fx, us_futures
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    logger.info("Fetching Asian session data at %s", timestamp)

    # -- Indices --
    indices: dict[str, dict[str, Optional[float]]] = {}
    for name, meta in ASIA_INDICES.items():
        if name == "S&P Futures":
            continue  # handled separately
        yf_ticker = meta["yf"]
        indices[name] = _safe_day_change(yf_ticker)
        logger.debug("  %s: %s", name, indices[name])

    # -- Defence stocks --
    defence_stocks: dict[str, dict[str, Optional[float]]] = {}
    for ticker, meta in ASIA_DEFENCE_STOCKS.items():
        defence_stocks[ticker] = _safe_day_change(ticker)
        defence_stocks[ticker]["name"] = meta.get("name", "")
        defence_stocks[ticker]["market"] = meta.get("market", "")
        logger.debug("  Defence %s: %s", ticker, defence_stocks[ticker])

    # -- Commodities --
    commodity_tickers = {
        "brent": "BZ=F",
        "gold": "GC=F",
    }
    commodities: dict[str, dict[str, Optional[float]]] = {}
    for label, yf_ticker in commodity_tickers.items():
        commodities[label] = _safe_day_change(yf_ticker)

    # -- FX --
    fx: dict[str, dict[str, Optional[float]]] = {}
    usd_inr = _safe_day_change("INR=X")
    fx["usd_inr"] = {"rate": usd_inr["price"], "change_pct": usd_inr["change_pct"]}

    # -- US futures --
    us_futures: dict[str, dict[str, Optional[float]]] = {}
    sp_future = ASIA_INDICES.get("S&P Futures", {})
    sp_ticker = sp_future.get("yf", "ES=F")
    sp_data = _safe_day_change(sp_ticker)
    us_futures["sp500"] = sp_data

    result = {
        "timestamp": timestamp,
        "indices": indices,
        "defence_stocks": defence_stocks,
        "commodities": commodities,
        "fx": fx,
        "us_futures": us_futures,
    }

    # Persist snapshot
    snapshot_file = DATA_DIR / "premarket_snapshot.json"
    try:
        snapshot_file.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    except Exception as exc:
        logger.warning("Failed to save snapshot: %s", exc)

    logger.info("Asian session data fetched successfully")
    return result


# ---------------------------------------------------------------------------
# Cascade signal detection
# ---------------------------------------------------------------------------

def detect_cascade_signals(
    asian_data: dict[str, Any],
) -> list[dict[str, Any]]:
    """Analyze Asian session data against ASIA_INDIA_CASCADE rules.

    Triggers detected:
    - nikkei_defence_up / kospi_defence_up: avg Asian defence stocks > +1%
    - asian_broad_selloff: Nikkei, KOSPI, STI all negative > -1%
    - oil_above_100: Brent > $100
    - usd_inr_spike: USD/INR moved > +0.5% (INR weakening)
    - asian_energy_up: broad energy-related uptick

    Returns list of triggered cascade signals with India trade implications.
    """
    triggered: list[dict[str, Any]] = []
    indices = asian_data.get("indices", {})
    defence = asian_data.get("defence_stocks", {})
    commodities = asian_data.get("commodities", {})
    fx = asian_data.get("fx", {})

    # -- Helper: safe float extraction --
    def _pct(d: dict, key: str = "change_pct") -> float:
        val = d.get(key)
        return float(val) if val is not None else 0.0

    def _price(d: dict, key: str = "price") -> float:
        val = d.get(key)
        return float(val) if val is not None else 0.0

    # --- Japanese defence stocks ---
    japan_defence_tickers = [t for t, m in ASIA_DEFENCE_STOCKS.items() if m.get("market") == "Japan"]
    japan_defence_changes = [_pct(defence.get(t, {})) for t in japan_defence_tickers]
    avg_japan_defence = sum(japan_defence_changes) / max(len(japan_defence_changes), 1)

    if avg_japan_defence > 1.0:
        cascade = ASIA_INDIA_CASCADE.get("nikkei_defence_up", {})
        triggered.append({
            "trigger": "nikkei_defence_up",
            "detail": f"Avg Japan defence stocks: +{avg_japan_defence:.1f}%",
            "india_long": cascade.get("india_long", []),
            "india_short": cascade.get("india_short", []),
            "strength": round(avg_japan_defence, 2),
        })
        logger.info("CASCADE: nikkei_defence_up (avg +%.1f%%)", avg_japan_defence)

    # --- Korean defence stocks ---
    korea_defence_tickers = [t for t, m in ASIA_DEFENCE_STOCKS.items() if m.get("market") == "Korea"]
    korea_defence_changes = [_pct(defence.get(t, {})) for t in korea_defence_tickers]
    avg_korea_defence = sum(korea_defence_changes) / max(len(korea_defence_changes), 1)

    if avg_korea_defence > 1.0:
        cascade = ASIA_INDIA_CASCADE.get("kospi_defence_up", {})
        triggered.append({
            "trigger": "kospi_defence_up",
            "detail": f"Avg Korea defence stocks: +{avg_korea_defence:.1f}%",
            "india_long": cascade.get("india_long", []),
            "india_short": cascade.get("india_short", []),
            "strength": round(avg_korea_defence, 2),
        })
        logger.info("CASCADE: kospi_defence_up (avg +%.1f%%)", avg_korea_defence)

    # --- Asian broad selloff ---
    nikkei_chg = _pct(indices.get("Nikkei 225", {}))
    kospi_chg = _pct(indices.get("KOSPI", {}))
    sti_chg = _pct(indices.get("STI", {}))

    if nikkei_chg < -1.0 and kospi_chg < -1.0 and sti_chg < -1.0:
        cascade = ASIA_INDIA_CASCADE.get("asian_broad_selloff", {})
        avg_decline = round((nikkei_chg + kospi_chg + sti_chg) / 3, 2)
        triggered.append({
            "trigger": "asian_broad_selloff",
            "detail": f"Nikkei {nikkei_chg:+.1f}%, KOSPI {kospi_chg:+.1f}%, STI {sti_chg:+.1f}%",
            "india_long": cascade.get("india_long", []),
            "india_short": cascade.get("india_short", []),
            "strength": abs(avg_decline),
        })
        logger.info("CASCADE: asian_broad_selloff (avg %.1f%%)", avg_decline)

    # --- Oil above $100 ---
    brent_price = _price(commodities.get("brent", {}))
    brent_chg = _pct(commodities.get("brent", {}))

    if brent_price > 100.0:
        cascade = ASIA_INDIA_CASCADE.get("oil_above_100", {})
        triggered.append({
            "trigger": "oil_above_100",
            "detail": f"Brent at ${brent_price:.2f} ({brent_chg:+.1f}%)",
            "india_long": cascade.get("india_long", []),
            "india_short": cascade.get("india_short", []),
            "strength": brent_price,
        })
        logger.info("CASCADE: oil_above_100 ($%.2f)", brent_price)

    # --- USD/INR spike (INR weakening) ---
    inr_chg = _pct(fx.get("usd_inr", {}))
    if inr_chg > 0.5:
        cascade = ASIA_INDIA_CASCADE.get("usd_inr_spike", {})
        triggered.append({
            "trigger": "usd_inr_spike",
            "detail": f"USD/INR +{inr_chg:.2f}% (INR weakening)",
            "india_long": cascade.get("india_long", []),
            "india_short": cascade.get("india_short", []),
            "strength": round(inr_chg, 2),
        })
        logger.info("CASCADE: usd_inr_spike (+%.2f%%)", inr_chg)

    # --- Asian energy up (broad commodity + energy index signal) ---
    # Trigger if Brent change > +1% AND avg all defence stocks positive
    all_defence_changes = [_pct(defence.get(t, {})) for t in ASIA_DEFENCE_STOCKS]
    avg_all_defence = sum(all_defence_changes) / max(len(all_defence_changes), 1)

    if brent_chg > 1.0 and avg_all_defence > 0:
        cascade = ASIA_INDIA_CASCADE.get("asian_energy_up", {})
        triggered.append({
            "trigger": "asian_energy_up",
            "detail": f"Brent {brent_chg:+.1f}%, avg defence {avg_all_defence:+.1f}%",
            "india_long": cascade.get("india_long", []),
            "india_short": cascade.get("india_short", []),
            "strength": round(brent_chg, 2),
        })
        logger.info("CASCADE: asian_energy_up (Brent +%.1f%%)", brent_chg)

    logger.info("Cascade detection complete: %d signals triggered", len(triggered))
    return triggered


# ---------------------------------------------------------------------------
# Regime detection (V2)
# ---------------------------------------------------------------------------

REGIME_FILE = DATA_DIR / "today_regime.json"


def detect_regime(
    asian_data: dict[str, Any],
    overnight_events: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Classify today as RISK_ON, RISK_OFF, or MIXED.

    Scoring:
      regime_score = 0.4 * political_score + 0.3 * oil_score + 0.3 * asian_score
      score > +0.3  → RISK_ON
      score < -0.3  → RISK_OFF
      else           → MIXED

    Political score: count escalation/de-escalation events in overnight_events
    Oil score: Brent direction (+1 if up, -1 if down)
    Asian score: avg Asian defence stock direction

    Saves result to data/today_regime.json and returns regime dict.
    """
    # -- Political score (from overnight events) --
    political_score = 0.0
    if overnight_events:
        risk_on_cats = {"escalation", "oil_positive", "sanctions", "hormuz", "trump_threat", "defense_spend"}
        risk_off_cats = {"de_escalation", "ceasefire", "diplomacy", "oil_negative"}
        on_count = sum(1 for e in overnight_events if e.get("category") in risk_on_cats)
        off_count = sum(1 for e in overnight_events if e.get("category") in risk_off_cats)
        total = on_count + off_count
        if total > 0:
            political_score = (on_count - off_count) / total  # normalized to [-1, +1]

    # -- Oil score --
    oil_score = 0.0
    commodities = asian_data.get("commodities", {})
    brent = commodities.get("brent", {})
    brent_chg = brent.get("change_pct")
    if brent_chg is not None:
        if brent_chg > 0.5:
            oil_score = 1.0
        elif brent_chg < -0.5:
            oil_score = -1.0
        else:
            oil_score = brent_chg / 0.5  # linear scale within ±0.5%

    # -- Asian score (defence stocks + indices direction) --
    asian_score = 0.0
    defence = asian_data.get("defence_stocks", {})
    if defence:
        changes = [
            float(d.get("change_pct", 0) or 0)
            for d in defence.values()
        ]
        if changes:
            avg_def = sum(changes) / len(changes)
            if avg_def > 1.0:
                asian_score = 1.0
            elif avg_def < -1.0:
                asian_score = -1.0
            else:
                asian_score = avg_def  # linear within ±1%

    # Composite
    regime_score = (
        REGIME_WEIGHT_POLITICAL * political_score
        + REGIME_WEIGHT_OIL * oil_score
        + REGIME_WEIGHT_ASIAN * asian_score
    )

    if regime_score > REGIME_THRESHOLD:
        regime = REGIME_RISK_ON
    elif regime_score < -REGIME_THRESHOLD:
        regime = REGIME_RISK_OFF
    else:
        regime = REGIME_MIXED

    logger.info(
        "Regime: %s (score=%.3f, political=%.2f, oil=%.2f, asian=%.2f)",
        regime, regime_score, political_score, oil_score, asian_score,
    )

    # Check for regime flip
    yesterday_regime = _load_yesterday_regime()
    flip_from = ""
    if yesterday_regime and yesterday_regime != regime and regime != REGIME_MIXED:
        flip_from = yesterday_regime
        logger.info("REGIME FLIP: %s → %s", flip_from, regime)

    result = {
        "regime": regime,
        "regime_score": round(regime_score, 4),
        "components": {
            "political_score": round(political_score, 4),
            "oil_score": round(oil_score, 4),
            "asian_score": round(asian_score, 4),
        },
        "flip_from": flip_from,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    }

    # Persist
    try:
        REGIME_FILE.write_text(json.dumps(result, indent=2), encoding="utf-8")
    except Exception as exc:
        logger.warning("Failed to save regime file: %s", exc)

    return result


def _load_yesterday_regime() -> Optional[str]:
    """Load yesterday's regime classification."""
    if not REGIME_FILE.exists():
        return None
    try:
        data = json.loads(REGIME_FILE.read_text(encoding="utf-8"))
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if data.get("date") != today:
            return data.get("regime")
        return None  # same day, no comparison
    except Exception:
        return None


def load_current_regime() -> str:
    """Load the current regime from today_regime.json."""
    if not REGIME_FILE.exists():
        return REGIME_MIXED
    try:
        data = json.loads(REGIME_FILE.read_text(encoding="utf-8"))
        return data.get("regime", REGIME_MIXED)
    except Exception:
        return REGIME_MIXED


# ---------------------------------------------------------------------------
# Pre-market briefing formatter
# ---------------------------------------------------------------------------

def generate_premarket_briefing(
    asian_data: dict[str, Any],
    cascade_signals: list[dict[str, Any]],
    overnight_events: Optional[list[dict[str, Any]]] = None,
    regime_info: Optional[dict[str, Any]] = None,
    correlation_briefing: Optional[str] = None,
) -> str:
    """Generate the morning briefing text for Telegram.

    V2: Now includes regime classification and correlation section.
    Returns a formatted string ready for sending.
    """
    indices = asian_data.get("indices", {})
    defence = asian_data.get("defence_stocks", {})
    commodities = asian_data.get("commodities", {})
    fx = asian_data.get("fx", {})
    us_futures = asian_data.get("us_futures", {})

    def _fmt_pct(val: Optional[float]) -> str:
        if val is None:
            return "N/A"
        return f"{val:+.1f}%"

    def _fmt_price(val: Optional[float]) -> str:
        if val is None:
            return "N/A"
        return f"${val:,.2f}"

    today = datetime.now().strftime("%d %b %Y")

    lines: list[str] = []
    lines.append(f"\u2600 ANKA PRE-MARKET BRIEFING \u2014 {today}")
    lines.append("\u2501" * 36)

    # Regime classification (V2)
    if regime_info:
        regime = regime_info.get("regime", "MIXED")
        regime_emoji = {
            "RISK_ON": "\U0001f534", "RISK_OFF": "\U0001f7e2", "MIXED": "\U0001f7e1"
        }
        r_emoji = regime_emoji.get(regime, "\U0001f7e1")
        score = regime_info.get("regime_score", 0)
        lines.append(f"{r_emoji} REGIME: {regime.replace('_', ' ')} (score: {score:+.2f})")

        flip_from = regime_info.get("flip_from", "")
        if flip_from:
            lines.append(f"\u26a0\ufe0f REGIME FLIP: {flip_from.replace('_', ' ')} \u2192 {regime.replace('_', ' ')}")

        # Show regime-appropriate spreads
        regime_spreads = REGIME_SPREADS.get(regime, {})
        if regime_spreads.get("primary"):
            lines.append(f"  Primary spreads: {', '.join(regime_spreads['primary'])}")
        if regime_spreads.get("secondary"):
            lines.append(f"  Secondary: {', '.join(regime_spreads['secondary'])}")

        lines.append("")

    # Asian session
    lines.append("\U0001F30F Asian Session (Live):")
    nikkei = indices.get("Nikkei 225", {})
    kospi = indices.get("KOSPI", {})
    sti = indices.get("STI", {})
    lines.append(
        f"  Nikkei: {_fmt_pct(nikkei.get('change_pct'))} | "
        f"KOSPI: {_fmt_pct(kospi.get('change_pct'))} | "
        f"STI: {_fmt_pct(sti.get('change_pct'))}"
    )

    # Defence highlights
    defence_highlights = []
    for ticker, data in defence.items():
        name = data.get("name", ticker)
        chg = data.get("change_pct")
        if chg is not None:
            defence_highlights.append(f"{name}: {_fmt_pct(chg)}")
    if defence_highlights:
        lines.append(f"  Defence: {' | '.join(defence_highlights)}")

    lines.append("")

    # Overnight
    brent = commodities.get("brent", {})
    gold = commodities.get("gold", {})
    sp500 = us_futures.get("sp500", {})
    usd_inr = fx.get("usd_inr", {})

    lines.append("\u26FD Overnight:")
    lines.append(
        f"  Brent: {_fmt_price(brent.get('price'))} ({_fmt_pct(brent.get('change_pct'))}) | "
        f"Gold: {_fmt_price(gold.get('price'))} ({_fmt_pct(gold.get('change_pct'))})"
    )

    if overnight_events:
        for evt in overnight_events[:3]:
            headline = evt.get("headline", "")[:80]
            category = evt.get("category", "")
            lines.append(f"  \u26A0 [{category}] {headline}")

    lines.append(
        f"  USD/INR: {usd_inr.get('rate', 'N/A')} ({_fmt_pct(usd_inr.get('change_pct'))}) | "
        f"US futures: S&P {_fmt_pct(sp500.get('change_pct'))}"
    )

    lines.append("")

    # Asian → India correlation section (V2)
    if correlation_briefing:
        # Add a condensed version of the correlation briefing
        lines.append("\U0001f4c8 ASIAN \u2192 INDIA CORRELATION (data-driven):")
        # Take the key lines from the full correlation briefing
        corr_lines = correlation_briefing.split("\n")
        for cl in corr_lines:
            if cl.startswith("BREACH:") or cl.startswith("  ") and any(
                c in cl for c in ["HAL", "BEL", "ONGC", "TCS", "INFY", "OIL", "RELIANCE"]
            ):
                lines.append(f"  {cl.strip()}")
        lines.append("")

    # Stock-level probability ranking (V2)
    try:
        from asian_correlation import get_stock_ranking_briefing
        stock_ranking = get_stock_ranking_briefing()
        if stock_ranking:
            lines.append("\U0001f52c " + stock_ranking)
            lines.append("")
    except ImportError:
        pass
    except Exception as exc:
        logger.warning("Stock ranking failed: %s", exc)

    # India expected
    lines.append("\U0001F1EE\U0001F1F3 India Expected:")
    if cascade_signals:
        for sig in cascade_signals:
            trigger = sig.get("trigger", "")
            detail = sig.get("detail", "")
            india_long = sig.get("india_long", [])
            india_short = sig.get("india_short", [])
            lines.append(f"  \u2192 {trigger}: {detail}")
            if india_long:
                lines.append(f"    Long bias: {', '.join(india_long)}")
            if india_short:
                lines.append(f"    Short bias: {', '.join(india_short)}")
    else:
        lines.append("  No strong directional cascade signals detected.")
        lines.append("  Watch Nifty open for local sentiment cues.")

    lines.append("")

    # Spread idea
    lines.append("\U0001F4CA SPREAD IDEA (exploring):")
    if cascade_signals:
        best = max(cascade_signals, key=lambda s: s.get("strength", 0))
        long_tickers = best.get("india_long", [])
        short_tickers = best.get("india_short", [])
        lines.append(f"  Long: {', '.join(long_tickers)}")
        lines.append(f"  Short: {', '.join(short_tickers)}")
        lines.append(f"  Trigger: {best.get('trigger', '')} -- {best.get('detail', '')}")
    else:
        lines.append("  No actionable spread from overnight session.")

    lines.append("")
    lines.append("\u26A0\uFE0F Not investment advice. Educational only.")
    lines.append("\u2501" * 36)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_premarket_scan(
    overnight_events: Optional[list[dict[str, Any]]] = None,
) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    """Main entry for the pre-market scanner.

    1. Fetch Asian session data
    2. Detect cascade signals
    3. Detect regime (RISK_ON / RISK_OFF / MIXED)
    4. Generate correlation briefing (data-driven)
    5. Optionally incorporate overnight political events
    6. Generate briefing text with all sections

    Returns (briefing_text, cascade_signals, asian_data).
    """
    logger.info("=== Pre-market scan started ===")

    # 1. Fetch data
    asian_data = fetch_asian_session_data()

    # 2. Detect cascades
    cascade_signals = detect_cascade_signals(asian_data)

    # 3. Load overnight events if not provided
    if overnight_events is None:
        seen_file = DATA_DIR / "seen_events.json"
        if seen_file.exists():
            signals_dir = DATA_DIR / "signals"
            overnight_events = []
            if signals_dir.exists():
                for sig_file in sorted(signals_dir.glob("SIG-*.json"), reverse=True)[:5]:
                    try:
                        sig = json.loads(sig_file.read_text(encoding="utf-8"))
                        evt = sig.get("event", {})
                        if evt.get("headline"):
                            overnight_events.append(evt)
                    except (json.JSONDecodeError, IOError):
                        continue

    # 4. Detect regime (V2)
    regime_info = detect_regime(asian_data, overnight_events)

    # 5. Generate correlation briefing (V2)
    correlation_briefing = None
    try:
        from asian_correlation import generate_correlation_briefing
        # Build today's Asian moves from our fetched data
        today_moves = {}
        for idx_name, idx_data in asian_data.get("indices", {}).items():
            chg = idx_data.get("change_pct")
            if chg is not None:
                today_moves[idx_name.split()[0]] = float(chg)  # "Nikkei 225" → "Nikkei"
        for ticker, d_data in asian_data.get("defence_stocks", {}).items():
            name = d_data.get("name", ticker)
            chg = d_data.get("change_pct")
            if chg is not None:
                today_moves[name] = float(chg)
        brent_chg = asian_data.get("commodities", {}).get("brent", {}).get("change_pct")
        if brent_chg is not None:
            today_moves["Brent"] = float(brent_chg)
        gold_chg = asian_data.get("commodities", {}).get("gold", {}).get("change_pct")
        if gold_chg is not None:
            today_moves["Gold"] = float(gold_chg)

        correlation_briefing = generate_correlation_briefing(today_moves)
        logger.info("Correlation briefing generated")
    except ImportError:
        logger.warning("asian_correlation module not available -- skipping correlation section")
    except Exception as exc:
        logger.warning("Correlation briefing failed: %s", exc)

    # 6. Generate briefing with all sections
    briefing_text = generate_premarket_briefing(
        asian_data, cascade_signals, overnight_events,
        regime_info=regime_info,
        correlation_briefing=correlation_briefing,
    )

    # Persist briefing
    briefing_file = DATA_DIR / "latest_briefing.txt"
    try:
        briefing_file.write_text(briefing_text, encoding="utf-8")
    except Exception as exc:
        logger.warning("Failed to save briefing: %s", exc)

    logger.info("=== Pre-market scan complete ===")
    logger.info("Briefing:\n%s", briefing_text)

    return briefing_text, cascade_signals, asian_data


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    briefing, signals, data = run_premarket_scan()
    print(briefing)
