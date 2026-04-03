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
    "TATAMOTORS": {"yf": "TMPV.NS",       "eodhd": "TATAMOTORS.NSE", "sector": "Auto",                 "group": "loser"},  # Tata Motors demerged Oct 2025 → TMPV (passenger vehicles)
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
    # Component C — Macro universe (PSU banks, metals, FMCG, NBFC)
    "SBI":        {"yf": "SBIN.NS",       "eodhd": "SBIN.NSE",       "sector": "Banking/PSU",          "group": "neutral"},
    "BANKBARODA": {"yf": "BANKBARODA.NS", "eodhd": "BANKBARODA.NSE", "sector": "Banking/PSU",          "group": "neutral"},
    "AXISBANK":   {"yf": "AXISBANK.NS",   "eodhd": "AXISBANK.NSE",   "sector": "Banking/Private",      "group": "neutral"},
    "HINDALCO":   {"yf": "HINDALCO.NS",   "eodhd": "HINDALCO.NSE",   "sector": "Metals/Aluminium",     "group": "winner"},
    "TATASTEEL":  {"yf": "TATASTEEL.NS",  "eodhd": "TATASTEEL.NSE",  "sector": "Metals/Steel",         "group": "winner"},
    "JSPL":       {"yf": "JINDALSTEL.NS", "eodhd": "JSPL.NSE",       "sector": "Metals/Steel PSU",     "group": "winner"},
    "HUL":        {"yf": "HINDUNILVR.NS", "eodhd": "HINDUNILVR.NSE", "sector": "FMCG/Defensive",       "group": "neutral"},
    "ITC":        {"yf": "ITC.NS",        "eodhd": "ITC.NSE",        "sector": "FMCG/Conglomerate",    "group": "neutral"},
    "BAJFINANCE": {"yf": "BAJFINANCE.NS", "eodhd": "BAJFINANCE.NSE", "sector": "NBFC/Private",         "group": "loser"},
    # INR/FII macro universe — broader IT exporters, pharma exporters, FII-sensitive
    "HCLTECH":    {"yf": "HCLTECH.NS",    "eodhd": "HCLTECH.NSE",    "sector": "IT Services",          "group": "loser"},
    "TECHM":      {"yf": "TECHM.NS",      "eodhd": "TECHM.NSE",      "sector": "IT Services",          "group": "loser"},
    "LTIM":       {"yf": "LTIM.NS",       "eodhd": "LTIM.NSE",       "sector": "IT Services/Mid",      "group": "loser"},
    "PERSISTENT": {"yf": "PERSISTENT.NS", "eodhd": "PERSISTENT.NSE", "sector": "IT Services/Mid",      "group": "loser"},
    "CIPLA":      {"yf": "CIPLA.NS",      "eodhd": "CIPLA.NSE",      "sector": "Pharma/Export",        "group": "winner"},
    "DIVISLAB":   {"yf": "DIVISLAB.NS",   "eodhd": "DIVISLAB.NSE",   "sector": "Pharma/Export",        "group": "winner"},
    "KOTAKBANK":  {"yf": "KOTAKBANK.NS",  "eodhd": "KOTAKBANK.NSE",  "sector": "Banking/Private",      "group": "neutral"},
    "DLF":        {"yf": "DLF.NS",        "eodhd": "DLF.NSE",        "sector": "Real Estate",          "group": "loser"},
    "TITAN":      {"yf": "TITAN.NS",      "eodhd": "TITAN.NSE",      "sector": "Consumer/Discretionary","group": "loser"},
    "ASIANPAINT": {"yf": "ASIANPAINT.NS", "eodhd": "ASIANPAINT.NSE", "sector": "Consumer/Domestic",    "group": "loser"},
    # ── ARCBE expansion — Gulf/ME exposed (hypothesis: underperform in ME stress)
    "SOBHA":       {"yf": "SOBHA.NS",       "eodhd": "SOBHA.NSE",       "sector": "Real Estate/Gulf",     "group": "loser",   "gulf_exposed": True},
    "ASTERDM":     {"yf": "ASTERDM.NS",     "eodhd": "ASTERDM.NSE",     "sector": "Healthcare/Gulf",      "group": "loser",   "gulf_exposed": True},
    "LT":          {"yf": "LT.NS",          "eodhd": "LT.NSE",          "sector": "EPC/Gulf",             "group": "loser",   "gulf_exposed": True},
    "KECINTL":     {"yf": "KECINTL.NS",     "eodhd": "KECINTL.NSE",     "sector": "EPC/Transmission",     "group": "loser",   "gulf_exposed": True},
    "INTERGLOBE":  {"yf": "INDIGO.NS",      "eodhd": "INDIGO.NSE",      "sector": "Aviation",             "group": "loser",   "gulf_exposed": True},
    "FEDERALBNK":  {"yf": "FEDERALBNK.NS",  "eodhd": "FEDERALBNK.NSE",  "sector": "Banking/NRI",          "group": "neutral", "gulf_exposed": True},
    # ── ARCBE expansion — Domestic-pure (hypothesis: outperform, insulated from ME)
    "GODREJPROP":  {"yf": "GODREJPROP.NS",  "eodhd": "GODREJPROP.NSE",  "sector": "Real Estate/Domestic", "group": "neutral", "gulf_exposed": False},
    "OBEROIRLTY":  {"yf": "OBEROIRLTY.NS",  "eodhd": "OBEROIRLTY.NSE",  "sector": "Real Estate/Premium",  "group": "neutral", "gulf_exposed": False},
    "LICHSGFIN":   {"yf": "LICHSGFIN.NS",   "eodhd": "LICHSGFIN.NSE",   "sector": "Housing Finance",      "group": "neutral", "gulf_exposed": False},
    "NBCC":        {"yf": "NBCC.NS",        "eodhd": "NBCC.NSE",        "sector": "Construction/PSU",     "group": "winner",  "gulf_exposed": False},
    "SIEMENS":     {"yf": "SIEMENS.NS",     "eodhd": "SIEMENS.NSE",     "sector": "Capital Goods",        "group": "neutral", "gulf_exposed": False},
    "BHARTIARTL":  {"yf": "BHARTIARTL.NS",  "eodhd": "BHARTIARTL.NSE",  "sector": "Telecom",              "group": "neutral", "gulf_exposed": False},
    "NTPC":        {"yf": "NTPC.NS",        "eodhd": "NTPC.NSE",        "sector": "Power/PSU",            "group": "winner",  "gulf_exposed": False},
    "POWERGRID":   {"yf": "POWERGRID.NS",   "eodhd": "POWERGRID.NSE",   "sector": "Power/Transmission",   "group": "winner",  "gulf_exposed": False},
    "BRITANNIA":   {"yf": "BRITANNIA.NS",   "eodhd": "BRITANNIA.NSE",   "sector": "FMCG/Staples",         "group": "neutral", "gulf_exposed": False},
    "DABUR":       {"yf": "DABUR.NS",       "eodhd": "DABUR.NSE",       "sector": "FMCG/Health",          "group": "neutral", "gulf_exposed": False},
    "NMDC":        {"yf": "NMDC.NS",        "eodhd": "NMDC.NSE",        "sector": "Mining/IronOre",        "group": "winner",  "gulf_exposed": False},
    "SAIL":        {"yf": "SAIL.NS",        "eodhd": "SAIL.NSE",        "sector": "Metals/Steel PSU",     "group": "neutral", "gulf_exposed": False},
    "VEDL":        {"yf": "VEDL.NS",        "eodhd": "VEDL.NSE",        "sector": "Metals/Diversified",   "group": "neutral", "gulf_exposed": False},
    "HAVELLS":     {"yf": "HAVELLS.NS",     "eodhd": "HAVELLS.NSE",     "sector": "Consumer Durables",    "group": "neutral", "gulf_exposed": False},
    "ULTRACEMCO":  {"yf": "ULTRACEMCO.NS",  "eodhd": "ULTRACEMCO.NSE",  "sector": "Cement",               "group": "neutral", "gulf_exposed": False},
    "AMBUJACEM":   {"yf": "AMBUJACEM.NS",   "eodhd": "AMBUJACEM.NSE",   "sector": "Cement",               "group": "neutral", "gulf_exposed": False},
    "APOLLOHOSP":  {"yf": "APOLLOHOSP.NS",  "eodhd": "APOLLOHOSP.NSE",  "sector": "Healthcare/Domestic",  "group": "neutral", "gulf_exposed": False},
    "TATAPOWER":   {"yf": "TATAPOWER.NS",   "eodhd": "TATAPOWER.NSE",   "sector": "Power/Renewable",      "group": "neutral", "gulf_exposed": False},
    "MAXHEALTH":   {"yf": "MAXHEALTH.NS",   "eodhd": "MAXHEALTH.NSE",   "sector": "Healthcare/Domestic",  "group": "neutral", "gulf_exposed": False},
}

