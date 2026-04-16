"""
Anka Research Pipeline — Configuration
All tickers, indices, FX pairs, and commodities tracked across 8 global markets.
"""

# === INDEX TICKERS (EODHD format: SYMBOL.EXCHANGE) ===
INDICES = {
    "S&P 500":       {"eodhd": "GSPC.INDX",     "yf": "^GSPC",                "currency": "USD"},
    "FTSE 100":      {"eodhd": "FTSE.INDX",     "yf": "^FTSE",                "currency": "GBP"},
    "CAC 40":        {"eodhd": "FCHI.INDX",     "yf": "^FCHI",                "currency": "EUR"},
    "DAX":           {"eodhd": "GDAXI.INDX",    "yf": "^GDAXI",               "currency": "EUR"},
    "Nifty 50":      {"eodhd": "NSEI.INDX",     "yf": "^NSEI",                "currency": "INR"},
    "KOSPI":         {"eodhd": "KS11.INDX",     "yf": "^KS11",                "currency": "KRW"},
    "Nikkei 225":    {"eodhd": "N225.INDX",     "yf": "^N225",                "currency": "JPY"},
    "CSI 300":       {"eodhd": "CSI300.INDX",   "yf": "000300.SS",            "currency": "CNY"},
    "NIFTY DEFENCE": {"eodhd": "",              "yf": "NIFTY_IND_DEFENCE.NS", "currency": "INR"},
    "INDIA VIX":     {"eodhd": "INDIAVIX.INDX", "yf": "^INDIAVIX",            "currency": "INR"},
}

# === STOCK WATCHLIST (from Week 001 report + Week 002 strategy ideas) ===
STOCKS = {
    # S&P 500
    "VLO":   {"exchange": "US", "eodhd": "VLO.US",    "yf": "VLO",    "sector": "Energy/Refiner",    "index": "S&P 500"},
    "MPC":   {"exchange": "US", "eodhd": "MPC.US",    "yf": "MPC",    "sector": "Energy/Refiner",    "index": "S&P 500"},
    "OXY":   {"exchange": "US", "eodhd": "OXY.US",    "yf": "OXY",    "sector": "Energy/Producer",   "index": "S&P 500"},
    "NOC":   {"exchange": "US", "eodhd": "NOC.US",    "yf": "NOC",    "sector": "Defense",           "index": "S&P 500"},
    "LMT":   {"exchange": "US", "eodhd": "LMT.US",    "yf": "LMT",    "sector": "Defense",           "index": "S&P 500"},
    # FTSE 100
    "BA.":   {"exchange": "LSE","eodhd": "BA.LSE",    "yf": "BA.L",   "sector": "Defense",           "index": "FTSE 100"},
    "GLEN":  {"exchange": "LSE","eodhd": "GLEN.LSE",  "yf": "GLEN.L", "sector": "Commodity/Mining",  "index": "FTSE 100"},
    "SSE":   {"exchange": "LSE","eodhd": "SSE.LSE",   "yf": "SSE.L",  "sector": "Energy/Utility",    "index": "FTSE 100"},
    # CAC 40
    "TTE":   {"exchange": "PA", "eodhd": "TTE.PA",    "yf": "TTE.PA", "sector": "Energy/Integrated", "index": "CAC 40"},
    "HO":    {"exchange": "PA", "eodhd": "HO.PA",     "yf": "HO.PA",  "sector": "Defense/Electronics","index": "CAC 40"},
    # DAX
    "ENR":   {"exchange": "XETRA","eodhd": "ENR.XETRA","yf": "ENR.DE","sector": "Energy Infra",     "index": "DAX"},
    "RHM":   {"exchange": "XETRA","eodhd": "RHM.XETRA","yf": "RHM.DE","sector": "Defense",          "index": "DAX"},
    # Nifty 50
    "HAL":   {"exchange": "NSE","eodhd": "HAL.NSE",   "yf": "HAL.NS", "sector": "Defense/Aerospace", "index": "Nifty 50"},
    "BEL":   {"exchange": "NSE","eodhd": "BEL.NSE",   "yf": "BEL.NS", "sector": "Defense Electronics","index": "Nifty 50"},
    "ONGC":  {"exchange": "NSE","eodhd": "ONGC.NSE",  "yf": "ONGC.NS","sector": "Energy",           "index": "Nifty 50"},
    # KOSPI
    "012450":{"exchange": "KO", "eodhd": "012450.KO",  "yf": "012450.KS","sector": "Defense",        "index": "KOSPI"},
    # Nikkei 225
    "7012":  {"exchange": "TSE","eodhd": "7012.TSE",   "yf": "7012.T", "sector": "Defense/Industrial","index": "Nikkei 225"},
    "7011":  {"exchange": "TSE","eodhd": "7011.TSE",   "yf": "7011.T", "sector": "Defense",          "index": "Nikkei 225"},
    # CSI 300
    "300750":{"exchange": "SHE","eodhd": "300750.SHE", "yf": "300750.SZ","sector": "EV Batteries",   "index": "CSI 300"},
    "601857":{"exchange": "SHG","eodhd": "601857.SHG", "yf": "601857.SS","sector": "Energy",         "index": "CSI 300"},
}

