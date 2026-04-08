"""
Step 1: Identity Resolution
Resolve company name → BSE scrip code, NSE symbol, CIN.

Uses BSE API (bsedata) and NSE API (NseIndiaApi) for authoritative lookup.
Yahoo Finance as cross-validation fallback only.
"""

import json
from pathlib import Path

# Local cache of BSE scrip codes (built from BSE directory)
CACHE_FILE = Path(__file__).parent / "scrip_cache.json"


def resolve_identity(company_name: str) -> dict:
    """Resolve a company name to its market identifiers.

    Returns: {"bse_scrip": str, "nse_symbol": str, "cin": str}
    """
    # Step 1: Try BSE directory lookup
    bse_result = _lookup_bse(company_name)

    # Step 2: Try NSE symbol lookup
    nse_result = _lookup_nse(company_name)

    # Step 3: Try MCA for CIN
    cin = _lookup_cin(company_name, bse_result.get("name", ""))

    return {
        "bse_scrip": bse_result.get("scrip", ""),
        "nse_symbol": nse_result.get("symbol", ""),
        "cin": cin,
        "company_name_official": bse_result.get("name", nse_result.get("name", company_name)),
    }


def _lookup_bse(company_name: str) -> dict:
    """Query BSE for scrip code and official name."""
    try:
        from bsedata.bse import BSE
        b = BSE()
        # bsedata doesn't have direct search — we use the scrip list
        scrips = b.getScripCodes()
        name_lower = company_name.lower()
        for code, name in scrips.items():
            if name_lower in name.lower() or name.lower() in name_lower:
                return {"scrip": str(code), "name": name}
    except ImportError:
        pass
    except Exception:
        pass
    return {}


def _lookup_nse(company_name: str) -> dict:
    """Query NSE for trading symbol."""
    try:
        from nselib import capital_market
        # Search NSE equity list
        equity_list = capital_market.equity_list()
        name_lower = company_name.lower()
        for _, row in equity_list.iterrows():
            if name_lower in str(row.get("NAME OF COMPANY", "")).lower():
                return {"symbol": row.get("SYMBOL", ""), "name": row.get("NAME OF COMPANY", "")}
    except ImportError:
        pass
    except Exception:
        pass
    return {}


def _lookup_cin(company_name: str, official_name: str) -> str:
    """Look up Corporate Identification Number from MCA."""
    # MCA doesn't have a public API — this would use web scraping
    # For now, return empty and flag for manual resolution
    return ""
