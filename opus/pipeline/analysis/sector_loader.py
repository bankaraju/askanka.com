"""
Step 7: Sector Identification
Identify company sector and load the corresponding ratio library.
"""

SECTOR_MAP = {
    # Banking & Financial Services
    "HDFCBANK": "banking", "ICICIBANK": "banking", "SBIN": "banking",
    "KOTAKBANK": "banking", "AXISBANK": "banking", "BANKBARODA": "banking",
    "PNB": "banking", "INDUSINDBK": "banking", "BANDHANBNK": "banking",
    "BAJFINANCE": "nbfc", "BAJAJFINSV": "nbfc", "MUTHOOTFIN": "nbfc",
    # IT
    "TCS": "it", "INFY": "it", "WIPRO": "it", "HCLTECH": "it",
    "TECHM": "it", "LTIM": "it", "COFORGE": "it",
    # Pharma
    "SUNPHARMA": "pharma", "DRREDDY": "pharma", "CIPLA": "pharma",
    "DIVISLAB": "pharma", "AUROPHARMA": "pharma",
    # FMCG
    "HINDUNILVR": "fmcg", "ITC": "fmcg", "NESTLEIND": "fmcg",
    "BRITANNIA": "fmcg", "DABUR": "fmcg", "MARICO": "fmcg",
    # Energy / Oil & Gas
    "RELIANCE": "energy", "ONGC": "energy", "BPCL": "energy",
    "IOC": "energy", "GAIL": "energy", "COALINDIA": "energy",
    # Auto
    "TATAMOTORS": "auto", "M&M": "auto", "MARUTI": "auto",
    "BAJAJ-AUTO": "auto", "HEROMOTOCO": "auto",
    # Defence
    "HAL": "defence", "BEL": "defence", "BDL": "defence",
    # Metals
    "TATASTEEL": "metals", "JSWSTEEL": "metals", "HINDALCO": "metals",
}


def identify_sector(nse_symbol: str, bse_scrip: str = "") -> str:
    """Identify the sector for a given company.

    Falls back to BSE sector classification if not in local map.
    """
    symbol = nse_symbol.upper()
    if symbol in SECTOR_MAP:
        return SECTOR_MAP[symbol]

    # Fallback: query BSE for sector
    try:
        from bsedata.bse import BSE
        b = BSE()
        quote = b.getQuote(bse_scrip)
        if quote and "group" in quote:
            return quote["group"].lower()
    except Exception:
        pass

    return "general"