# === FX PAIRS ===
FX_PAIRS = {
    "EUR/USD": {"eodhd": "EURUSD.FOREX", "yf": "EURUSD=X"},
    "USD/JPY": {"eodhd": "USDJPY.FOREX", "yf": "JPY=X"},
    "GBP/USD": {"eodhd": "GBPUSD.FOREX", "yf": "GBPUSD=X"},
    "USD/CNY": {"eodhd": "USDCNY.FOREX", "yf": "CNY=X"},
    "USD/KRW": {"eodhd": "USDKRW.FOREX", "yf": "KRW=X"},
    "USD/INR": {"eodhd": "USDINR.FOREX", "yf": "INR=X"},
}

# === COMMODITIES ===
COMMODITIES = {
    "Brent Crude":  {"eodhd": "BZ.COMM",   "yf": "BZ=F"},
    "WTI Crude":    {"eodhd": "CL.COMM",   "yf": "CL=F"},
    "Gold":         {"eodhd": "GC.COMM",   "yf": "GC=F"},
    "Natural Gas":  {"eodhd": "NG.COMM",   "yf": "NG=F"},
}

# === SECTOR ETFs (for spread strategy tracking) ===
SECTOR_ETFS = {
    "XLE":  {"yf": "XLE",  "name": "Energy Select SPDR"},
    "XLY":  {"yf": "XLY",  "name": "Consumer Discretionary SPDR"},
    "ITA":  {"yf": "ITA",  "name": "iShares US Aerospace & Defense"},
    "JETS": {"yf": "JETS", "name": "US Global Jets ETF"},
    "CIBR": {"yf": "CIBR", "name": "First Trust Cybersecurity"},
    "GDX":  {"yf": "GDX",  "name": "VanEck Gold Miners"},
    "GLD":  {"yf": "GLD",  "name": "SPDR Gold Shares"},
    "EWZ":  {"yf": "EWZ",  "name": "iShares MSCI Brazil"},
    "SPY":  {"yf": "SPY",  "name": "SPDR S&P 500"},
}

# === VOLATILITY ===
VOLATILITY = {
    "VIX": {"eodhd": "VIX.INDX", "yf": "^VIX"},
}

