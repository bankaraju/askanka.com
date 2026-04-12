"""
Step 3: Quarterly Filing Acquisition
Retrieve all quarterly results as XBRL or PDFs.

XBRL is strongly preferred — direct structured data without OCR noise.
"""

from pathlib import Path

VAULT = Path(__file__).parent.parent.parent / "artifacts" / "filings"


def fetch_quarterly_filings(bse_scrip: str, nse_symbol: str) -> list:
    """Fetch quarterly financial results.

    Returns list of dicts with structured financials per quarter.
    XBRL source tagged separately from PDF-OCR source.
    """
    VAULT.mkdir(parents=True, exist_ok=True)
    filings = []

    # Priority 1: BSE XBRL
    xbrl_filings = _fetch_bse_xbrl(bse_scrip)
    filings.extend(xbrl_filings)

    # Priority 2: BSE PDF (for older quarters without XBRL)
    quarters_covered = {f["quarter"] for f in filings}
    pdf_filings = _fetch_bse_pdf(bse_scrip)
    for f in pdf_filings:
        if f["quarter"] not in quarters_covered:
            filings.append(f)

    return sorted(filings, key=lambda x: x["quarter"], reverse=True)


def _fetch_bse_xbrl(bse_scrip: str) -> list:
    """Parse XBRL quarterly filings from BSE."""
    # TODO: Implement XBRL parser
    return []


def _fetch_bse_pdf(bse_scrip: str) -> list:
    """OCR quarterly filings from BSE PDFs via Azure OCR."""
    # TODO: Implement Azure OCR pipeline
    return []
