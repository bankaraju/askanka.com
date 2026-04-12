---
name: Financial Data Extraction Protocol
version: 1.0
---

# Extraction Protocol

## Source Priority
1. BSE/NSE XBRL filings (structured, machine-readable)
2. BSE/NSE PDF filings (requires Azure OCR)
3. MCA filings (charges, director changes)
4. Verified newspaper archives (contract signings, expansions)
5. Data aggregators (Screener, Yahoo Finance) — cross-validation ONLY

## Rules
- NEVER use aggregator data as primary source
- Every number must trace to a filing page/paragraph
- If BSE and NSE filings diverge, flag as "High-Interest Intelligence"
- XBRL > PDF always (less OCR noise)
- For quarterly results: check both standalone AND consolidated

## XBRL Taxonomy Mapping
- Revenue: `RevenueFromOperations`
- PAT: `ProfitLossForPeriod`
- Total Assets: `Assets`
- Equity: `Equity`
- Borrowings: `Borrowings`

## OCR Quality Checks
- After Azure OCR: verify column alignment on tabular data
- Cross-check OCR totals against sub-items (must sum correctly)
- Flag any OCR confidence < 0.85 for manual review