# === INDIA SIGNAL STOCKS (for political sentiment engine) ===
INDIA_SIGNAL_STOCKS = {
    # Winners (defense + upstream energy + defensives)
    "HAL":        {"yf": "HAL.NS",        "eodhd": "HAL.NSE",        "sector": "Defense/Aerospace",    "group": "winner"},
    "BEL":        {"yf": "BEL.NS",        "eodhd": "BEL.NSE",        "sector": "Defense Electronics",  "group": "winner"},
    "BDL":        {"yf": "BDL.NS",        "eodhd": "BDL.NSE",        "sector": "Defense/Missiles",     "group": "winner"},
    "MTAR":       {"yf": "MTARTECH.NS",   "eodhd": "MTARTECH.NSE",   "sector": "Defense/Precision",    "group": "winner"},
    "ONGC":       {"yf": "ONGC.NS",       "eodhd": "ONGC.NSE",       "sector": "Energy/Upstream",      "group": "winner"},
    "OIL":        {"yf": "OIL.NS",        "eodhd": "OIL.NSE",        "sector": "Energy/Upstream",      "group": "winner"},
    "RELIANCE":   {"yf": "RELIANCE.NS",   "eodhd": "RELIANCE.NSE",   "sector": "Energy/Conglomerate",  "group": "winner"},
    "COALINDIA":  {"yf": "COALINDIA.NS",  "eodhd": "COALINDIA.NSE",  "sector": "Energy/Coal",          "group": "winner"},
    "SUNPHARMA":  {"yf": "SUNPHARMA.NS",  "eodhd": "SUNPHARMA.NSE",  "sector": "Pharma",               "group": "winner"},
    "DRREDDY":    {"yf": "DRREDDY.NS",    "eodhd": "DRREDDY.NSE",    "sector": "Pharma",               "group": "winner"},
    "BHARATFORG": {"yf": "BHARATFORG.NS", "eodhd": "BHARATFORG.NSE", "sector": "Defense/Forging",      "group": "winner"},
    # Neutral / multi-factor
    "HDFCBANK":   {"yf": "HDFCBANK.NS",   "eodhd": "HDFCBANK.NSE",   "sector": "Banking/Private",      "group": "neutral"},
    "ICICIBANK":  {"yf": "ICICIBANK.NS",  "eodhd": "ICICIBANK.NSE",  "sector": "Banking/Private",      "group": "neutral"},
    "TMPV": {"yf": "TMPV.NS",       "eodhd": "TMPV.NSE", "sector": "Auto",                 "group": "loser"},  # Tata Motors demerged Oct 2025 → TMPV (passenger vehicles)
    "M&M":        {"yf": "M&M.NS",        "eodhd": "M&M.NSE",        "sector": "Auto/Farm",            "group": "neutral"},
    "MARUTI":     {"yf": "MARUTI.NS",     "eodhd": "MARUTI.NSE",     "sector": "Auto/Passenger",       "group": "loser"},
    "ADANIENT":   {"yf": "ADANIENT.NS",   "eodhd": "ADANIENT.NSE",   "sector": "Conglomerate",         "group": "neutral"},
    # Losers (downstream OMCs + IT)
    "IOC":        {"yf": "IOC.NS",        "eodhd": "IOC.NSE",        "sector": "Energy/Downstream",    "group": "loser"},
    "BPCL":       {"yf": "BPCL.NS",       "eodhd": "BPCL.NSE",       "sector": "Energy/Downstream",    "group": "loser"},
    "HPCL":       {"yf": "HINDPETRO.NS",  "eodhd": "HINDPETRO.NSE",  "sector": "Energy/Downstream",    "group": "loser"},
    "TCS":        {"yf": "TCS.NS",        "eodhd": "TCS.NSE",        "sector": "IT Services",          "group": "loser"},
    "INFY":       {"yf": "INFY.NS",       "eodhd": "INFY.NSE",       "sector": "IT Services",          "group": "loser"},
    "WIPRO":      {"yf": "WIPRO.NS",      "eodhd": "WIPRO.NSE",      "sector": "IT Services",          "group": "loser"},
}

