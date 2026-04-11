"""
Anka Research - Model Portfolio Tracker
Tracks 15-stock war portfolio with:
- 10% trailing stop loss
- USD-equivalent returns (all positions converted to USD)
- Technical signals (20-day MA, RSI) for re-entry screening
- Fundamental screening (analyst targets, forward P/E, earnings growth)
- ETF equivalents for each sector
- Re-entry / replacement decision engine

Runs as part of the weekly aggregator or standalone.
"""

import json
import sys
import logging
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional

import yfinance as yf
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from config import FX_PAIRS, WAR_START_DATE

DATA_DIR = Path(__file__).parent / "data"
LOG_DIR = Path(__file__).parent / "logs"
DATA_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "portfolio_tracker.log", delay=True, encoding="utf-8"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("portfolio_tracker")


# ============================================================
# MODEL PORTFOLIO DEFINITION
# ============================================================
# All positions tracked in USD. Non-USD stocks converted at current FX.
# ETF equivalents provided for each sector.
# ============================================================

MODEL_PORTFOLIO = {
    # === DEFENSE (5 slots) ===
    "LMT": {
        "name": "Lockheed Martin", "yf": "LMT", "sector": "Defense",
        "currency": "USD", "region": "US", "etf": "ITA",
        "thesis": "F-35 program, THAAD/PAC-3 expansion, $194B backlog",
        "entry_date": "2026-02-27", "entry_price_local": 654.63,
        "status": "ACTIVE",
    },
    "NOC": {
        "name": "Northrop Grumman", "yf": "NOC", "sector": "Defense",
        "currency": "USD", "region": "US", "etf": "ITA",
        "thesis": "B-21 Raider, nuclear modernization, $95.7B backlog",
        "entry_date": "2026-02-27", "entry_price_local": 724.38,
        "status": "ACTIVE",
    },
    "BA.": {
        "name": "BAE Systems", "yf": "BA.L", "sector": "Defense",
        "currency": "GBX", "region": "UK", "etf": "EUAD.L",
        "thesis": "EU EUR 800B rearmament, GBP 83.6B backlog",
        "entry_date": "2026-02-27", "entry_price_local": 2112.0,
        "status": "ACTIVE",
    },
    "012450": {
        "name": "Hanwha Aerospace", "yf": "012450.KS", "sector": "Defense",
        "currency": "KRW", "region": "Korea", "etf": None,
        "thesis": "K9/Chunmoo exports to Europe, 137% revenue growth",
        "entry_date": "2026-02-27", "entry_price_local": 1195000.0,
        "status": "ACTIVE",
    },
    "7012": {
        "name": "Kawasaki Heavy", "yf": "7012.T", "sector": "Defense",
        "currency": "JPY", "region": "Japan", "etf": None,
        "thesis": "GCAP program, PM Takaichi defense push",
        "entry_date": "2026-02-27", "entry_price_local": 3651.0,
        "status": "STOPPED_OUT", "stop_date": "2026-03-15",
        "stop_price_local": 3285.9,
        "replacement_pending": "7011 (MHI) — conditional on reclaiming 20d MA",
    },

    # === ENERGY (4 slots) ===
    "VLO": {
        "name": "Valero Energy", "yf": "VLO", "sector": "Energy/Refiner",
        "currency": "USD", "region": "US", "etf": "XLE",
        "thesis": "Crack spread expansion, Hormuz removes Gulf refining capacity",
        "entry_date": "2026-02-27", "entry_price_local": 204.64,
        "status": "ACTIVE",
    },
    "MPC": {
        "name": "Marathon Petroleum", "yf": "MPC", "sector": "Energy/Refiner",
        "currency": "USD", "region": "US", "etf": "XLE",
        "thesis": "Highest throughput efficiency among US refiners",
        "entry_date": "2026-02-27", "entry_price_local": 198.21,
        "status": "ACTIVE",
    },
    "OXY": {
        "name": "Occidental Petroleum", "yf": "OXY", "sector": "Energy/Producer",
        "currency": "USD", "region": "US", "etf": "XLE",
        "thesis": "Buffett's 28% stake, pure-play oil at $100+",
        "entry_date": "2026-02-27", "entry_price_local": 52.83,
        "status": "ACTIVE",
    },
    "TTE": {
        "name": "TotalEnergies", "yf": "TTE.PA", "sector": "Energy/Integrated",
        "currency": "EUR", "region": "Europe", "etf": "XLE",
        "thesis": "Europe's largest energy company, ATH, 4.2% dividend",
        "entry_date": "2026-02-27", "entry_price_local": 67.28,
        "status": "ACTIVE",
    },

    # === SHIPPING (1 slot) ===
    "FRO": {
        "name": "Frontline", "yf": "FRO", "sector": "Shipping/Tanker",
        "currency": "USD", "region": "US", "etf": None,
        "thesis": "VLCC rates $315-445K/day, Hormuz rerouting doubles ton-miles",
        "entry_date": "2026-02-27", "entry_price_local": 36.78,
        "status": "ACTIVE",
    },

    # === ENERGY INFRA (1 slot) ===
    "ENR": {
        "name": "Siemens Energy", "yf": "ENR.DE", "sector": "Energy Infra",
        "currency": "EUR", "region": "Germany", "etf": None,
        "thesis": "Gas turbine demand, AI datacenter power, EUR 2B buyback",
        "entry_date": "2026-02-27", "entry_price_local": 166.45,
        "status": "REPLACED", "stop_date": "2026-03-18",
        "stop_price_local": 149.805, "replaced_by": "RHM",
    },
    "RHM": {
        "name": "Rheinmetall", "yf": "RHM.DE", "sector": "Defense",
        "currency": "EUR", "region": "Germany", "etf": "EUAD.L",
        "thesis": "EU rearmament leader, Goldman EUR 2,300 target, EUR 63.8B backlog, PEG 0.83",
        "entry_date": "2026-03-29", "entry_price_local": 1379.50,
        "status": "ACTIVE", "replaces": "ENR",
    },

    # === CYBERSECURITY (2 slots) ===
    "PLTR": {
        "name": "Palantir Technologies", "yf": "PLTR", "sector": "Cyber/Defense AI",
        "currency": "USD", "region": "US", "etf": "CIBR",
        "thesis": "AI-enabled defense intelligence, government contracts",
        "entry_date": "2026-02-27", "entry_price_local": 137.19,
        "status": "ACTIVE",
    },
    "CRWD": {
        "name": "CrowdStrike", "yf": "CRWD", "sector": "Cybersecurity",
        "currency": "USD", "region": "US", "etf": "CIBR",
        "thesis": "State-sponsored cyber attacks surge during war",
        "entry_date": "2026-02-27", "entry_price_local": 371.98,
        "status": "ACTIVE",
    },

    # === COMMODITIES (1 slot) ===
    "GLEN": {
        "name": "Glencore", "yf": "GLEN.L", "sector": "Commodity/Mining",
        "currency": "GBX", "region": "UK", "etf": "GDX",
        "thesis": "Trading arm profits from volatility, diversified commodities",
        "entry_date": "2026-02-27", "entry_price_local": 534.0,
        "status": "ACTIVE",
    },

    # === EV / ENERGY TRANSITION (1 slot) ===
    "300750": {
        "name": "CATL", "yf": "300750.SZ", "sector": "EV Batteries",
        "currency": "CNY", "region": "China", "etf": "LIT",
        "thesis": "$112 oil accelerates EV adoption, 50% China market share",
        "entry_date": "2026-02-27", "entry_price_local": 342.01,
        "status": "ACTIVE",
    },
}

