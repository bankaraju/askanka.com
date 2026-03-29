"""
Anka Research — Week Zero: Pre-War Baseline
Captures the market state on Feb 27, 2026 (last trading day before the war).
This is the benchmark against which ALL future performance is measured.

Model Portfolio: 15 stocks across war-beneficiary sectors
Trailing stop: 10% from entry price
"""

import json
import sys
import logging
from datetime import datetime, timedelta
from pathlib import Path

import yfinance as yf

sys.path.insert(0, str(Path(__file__).parent))
from config import WAR_START_DATE

DATA_DIR = Path(__file__).parent / "data"
LOG_DIR = Path(__file__).parent / "logs"
DATA_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "week_zero.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("week_zero")

# Pre-war baseline date
BASELINE_DATE = "2026-02-27"  # Last trading day before Feb 28 war start

# ============================================================
# MODEL PORTFOLIO — 15 stocks across post-war beneficiary sectors
# ============================================================
# Selection rationale:
# - Defense (5): Global rearmament cycle is structural, not cyclical
# - Energy (4): Hormuz closure = oil supercycle for producers/refiners
# - Shipping (2): Rerouting around Cape = tanker boom
# - Cybersecurity (2): State-sponsored attacks surge during war
# - Commodities (1): War = commodity supercycle
# - EV/Energy Transition (1): $112 oil accelerates EV adoption
#
# NOT included: airlines, consumer, pure tech — these are war losers.
# NOT trying to replicate pre-war index weights. This is a war portfolio.
# ============================================================

MODEL_PORTFOLIO = {
    # === DEFENSE (5 stocks, ~33% weight) ===
    "LMT":    {"name": "Lockheed Martin",       "yf": "LMT",       "sector": "Defense",         "currency": "USD", "region": "US",     "thesis": "F-35 program, THAAD/PAC-3 expansion, $194B backlog"},
    "NOC":    {"name": "Northrop Grumman",       "yf": "NOC",       "sector": "Defense",         "currency": "USD", "region": "US",     "thesis": "B-21 Raider, nuclear modernization, $95.7B backlog"},
    "BA.":    {"name": "BAE Systems",            "yf": "BA.L",      "sector": "Defense",         "currency": "GBX", "region": "UK",     "thesis": "EU EUR 800B rearmament, GBP 83.6B backlog"},
    "012450": {"name": "Hanwha Aerospace",       "yf": "012450.KS", "sector": "Defense",         "currency": "KRW", "region": "Korea",  "thesis": "K9/Chunmoo exports to Europe, 137% revenue growth"},
    "7012":   {"name": "Kawasaki Heavy",         "yf": "7012.T",    "sector": "Defense",         "currency": "JPY", "region": "Japan",  "thesis": "GCAP program, PM Takaichi defense push, #2 MSCI World YTD"},

    # === ENERGY (4 stocks, ~27% weight) ===
    "VLO":    {"name": "Valero Energy",          "yf": "VLO",       "sector": "Energy/Refiner",  "currency": "USD", "region": "US",     "thesis": "Crack spread expansion, Hormuz removes Gulf refining capacity"},
    "MPC":    {"name": "Marathon Petroleum",     "yf": "MPC",       "sector": "Energy/Refiner",  "currency": "USD", "region": "US",     "thesis": "Highest throughput efficiency among US refiners"},
    "OXY":    {"name": "Occidental Petroleum",   "yf": "OXY",       "sector": "Energy/Producer", "currency": "USD", "region": "US",     "thesis": "Buffett's 28% stake, pure-play oil at $100+"},
    "TTE":    {"name": "TotalEnergies",          "yf": "TTE.PA",    "sector": "Energy/Integrated","currency":"EUR", "region": "Europe", "thesis": "Europe's largest energy company, ATH, 4.2% dividend"},

    # === SHIPPING (2 stocks, ~13% weight) ===
    "FRO":    {"name": "Frontline",              "yf": "FRO",       "sector": "Shipping/Tanker", "currency": "USD", "region": "US",     "thesis": "VLCC rates $315-445K/day, Hormuz rerouting doubles ton-miles"},
    "ENR":    {"name": "Siemens Energy",         "yf": "ENR.DE",    "sector": "Energy Infra",    "currency": "EUR", "region": "Germany","thesis": "Gas turbine demand, AI datacenter power, EUR 2B buyback"},

    # === CYBERSECURITY (2 stocks, ~13% weight) ===
    "PLTR":   {"name": "Palantir Technologies",  "yf": "PLTR",      "sector": "Cyber/Defense AI","currency": "USD", "region": "US",     "thesis": "AI-enabled defense intelligence, government contracts"},
    "CRWD":   {"name": "CrowdStrike",            "yf": "CRWD",      "sector": "Cybersecurity",   "currency": "USD", "region": "US",     "thesis": "State-sponsored cyber attacks surge during war"},

    # === COMMODITIES (1 stock, ~7% weight) ===
    "GLEN":   {"name": "Glencore",               "yf": "GLEN.L",    "sector": "Commodity/Mining","currency": "GBX", "region": "UK",     "thesis": "Trading arm profits from volatility, diversified commodities"},

    # === EV / ENERGY TRANSITION (1 stock, ~7% weight) ===
    "300750": {"name": "CATL",                   "yf": "300750.SZ", "sector": "EV Batteries",    "currency": "CNY", "region": "China",  "thesis": "$112 oil accelerates EV adoption, 50% China market share"},
}