# === INDIA SPREAD PAIRS ===
INDIA_SPREAD_PAIRS = [
    # ── Active spread universe ──────────────────────────────────────────
    {
        "name": "Upstream vs Downstream",
        "long": ["ONGC", "OIL"],
        "short": ["IOC", "BPCL"],
        "triggers": ["oil_up", "escalation", "hormuz", "sanctions", "trump_threat"],
    },
    {
        "name": "Defence vs IT",
        "long": ["HAL", "BEL", "BDL"],
        "short": ["TCS", "INFY", "WIPRO"],
        "triggers": ["escalation", "defense_spend", "sanctions", "trump_threat", "hormuz", "oil_positive"],
    },
    {
        "name": "Reliance vs OMCs",
        "long": ["RELIANCE"],
        "short": ["BPCL", "IOC"],
        "triggers": ["oil_up", "refining_margin", "escalation"],
    },
    {
        "name": "Coal vs OMCs",
        "long": ["COALINDIA"],
        "short": ["BPCL", "IOC"],
        "triggers": ["energy_crisis", "oil_up", "escalation", "hormuz", "oil_positive"],
    },
    # ── Phase 2 spreads (expanding universe) ────────────────────────────
    {
        "name": "Pharma vs Cyclicals",
        "long": ["SUNPHARMA", "DRREDDY"],
        "short": ["TMPV", "M&M"],
        "triggers": ["escalation", "de_escalation", "diplomacy"],
    },
    {
        "name": "PSU Commodity vs Banks",
        "long": ["ONGC", "COALINDIA"],      # proxy for commodity/haven
        "short": ["HDFCBANK", "ICICIBANK"],
        "triggers": ["escalation", "sanctions", "hormuz"],
    },
    {
        "name": "Defence vs Auto",
        "long": ["HAL", "BEL"],
        "short": ["TMPV", "MARUTI"],
        "triggers": ["escalation", "defense_spend", "trump_threat"],
    },
    {
        "name": "PSU Energy vs Private",
        "long": ["ONGC", "COALINDIA", "OIL"],
        "short": ["RELIANCE", "ADANIENT"],
        "triggers": ["oil_up", "escalation", "hormuz"],
    },
    # ── ETF-backtested spreads (from autoresearch regime engine) ─────
    {
        "name": "Pharma vs Banks",
        "long": ["SUNPHARMA", "DRREDDY"],
        "short": ["HDFCBANK", "ICICIBANK"],
        "triggers": ["rbi_policy", "de_escalation", "diplomacy"],
    },
    {
        "name": "Banks vs IT",
        "long": ["HDFCBANK", "ICICIBANK"],
        "short": ["TCS", "INFY", "WIPRO"],
        "triggers": ["rbi_policy", "de_escalation", "diplomacy"],
    },
    # ── Domestic policy spreads ────────────────────────────────────────
    {
        "name": "PSU NBFC vs Private Banks",
        "long": ["HUDCO", "NHPC"],
        "short": ["HDFCBANK", "ICICIBANK"],
        "triggers": ["rbi_policy", "nbfc_reform"],
    },
    {
        "name": "EV Plays vs ICE Auto",
        "long": ["TMPV", "M&M"],
        "short": ["MARUTI"],
        "triggers": ["ev_policy"],
    },
    {
        "name": "Infra Capex Beneficiaries",
        "long": ["ULTRACEMCO", "AMBUJACEM"],
        "short": ["ADANIENT"],
        "triggers": ["infra_capex", "tax_reform"],
    },
]

# === EVENT TAXONOMY (political event → expected market direction) ===
EVENT_TAXONOMY = {
    "escalation":    {"oil": "up",   "defense": "up",   "it": "down",  "downstream": "down"},
    "de_escalation": {"oil": "down", "defense": "down", "it": "up",    "downstream": "up"},
    "ceasefire":     {"oil": "down", "defense": "down", "it": "up",    "downstream": "up"},
    "oil_positive":  {"oil": "up",   "defense": "flat", "it": "down",  "downstream": "down"},
    "oil_negative":  {"oil": "down", "defense": "flat", "it": "up",    "downstream": "up"},
    "sanctions":     {"oil": "up",   "defense": "up",   "it": "down",  "downstream": "down"},
    "hormuz":        {"oil": "up",   "defense": "flat", "it": "down",  "downstream": "down"},
    "defense_spend": {"oil": "flat", "defense": "up",   "it": "flat",  "downstream": "flat"},
    "trump_threat":  {"oil": "up",   "defense": "up",   "it": "down",  "downstream": "down"},
    "diplomacy":     {"oil": "down", "defense": "down", "it": "up",    "downstream": "up"},
    # ── Domestic regulatory / policy ──────────────────────────────────
    "rbi_policy":    {"banking": "move", "nbfc": "move", "rate_sensitive": "move", "it": "flat"},
    "nbfc_reform":   {"nbfc": "up",     "banking": "flat", "housing_fin": "up"},
    "ev_policy":     {"auto_ev": "up",   "auto_ice": "down", "battery": "up"},
    "tax_reform":    {"broad_market": "move", "fmcg": "move", "auto": "move"},
    "infra_capex":   {"infra": "up",    "cement": "up", "steel": "up", "capital_goods": "up"},
    "sebi_regulation": {"broad_market": "move", "brokers": "move"},
}

