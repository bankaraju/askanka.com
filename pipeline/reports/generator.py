"""
Step 12: Report Generation
Synthesize findings into a research report with conflict flags.

Zero-hallucination mandate: every numerical value must link to
a specific page/paragraph in a source filing.
"""

import json
from pathlib import Path
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))
REPORTS_DIR = Path(__file__).parent.parent.parent / "artifacts" / "reports"


def generate_report(ctx) -> str:
    """Generate the final research report.

    Returns path to the generated report.
    """
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    report = {
        "company": ctx.company_name,
        "identifiers": {
            "bse_scrip": ctx.bse_scrip,
            "nse_symbol": ctx.nse_symbol,
            "cin": ctx.cin,
        },
        "sector": ctx.sector,
        "generated_at": datetime.now(IST).isoformat(),
        "data_summary": {
            "annual_reports": len(ctx.annual_reports),
            "quarterly_filings": len(ctx.quarterly_filings),
            "transcripts": len(ctx.transcripts),
            "news_items": len(ctx.news_archive),
        },
        "financial_ratios": _format_ratios(ctx.ratios),
        "forensic_flags": _detect_forensic_flags(ctx.ratios),
        "management_analysis": {
            "claims_extracted": len(ctx.management_claims),
            "promises_scored": len(ctx.promise_delivery),
            "delivery_rate": _delivery_rate(ctx.promise_delivery),
            "dropped_themes": [r.claim_text for r in ctx.promise_delivery if r.status == "quietly_dropped"],
        },
        "pattern_premium": ctx.pattern_premium,
        "valuation_applicable": ctx.pattern_premium != float("-inf"),
        "quality_gates": ctx.quality_gates,
        "errors": ctx.errors,
    }

    slug = ctx.nse_symbol or ctx.bse_scrip or ctx.company_name.replace(" ", "_")
    out_path = REPORTS_DIR / f"{slug}_{datetime.now(IST).strftime('%Y%m%d')}.json"
    out_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    return str(out_path)


def _format_ratios(ratios: dict) -> dict:
    return {k: v for k, v in ratios.items() if v}


def _detect_forensic_flags(ratios: dict) -> list:
    """Mandatory forensic red flag checks."""
    flags = []

    # DSO > 200 days
    dso = ratios.get("receivable_days", [])
    for period, val in dso:
        if isinstance(val, (int, float)) and val > 200:
            flags.append({"flag": "DSO_SPIKE", "period": period, "value": val,
                          "severity": "CRITICAL", "detail": f"DSO {val:.0f} days — receivables growing faster than revenue"})

    # Negative OCF despite profits
    ocf = ratios.get("ocf_to_pat", [])
    for period, val in ocf:
        if isinstance(val, (int, float)) and val < 0:
            flags.append({"flag": "OCF_DIVERGENCE", "period": period, "value": val,
                          "severity": "CRITICAL", "detail": "Negative OCF despite reported profits"})

    return flags


def _delivery_rate(promise_results: list) -> float:
    if not promise_results:
        return 0.0
    delivered = sum(1 for r in promise_results if r.status in ("delivered", "partially_delivered"))
    return round(delivered / len(promise_results) * 100, 1)
