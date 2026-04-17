# Full Data Retrieval Pipeline — Design Spec

> **Status:** Approved 2026-04-17
> **Goal:** Wire all 3 retrieval stubs (transcripts, annual reports, quarterly filings) to real data sources, resolve BSE scrip codes for all 213 F&O stocks, add sector peer imputation, and re-run batch scoring to achieve 213/213 trust score coverage.

## Context

The OPUS ANKA Trust Score pipeline has a 12-step HAL pipeline where steps 2-6 fetch data. Currently:
- Steps 2, 3, 5 are **stubs** returning `[]`
- Only 2 of 213 F&O stocks have trust scores (GAIL, HAL)
- 153+ stocks show `INSUFFICIENT_DATA`
- Root cause: `transcripts.py` returns `[]` → no claims → no promise-vs-delivery → no trust score

Five data clients already exist and work:
- `opus/pipeline/retrieval/screener_client.py` — financials, transcript PDF links, peers
- `opus/pipeline/retrieval/bse_client.py` — annual reports, financial results, corp actions
- `opus/pipeline/retrieval/nse_client.py` — XBRL results, shareholding, annual reports
- `pipeline/eodhd_client.py` — real-time + EOD prices (Fundamentals API available but unwired)
- `pipeline/news_scanner.py` — uses IndianAPI for announcements (financial data endpoints available but unwired)

The stubs just need to be wired to these clients. EODHD and IndianAPI extend coverage beyond the free BSE/NSE/Screener sources.

## Architecture

```
213 F&O stocks (opus/config/fno_stocks.json)
         │
    ┌────┴────┐
    │ Phase 1 │  BSE Scrip Resolution (all 213)
    └────┬────┘
         │
    ┌────┴──────────────────────────┐
    │        Per-Stock Retrieval     │
    │                                │
    │  Source 1: Screener.in         │  ← transcripts, AR links, financials
    │  Source 2: BSE API             │  ← annual reports, XBRL filings
    │  Source 3: NSE API             │  ← gap-fill for BSE misses
    │  Source 4: EODHD Fundamentals  │  ← quarterly financials (cross-verify)
    │  Source 5: IndianAPI           │  ← announcements + financial data
    │                                │
    │  Merge: deduplicate by quarter │
    └────┬──────────────────────────┘
         │
    ┌────┴────┐
    │ Phase 2 │  Imputation (sector peers for transcript gaps)
    └────┬────┘
         │
    ┌────┴────┐
    │ Phase 3 │  Batch re-score (all 213 through HAL pipeline)
    └─────────┘
```

## Components

### 1. BSE Scrip Resolver

**File:** `opus/pipeline/retrieval/bse_resolver.py`

**Purpose:** Map all 213 NSE symbols to BSE scrip codes so BSE API can be used uniformly.

**Approach:**
- BSE search API: `https://api.bseindia.com/BseIndiaAPI/api/Suggest/w?query={symbol}`
- Returns JSON with scrip code, company name, ISIN
- Match by exact symbol or ISIN cross-reference
- Cache results to `opus/config/bse_scrip_map.json`
- Bootstrap: resolve all 213 in one batch run
- Subsequent runs: only resolve missing/stale entries

**Output format:**
```json
{
  "resolved_at": "2026-04-17T10:00:00+05:30",
  "count": 213,
  "mappings": {
    "RELIANCE": {"bse_scrip": "500325", "company_name": "Reliance Industries Ltd.", "isin": "INE002A01018"},
    ...
  }
}
```

**Rate limiting:** 1 request per second, retry with backoff on 429/5xx.

### 2. Transcript Fetcher

**File:** `opus/pipeline/retrieval/transcripts.py` (replace stub)

**Purpose:** Fetch earnings call transcripts for trust score claim extraction.

**Source priority:**
1. Screener.in — `get_transcript_urls(symbol)` → download PDF → extract text via pymupdf
2. BSE corporate announcements — category filter for "Analyst/Institutional Investor Meet"

**Output format:**
```python
[
    {
        "quarter": "Q3FY25",
        "text": "...",          # full transcript text
        "source": "screener",   # or "bse"
        "url": "https://...",
        "word_count": 4521,
        "fetched_at": "2026-04-17T10:00:00+05:30"
    }
]
```

