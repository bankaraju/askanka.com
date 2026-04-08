# OPUS ANKA — Automated Equity Research & Pattern Premium Engine

## What This Is
Agentic equity research system for Indian markets. Takes a company name, runs a 12-step forensic pipeline, outputs a research report with a proprietary "Pattern Premium" score based on management credibility over multi-year cycles.

## Architecture (Three Pillars)
- **PostgreSQL V2** (Port 5000): Forensics — XBRL data, working capital, unified financials
- **PostgreSQL V3** (Port 9001): Trading — dashboard, options, ML manipulation scores
- **Neo4j**: Narrative graph — management claims, entity relationships, BGE embeddings
- **Obsidian**: Source intelligence vault, SKILL.md protocols, reliability rankings

## The 12-Step HAL Pipeline
1. Identity Resolution (Name → CIN / BSE / NSE)
2. Annual Report Retrieval (5 years)
3. Quarterly Filing Acquisition (XBRL preferred)
4. Shareholding Pattern Analysis
5. Transcript Retrieval (min 8 quarters)
6. News Archive Ingestion (5 years)
7. Sector Identification (load ratio library)
8. Ratio Calculation (Goldman-style framework)
9. Management Claim Extraction (min 5 claims/filing)
10. Promise-vs-Delivery Scoring (boolean verification)
11. Pattern Premium Calculation (credibility → valuation adjustment)
12. Report Generation (zero-hallucination sign-off)

## Quality Rules
- Every number must trace to a named, dated official filing
- Source hierarchy: BSE/NSE XBRL > BSE/NSE PDF > MCA > Verified News > Aggregators
- Material claims require 2+ independent sources
- Source divergence = "High-Interest Intelligence" (never resolve silently)
- DCF aborted when DSO > 200 days or negative OCF exposure

## Sector Libraries
- Banking: 23-ratio framework (NIM, RBI stress, NPA forensics)
- Pharma, FMCG, IT: separate ratio dependencies

## Code Standards
- Python 3.13, type hints on public functions
- All DB writes through validated commit layer
- No hallucinated numbers — flag in red if not source-traced
- Scope discipline: declare Forensic vs Strategic intent before execution