# Replacement candidates (bench) — tracked but not in active portfolio
REPLACEMENT_BENCH = {
    "RHM": {
        "name": "Rheinmetall", "yf": "RHM.DE", "sector": "Defense",
        "currency": "EUR", "region": "Germany", "etf": "EUAD.L",
        "thesis": "Goldman EUR 2,300 target, EU rearmament leader, 52% order growth",
        "candidate_for": "ENR",  # could replace ENR's slot
    },
    "7011": {
        "name": "Mitsubishi Heavy Industries", "yf": "7011.T", "sector": "Defense",
        "currency": "JPY", "region": "Japan", "etf": None,
        "thesis": "GCAP lead contractor, SpaceJet successor, nuclear restart",
        "candidate_for": "7012",  # could replace 7012's slot
    },
    "INPEX": {
        "name": "INPEX Corporation", "yf": "1605.T", "sector": "Energy/Producer",
        "currency": "JPY", "region": "Japan", "etf": None,
        "thesis": "Japan's largest E&P, Ichthys LNG, benefits from oil >$100",
        "candidate_for": "7012",  # alternative Japan energy play
    },
    "HAL_IN": {
        "name": "Hindustan Aeronautics", "yf": "HAL.NS", "sector": "Defense/Aerospace",
        "currency": "INR", "region": "India", "etf": None,
        "thesis": "India defense capex surge, Tejas orders, monopoly supplier",
        "candidate_for": "ENR",  # if we want India defense exposure
    },
}

