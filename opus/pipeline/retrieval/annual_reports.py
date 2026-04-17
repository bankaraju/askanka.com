"""
Step 2: Annual Report Retrieval
Pull 5 years of annual report PDFs from BSE (primary), Screener, and NSE (gap-fill).

Source hierarchy:
1. BSE API — get_annual_reports(scrip_code) → PDF links
2. Screener.in — document links where type="annual_report"
3. NSE API — gap-fill
"""
from __future__ import annotations

import re
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

from opus.pipeline.retrieval.bse_client import BSEClient
from opus.pipeline.retrieval.screener_client import ScreenerClient
from opus.pipeline.retrieval.nse_client import NSEClient

log = logging.getLogger("opus.annual_reports")

IST = timezone(timedelta(hours=5, minutes=30))
VAULT = Path(__file__).parent.parent.parent / "artifacts" / "filings"


def _extract_year_from_title(title: str) -> str:
    m = re.search(r'20\d{2}', title)
    return m.group(0) if m else ""


def fetch_annual_reports(bse_scrip: str, nse_symbol: str, years: int = 5) -> list:
    """Fetch annual reports for the given company.

    Returns list of dicts sorted by year descending:
    [{"year": "2024", "source": "BSE", "format": "PDF", "url": "...", "fetched_at": "..."}]

    Source hierarchy:
    1. BSE (primary, only if bse_scrip provided)
    2. Screener.in (fills gaps or acts as primary when no bse_scrip)
    3. NSE (gap-fill when years_covered < years)
    """
    reports: list[dict] = []
    years_covered: set[str] = set()
    now = datetime.now(IST).isoformat()

    # 1. BSE — primary source (skip entirely if no scrip code)
    if bse_scrip:
        try:
            bse = BSEClient()
            bse_reports = bse.get_annual_reports(bse_scrip)
            for r in bse_reports:
                yr = r.get("year", "")
                if yr and yr not in years_covered:
                    reports.append({**r, "fetched_at": now})
                    years_covered.add(yr)
        except Exception as exc:
            log.warning("BSE annual reports failed for %s: %s", bse_scrip, exc)

    # 2. Screener — always run to fill gaps (or act as primary if no BSE scrip)
    try:
        sc = ScreenerClient()
        data = sc.get_financials(nse_symbol)
        docs = data.get("documents", [])
        for doc in docs:
            if doc.get("type") != "annual_report":
                continue
            yr = _extract_year_from_title(doc.get("title", ""))
            if yr and yr not in years_covered:
                reports.append({
                    "year": yr,
                    "source": "screener",
                    "format": "PDF",
                    "url": doc["url"],
                    "fetched_at": now,
                })
                years_covered.add(yr)
    except Exception as exc:
        log.warning("Screener annual reports failed for %s: %s", nse_symbol, exc)

    # 3. NSE — gap-fill only when still under target year count
    if len(years_covered) < years:
        try:
            nse = NSEClient()
            nse_reports = nse.get_annual_reports(nse_symbol)
            for r in nse_reports:
                yr_raw = r.get("year", "")
                yr = yr_raw.split("-")[0] if "-" in yr_raw else yr_raw
                if yr and yr not in years_covered:
                    reports.append({**r, "year": yr, "fetched_at": now})
                    years_covered.add(yr)
        except Exception as exc:
            log.warning("NSE annual reports failed for %s: %s", nse_symbol, exc)

    return sorted(reports, key=lambda x: x.get("year", ""), reverse=True)
