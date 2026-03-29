"""
Anka Research Pipeline — Configuration
All tickers, indices, FX pairs, and commodities tracked across 8 global markets.
"""

# === INDEX TICKERS (EODHD format: SYMBOL.EXCHANGE) ===
INDICES = {
    "S&P 500":    {"eodhd": "GSPC.INDX",   "yf": "^GSPC",    "currency": "USD"},
    "FTSE 100":   {"eodhd": "FTSE.INDX",   "yf": "^FTSE",    "currency": "GBP"},
    "CAC 40":     {"eodhd": "FCHI.INDX",   "yf": "^FCHI",    "currency": "EUR"},
    "DAX":        {"eodhd": "GDAXI.INDX",  "yf": "^GDAXI",   "currency": "EUR"},
    "Nifty 50":   {"eodhd": "NSEI.INDX",   "yf": "^NSEI",    "currency": "INR"},
    "KOSPI":      {"eodhd": "KS11.INDX",   "yf": "^KS11",    "currency": "KRW"},
    "Nikkei 225": {"eodhd": "N225.INDX",   "yf": "^N225",    "currency": "JPY"},
    "CSI 300":    {"eodhd": "CSI300.INDX",  "yf": "000300.SS", "currency": "CNY"},
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
    "HAL":        {"yf": "HAL.NS",        "sector": "Defense/Aerospace",    "group": "winner"},
    "BEL":        {"yf": "BEL.NS",        "sector": "Defense Electronics",  "group": "winner"},
    "BDL":        {"yf": "BDL.NS",        "sector": "Defense/Missiles",     "group": "winner"},
    "MTAR":       {"yf": "MTARTECH.NS",   "sector": "Defense/Precision",    "group": "winner"},
    "ONGC":       {"yf": "ONGC.NS",       "sector": "Energy/Upstream",      "group": "winner"},
    "OIL":        {"yf": "OIL.NS",        "sector": "Energy/Upstream",      "group": "winner"},
    "RELIANCE":   {"yf": "RELIANCE.NS",   "sector": "Energy/Conglomerate",  "group": "winner"},
    "COALINDIA":  {"yf": "COALINDIA.NS",  "sector": "Energy/Coal",          "group": "winner"},
    "SUNPHARMA":  {"yf": "SUNPHARMA.NS",  "sector": "Pharma",              "group": "winner"},
    "BHARATFORG": {"yf": "BHARATFORG.NS", "sector": "Defense/Forging",      "group": "winner"},
    # Losers (downstream OMCs + IT)
    "IOC":        {"yf": "IOC.NS",        "sector": "Energy/Downstream",    "group": "loser"},
    "BPCL":       {"yf": "BPCL.NS",       "sector": "Energy/Downstream",    "group": "loser"},
    "HPCL":       {"yf": "HINDPETRO.NS",  "sector": "Energy/Downstream",    "group": "loser"},
    "TCS":        {"yf": "TCS.NS",        "sector": "IT Services",          "group": "loser"},
    "INFY":       {"yf": "INFY.NS",       "sector": "IT Services",          "group": "loser"},
    "WIPRO":      {"yf": "WIPRO.NS",      "sector": "IT Services",          "group": "loser"},
}

# === INDIA SPREAD PAIRS ===
INDIA_SPREAD_PAIRS = [
    {
        "name": "Upstream vs Downstream",
        "long": ["ONGC", "OIL"],
        "short": ["IOC", "BPCL", "HPCL"],
        "triggers": ["oil_up", "escalation", "hormuz", "sanctions", "trump_threat"],
    },
    {
        "name": "Defence vs IT",
        "long": ["HAL", "BEL", "BDL"],
        "short": ["TCS", "INFY", "WIPRO"],
        "triggers": ["escalation", "defense_spend", "sanctions", "trump_threat", "hormuz", "oil_positive"],
    },
    {
        "name": "Reliance Pivot",
        "long": ["RELIANCE"],
        "short": ["HPCL", "IOC"],
        "triggers": ["oil_up", "refining_margin", "escalation"],
    },
    {
        "name": "Coal vs OMCs",
        "long": ["COALINDIA"],
        "short": ["BPCL", "HPCL"],
        "triggers": ["energy_crisis", "oil_up", "escalation", "hormuz", "oil_positive"],
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
    "asian_broad_selloff": {"india_long": ["COALINDIA", "SUNPHARMA"], "india_short": ["HPCL", "BPCL"]},
    "oil_above_100":       {"india_long": ["ONGC", "OIL"],         "india_short": ["IOC", "BPCL", "HPCL"]},
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
SIGNAL_CONFIDENCE_THRESHOLD = 0.6
SIGNAL_HIT_RATE_THRESHOLD = 0.65
SIGNAL_MIN_PRECEDENTS = 3
POLL_INTERVAL_MINUTES = 30
MARKET_HOURS_IST = {"open": "09:15", "close": "15:30"}
PREMARKET_SCAN_IST = "08:30"

# === TELEGRAM CONFIG (set in .env) ===
TELEGRAM_BOT_TOKEN = None  # Override from .env
TELEGRAM_CHAT_ID = None    # Override from .env

# === REFERENCE DATE (war start) ===
WAR_START_DATE = "2026-02-28"