# === ASIAN MARKET CASCADE (pre-market signals for India) ===
ASIA_INDICES = {
    "Nikkei 225": {"yf": "^N225",     "currency": "JPY", "opens_ist": "05:30"},
    "KOSPI":      {"yf": "^KS11",     "currency": "KRW", "opens_ist": "05:30"},
    "ASX 200":    {"yf": "^AXJO",     "currency": "AUD", "opens_ist": "05:30"},
    "STI":        {"yf": "^STI",      "currency": "SGD", "opens_ist": "06:30"},
    "S&P Futures":{"yf": "ES=F",      "currency": "USD", "opens_ist": "overnight"},
}

ASIA_DEFENCE_STOCKS = {
    "7012.T":    {"name": "Kawasaki Heavy",    "market": "Japan"},
    "7011.T":    {"name": "MHI",               "market": "Japan"},
    "012450.KS": {"name": "Hanwha Aerospace",  "market": "Korea"},
    "S63.SI":    {"name": "ST Engineering",    "market": "Singapore"},
}

ASIA_INDIA_CASCADE = {
    "nikkei_defence_up":   {"india_long": ["HAL", "BEL"],          "india_short": ["TCS", "INFY"]},
    "kospi_defence_up":    {"india_long": ["HAL", "BEL", "BDL"],   "india_short": ["WIPRO"]},
    "asian_energy_up":     {"india_long": ["ONGC", "OIL", "RELIANCE"], "india_short": ["IOC", "BPCL"]},
    "asian_broad_selloff": {"india_long": ["COALINDIA", "SUNPHARMA"], "india_short": ["IOC", "BPCL"]},
    "oil_above_100":       {"india_long": ["ONGC", "OIL"],         "india_short": ["IOC", "BPCL"]},
    "usd_inr_spike":       {"india_long": ["TCS", "INFY"],         "india_short": ["IOC"]},
}

# === NEWS RSS FEEDS ===
NEWS_RSS_FEEDS = [
    # Major wire services
    "https://feeds.reuters.com/reuters/worldNews",
    "http://feeds.bbci.co.uk/news/world/rss.xml",
    # Middle East focused
    "https://www.aljazeera.com/xml/rss/all.xml",
    "https://www.middleeasteye.net/rss",
    # Financial / markets
    "https://www.cnbctv18.com/commonfeeds/v1/cne/rss/world.xml",
    # India focused
    "https://www.livemint.com/rss/news",
    # Energy / oil
    "https://oilprice.com/rss/main",
]

NEWS_KEYWORDS = [
    # Countries & regions
    "iran", "israel", "middle east", "persian gulf", "red sea",
    "yemen", "lebanon", "syria", "iraq",
    # Key leaders (all voices that move markets)
    "trump", "netanyahu", "khamenei", "putin", "xi jinping",
    "erdogan", "mbs", "houthi", "hezbollah", "nasrallah",
    "gallant", "katz", "irgc", "modi", "guterres",
    # Military / conflict
    "hormuz", "ceasefire", "sanctions", "military strike",
    "missile", "drone strike", "naval", "blockade",
    "escalat", "retaliat", "war", "invasion",
    # Oil / energy
    "oil price", "crude oil", "brent", "opec",
    "oil surge", "oil crash", "energy crisis",
    "tanker", "shipping", "pipeline",
    # Defense
    "defense budget", "defence budget", "arms deal", "rearm",
    # Diplomacy
    "nuclear deal", "peace talk", "ceasefire", "truce",
    "diplomatic", "negotiat", "summit",
]

# === SIGNAL ENGINE CONFIG ===
SIGNAL_STOP_LOSS_PCT = 10.0
SIGNAL_TRAILING_STOP_ACTIVATE_PCT = 3.0   # Trailing stop activates when spread P&L >= 3%
SIGNAL_TRAILING_STOP_DISTANCE_PCT = 2.0   # Once active, exit if P&L drops 2% from peak
SIGNAL_CONFIDENCE_THRESHOLD = 0.6
SIGNAL_HIT_RATE_THRESHOLD = 0.65
SIGNAL_MIN_PRECEDENTS = 3
POLL_INTERVAL_MINUTES = 30
MARKET_HOURS_IST = {"open": "09:15", "close": "15:30"}
PREMARKET_SCAN_IST = "08:30"
MIDDAY_WINDOW_IST = {"start": "12:10", "end": "12:50"}
OPEN_CAPTURE_IST = "09:22"
EOD_REVIEW_IST = "15:45"

