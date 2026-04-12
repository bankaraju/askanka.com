"""
Step 9: Management Claim Extraction
Extract forward-looking claims from MD&A and earnings call transcripts.

Identifies specific, measurable targets that can be scored in Step 10.
Tags: revenue_target, margin_guidance, capex_plan, market_entry,
      digital_transformation, capacity_expansion, etc.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class ManagementClaim:
    """A specific, measurable claim from management."""
    quarter: str                    # e.g., "Q3FY25"
    source: str                     # "annual_report" | "transcript" | "investor_pres"
    page_or_timestamp: str          # Source traceability
    claim_text: str                 # Exact quote
    category: str                   # revenue_target, margin_guidance, etc.
    target_metric: str              # e.g., "revenue", "EBITDA margin"
    target_value: Optional[str]     # e.g., "15%", "Rs 5000 Cr"
    target_timeline: Optional[str]  # e.g., "FY26", "next 2 years"
    confidence: float = 0.0         # Extraction confidence (0-1)


def extract_claims(annual_reports: list, transcripts: list) -> list[ManagementClaim]:
    """Extract forward-looking claims from filings and transcripts.

    Uses Claude to identify claims with measurable targets.
    Minimum 5 claims per filing.

    Returns list of ManagementClaim objects.
    """
    claims = []

    for report in annual_reports:
        report_claims = _extract_from_text(
            text=report.get("md_a_text", ""),
            quarter=report.get("year", ""),
            source="annual_report",
        )
        claims.extend(report_claims)

    for transcript in transcripts:
        transcript_claims = _extract_from_text(
            text=transcript.get("text", ""),
            quarter=transcript.get("quarter", ""),
            source="transcript",
        )
        claims.extend(transcript_claims)

    return claims


def _extract_from_text(text: str, quarter: str, source: str) -> list[ManagementClaim]:
    """Use Claude to extract forward-looking claims from text."""
    if not text:
        return []

    # TODO: Claude API call to extract claims
    # Prompt: identify specific, measurable forward-looking statements
    # with target metrics, values, and timelines
    return []