def fetch_price_on_date(yf_symbol: str, target_date: str) -> dict:
    """Fetch closing price for a symbol on a specific date."""
    try:
        dt = datetime.strptime(target_date, "%Y-%m-%d")
        start = dt - timedelta(days=10)  # buffer for holidays
        ticker = yf.Ticker(yf_symbol)
        hist = ticker.history(start=start.strftime("%Y-%m-%d"),
                              end=(dt + timedelta(days=1)).strftime("%Y-%m-%d"))
        if hist.empty:
            return {"error": "no data"}

        # Get the closest date <= target
        row = hist.iloc[-1]
        return {
            "date": hist.index[-1].strftime("%Y-%m-%d"),
            "open": round(float(row["Open"]), 4),
            "high": round(float(row["High"]), 4),
            "low": round(float(row["Low"]), 4),
            "close": round(float(row["Close"]), 4),
            "volume": int(row["Volume"]) if "Volume" in row else 0,
        }
    except Exception as e:
        return {"error": str(e)}


def fetch_current_price(yf_symbol: str) -> dict:
    """Fetch the most recent available price."""
    try:
        ticker = yf.Ticker(yf_symbol)
        hist = ticker.history(period="5d")
        if hist.empty:
            return {"error": "no data"}
        row = hist.iloc[-1]
        return {
            "date": hist.index[-1].strftime("%Y-%m-%d"),
            "close": round(float(row["Close"]), 4),
        }
    except Exception as e:
        return {"error": str(e)}


def calculate_stop_loss(entry_price: float, stop_pct: float = 0.10) -> float:
    """Calculate trailing stop loss level."""
    return round(entry_price * (1 - stop_pct), 4)