# === POSITION SIZING ===
# Reference unit: ₹10,000 per side (long ₹10K + short ₹10K = ₹20K total exposure)
# Subscribers scale to their own book. We report P&L in both % and ₹ terms.
UNIT_SIZE_INR = 10_000            # ₹10,000 per side per spread
SIGNAL_UNITS = 1.0                # SIGNAL tier → 1 full unit (₹10K per side)
EXPLORING_UNITS = 0.5             # EXPLORING tier → half unit (₹5K per side)
NO_DATA_UNITS = 0.0               # NO_DATA tier → not traded, tracked only

# === SIGNAL TIERS ===
# SIGNAL (🟢): passes all backtest gates → trade-worthy, 1 unit
# EXPLORING (🟡): has data but below gates → half unit, tracked for promotion
# NO_DATA (⚪): no backtest data → not traded, paper-tracked only
TIER_SIGNAL = "SIGNAL"
TIER_EXPLORING = "EXPLORING"
TIER_NO_DATA = "NO_DATA"
TIER_PROMOTION_MIN_SIGNALS = 20   # need 20+ closed EXPLORING trades to consider promotion
TIER_PROMOTION_WIN_RATE = 0.65    # EXPLORING → SIGNAL if win rate >= 65%

# === REGIME DETECTION ===
REGIME_RISK_ON = "RISK_ON"
REGIME_RISK_OFF = "RISK_OFF"
REGIME_MIXED = "MIXED"

# Risk ON regime: escalation day → long defence/upstream, short IT/downstream
# Risk OFF regime: de-escalation day → reverse all spreads
REGIME_SPREADS = {
    "RISK_ON": {
        "primary": ["Upstream vs Downstream", "Defence vs IT"],
        "secondary": ["Coal vs OMCs"],
        "description": "Escalation day — long defence+upstream, short IT+downstream",
    },
    "RISK_OFF": {
        "primary": ["Upstream vs Downstream (REVERSED)", "Defence vs IT (REVERSED)"],
        "secondary": ["Reliance Pivot"],
        "description": "De-escalation day — reverse spreads, long IT+downstream",
    },
    "MIXED": {
        "primary": [],
        "secondary": [],
        "description": "Conflicting signals — hold existing positions, trailing stops active",
    },
}

# Regime scoring weights
REGIME_WEIGHT_POLITICAL = 0.4
REGIME_WEIGHT_OIL = 0.3
REGIME_WEIGHT_ASIAN = 0.3
REGIME_THRESHOLD = 0.3  # score > +0.3 → RISK_ON, < -0.3 → RISK_OFF

# === CORRELATION ENGINE CONFIG ===
CORRELATION_CACHE_HOURS = 24
CORRELATION_MIN_EVENTS = 5
CORRELATION_THRESHOLDS = [-5.0, -3.0, -2.0, 2.0, 3.0, 5.0]

# === TELEGRAM CONFIG (set in .env) ===
TELEGRAM_BOT_TOKEN = None  # Override from .env
TELEGRAM_CHAT_ID = None    # Override from .env

# === F&O UNIVERSE ===
from pathlib import Path as _Path
FNO_UNIVERSE_FILE = _Path(__file__).parent.parent / "opus" / "config" / "fno_stocks.json"

FNO_TOP_40 = [
    "RELIANCE", "HDFCBANK", "ICICIBANK", "INFY", "TCS",
    "BHARTIARTL", "SBIN", "BAJFINANCE", "AXISBANK", "KOTAKBANK",
    "LT", "MARUTI", "HCLTECH", "SUNPHARMA", "TITAN",
    "ADANIENT", "ADANIPORTS", "TATASTEEL", "HINDUNILVR", "ITC",
    "WIPRO", "CIPLA", "COALINDIA", "HAL", "BEL",
    "NTPC", "ONGC", "GAIL", "BPCL", "M&M",
    "ASIANPAINT", "TECHM", "DLF", "VEDL", "INDIGO",
    "DRREDDY", "JSWSTEEL", "TATAPOWER", "PNB", "HDFCLIFE",
]

