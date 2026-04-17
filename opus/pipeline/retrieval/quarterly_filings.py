"""
Step 3: Quarterly Filing Acquisition
Retrieve quarterly financial results from multiple sources.

Source priority:
1. Screener.in — structured HTML tables (10+ years, no PDF)
2. BSE API — financial result filings
3. EODHD Fundamentals — cross-verification
4. IndianAPI — cross-verification
"""
from __future__ import annotations

import re
import logging
from datetime import datetime, timezone, timedelta

from opus.pipeline.retrieval.screener_client import ScreenerClient
from opus.pipeline.retrieval.bse_client import BSEClient

log = logging.getLogger("opus.quarterly_filings")

IST = timezone(timedelta(hours=5, minutes=30))


def _parse_screener_number(val: str) -> float:
    if not val:
        return 0.0
    cleaned = val.replace(",", "").replace("%", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def _screener_col_to_quarter(col_name: str) -> str:
    m = re.match(r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{4})', col_name)
    if not m:
        return col_name
    month, year = m.group(1), int(m.group(2))
    month_map = {"Mar": ("Q4", year), "Jun": ("Q1", year + 1), "Sep": ("Q2", year + 1), "Dec": ("Q3", year + 1),
                 "Jan": ("Q3", year), "Feb": ("Q3", year), "Apr": ("Q1", year + 1), "May": ("Q1", year + 1),
                 "Jul": ("Q2", year + 1), "Aug": ("Q2", year + 1), "Oct": ("Q2", year + 1), "Nov": ("Q3", year + 1)}
    q, fy = month_map.get(month, ("Q?", year))
    return f"{q}FY{str(fy)[-2:]}"


def _parse_screener_quarterly(rows: list[dict]) -> list[dict]:
    if not rows:
        return []

    label_map: dict[str, dict[str, str]] = {}
    for row in rows:
        label = row.get("", "").strip()
        if label:
            label_map[label] = row

    all_cols = set()
    for row in rows:
        all_cols.update(k for k in row.keys() if k and k != "")
    date_cols = sorted(all_cols, reverse=True)

    now = datetime.now(IST).isoformat()
    filings = []
    for col in date_cols:
        quarter = _screener_col_to_quarter(col)
        revenue = _parse_screener_number(label_map.get("Sales", {}).get(col, ""))
        pat = _parse_screener_number(label_map.get("Net Profit", {}).get(col, ""))
        opm = _parse_screener_number(label_map.get("OPM %", {}).get(col, ""))

        if revenue == 0 and pat == 0:
            continue

        filings.append({
            "quarter": quarter,
            "source": "screener",
            "revenue": revenue,
            "pat": pat,
            "opm_pct": opm,
            "raw_column": col,
            "fetched_at": now,
        })

    return filings


def fetch_quarterly_filings(bse_scrip: str, nse_symbol: str) -> list:
    filings: list[dict] = []

    try:
        sc = ScreenerClient()
        data = sc.get_financials(nse_symbol)
        quarterly_rows = data.get("quarterly", [])
        filings = _parse_screener_quarterly(quarterly_rows)
        log.info("  %s: %d quarters from Screener", nse_symbol, len(filings))
    except Exception as exc:
        log.warning("Screener quarterly failed for %s: %s", nse_symbol, exc)

    if bse_scrip:
        try:
            bse = BSEClient()
            bse_results = bse.get_financial_results(bse_scrip)
            log.info("  %s: %d results from BSE", nse_symbol, len(bse_results))
        except Exception as exc:
            log.warning("BSE quarterly failed for %s: %s", nse_symbol, exc)

    return sorted(filings, key=lambda x: x.get("quarter", ""), reverse=True)