def run_week_zero():
    """Build the Week Zero baseline snapshot."""
    log.info("=" * 60)
    log.info("WEEK ZERO — PRE-WAR BASELINE")
    log.info(f"Baseline date: {BASELINE_DATE}")
    log.info("=" * 60)

    week_zero = {
        "week_number": 0,
        "label": "Week 000 — Pre-War Baseline",
        "baseline_date": BASELINE_DATE,
        "war_start": WAR_START_DATE,
        "generated_at": datetime.now().isoformat(),
        "portfolio_rules": {
            "trailing_stop_pct": 10.0,
            "max_positions": 15,
            "reentry_rule": "Re-enter on analyst upgrade OR 5%+ pullback from stop-out level",
            "rebalance_trigger": "Stop-out event OR weekly review",
        },
        "portfolio": {},
        "benchmarks": {},
        "fx_baseline": {},
        "commodity_baseline": {},
    }

    # === PORTFOLIO STOCKS ===
    log.info("\n--- Model Portfolio (15 stocks) ---")
    for ticker, cfg in MODEL_PORTFOLIO.items():
        log.info(f"  Fetching {ticker} ({cfg['name']})...")

        # Pre-war price
        baseline = fetch_price_on_date(cfg["yf"], BASELINE_DATE)
        # Current price
        current = fetch_current_price(cfg["yf"])

        entry_price = baseline.get("close")
        current_price = current.get("close")

        # Calculate metrics
        stop_loss = calculate_stop_loss(entry_price, 0.10) if entry_price else None
        change_pct = round(((current_price - entry_price) / entry_price) * 100, 2) if entry_price and current_price else None
        stopped_out = current_price < stop_loss if current_price and stop_loss else False
        # Track high since entry for trailing stop
        high_since_entry = max(entry_price or 0, current_price or 0)  # simplified

        week_zero["portfolio"][ticker] = {
            "name": cfg["name"],
            "sector": cfg["sector"],
            "currency": cfg["currency"],
            "region": cfg["region"],
            "thesis": cfg["thesis"],
            "entry_date": baseline.get("date", BASELINE_DATE),
            "entry_price": entry_price,
            "current_price": current_price,
            "current_date": current.get("date"),
            "change_pct": change_pct,
            "stop_loss_level": stop_loss,
            "stopped_out": stopped_out,
            "status": "STOPPED OUT" if stopped_out else "ACTIVE",
            "high_since_entry": high_since_entry,
            "trailing_stop": calculate_stop_loss(high_since_entry, 0.10) if high_since_entry else None,
        }

        status = "STOPPED OUT" if stopped_out else "ACTIVE"
        log.info(f"    Entry: {entry_price} → Current: {current_price} "
                 f"({change_pct}%) | Stop: {stop_loss} | {status}")

    # === BENCHMARK INDICES ===
    log.info("\n--- Benchmarks ---")
    benchmarks = {
        "S&P 500":    "^GSPC",
        "FTSE 100":   "^FTSE",
        "CAC 40":     "^FCHI",
        "DAX":        "^GDAXI",
        "Nifty 50":   "^NSEI",
        "KOSPI":      "^KS11",
        "Nikkei 225": "^N225",
        "VIX":        "^VIX",
    }
    for name, yf_sym in benchmarks.items():
        baseline = fetch_price_on_date(yf_sym, BASELINE_DATE)
        current = fetch_current_price(yf_sym)
        bp = baseline.get("close")
        cp = current.get("close")
        chg = round(((cp - bp) / bp) * 100, 2) if bp and cp else None
        week_zero["benchmarks"][name] = {
            "pre_war": bp, "current": cp, "change_pct": chg
        }
        log.info(f"  {name}: {bp} → {cp} ({chg}%)")

    # === FX BASELINE ===
    log.info("\n--- FX Rates ---")
    fx_pairs = {
        "EUR/USD": "EURUSD=X", "USD/JPY": "JPY=X", "GBP/USD": "GBPUSD=X",
        "USD/CNY": "CNY=X", "USD/KRW": "KRW=X", "USD/INR": "INR=X",
    }
    for pair, yf_sym in fx_pairs.items():
        baseline = fetch_price_on_date(yf_sym, BASELINE_DATE)
        current = fetch_current_price(yf_sym)
        bp = baseline.get("close")
        cp = current.get("close")
        chg = round(((cp - bp) / bp) * 100, 2) if bp and cp else None
        week_zero["fx_baseline"][pair] = {
            "pre_war": bp, "current": cp, "change_pct": chg
        }
        log.info(f"  {pair}: {bp} → {cp} ({chg}%)")

    # === COMMODITIES BASELINE ===
    log.info("\n--- Commodities ---")
    commodities = {
        "Brent Crude": "BZ=F", "WTI Crude": "CL=F",
        "Gold": "GC=F", "Natural Gas": "NG=F",
    }
    for name, yf_sym in commodities.items():
        baseline = fetch_price_on_date(yf_sym, BASELINE_DATE)
        current = fetch_current_price(yf_sym)
        bp = baseline.get("close")
        cp = current.get("close")
        chg = round(((cp - bp) / bp) * 100, 2) if bp and cp else None
        week_zero["commodity_baseline"][name] = {
            "pre_war": bp, "current": cp, "change_pct": chg
        }
        log.info(f"  {name}: {bp} → {cp} ({chg}%)")

    # === SUMMARY ===
    active = sum(1 for v in week_zero["portfolio"].values() if v["status"] == "ACTIVE")
    stopped = sum(1 for v in week_zero["portfolio"].values() if v["status"] == "STOPPED OUT")
    avg_return = sum(v["change_pct"] or 0 for v in week_zero["portfolio"].values()) / 15

    week_zero["summary"] = {
        "active_positions": active,
        "stopped_out": stopped,
        "avg_portfolio_return": round(avg_return, 2),
        "portfolio_inception": BASELINE_DATE,
    }

    # Save
    outfile = DATA_DIR / "week-000-baseline.json"
    with open(outfile, "w") as f:
        json.dump(week_zero, f, indent=2, default=str)

    log.info(f"\n{'='*60}")
    log.info(f"WEEK ZERO COMPLETE")
    log.info(f"Active: {active}/15 | Stopped: {stopped}/15")
    log.info(f"Avg Return since war: {avg_return:.2f}%")
    log.info(f"Saved to: {outfile}")
    log.info(f"{'='*60}")

    return week_zero


if __name__ == "__main__":
    run_week_zero()