# ETF sector mapping for readers who prefer ETFs
ETF_SECTOR_MAP = {
    "Defense (US)":       {"etf": "ITA",   "name": "iShares US Aerospace & Defense"},
    "Defense (EU)":       {"etf": "EUAD.L","name": "European Aerospace & Defence (not very liquid)"},
    "Energy":             {"etf": "XLE",   "name": "Energy Select Sector SPDR"},
    "Cybersecurity":      {"etf": "CIBR",  "name": "First Trust Cybersecurity ETF"},
    "Gold/Commodities":   {"etf": "GDX",   "name": "VanEck Gold Miners ETF"},
    "EV/Batteries":       {"etf": "LIT",   "name": "Global X Lithium & Battery Tech ETF"},
    "Shipping":           {"etf": None,     "name": "No liquid tanker ETF - stock only"},
    "Broad War Play":     {"etf": "SPY",   "name": "SPDR S&P 500 (for short leg)"},
}

# FX conversion map: currency code -> yfinance FX symbol
# All FX symbols return rate in terms of: how many units of currency per 1 USD
FX_TO_USD = {
    "USD": None,          # no conversion needed
    "EUR": "EURUSD=X",    # EUR per USD -> invert: 1/rate gives USD per EUR
    "GBX": "GBPUSD=X",    # GBP per USD -> invert, then /100 for pence
    "GBP": "GBPUSD=X",    # same but no /100
    "JPY": "JPY=X",       # JPY per USD -> 1/rate gives USD per JPY
    "KRW": "KRW=X",       # KRW per USD -> 1/rate
    "CNY": "CNY=X",       # CNY per USD -> 1/rate
    "INR": "INR=X",       # INR per USD -> 1/rate
}


# ============================================================
# TECHNICAL ANALYSIS FUNCTIONS
# ============================================================

def compute_rsi(prices, period=14):
    """Compute RSI from a series of closing prices."""
    if len(prices) < period + 1:
        return None
    deltas = np.diff(prices)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)

    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])

    if avg_loss == 0:
        return 100.0

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def compute_sma(prices, period=20):
    """Compute Simple Moving Average."""
    if len(prices) < period:
        return None
    return round(float(np.mean(prices[-period:])), 4)


def get_technical_signals(yf_symbol: str, lookback_days: int = 60) -> dict:
    """Fetch price history and compute technical signals."""
    try:
        ticker = yf.Ticker(yf_symbol)
        hist = ticker.history(period=f"{lookback_days}d")
        if hist.empty or len(hist) < 21:
            return {"error": "insufficient data"}

        closes = hist["Close"].values
        current_price = float(closes[-1])
        sma_20 = compute_sma(closes, 20)
        rsi_14 = compute_rsi(closes, 14)

        # Volume analysis
        avg_volume_20 = float(np.mean(hist["Volume"].values[-20:]))
        last_volume = float(hist["Volume"].values[-1])
        volume_ratio = round(last_volume / avg_volume_20, 2) if avg_volume_20 > 0 else None

        # Price vs SMA
        above_sma20 = current_price > sma_20 if sma_20 else None

        # 52-week high/low from available data
        high_52w = float(np.max(closes))
        low_52w = float(np.min(closes))
        pct_from_high = round(((current_price - high_52w) / high_52w) * 100, 2)

        return {
            "current_price": round(current_price, 4),
            "sma_20": sma_20,
            "above_sma20": above_sma20,
            "rsi_14": rsi_14,
            "volume_ratio": volume_ratio,  # >1 = above avg
            "high_period": round(high_52w, 4),
            "low_period": round(low_52w, 4),
            "pct_from_high": pct_from_high,
            "date": hist.index[-1].strftime("%Y-%m-%d"),
        }
    except Exception as e:
        return {"error": str(e)}


# ============================================================
# FUNDAMENTAL ANALYSIS FUNCTIONS
# ============================================================