**Quality gates:**
- Minimum 500 words per transcript (filters junk/empty PDFs)
- Deduplicate by quarter (same Q from multiple sources → prefer Screener, longer text)
- Target: 8+ quarters per stock (HAL pipeline gate requirement)

**Caching:**
- Extracted text cached to `opus/artifacts/transcripts/{symbol}/{quarter}.json`
- PDF not cached (re-downloadable, saves disk)
- Cache hit = skip download + extraction

**Error handling:**
- PDF download timeout: 30 seconds, retry once
- pymupdf extraction failure: log warning, skip that transcript
- Screener 404: fall through to BSE source
- Return whatever transcripts were successfully fetched (partial is better than nothing)

### 3. Annual Report Retriever

**File:** `opus/pipeline/retrieval/annual_reports.py` (replace stub)

**Purpose:** Fetch 5 years of annual reports for MD&A claim extraction.

**Source priority:**
1. BSE API — `bse_client.get_annual_reports(scrip_code)` (already implemented, returns PDF links)
2. Screener.in — document links where type="annual_report"
3. NSE API — gap-fill

**Output format:**
```python
[
    {
        "year": "2024",
        "source": "BSE",
        "format": "PDF",
        "url": "https://...",
        "path": "opus/artifacts/filings/{symbol}/annual/2024.pdf",  # local cached path
        "md_a_text": "...",  # extracted MD&A section text (if PDF downloaded + parsed)
        "fetched_at": "2026-04-17T10:00:00+05:30"
    }
]
```

**Key detail:** The claim extractor (step 9) needs `md_a_text` field. For now, we extract full PDF text and the claim extractor's LLM prompt identifies the MD&A section. Future: targeted section extraction.

**Caching:** Downloaded PDFs cached to `opus/artifacts/filings/{symbol}/annual/`. Extracted text alongside as `.txt`.

### 4. Quarterly Filings Retriever

**File:** `opus/pipeline/retrieval/quarterly_filings.py` (replace stub)

**Purpose:** Fetch quarterly financial results for promise-vs-delivery verification.

**Source priority:**
1. Screener.in — `get_financials(symbol)["quarterly"]` gives structured table data (10+ years, no PDF needed)
2. BSE API — `bse_client.get_financial_results(scrip_code)` for cross-verification
3. EODHD Fundamentals API — `GET /fundamentals/{symbol}.NSE` returns income statement, balance sheet, cash flow (paid, already have key)
4. IndianAPI — `GET /financial_data?stock_name={symbol}` returns P&L, balance sheet (paid, already have key)

**Output format:**
```python
[
    {
        "quarter": "Q3FY25",
        "source": "screener",
        "revenue": 15000.0,    # in crores
        "pat": 2100.0,
        "opm_pct": 22.5,
        "eps": 31.2,
        "raw_data": {...},      # full row from Screener table
        "fetched_at": "2026-04-17T10:00:00+05:30"
    }
]
```

**Cross-verification:** When both Screener and BSE have data for same quarter, compare revenue/PAT. If divergence > 5%, flag as `"cross_check": "DIVERGENT"` — don't silently pick one.

### 5. Sector Peer Imputer

**File:** `opus/pipeline/analysis/peer_imputer.py`

**Purpose:** For stocks where transcript count < 8 after all sources exhausted, impute trust score from scored sector peers.

**Approach:**
- Use sector classification from `opus/config/universe.json`
- For stocks not in universe.json sectors, use Screener peer data to identify sector
- Imputed score = weighted average of scored peers (weight by market cap if available, else equal)
- Cap imputed grade at B+ (never award A/A+ via imputation)
- Flag: `"trust_source": "PEER_IMPUTED", "peer_count": N, "peer_symbols": [...]`

**When NOT to impute:**
- If stock has ≥ 3 transcripts: run partial scoring instead (lower confidence but real data)
- If no sector peers are scored: mark as `INSUFFICIENT_DATA` (honest, not fabricated)

### 6. Batch Runner

**File:** `opus/pipeline/batch_retrieval.py`

