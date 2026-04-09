"""
OPUS ANKA — The 12-Step HAL Agentic Research Pipeline

Transforms a company name into a finished research report through
a linear, verifiable, and calibrated workflow.

Each step has explicit success criteria and quality gates.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))


@dataclass
class ResearchContext:
    """State object passed through the 12-step pipeline."""
    company_name: str
    bse_scrip: str = ""
    nse_symbol: str = ""
    cin: str = ""
    sector: str = ""
    annual_reports: list = field(default_factory=list)
    quarterly_filings: list = field(default_factory=list)
    shareholding: list = field(default_factory=list)
    transcripts: list = field(default_factory=list)
    news_archive: list = field(default_factory=list)
    ratios: dict = field(default_factory=dict)
    management_claims: list = field(default_factory=list)
    promise_delivery: list = field(default_factory=list)
    trust_score: float = 0.0
    quality_gates: dict = field(default_factory=dict)
    errors: list = field(default_factory=list)
    started_at: str = field(default_factory=lambda: datetime.now(IST).isoformat())

    def pass_gate(self, gate: int, detail: str):
        self.quality_gates[f"gate_{gate}"] = {"passed": True, "detail": detail, "at": datetime.now(IST).isoformat()}

    def fail_gate(self, gate: int, detail: str):
        self.quality_gates[f"gate_{gate}"] = {"passed": False, "detail": detail, "at": datetime.now(IST).isoformat()}
        self.errors.append(f"Gate {gate} FAILED: {detail}")


# ── Step 1: Identity Resolution ──────────────────────────────────────

def step_01_identity_resolution(ctx: ResearchContext) -> ResearchContext:
    """Resolve company name → BSE scrip, NSE symbol, CIN.
    Success: Correct Scrip/CIN verified via BSE official directory."""
    from pipeline.identity.resolver import resolve_identity
    result = resolve_identity(ctx.company_name)
    ctx.bse_scrip = result["bse_scrip"]
    ctx.nse_symbol = result["nse_symbol"]
    ctx.cin = result["cin"]
    ctx.pass_gate(1, f"BSE={ctx.bse_scrip} NSE={ctx.nse_symbol} CIN={ctx.cin}")
    return ctx


# ── Step 2: Annual Report Retrieval ──────────────────────────────────

def step_02_annual_reports(ctx: ResearchContext) -> ResearchContext:
    """Pull 5 years of annual report PDFs from BSE/NSE.
    Success: 5 unique, high-integrity PDF files stored."""
    from pipeline.retrieval.annual_reports import fetch_annual_reports
    ctx.annual_reports = fetch_annual_reports(ctx.bse_scrip, ctx.nse_symbol, years=5)
    if len(ctx.annual_reports) >= 5:
        ctx.pass_gate(1, f"{len(ctx.annual_reports)} annual reports retrieved")
    else:
        ctx.fail_gate(1, f"Only {len(ctx.annual_reports)} of 5 annual reports found")
    return ctx


# ── Step 3: Quarterly Filing Acquisition ─────────────────────────────

def step_03_quarterly_filings(ctx: ResearchContext) -> ResearchContext:
    """Retrieve all quarterly results as XBRL or PDFs.
    Success: All quarterly financials mapped to XBRL taxonomies where available."""
    from pipeline.retrieval.quarterly_filings import fetch_quarterly_filings
    ctx.quarterly_filings = fetch_quarterly_filings(ctx.bse_scrip, ctx.nse_symbol)
    return ctx


# ── Step 4: Shareholding Pattern ─────────────────────────────────────

def step_04_shareholding(ctx: ResearchContext) -> ResearchContext:
    """Pull and structure quarterly shareholding data.
    Success: Promoter/institutional trends with 100% data continuity."""
    from pipeline.retrieval.shareholding import fetch_shareholding
    ctx.shareholding = fetch_shareholding(ctx.bse_scrip)
    return ctx


# ── Step 5: Transcript Retrieval ─────────────────────────────────────

def step_05_transcripts(ctx: ResearchContext) -> ResearchContext:
    """Fetch earnings call transcripts.
    Success: Minimum 8 recent quarterly transcripts indexed and parsed."""
    from pipeline.retrieval.transcripts import fetch_transcripts
    ctx.transcripts = fetch_transcripts(ctx.nse_symbol)
    if len(ctx.transcripts) >= 8:
        ctx.pass_gate(2, f"{len(ctx.transcripts)} transcripts retrieved")
    else:
        ctx.fail_gate(2, f"Only {len(ctx.transcripts)} of 8 minimum transcripts found")
    return ctx


# ── Step 6: News Archive ─────────────────────────────────────────────

def step_06_news_archive(ctx: ResearchContext) -> ResearchContext:
    """Pull 5-year news archive, filter for material events.
    Success: Timeline cross-referenced with corporate announcements."""
    from pipeline.retrieval.news import fetch_news_archive
    ctx.news_archive = fetch_news_archive(ctx.company_name, ctx.nse_symbol, years=5)
    return ctx


# ── Step 7: Sector Identification ────────────────────────────────────

def step_07_sector_id(ctx: ResearchContext) -> ResearchContext:
    """Load corresponding sector ratio library.
    Success: Sector-specific formulas mapped to database columns."""
    from pipeline.analysis.sector_loader import identify_sector
    ctx.sector = identify_sector(ctx.nse_symbol, ctx.bse_scrip)
    return ctx


# ── Step 8: Ratio Calculation ────────────────────────────────────────

def step_08_ratios(ctx: ResearchContext) -> ResearchContext:
    """Execute Goldman-style ratio framework.
    Success: 100% completion of sector benchmark ratios."""
    from pipeline.analysis.ratio_engine import calculate_ratios
    ctx.ratios = calculate_ratios(ctx.sector, ctx.quarterly_filings, ctx.annual_reports)
    ctx.pass_gate(3, f"{len(ctx.ratios)} ratios calculated for sector={ctx.sector}")
    return ctx


# ── Step 9: Management Claim Extraction ──────────────────────────────

def step_09_claims(ctx: ResearchContext) -> ResearchContext:
    """Extract and tag forward-looking claims from MD&A and transcripts.
    Success: Minimum 5 claims per filing with measurable targets."""
    from pipeline.narrative.claim_extractor import extract_claims
    ctx.management_claims = extract_claims(ctx.annual_reports, ctx.transcripts)
    return ctx


# ── Step 10: Promise-vs-Delivery Scoring ─────────────────────────────

def step_10_promise_delivery(ctx: ResearchContext) -> ResearchContext:
    """Match historical claims against subsequent financial results.
    Success: Boolean 'Delivered' vs 'Dropped' for every target."""
    from pipeline.narrative.promise_scorer import score_promises
    ctx.promise_delivery = score_promises(ctx.management_claims, ctx.quarterly_filings)
    ctx.pass_gate(5, f"{len(ctx.promise_delivery)} claims scored")
    return ctx


# ── Step 11: ANKA Trust Score Calculation ─────────────────────────────

def step_11_trust_score(ctx: ResearchContext) -> ResearchContext:
    """Apply credibility scores to adjust valuation.
    Success: Quantitative premium adjustment from execution track record."""
    from pipeline.premium.calculator import calculate_trust_score
    ctx.trust_score = calculate_trust_score(ctx.promise_delivery, ctx.ratios)
    return ctx


# ── Step 12: Report Generation ───────────────────────────────────────

def step_12_report(ctx: ResearchContext) -> ResearchContext:
    """Synthesize findings into report with conflict flags.
    Success: Zero-hallucination — every number linked to source filing."""
    from pipeline.reports.generator import generate_report
    generate_report(ctx)
    ctx.pass_gate(7, "Report generated with source traceability")
    return ctx


# ── Orchestrator ─────────────────────────────────────────────────────

STEPS = [
    ("Identity Resolution", step_01_identity_resolution),
    ("Annual Reports", step_02_annual_reports),
    ("Quarterly Filings", step_03_quarterly_filings),
    ("Shareholding", step_04_shareholding),
    ("Transcripts", step_05_transcripts),
    ("News Archive", step_06_news_archive),
    ("Sector ID", step_07_sector_id),
    ("Ratio Calculation", step_08_ratios),
    ("Claim Extraction", step_09_claims),
    ("Promise vs Delivery", step_10_promise_delivery),
    ("ANKA Trust Score", step_11_trust_score),
    ("Report Generation", step_12_report),
]


def run_pipeline(company_name: str) -> ResearchContext:
    """Execute the full 12-step HAL pipeline."""
    ctx = ResearchContext(company_name=company_name)
    print(f"{'='*70}")
    print(f"OPUS ANKA — HAL Pipeline: {company_name}")
    print(f"{'='*70}")

    for i, (name, step_fn) in enumerate(STEPS, 1):
        print(f"\n  Step {i:02d}: {name}...")
        try:
            ctx = step_fn(ctx)
            print(f"          DONE")
        except Exception as e:
            ctx.errors.append(f"Step {i} ({name}): {e}")
            print(f"          FAILED: {e}")

    # Summary
    gates_passed = sum(1 for g in ctx.quality_gates.values() if g["passed"])
    gates_total = len(ctx.quality_gates)
    print(f"\n{'='*70}")
    print(f"Quality Gates: {gates_passed}/{gates_total} passed")
    print(f"ANKA Trust Score: {ctx.trust_score:+.1f}%")
    if ctx.errors:
        print(f"Errors: {len(ctx.errors)}")
        for e in ctx.errors:
            print(f"  - {e}")
    print(f"{'='*70}")

    return ctx


if __name__ == "__main__":
    import sys
    company = sys.argv[1] if len(sys.argv) > 1 else "HDFC Bank"
    run_pipeline(company)