def get_fundamental_signals(yf_symbol: str) -> dict:
    """Fetch fundamental data: analyst targets, forward P/E, earnings growth."""
    try:
        ticker = yf.Ticker(yf_symbol)
        info = ticker.info or {}

        # Analyst consensus
        rec = info.get("recommendationKey", "none")
        num_analysts = info.get("numberOfAnalystOpinions", 0)
        target_mean = info.get("targetMeanPrice")
        target_high = info.get("targetHighPrice")
        target_low = info.get("targetLowPrice")
        current = info.get("currentPrice") or info.get("regularMarketPrice")

        # Upside based on mean target
        upside_pct = None
        if target_mean and current and current > 0:
            upside_pct = round(((target_mean - current) / current) * 100, 2)

        # Valuation
        forward_pe = info.get("forwardPE")
        trailing_pe = info.get("trailingPE")
        peg_ratio = info.get("pegRatio")

        # Earnings growth
        earnings_growth = info.get("earningsGrowth")  # quarterly YoY
        revenue_growth = info.get("revenueGrowth")

        # Forward EPS
        forward_eps = info.get("forwardEps")
        trailing_eps = info.get("trailingEps")
        eps_growth = None
        if forward_eps and trailing_eps and trailing_eps > 0:
            eps_growth = round(((forward_eps - trailing_eps) / abs(trailing_eps)) * 100, 2)

        # Recent analyst actions
        try:
            upgrades = ticker.upgrades_downgrades
            recent = []
            if upgrades is not None and len(upgrades) > 0:
                for idx in range(min(5, len(upgrades))):
                    row = upgrades.iloc[-(idx + 1)]
                    recent.append({
                        "firm": row.get("Firm", "Unknown"),
                        "action": row.get("ToGrade", "Unknown"),
                        "from": row.get("FromGrade", ""),
                    })
        except Exception:
            recent = []

        return {
            "recommendation": rec,
            "num_analysts": num_analysts,
            "target_mean": target_mean,
            "target_high": target_high,
            "target_low": target_low,
            "upside_pct": upside_pct,
            "forward_pe": forward_pe,
            "trailing_pe": trailing_pe,
            "peg_ratio": peg_ratio,
            "forward_eps": forward_eps,
            "trailing_eps": trailing_eps,
            "eps_growth_pct": eps_growth,
            "earnings_growth_qoq": earnings_growth,
            "revenue_growth_qoq": revenue_growth,
            "recent_actions": recent,
        }
    except Exception as e:
        return {"error": str(e)}


# ============================================================
# FX CONVERSION
# ============================================================

def get_fx_rates() -> dict:
    """Fetch current FX rates. Returns dict of currency -> USD multiplier.
    e.g., EUR -> 1.15 means 1 EUR = 1.15 USD
    """
    rates = {"USD": 1.0}

    # EUR/USD: EURUSD=X gives how many USD per 1 EUR
    for pair_name, cfg in [
        ("EUR", "EURUSD=X"),
        ("GBP", "GBPUSD=X"),
    ]:
        try:
            t = yf.Ticker(cfg)
            h = t.history(period="5d")
            if not h.empty:
                rates[pair_name] = float(h["Close"].iloc[-1])
        except Exception:
            pass

    # GBX (pence) = GBP / 100
    if "GBP" in rates:
        rates["GBX"] = rates["GBP"] / 100.0

    # JPY, KRW, CNY, INR: these symbols return how many foreign per 1 USD
    for pair_name, cfg in [
        ("JPY", "JPY=X"),
        ("KRW", "KRW=X"),
        ("CNY", "CNY=X"),
        ("INR", "INR=X"),
    ]:
        try:
            t = yf.Ticker(cfg)
            h = t.history(period="5d")
            if not h.empty:
                foreign_per_usd = float(h["Close"].iloc[-1])
                rates[pair_name] = 1.0 / foreign_per_usd  # USD per 1 foreign unit
        except Exception:
            pass

    return rates


def to_usd(price_local: float, currency: str, fx_rates: dict) -> Optional[float]:
    """Convert local price to USD."""
    if currency == "USD":
        return price_local
    rate = fx_rates.get(currency)
    if rate is None:
        return None
    return round(price_local * rate, 4)


# ============================================================
# RE-ENTRY / REPLACEMENT DECISION ENGINE
# ============================================================