**Purpose:** Orchestrate data retrieval for all 213 stocks with rate limiting, progress tracking, and resume capability.

**Flow per stock:**
1. Look up BSE scrip from `bse_scrip_map.json`
2. Fetch Screener financials + document links (1 HTTP request)
3. Download + extract transcript PDFs from Screener links
4. Fetch BSE annual reports + financial results (2 HTTP requests)
5. Fetch EODHD fundamentals (1 HTTP request) — cross-verify quarterly numbers
6. Fetch IndianAPI financial data (1 HTTP request) — additional cross-verify
7. Merge + deduplicate by quarter/year, flag divergences
8. If transcripts < 8: try BSE announcements + IndianAPI announcements
9. Cache all results

**Rate limiting:**
- Screener: 1 req/sec (polite, no auth)
- BSE: 2 req/sec
- NSE: 1 req/sec
- EODHD: 5 req/sec (paid tier)
- IndianAPI: 2 req/sec (paid tier)
- Global: max 3 concurrent HTTP requests

**Resume capability:**
- Write progress to `opus/artifacts/batch_progress.json`
- On restart, skip stocks already completed in current batch
- Force flag to re-fetch specific stocks

**Progress output:**
```
[42/213] RELIANCE — 12 transcripts, 5 annual reports, 40 quarterly filings ✓
[43/213] SBIN — 8 transcripts, 5 annual reports, 38 quarterly filings ✓
[44/213] ADANIGREEN — 3 transcripts (below threshold, flagged for imputation)
```

**Output summary:** `opus/artifacts/retrieval_summary.json`
```json
{
  "run_date": "2026-04-17",
  "total": 213,
  "fully_covered": 185,
  "partial_transcripts": 15,
  "imputation_needed": 13,
  "failed": 0,
  "by_source": {"screener": 195, "bse": 180, "nse": 42, "eodhd": 213, "indianapi": 200}
}
```

## Data Provenance

Every piece of fetched data carries:
- `source`: which API/scraper provided it
- `url`: original URL
- `fetched_at`: ISO timestamp
- `word_count`: for transcripts (quality indicator)

When BSE and Screener both provide data for the same item, both are stored. Cross-verification divergences are flagged, never silently resolved.

## File Changes Summary

| File | Action | Description |
|------|--------|-------------|
| `opus/pipeline/retrieval/bse_resolver.py` | CREATE | BSE scrip resolution for all 213 stocks |
| `opus/pipeline/retrieval/transcripts.py` | REPLACE | Wire to Screener + BSE sources |
| `opus/pipeline/retrieval/annual_reports.py` | REPLACE | Wire to BSE client + Screener fallback |
| `opus/pipeline/retrieval/quarterly_filings.py` | REPLACE | Wire to Screener structured data + BSE |
| `opus/pipeline/analysis/peer_imputer.py` | CREATE | Sector peer trust score imputation |
| `opus/pipeline/batch_retrieval.py` | CREATE | Orchestrator for all 213 stocks |
| `opus/config/bse_scrip_map.json` | CREATE (generated) | Cached BSE scrip mappings |
| `opus/artifacts/transcripts/` | CREATE (generated) | Cached transcript text per stock |
| `opus/artifacts/retrieval_summary.json` | CREATE (generated) | Batch run coverage report |

## Testing Strategy

- Unit tests per retrieval module with mocked HTTP responses
- Integration test: run 3 stocks (HAL, TCS, RELIANCE) end-to-end against live APIs
- Coverage test: verify batch runner handles 404s, timeouts, empty responses gracefully
- Cross-verification test: synthetic divergent data → confirm flag is set
- Imputation test: mock scored peers → verify weighted average + B+ cap

## Success Criteria

1. BSE scrip codes resolved for ≥ 200 of 213 stocks
2. Transcripts fetched for ≥ 170 of 213 stocks (≥ 8 quarters each)
3. Annual reports fetched for ≥ 190 of 213 stocks
4. Quarterly filings fetched for ≥ 200 of 213 stocks
5. After imputation: 213/213 stocks have either a real or imputed trust score
6. All data tagged with source provenance
7. BSE data flowing uniformly alongside Screener data (not Screener-only)
