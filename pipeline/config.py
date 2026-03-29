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

# === REFERENCE DATE (war start) ===
WAR_START_DATE = "2026-02-28"