# === INDIA SPREAD PAIRS ===
INDIA_SPREAD_PAIRS = [
    # ── Active spread universe ──────────────────────────────────────────
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
    # ── Phase 2 spreads (expanding universe) ────────────────────────────
    {
        "name": "Pharma vs Cyclicals",
        "long": ["SUNPHARMA", "DRREDDY"],
        "short": ["TATAMOTORS", "M&M"],
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
        "short": ["TATAMOTORS", "MARUTI"],
        "triggers": ["escalation", "defense_spend", "trump_threat"],
    },
    {
        "name": "PSU Energy vs Private",
        "long": ["ONGC", "COALINDIA", "OIL"],
        "short": ["RELIANCE", "ADANIENT"],
        "triggers": ["oil_up", "escalation", "hormuz"],
    },
    # ── Component C — Macro regime spreads ──────────────────────────────
    {
        "name": "PSU Banks vs Private Banks",
        "long": ["SBI", "BANKBARODA"],
        "short": ["HDFCBANK", "ICICIBANK", "AXISBANK"],
        "triggers": ["MACRO_STRESS", "escalation", "sanctions", "rbi_rate_hike", "india_stress"],
    },
    {
        "name": "Metals vs IT",
        "long": ["HINDALCO", "TATASTEEL"],
        "short": ["TCS", "INFY"],
        "triggers": ["MACRO_STRESS", "escalation", "sanctions", "weak_dollar"],
    },
    {
        "name": "FMCG vs Cyclicals",
        "long": ["HUL", "ITC"],
        "short": ["TATAMOTORS", "M&M"],
        "triggers": ["MACRO_STRESS", "india_stress", "us_recession"],
    },
    {
        "name": "Metals vs Auto",
        "long": ["HINDALCO", "JSPL"],
        "short": ["TATAMOTORS", "MARUTI"],
        "triggers": ["MACRO_STRESS", "oil_positive", "weak_dollar"],
    },
    {
        "name": "Private Finance vs PSU Energy",
        "long": ["BAJFINANCE", "HDFCBANK"],
        "short": ["ONGC", "COALINDIA"],
        "triggers": ["de_escalation", "diplomacy", "MACRO_EASY", "rbi_rate_cut", "fii_buying"],
    },
    # ── INR / FII macro themes (broader universe) ────────────────────────
    {
        "name": "IT Exporters vs Private Banks",
        "long": ["TCS", "INFY", "WIPRO", "HCLTECH", "TECHM"],
        "short": ["HDFCBANK", "ICICIBANK", "KOTAKBANK"],
        "triggers": ["INR_WEAKNESS", "fii_outflow", "usd_inr_spike", "strong_dollar", "fii_selling"],
        "notes": "INR weakening favours dollar earners over domestic rate-sensitives",
    },
    {
        "name": "Pharma Exporters vs Domestic Consumer",
        "long": ["SUNPHARMA", "DRREDDY", "CIPLA", "DIVISLAB"],
        "short": ["HUL", "ITC", "ASIANPAINT"],
        "triggers": ["INR_WEAKNESS", "fii_outflow", "MACRO_STRESS", "strong_dollar", "india_stress"],
        "notes": "INR weakness + global risk-off: export pharma defensive vs domestic consumption",
    },
    {
        "name": "FII Exit Canary",
        "long": ["TCS", "INFY", "SUNPHARMA"],
        "short": ["DLF", "TITAN", "TATAMOTORS"],
        "triggers": ["fii_outflow", "MACRO_STRESS", "fii_selling"],
        "notes": "FII sustained outflow: dollar earners + defensives vs FII-darling domestic cyclicals",
    },
    # ── Weak/Strong Dollar spreads ─────────────────────────────────────
    {
        "name": "Domestic Finance vs Export IT",
        "long": ["HDFCBANK", "ICICIBANK", "KOTAKBANK"],
        "short": ["TCS", "INFY", "WIPRO"],
        "triggers": ["weak_dollar", "fii_buying", "rbi_rate_cut"],
        "notes": "Weak dollar = EM inflows, banks rally; IT loses USD translation benefit",
    },
    {
        "name": "Real Assets vs Dollar Earners",
        "long": ["HINDALCO", "TATASTEEL", "ONGC"],
        "short": ["TCS", "INFY", "HCLTECH"],
        "triggers": ["weak_dollar", "fii_buying"],
        "notes": "Weak dollar lifts commodity prices in USD; IT exporters lose FX tailwind",
    },
    {
        "name": "IT Exporters vs Auto",
        "long": ["TCS", "INFY", "WIPRO", "HCLTECH"],
        "short": ["TATAMOTORS", "MARUTI", "M&M"],
        "triggers": ["strong_dollar", "us_recession"],
        "notes": "Strong dollar = IT earns more in INR terms; auto hit by input cost + demand",
    },
    # ── RBI rate action spreads ────────────────────────────────────────
    {
        "name": "Rate Beneficiaries vs Upstream",
        "long": ["BAJFINANCE", "HDFCBANK", "DLF"],
        "short": ["ONGC", "COALINDIA"],
        "triggers": ["rbi_rate_cut", "fii_buying"],
        "notes": "Rate cuts boost lending margins, real estate demand; commodity plays unrelated",
    },
    {
        "name": "Upstream vs Rate Sensitives",
        "long": ["ONGC", "OIL", "COALINDIA"],
        "short": ["BAJFINANCE", "DLF"],
        "triggers": ["rbi_rate_hike", "india_stress"],
        "notes": "Rate hikes crush leveraged sectors; commodity/upstream defensive",
    },
    # ── India market stress / safety spreads ───────────────────────────
    {
        "name": "Defensive Core vs High Beta",
        "long": ["HUL", "SUNPHARMA", "COALINDIA"],
        "short": ["BAJFINANCE", "DLF", "TITAN"],
        "triggers": ["india_stress", "fii_selling", "MACRO_STRESS"],
        "notes": "Flight to safety: FMCG + pharma + commodity vs leveraged high-beta names",
    },
    {
        "name": "Domestic India vs Export IT",
        "long": ["HUL", "ITC", "HDFCBANK"],
        "short": ["TCS", "INFY", "WIPRO"],
        "triggers": ["us_recession"],
        "notes": "US recession = IT budget cuts; domestic consumption resilient",
    },
    # ── FII flow reversal spreads ──────────────────────────────────────
    {
        "name": "FII Return Play",
        "long": ["HDFCBANK", "ICICIBANK", "BAJFINANCE"],
        "short": ["COALINDIA", "SUNPHARMA", "ITC"],
        "triggers": ["fii_buying", "weak_dollar", "rbi_rate_cut"],
        "notes": "FII return flow: buy underowned private banks/NBFC, sell defensives they never owned",
    },
    {
        "name": "Gold Proxy vs Cyclicals",
        "long": ["SUNPHARMA", "HUL", "ITC"],
        "short": ["HINDALCO", "TATASTEEL", "JSPL"],
        "triggers": ["india_stress", "us_recession", "fii_selling"],
        "notes": "Domestic defensives as gold proxy; metals crash on global demand fear",
    },
]