def evaluate_reentry(ticker: str, portfolio_entry: dict, technicals: dict, fundamentals: dict) -> dict:
    """Evaluate whether a stopped-out stock qualifies for re-entry.

    Re-entry requires BOTH:
    1. Fundamental: Fresh analyst upgrade OR target >= 15% upside
    2. Technical: Price above 20-day MA AND RSI > 40

    Returns a signal dict with recommendation.
    """
    signals = {
        "ticker": ticker,
        "name": portfolio_entry.get("name", ""),
        "fundamental_pass": False,
        "technical_pass": False,
        "recommendation": "WAIT",
        "reasons": [],
    }

    # Fundamental check
    if fundamentals and not fundamentals.get("error"):
        upside = fundamentals.get("upside_pct")
        rec = fundamentals.get("recommendation", "").lower()

        if upside and upside >= 15:
            signals["fundamental_pass"] = True
            signals["reasons"].append(f"Analyst target upside: {upside}%")
        if rec in ("buy", "strong_buy", "strongbuy"):
            signals["fundamental_pass"] = True
            signals["reasons"].append(f"Consensus: {rec}")
        if fundamentals.get("eps_growth_pct") and fundamentals["eps_growth_pct"] > 10:
            signals["reasons"].append(f"Forward EPS growth: {fundamentals['eps_growth_pct']}%")

        # Check recent upgrades
        recent = fundamentals.get("recent_actions", [])
        for action in recent:
            grade = (action.get("action") or "").lower()
            if grade in ("buy", "overweight", "outperform", "strong buy"):
                signals["fundamental_pass"] = True
                signals["reasons"].append(f"Recent upgrade: {action.get('firm', '?')} -> {action.get('action', '?')}")
                break

    # Technical check
    if technicals and not technicals.get("error"):
        above_sma = technicals.get("above_sma20")
        rsi = technicals.get("rsi_14")

        if above_sma and rsi and rsi > 40:
            signals["technical_pass"] = True
            signals["reasons"].append(f"Above 20-day MA, RSI: {rsi}")
        elif above_sma:
            signals["reasons"].append(f"Above 20-day MA but RSI weak: {rsi}")
        elif rsi and rsi > 40:
            signals["reasons"].append(f"RSI OK ({rsi}) but below 20-day MA")
        else:
            signals["reasons"].append(f"Below 20-day MA, RSI: {rsi} - no momentum")

    # Decision
    if signals["fundamental_pass"] and signals["technical_pass"]:
        signals["recommendation"] = "RE-ENTER"
    elif signals["fundamental_pass"]:
        signals["recommendation"] = "WATCH - Fundamentals OK, waiting for technical confirmation"
    elif signals["technical_pass"]:
        signals["recommendation"] = "WATCH - Technicals OK, need fundamental catalyst"
    else:
        signals["recommendation"] = "WAIT - Neither signal triggered"

    return signals


def evaluate_replacement(ticker: str, bench_entry: dict, technicals: dict, fundamentals: dict) -> dict:
    """Evaluate whether a bench candidate qualifies to replace a stopped-out stock.

    Replacement requires at least 2 of 3:
    1. Analyst consensus: Majority Buy/Strong Buy, target >= 15% upside
    2. Technical: Above 20-day MA, RSI 45-65, volume above average
    3. Sector thesis: (always True for our bench candidates - pre-screened)

    Returns a signal dict with score and recommendation.
    """
    signals = {
        "ticker": ticker,
        "name": bench_entry.get("name", ""),
        "replaces": bench_entry.get("candidate_for", ""),
        "score": 0,
        "max_score": 3,
        "fundamental_pass": False,
        "technical_pass": False,
        "sector_pass": True,  # pre-screened
        "recommendation": "NOT READY",
        "reasons": [],
    }

    signals["score"] += 1  # sector thesis always counts
    signals["reasons"].append(f"Sector thesis: {bench_entry.get('thesis', '')[:80]}")

    # Fundamental check
    if fundamentals and not fundamentals.get("error"):
        upside = fundamentals.get("upside_pct")
        rec = fundamentals.get("recommendation", "").lower()

        if (upside and upside >= 15) or rec in ("buy", "strong_buy", "strongbuy"):
            signals["fundamental_pass"] = True
            signals["score"] += 1
            signals["reasons"].append(f"Consensus: {rec}, target upside: {upside}%")
        else:
            signals["reasons"].append(f"Weak consensus: {rec}, upside: {upside}%")

        if fundamentals.get("forward_pe"):
            signals["reasons"].append(f"Forward P/E: {fundamentals['forward_pe']}")
        if fundamentals.get("eps_growth_pct"):
            signals["reasons"].append(f"EPS growth: {fundamentals['eps_growth_pct']}%")

    # Technical check
    if technicals and not technicals.get("error"):
        above_sma = technicals.get("above_sma20")
        rsi = technicals.get("rsi_14")
        vol_ratio = technicals.get("volume_ratio")

        tech_ok = True
        if not above_sma:
            tech_ok = False
        if rsi and (rsi < 45 or rsi > 65):
            tech_ok = False  # we want goldilocks zone, not overbought/oversold

        if tech_ok:
            signals["technical_pass"] = True
            signals["score"] += 1
            signals["reasons"].append(f"Technical: Above 20d MA, RSI {rsi}, Vol ratio {vol_ratio}")
        else:
            signals["reasons"].append(f"Technical weak: {'Below' if not above_sma else 'Above'} 20d MA, RSI {rsi}")

    # Decision
    if signals["score"] >= 2:
        signals["recommendation"] = "REPLACE"
    else:
        signals["recommendation"] = "BENCH - Score {}/3, need 2+".format(signals["score"])

    return signals


