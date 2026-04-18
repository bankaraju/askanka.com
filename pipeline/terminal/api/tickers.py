"""GET /api/tickers — F&O stock universe with company names for autocomplete."""
import json
from pathlib import Path
from fastapi import APIRouter

router = APIRouter()

_HERE = Path(__file__).resolve().parent.parent
_FNO_FILE = _HERE.parent.parent / "opus" / "config" / "fno_stocks.json"

COMPANY_NAMES = {
    "360ONE": "360 One WAM", "ABB": "ABB India", "ABCAPITAL": "Aditya Birla Capital",
    "ADANIENSOL": "Adani Energy Solutions", "ADANIENT": "Adani Enterprises",
    "ADANIGREEN": "Adani Green Energy", "ADANIPORTS": "Adani Ports", "ADANIPOWER": "Adani Power",
    "ALKEM": "Alkem Laboratories", "AMBER": "Amber Enterprises", "AMBUJACEM": "Ambuja Cements",
    "ANGELONE": "Angel One", "APLAPOLLO": "APL Apollo Tubes", "APOLLOHOSP": "Apollo Hospitals",
    "ASHOKLEY": "Ashok Leyland", "ASIANPAINT": "Asian Paints", "ASTRAL": "Astral",
    "AUBANK": "AU Small Finance Bank", "AUROPHARMA": "Aurobindo Pharma", "AXISBANK": "Axis Bank",
    "BAJAJ-AUTO": "Bajaj Auto", "BAJAJFINSV": "Bajaj Finserv", "BAJAJHLDNG": "Bajaj Holdings",
    "BAJFINANCE": "Bajaj Finance", "BANDHANBNK": "Bandhan Bank", "BANKBARODA": "Bank of Baroda",
    "BANKINDIA": "Bank of India", "BDL": "Bharat Dynamics", "BEL": "Bharat Electronics",
    "BHARATFORG": "Bharat Forge", "BHARTIARTL": "Bharti Airtel", "BHEL": "BHEL",
    "BIOCON": "Biocon", "BLUESTARCO": "Blue Star", "BOSCHLTD": "Bosch",
    "BPCL": "Bharat Petroleum", "BRITANNIA": "Britannia Industries", "BSE": "BSE Ltd",
    "CAMS": "CAMS", "CANBK": "Canara Bank", "CDSL": "CDSL",
    "CGPOWER": "CG Power", "CHOLAFIN": "Cholamandalam Finance", "CIPLA": "Cipla",
    "COALINDIA": "Coal India", "COCHINSHIP": "Cochin Shipyard", "COFORGE": "Coforge",
    "COLPAL": "Colgate Palmolive", "CONCOR": "Container Corp", "CROMPTON": "Crompton Greaves",
    "CUMMINSIND": "Cummins India", "DABUR": "Dabur India", "DALBHARAT": "Dalmia Bharat",
    "DELHIVERY": "Delhivery", "DIVISLAB": "Divi's Laboratories", "DIXON": "Dixon Technologies",
    "DLF": "DLF", "DMART": "Avenue Supermarts DMart", "DRREDDY": "Dr Reddy's Laboratories",
    "EICHERMOT": "Eicher Motors", "ETERNAL": "Eternal (Zomato)", "EXIDEIND": "Exide Industries",
    "FEDERALBNK": "Federal Bank", "FORCEMOT": "Force Motors", "FORTIS": "Fortis Healthcare",
    "GAIL": "GAIL India", "GLENMARK": "Glenmark Pharma", "GMRAIRPORT": "GMR Airports",
    "GODFRYPHLP": "Godfrey Phillips", "GODREJCP": "Godrej Consumer", "GODREJPROP": "Godrej Properties",
    "GRASIM": "Grasim Industries", "HAL": "Hindustan Aeronautics", "HAVELLS": "Havells India",
    "HCLTECH": "HCL Technologies", "HDFCAMC": "HDFC AMC", "HDFCBANK": "HDFC Bank",
    "HDFCLIFE": "HDFC Life", "HEROMOTOCO": "Hero MotoCorp", "HINDALCO": "Hindalco Industries",
    "HINDPETRO": "Hindustan Petroleum", "HINDUNILVR": "Hindustan Unilever", "HINDZINC": "Hindustan Zinc",
    "HUDCO": "HUDCO", "HYUNDAI": "Hyundai Motor India", "ICICIBANK": "ICICI Bank",
    "ICICIGI": "ICICI Lombard", "ICICIPRULI": "ICICI Prudential Life", "IDEA": "Vodafone Idea",
    "IDFCFIRSTB": "IDFC First Bank", "IEX": "Indian Energy Exchange", "INDHOTEL": "Indian Hotels",
    "INDIANB": "Indian Bank", "INDIGO": "InterGlobe Aviation IndiGo", "INDUSINDBK": "IndusInd Bank",
    "INDUSTOWER": "Indus Towers", "INFY": "Infosys", "INOXWIND": "Inox Wind",
    "IOC": "Indian Oil Corp", "IREDA": "IREDA", "IRFC": "IRFC",
    "ITC": "ITC", "JINDALSTEL": "Jindal Steel", "JIOFIN": "Jio Financial Services",
    "JSWENERGY": "JSW Energy", "JSWSTEEL": "JSW Steel", "JUBLFOOD": "Jubilant FoodWorks",
    "KALYANKJIL": "Kalyan Jewellers", "KAYNES": "Kaynes Technology", "KEI": "KEI Industries",
    "KFINTECH": "KFin Technologies", "KOTAKBANK": "Kotak Mahindra Bank", "KPITTECH": "KPIT Technologies",
    "LAURUSLABS": "Laurus Labs", "LICHSGFIN": "LIC Housing Finance", "LICI": "LIC of India",
    "LODHA": "Macrotech Developers Lodha", "LT": "Larsen & Toubro", "LTF": "L&T Finance",
    "LTM": "L&T Technology Services", "LUPIN": "Lupin", "M&M": "Mahindra & Mahindra",
    "MANAPPURAM": "Manappuram Finance", "MANKIND": "Mankind Pharma", "MARICO": "Marico",
    "MARUTI": "Maruti Suzuki", "MAXHEALTH": "Max Healthcare", "MAZDOCK": "Mazagon Dock",
    "MCX": "Multi Commodity Exchange", "MFSL": "Max Financial Services", "MOTHERSON": "Samvardhana Motherson",
    "MOTILALOFS": "Motilal Oswal Financial", "MPHASIS": "Mphasis", "MUTHOOTFIN": "Muthoot Finance",
    "NAM-INDIA": "Nippon Life AMC", "NATIONALUM": "National Aluminium", "NAUKRI": "Info Edge Naukri",
    "NBCC": "NBCC India", "NESTLEIND": "Nestle India", "NHPC": "NHPC",
    "NMDC": "NMDC", "NTPC": "NTPC", "NUVAMA": "Nuvama Wealth",
    "NYKAA": "FSN E-Commerce Nykaa", "OBEROIRLTY": "Oberoi Realty", "OFSS": "Oracle Financial Services",
    "OIL": "Oil India", "ONGC": "ONGC", "PAGEIND": "Page Industries",
    "PATANJALI": "Patanjali Foods", "PAYTM": "One97 Communications Paytm", "PERSISTENT": "Persistent Systems",
    "PETRONET": "Petronet LNG", "PFC": "Power Finance Corp", "PGEL": "PG Electroplast",
    "PHOENIXLTD": "Phoenix Mills", "PIDILITIND": "Pidilite Industries", "PIIND": "PI Industries",
    "PNB": "Punjab National Bank", "PNBHOUSING": "PNB Housing Finance", "POLICYBZR": "PB Fintech PolicyBazaar",
    "POLYCAB": "Polycab India", "POWERGRID": "Power Grid Corp", "POWERINDIA": "Hitachi Energy India",
    "PPLPHARMA": "Piramal Pharma", "PREMIERENE": "Premier Energies", "PRESTIGE": "Prestige Estates",
    "RBLBANK": "RBL Bank", "RECLTD": "REC Ltd", "RELIANCE": "Reliance Industries",
    "RVNL": "Rail Vikas Nigam", "SAIL": "Steel Authority of India", "SAMMAANCAP": "Sammaan Capital",
    "SBICARD": "SBI Cards", "SBILIFE": "SBI Life Insurance", "SBIN": "State Bank of India",
    "SHREECEM": "Shree Cement", "SHRIRAMFIN": "Shriram Finance", "SIEMENS": "Siemens",
    "SOLARINDS": "Solar Industries", "SONACOMS": "Sona BLW Precision", "SRF": "SRF",
    "SUNPHARMA": "Sun Pharmaceutical", "SUPREMEIND": "Supreme Industries", "SUZLON": "Suzlon Energy",
    "SWIGGY": "Swiggy", "TATACONSUM": "Tata Consumer Products", "TATAELXSI": "Tata Elxsi",
    "TATAPOWER": "Tata Power", "TATASTEEL": "Tata Steel", "TATATECH": "Tata Technologies",
    "TCS": "Tata Consultancy Services", "TECHM": "Tech Mahindra", "TIINDIA": "Tube Investments",
    "TITAN": "Titan Company", "TMPV": "Tata Motors DVR", "TORNTPHARM": "Torrent Pharmaceuticals",
    "TORNTPOWER": "Torrent Power", "TRENT": "Trent", "TVSMOTOR": "TVS Motor",
    "ULTRACEMCO": "UltraTech Cement", "UNIONBANK": "Union Bank of India", "UNITDSPR": "United Spirits",
    "UNOMINDA": "UNO Minda", "UPL": "UPL", "VBL": "Varun Beverages",
    "VEDL": "Vedanta", "VMM": "Vodafone Idea Merged", "VOLTAS": "Voltas",
    "WAAREEENER": "Waaree Energies", "WIPRO": "Wipro", "YESBANK": "Yes Bank",
    "ZYDUSLIFE": "Zydus Lifesciences",
}


@router.get("/tickers")
def tickers():
    raw = _read_json(_FNO_FILE)
    symbols = raw.get("symbols", list(COMPANY_NAMES.keys()))
    result = []
    for sym in symbols:
        result.append({
            "symbol": sym,
            "name": COMPANY_NAMES.get(sym, sym),
        })
    return {"tickers": result, "total": len(result)}


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