# === ARCBE — Sector groupings for intra-sector dispersion monitor ===
ARCBE_SECTOR_GROUPS: dict[str, list[str]] = {
    "IT":            ["TCS", "INFY", "WIPRO", "HCLTECH", "TECHM", "LTIM", "PERSISTENT"],
    "Real Estate":   ["DLF", "SOBHA", "GODREJPROP", "OBEROIRLTY"],
    "Banks Private": ["HDFCBANK", "ICICIBANK", "AXISBANK", "KOTAKBANK"],
    "Banks PSU":     ["SBI", "BANKBARODA", "FEDERALBNK"],
    "Metals":        ["HINDALCO", "TATASTEEL", "JSPL", "NMDC", "SAIL", "VEDL"],
    "FMCG":          ["HUL", "ITC", "BRITANNIA", "DABUR"],
    "Energy Upstream": ["ONGC", "OIL", "COALINDIA"],
    "Defence":       ["HAL", "BEL", "BDL", "MTAR", "BHARATFORG"],
    "Power":         ["NTPC", "POWERGRID", "TATAPOWER"],
    "Cement":        ["ULTRACEMCO", "AMBUJACEM"],
    "Healthcare":    ["SUNPHARMA", "DRREDDY", "CIPLA", "DIVISLAB", "APOLLOHOSP", "MAXHEALTH", "ASTERDM"],
}