# ============================================================
# MAIN PORTFOLIO TRACKER
# ============================================================

def run_portfolio_tracker(as_of_date: str = None):
    """Run full portfolio analysis."""
    if as_of_date is None:
        as_of_date = datetime.now().strftime("%Y-%m-%d")

    log.info("=" * 60)
    log.info(f"MODEL PORTFOLIO TRACKER - {as_of_date}")
    log.info("=" * 60)

    # Step 1: Get FX rates
    log.info("\n--- FX Rates ---")
    fx_rates = get_fx_rates()
    for curr, rate in fx_rates.items():
        log.info(f"  {curr}/USD: {rate:.6f}" if rate < 1 else f"  1 {curr} = {rate:.4f} USD")

    # Step 2: Analyze each active position
    log.info("\n--- Active Positions ---")
    portfolio_output = {}
    total_return_usd = 0
    active_count = 0
    stopped_count = 0

    for ticker, pos in MODEL_PORTFOLIO.items():
        log.info(f"\n  [{ticker}] {pos['name']} ({pos['status']})")

        # Get technicals
        tech = get_technical_signals(pos["yf"])
        fund = get_fundamental_signals(pos["yf"])

        current_local = tech.get("current_price") if not tech.get("error") else None
        entry_local = pos["entry_price_local"]

        # USD conversion
        entry_usd = to_usd(entry_local, pos["currency"], fx_rates)
        current_usd = to_usd(current_local, pos["currency"], fx_rates) if current_local else None

        # Returns
        local_return_pct = round(((current_local - entry_local) / entry_local) * 100, 2) if current_local else None
        usd_return_pct = round(((current_usd - entry_usd) / entry_usd) * 100, 2) if current_usd and entry_usd else None

        # Trailing stop: 10% from highest price since entry
        # For simplicity, use current high from technical data
        high_since_entry = max(entry_local, current_local or 0)
        trailing_stop_local = round(high_since_entry * 0.90, 4)

        # Stop-out check
        is_stopped = pos["status"] == "STOPPED_OUT"
        if not is_stopped and current_local and current_local < trailing_stop_local:
            is_stopped = True
            log.info(f"    *** NEW STOP-OUT: {current_local} < {trailing_stop_local} ***")

        # Build entry
        position_data = {
            "name": pos["name"],
            "sector": pos["sector"],
            "currency": pos["currency"],
            "region": pos["region"],
            "etf_equivalent": pos.get("etf"),
            "thesis": pos["thesis"],
            "entry_date": pos["entry_date"],
            "entry_price_local": entry_local,
            "entry_price_usd": entry_usd,
            "current_price_local": current_local,
            "current_price_usd": current_usd,
            "return_local_pct": local_return_pct,
            "return_usd_pct": usd_return_pct,
            "high_since_entry": high_since_entry,
            "trailing_stop_local": trailing_stop_local,
            "status": "STOPPED_OUT" if is_stopped else "ACTIVE",
            "technicals": tech if not tech.get("error") else None,
            "fundamentals": {
                "recommendation": fund.get("recommendation"),
                "num_analysts": fund.get("num_analysts"),
                "target_mean": fund.get("target_mean"),
                "upside_pct": fund.get("upside_pct"),
                "forward_pe": fund.get("forward_pe"),
                "trailing_pe": fund.get("trailing_pe"),
                "eps_growth_pct": fund.get("eps_growth_pct"),
                "revenue_growth_qoq": fund.get("revenue_growth_qoq"),
                "recent_actions": fund.get("recent_actions", []),
            } if not fund.get("error") else None,
        }

        portfolio_output[ticker] = position_data

        if not is_stopped:
            active_count += 1
            if usd_return_pct:
                total_return_usd += usd_return_pct
        else:
            stopped_count += 1

        status_str = "STOPPED OUT" if is_stopped else "ACTIVE"
        log.info(f"    Local: {entry_local} -> {current_local} ({local_return_pct}%)")
        log.info(f"    USD:   ${entry_usd} -> ${current_usd} ({usd_return_pct}%)")
        log.info(f"    Stop:  {trailing_stop_local} | Status: {status_str}")
        if fund and not fund.get("error"):
            log.info(f"    Analyst: {fund.get('recommendation')} | Target: {fund.get('target_mean')} ({fund.get('upside_pct')}% upside)")
            log.info(f"    Fwd P/E: {fund.get('forward_pe')} | EPS growth: {fund.get('eps_growth_pct')}%")

    # Step 3: Evaluate stopped-out stocks for re-entry
    log.info("\n--- Re-Entry Screening ---")
    reentry_signals = {}
    for ticker, pos in MODEL_PORTFOLIO.items():
        if pos["status"] == "STOPPED_OUT":
            tech = get_technical_signals(pos["yf"])
            fund = get_fundamental_signals(pos["yf"])
            signal = evaluate_reentry(ticker, pos, tech, fund)
            reentry_signals[ticker] = signal
            log.info(f"  [{ticker}] {signal['recommendation']}")
            for r in signal["reasons"]:
                log.info(f"    - {r}")

    # Step 4: Evaluate replacement candidates
    log.info("\n--- Replacement Candidates ---")
    replacement_signals = {}
    for ticker, bench in REPLACEMENT_BENCH.items():
        tech = get_technical_signals(bench["yf"])
        fund = get_fundamental_signals(bench["yf"])
        signal = evaluate_replacement(ticker, bench, tech, fund)
        replacement_signals[ticker] = signal
        log.info(f"  [{ticker}] {signal['recommendation']} (score {signal['score']}/{signal['max_score']})")
        for r in signal["reasons"]:
            log.info(f"    - {r}")

    # Step 5: Summary
    avg_return_usd = round(total_return_usd / active_count, 2) if active_count > 0 else 0

    summary = {
        "as_of_date": as_of_date,
        "generated_at": datetime.now().isoformat(),
        "war_start": WAR_START_DATE,
        "active_positions": active_count,
        "stopped_out": stopped_count,
        "total_positions": len(MODEL_PORTFOLIO),
        "avg_return_usd_pct": avg_return_usd,
        "fx_rates": {k: round(v, 6) for k, v in fx_rates.items()},
    }

    # Build final output
    output = {
        "summary": summary,
        "portfolio": portfolio_output,
        "reentry_screening": reentry_signals,
        "replacement_screening": replacement_signals,
        "etf_sector_map": ETF_SECTOR_MAP,
        "rules": {
            "trailing_stop_pct": 10.0,
            "max_positions": 15,
            "reentry_rule": "BOTH: (1) Analyst upgrade/Buy + target >=15% upside, AND (2) Price above 20d MA + RSI > 40",
            "replacement_rule": "At least 2 of 3: (1) Analyst Buy + >=15% upside, (2) Above 20d MA + RSI 45-65 + vol above avg, (3) War-beneficiary sector thesis",
            "usd_conversion": "All returns tracked in USD using live FX rates",
        },
    }

    # Save
    outfile = DATA_DIR / f"portfolio-{as_of_date}.json"
    with open(outfile, "w") as f:
        json.dump(output, f, indent=2, default=str)

    log.info(f"\n{'='*60}")
    log.info(f"PORTFOLIO TRACKER COMPLETE")
    log.info(f"Active: {active_count}/15 | Stopped: {stopped_count}/15")
    log.info(f"Avg USD Return: {avg_return_usd}%")
    log.info(f"Saved to: {outfile}")
    log.info(f"{'='*60}")

    return output


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else None
    run_portfolio_tracker(target)