# === NEWS INTELLIGENCE CATEGORIES ===
NEWS_CATEGORIES = {
    "merger_acquisition": {
        "keywords": ["acquire", "acquisition", "merger", "takeover", "buyout", "amalgamation", "demerger"],
        "impact": "HIGH", "default_shelf_life_days": 5,
    },
    "results_announcement": {
        "keywords": ["quarterly result", "Q1 result", "Q2 result", "Q3 result", "Q4 result",
                     "profit rises", "profit falls", "net profit", "revenue growth", "PAT"],
        "impact": "HIGH", "default_shelf_life_days": 3,
    },
    "block_deal": {
        "keywords": ["block deal", "bulk deal", "stake sale", "promoter sell", "FII buying"],
        "impact": "MEDIUM", "default_shelf_life_days": 2,
    },
    "rating_action": {
        "keywords": ["upgrade", "downgrade", "target price", "price target", "initiating coverage",
                     "outperform", "underperform", "overweight", "underweight"],
        "impact": "MEDIUM", "default_shelf_life_days": 3,
    },
    "fraud_investigation": {
        "keywords": ["fraud", "SEBI penalty", "investigation", "insider trading", "manipulation",
                     "default", "NPA", "scam", "irregularities"],
        "impact": "HIGH", "default_shelf_life_days": 5,
    },
    "govt_policy": {
        "keywords": ["RBI", "repo rate", "rate cut", "rate hike", "monetary policy",
                     "GST", "fiscal", "budget", "subsidy", "tariff", "import duty",
                     "FAME", "EV policy", "PLI scheme", "disinvestment"],
        "impact": "HIGH", "default_shelf_life_days": 5,
    },
    "sector_regulation": {
        "keywords": ["SEBI regulation", "TRAI", "FSSAI", "drug pricing", "DPCO",
                     "mining policy", "coal auction", "spectrum auction", "licence"],
        "impact": "HIGH", "default_shelf_life_days": 5,
    },
    "management_change": {
        "keywords": ["CEO appoint", "MD appoint", "CFO resign", "board member",
                     "promoter", "succession", "chairman"],
        "impact": "MEDIUM", "default_shelf_life_days": 2,
    },
    "capex_expansion": {
        "keywords": ["capex", "expansion", "new plant", "capacity addition", "greenfield",
                     "brownfield", "order win", "contract win", "order book"],
        "impact": "MEDIUM", "default_shelf_life_days": 3,
    },
}

# === POLICY KEYWORDS (policy → affected spreads mapping) ===
POLICY_KEYWORDS = {
    "oil_policy": {
        "keywords": ["oil price", "crude oil", "OPEC", "Hormuz", "fuel price", "petrol price",
                     "diesel price", "oil import", "strategic reserve"],
        "spreads": ["Upstream vs Downstream", "Coal vs OMCs", "PSU Energy vs Private"],
        "default_direction": "long_energy",
    },
    "defence_policy": {
        "keywords": ["defence budget", "defense budget", "military spend", "arms deal",
                     "border tension", "surgical strike", "ceasefire violation"],
        "spreads": ["Defence vs IT", "Defence vs Auto"],
        "default_direction": "long_defence",
    },
    "rbi_monetary": {
        "keywords": ["repo rate", "rate cut", "rate hike", "monetary policy", "RBI MPC",
                     "liquidity injection", "CRR", "SLR"],
        "spreads": ["Banks vs IT", "Pharma vs Banks", "PSU NBFC vs Private Banks"],
        "default_direction": "context_dependent",
    },
    "ev_auto": {
        "keywords": ["EV policy", "electric vehicle", "FAME scheme", "battery policy",
                     "EV subsidy", "charging infra"],
        "spreads": ["EV Plays vs ICE Auto"],
        "default_direction": "long_ev",
    },
    "infra_capex": {
        "keywords": ["infrastructure spend", "capex push", "highway project", "smart city",
                     "PLI scheme", "production linked"],
        "spreads": ["Infra Capex Beneficiaries"],
        "default_direction": "long_infra",
    },
    "sanctions_geopolitics": {
        "keywords": ["sanctions", "trade war", "tariff war", "export ban", "import restriction",
                     "Trump threat", "escalation"],
        "spreads": ["Upstream vs Downstream", "Defence vs IT", "PSU Commodity vs Banks"],
        "default_direction": "risk_off",
    },
}

# === REFERENCE DATE (war start) ===
WAR_START_DATE = "2026-02-28"