# === ARCBE — Hypothesis spreads (data must confirm before publishing) ===
ARCBE_HYPOTHESIS_SPREADS: list[dict] = [
    {
        "name": "Domestic vs Gulf Real Estate",
        "long": ["GODREJPROP", "OBEROIRLTY"],
        "short": ["SOBHA"],
        "theme": "Gulf NRI demand risk — domestic RE insulated, SOBHA exposed",
        "expected_driver": "brent",
    },
    {
        "name": "Domestic vs ME-Exposed IT",
        "long": ["TCS", "INFY"],
        "short": ["WIPRO", "HCLTECH", "LTIM"],
        "theme": "ME project revenue risk — US-heavy IT vs ME-project-heavy IT",
        "expected_driver": "brent",
    },
    {
        "name": "Domestic Infra vs Gulf EPC",
        "long": ["NBCC", "SIEMENS"],
        "short": ["LT", "KECINTL"],
        "theme": "ME construction exposure — domestic govt contracts vs Gulf infra",
        "expected_driver": "brent",
    },
    {
        "name": "Domestic Banking vs NRI Corridor",
        "long": ["HDFCBANK", "ICICIBANK"],
        "short": ["FEDERALBNK"],
        "theme": "Gulf remittance risk — Kerala-Gulf NRI deposit base",
        "expected_driver": "brent",
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
    # ── Macro / FX / Rate categories ──────────────────────────────────────
    "weak_dollar":   {"banking": "up",  "metals": "up",  "it": "down",  "pharma": "down", "auto": "up",  "fmcg": "flat", "nbfc": "up",  "real_estate": "up"},
    "strong_dollar": {"banking": "down","metals": "down","it": "up",    "pharma": "up",   "auto": "down","fmcg": "flat", "nbfc": "down","real_estate": "down"},
    "india_stress":  {"banking": "down","metals": "down","it": "down",  "pharma": "up",   "auto": "down","fmcg": "up",   "nbfc": "down","real_estate": "down", "oil": "up", "defense": "flat"},
    "rbi_rate_cut":  {"banking": "up",  "metals": "flat","it": "flat",  "pharma": "flat", "auto": "up",  "fmcg": "flat", "nbfc": "up",  "real_estate": "up"},
    "rbi_rate_hike": {"banking": "down","metals": "flat","it": "flat",  "pharma": "flat", "auto": "down","fmcg": "flat", "nbfc": "down","real_estate": "down"},
    "us_recession":  {"banking": "flat","metals": "down","it": "down",  "pharma": "up",   "auto": "down","fmcg": "up",   "nbfc": "down","real_estate": "down"},
    "fii_selling":   {"banking": "down","metals": "down","it": "up",    "pharma": "up",   "auto": "down","fmcg": "up",   "nbfc": "down","real_estate": "down"},
    "fii_buying":    {"banking": "up",  "metals": "up",  "it": "down",  "pharma": "flat", "auto": "up",  "fmcg": "flat", "nbfc": "up",  "real_estate": "up"},
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
SIGNAL_TRAILING_STOP_ACTIVATE_PCT = 3.0   # Trailing stop activates when spread P&L >= 3%
SIGNAL_TRAILING_STOP_DISTANCE_PCT = 2.0   # Once active, exit if P&L drops 2% from peak
SIGNAL_CONFIDENCE_THRESHOLD = 0.6
SIGNAL_HIT_RATE_THRESHOLD = 0.65
SIGNAL_MIN_PRECEDENTS = 15          # min historical trades before SIGNAL tier
SIGNAL_MIN_PRECEDENTS_RECAL = 10   # trades needed after basket change to exit RECALIBRATING
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

# === ML CORRELATION REGIME CONFIG ===
# Pairs to track for rolling correlation and regime break detection
CORRELATION_PAIRS = [
    {"name": "Nifty_vs_BankNifty",  "a": "HDFCBANK",  "b": "ICICIBANK", "a_label": "Nifty proxy", "b_label": "Bank proxy"},
    {"name": "Defence_vs_IT",       "a": "HAL",        "b": "TCS",       "a_label": "Defence",     "b_label": "IT"},
    {"name": "Defence_vs_Auto",     "a": "HAL",        "b": "TATAMOTORS","a_label": "Defence",     "b_label": "Auto"},
    {"name": "Upstream_vs_Downstream","a": "ONGC",      "b": "BPCL",     "a_label": "Upstream",    "b_label": "Downstream"},
    {"name": "Metals_vs_IT",        "a": "HINDALCO",   "b": "INFY",     "a_label": "Metals",      "b_label": "IT"},
    {"name": "FMCG_vs_Cyclicals",   "a": "HUL",        "b": "TATAMOTORS","a_label": "FMCG",       "b_label": "Cyclicals"},
    {"name": "Pharma_vs_Banks",     "a": "SUNPHARMA",  "b": "HDFCBANK", "a_label": "Pharma",      "b_label": "Banks"},
    {"name": "PSU_vs_Private",      "a": "SBI",        "b": "HDFCBANK", "a_label": "PSU Bank",    "b_label": "Pvt Bank"},
    {"name": "Coal_vs_OMC",         "a": "COALINDIA",  "b": "BPCL",     "a_label": "Coal",        "b_label": "OMC"},
    {"name": "Finance_vs_Energy",   "a": "BAJFINANCE", "b": "ONGC",     "a_label": "NBFC",        "b_label": "Energy"},
]

# Rolling windows for correlation computation
CORR_WINDOW_SHORT = 21   # ~1 month trading days
CORR_WINDOW_LONG = 63    # ~3 months trading days

# Change-point detection
CORR_BREAK_ZSCORE = 2.0        # Z-score threshold for break detection
CORR_BREAK_MIN_SHIFT = 0.3     # minimum absolute correlation change to flag

# Fragility model
FRAGILITY_FORWARD_WINDOW = 5   # predict break in next N trading days
FRAGILITY_RETRAIN_DAYS = 30    # retrain model every N days

# === TELEGRAM CONFIG (set in .env) ===
TELEGRAM_BOT_TOKEN = None  # Override from .env
TELEGRAM_CHAT_ID = None    # Override from .env

# === REFERENCE DATE (war start) ===
WAR_START_DATE = "2026-02-28"
