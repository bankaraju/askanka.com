"""
Step 2: Annual Report Retrieval
Pull 5 years of annual report PDFs from BSE/NSE.

Source hierarchy:
1. BSE XBRL filings (structured, preferred)
2. BSE PDF filings
3. NSE corporate filings
"""

from pathlib import Path

VAULT = Path(__file__).parent.parent.parent / "artifacts" / "filings"


def fetch_annual_reports(bse_scrip: str, nse_symbol: str, years: int = 5) -> list:
    """Fetch annual reports for the given company.

    Returns list of dicts: [{"year": "2024", "source": "BSE", "format": "XBRL", "path": "..."}]
    """
    VAULT.mkdir(parents=True, exist_ok=True)
    reports = []

    # Try BSE first (XBRL preferred over PDF)
    bse_reports = _fetch_bse_annual(bse_scrip, years)
    reports.extend(bse_reports)

    # Fill gaps from NSE
    years_covered = {r["year"] for r in reports}
    if len(years_covered) < years:
        nse_reports = _fetch_nse_annual(nse_symbol, years)
        for r in nse_reports:
            if r["year"] not in years_covered:
                reports.append(r)

    return sorted(reports, key=lambda x: x["year"], reverse=True)


def _fetch_bse_annual(bse_scrip: str, years: int) -> list:
    """Fetch from BSE corporate filings."""
    reports = []
    try:
        from bsedata.bse import BSE
        b = BSE()
        # BSE API for annual reports
        # TODO: Implement BSE annual report download
        pass
    except Exception:
        pass
    return reports


def _fetch_nse_annual(nse_symbol: str, years: int) -> list:
    """Fetch from NSE corporate filings."""
    reports = []
    try:
        from nselib import capital_market
        # TODO: Implement NSE annual report download
        pass
    except Exception:
        pass
    return reports
