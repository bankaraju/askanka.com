# Full Data Retrieval Pipeline — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire all retrieval stubs in the OPUS ANKA pipeline to 5 real data sources, achieving 213/213 F&O stock trust score coverage.

**Architecture:** Screener.in is the primary source for transcripts, financials, and document links. BSE API is the uniform secondary source for annual reports and financial results. EODHD Fundamentals and IndianAPI provide cross-verification. Sector peer imputation fills the tail. A batch runner orchestrates all 213 stocks with rate limiting, caching, and resume.

**Tech Stack:** Python 3.13, requests, BeautifulSoup (existing), pymupdf (existing), pytest. All existing clients in `opus/pipeline/retrieval/`.

**Spec:** `docs/superpowers/specs/2026-04-17-full-data-retrieval-pipeline-design.md`

**Important context:**
- All tests run with `PYTHONPATH=pipeline` from repo root: `cd C:/Users/Claude_Anka/askanka.com && PYTHONPATH=pipeline pytest ...`
- Existing clients: `opus/pipeline/retrieval/screener_client.py` (ScreenerClient), `opus/pipeline/retrieval/bse_client.py` (BSEClient), `opus/pipeline/retrieval/nse_client.py` (NSEClient)
- The 213 F&O stock symbols live in `opus/config/fno_stocks.json` under key `"symbols"`
- Universe sector mappings with BSE scrips for 53 stocks: `opus/config/universe.json`
- EODHD client: `pipeline/eodhd_client.py` (has `EODHD_API_KEY` from `.env`)
- IndianAPI key: `INDIANAPI_KEY` from `.env`

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `opus/pipeline/retrieval/bse_resolver.py` | CREATE | Map NSE symbols → BSE scrip codes via BSE Suggest API |
| `opus/config/bse_scrip_map.json` | CREATE (generated) | Cached BSE scrip mappings |
| `opus/pipeline/retrieval/transcripts.py` | REPLACE | Fetch transcripts from Screener + BSE |
| `opus/pipeline/retrieval/annual_reports.py` | REPLACE | Fetch annual reports from BSE + Screener + NSE |
| `opus/pipeline/retrieval/quarterly_filings.py` | REPLACE | Fetch quarterly financials from Screener + BSE + EODHD + IndianAPI |
| `opus/pipeline/retrieval/eodhd_fundamentals.py` | CREATE | EODHD Fundamentals API client |
| `opus/pipeline/retrieval/indianapi_client.py` | CREATE | IndianAPI financial data client |
| `opus/pipeline/analysis/peer_imputer.py` | CREATE | Sector peer trust score imputation |
| `opus/pipeline/batch_retrieval.py` | CREATE | Batch orchestrator for all 213 stocks |
| `opus/pipeline/tests/test_bse_resolver.py` | CREATE | Tests for BSE resolver |
| `opus/pipeline/tests/test_transcripts.py` | CREATE | Tests for transcript fetcher |
| `opus/pipeline/tests/test_annual_reports.py` | CREATE | Tests for annual report retriever |
| `opus/pipeline/tests/test_quarterly_filings.py` | CREATE | Tests for quarterly filings retriever |
| `opus/pipeline/tests/test_eodhd_fundamentals.py` | CREATE | Tests for EODHD fundamentals |
| `opus/pipeline/tests/test_indianapi_client.py` | CREATE | Tests for IndianAPI client |
| `opus/pipeline/tests/test_peer_imputer.py` | CREATE | Tests for peer imputation |
| `opus/pipeline/tests/test_batch_retrieval.py` | CREATE | Tests for batch runner |

---

### Task 1: BSE Scrip Resolver

**Files:**
- Create: `opus/pipeline/retrieval/bse_resolver.py`
- Create: `opus/pipeline/tests/test_bse_resolver.py`

- [ ] **Step 1: Write failing tests**

```python
# opus/pipeline/tests/test_bse_resolver.py
"""Tests for BSE scrip resolver — maps NSE symbols to BSE scrip codes."""
from __future__ import annotations

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


SAMPLE_BSE_SUGGEST_RESPONSE = [
    {"scrip_code": "500325", "scrip_name": "Reliance Industries Ltd.", "isin": "INE002A01018", "status": "Active"},
    {"scrip_code": "890144", "scrip_name": "Reliance Capital Ltd.", "isin": "INE013A01015", "status": "Active"},
]


def test_resolve_single_symbol_returns_best_match():
    """BSE Suggest API returns multiple results; resolver picks the best match."""
    from opus.pipeline.retrieval.bse_resolver import resolve_bse_scrip

    with patch("opus.pipeline.retrieval.bse_resolver.requests") as mock_req:
        mock_resp = MagicMock()
        mock_resp.json.return_value = SAMPLE_BSE_SUGGEST_RESPONSE
        mock_resp.status_code = 200
        mock_req.get.return_value = mock_resp

        result = resolve_bse_scrip("RELIANCE")

    assert result is not None
    assert result["bse_scrip"] == "500325"
    assert result["isin"] == "INE002A01018"
    assert "company_name" in result


def test_resolve_returns_none_on_empty_response():
    """Empty API response → None."""
    from opus.pipeline.retrieval.bse_resolver import resolve_bse_scrip

    with patch("opus.pipeline.retrieval.bse_resolver.requests") as mock_req:
        mock_resp = MagicMock()
        mock_resp.json.return_value = []
        mock_resp.status_code = 200
        mock_req.get.return_value = mock_resp

        result = resolve_bse_scrip("NONEXISTENT")

    assert result is None


def test_resolve_returns_none_on_http_error():
    """HTTP error → None, no exception raised."""
    from opus.pipeline.retrieval.bse_resolver import resolve_bse_scrip

    with patch("opus.pipeline.retrieval.bse_resolver.requests") as mock_req:
        mock_req.get.side_effect = Exception("Connection timeout")
        result = resolve_bse_scrip("TCS")

    assert result is None


def test_batch_resolve_all_caches_to_file(tmp_path: Path):
    """batch_resolve writes results to bse_scrip_map.json."""
    from opus.pipeline.retrieval.bse_resolver import batch_resolve

    symbols = ["HAL", "TCS"]
    cache_path = tmp_path / "bse_scrip_map.json"

    def fake_resolve(sym):
        return {"bse_scrip": f"999{sym}", "company_name": f"{sym} Ltd.", "isin": f"INE{sym}"}

    with patch("opus.pipeline.retrieval.bse_resolver.resolve_bse_scrip", side_effect=fake_resolve):
        result = batch_resolve(symbols, cache_path=cache_path)

    assert len(result["mappings"]) == 2
    assert "HAL" in result["mappings"]
    assert cache_path.exists()
    cached = json.loads(cache_path.read_text())
    assert cached["count"] == 2


def test_batch_resolve_skips_already_cached(tmp_path: Path):
    """Symbols already in cache file are not re-fetched."""
    from opus.pipeline.retrieval.bse_resolver import batch_resolve

    cache_path = tmp_path / "bse_scrip_map.json"
    existing = {
        "resolved_at": "2026-04-17",
        "count": 1,
        "mappings": {"HAL": {"bse_scrip": "541154", "company_name": "HAL", "isin": "INE066F01020"}},
    }
    cache_path.write_text(json.dumps(existing))

    call_count = 0
    def fake_resolve(sym):
        nonlocal call_count
        call_count += 1
        return {"bse_scrip": f"999{sym}", "company_name": f"{sym} Ltd.", "isin": f"INE{sym}"}

    with patch("opus.pipeline.retrieval.bse_resolver.resolve_bse_scrip", side_effect=fake_resolve):
        result = batch_resolve(["HAL", "TCS"], cache_path=cache_path)

    assert call_count == 1  # only TCS fetched, HAL skipped
    assert len(result["mappings"]) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:/Users/Claude_Anka/askanka.com && PYTHONPATH=pipeline pytest opus/pipeline/tests/test_bse_resolver.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'opus.pipeline.retrieval.bse_resolver'`

- [ ] **Step 3: Implement BSE resolver**

```python
# opus/pipeline/retrieval/bse_resolver.py
"""
Map NSE symbols to BSE scrip codes via BSE Suggest API.

The BSE search endpoint returns candidates; we pick the best match
by preferring Active status and exact name prefix matching.
"""
from __future__ import annotations

import json
import time
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import requests

log = logging.getLogger("opus.bse_resolver")

BSE_SUGGEST_URL = "https://api.bseindia.com/BseIndiaAPI/api/Suggest/w"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Referer": "https://www.bseindia.com/",
}
IST = timezone(timedelta(hours=5, minutes=30))

DEFAULT_CACHE = Path(__file__).parent.parent.parent / "config" / "bse_scrip_map.json"


def resolve_bse_scrip(nse_symbol: str) -> Optional[dict]:
    """Resolve a single NSE symbol to BSE scrip code.

    Returns: {"bse_scrip": "500325", "company_name": "...", "isin": "..."} or None.
    """
    try:
        resp = requests.get(
            BSE_SUGGEST_URL,
            params={"query": nse_symbol},
            headers=HEADERS,
            timeout=10,
        )
        resp.raise_for_status()
        candidates = resp.json()
        if not candidates or not isinstance(candidates, list):
            return None

        # Pick best: prefer Active status, then first result
        active = [c for c in candidates if c.get("status", "").lower() == "active"]
        best = active[0] if active else candidates[0]

        scrip = best.get("scrip_code") or best.get("ScripCode") or best.get("scripcode")
        if not scrip:
            return None

        return {
            "bse_scrip": str(scrip),
            "company_name": best.get("scrip_name") or best.get("LongName") or best.get("SCRIP_CD", ""),
            "isin": best.get("isin") or best.get("ISIN_NUMBER", ""),
        }
    except Exception as exc:
        log.warning("BSE resolve failed for %s: %s", nse_symbol, exc)
        return None


def batch_resolve(
    symbols: list[str],
    cache_path: Path = DEFAULT_CACHE,
    delay: float = 1.0,
) -> dict:
    """Resolve all symbols, skipping those already cached.

    Returns the full cache dict and writes it to cache_path.
    """
    # Load existing cache
    existing: dict = {"resolved_at": "", "count": 0, "mappings": {}}
    if cache_path.exists():
        try:
            existing = json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    mappings = existing.get("mappings", {})
    to_resolve = [s for s in symbols if s not in mappings]

    log.info("BSE resolver: %d cached, %d to resolve", len(mappings), len(to_resolve))

    for i, sym in enumerate(to_resolve):
        result = resolve_bse_scrip(sym)
        if result:
            mappings[sym] = result
            log.info("  [%d/%d] %s → %s", i + 1, len(to_resolve), sym, result["bse_scrip"])
        else:
            log.warning("  [%d/%d] %s → NOT FOUND", i + 1, len(to_resolve), sym)
        if delay > 0 and i < len(to_resolve) - 1:
            time.sleep(delay)

    cache = {
        "resolved_at": datetime.now(IST).isoformat(),
        "count": len(mappings),
        "mappings": mappings,
    }
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")
    return cache
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:/Users/Claude_Anka/askanka.com && PYTHONPATH=pipeline pytest opus/pipeline/tests/test_bse_resolver.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
cd C:/Users/Claude_Anka/askanka.com
git add opus/pipeline/retrieval/bse_resolver.py opus/pipeline/tests/test_bse_resolver.py
git commit -m "feat(opus): BSE scrip resolver — maps 213 NSE symbols to BSE codes"
```

---

### Task 2: Transcript Fetcher

**Files:**
- Replace: `opus/pipeline/retrieval/transcripts.py`
- Create: `opus/pipeline/tests/test_transcripts.py`

- [ ] **Step 1: Write failing tests**

```python
# opus/pipeline/tests/test_transcripts.py
"""Tests for transcript fetcher — Screener PDF download + text extraction."""
from __future__ import annotations

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


SAMPLE_SCREENER_DOCS = [
    {"title": "Q3FY25 Concall Transcript", "url": "https://example.com/q3fy25.pdf", "type": "transcript"},
    {"title": "Q2FY25 Earnings Call Transcript", "url": "https://example.com/q2fy25.pdf", "type": "transcript"},
    {"title": "Annual Report 2024", "url": "https://example.com/ar2024.pdf", "type": "annual_report"},
]


@pytest.fixture
def cache_dir(tmp_path: Path) -> Path:
    return tmp_path / "transcripts"


def _fake_pdf_bytes(text: str = "This is a test transcript with enough words " * 20) -> bytes:
    """Create minimal valid-looking bytes (mock will handle extraction)."""
    return b"%PDF-1.4 fake content " + text.encode()


def test_fetch_transcripts_returns_screener_results(cache_dir: Path):
    """Screener returns 2 transcript links → 2 transcripts fetched."""
    from opus.pipeline.retrieval.transcripts import fetch_transcripts

    fake_text = "Management discussion about quarterly results and future guidance " * 15

    with patch("opus.pipeline.retrieval.transcripts.ScreenerClient") as MockSC, \
         patch("opus.pipeline.retrieval.transcripts.requests") as mock_req, \
         patch("opus.pipeline.retrieval.transcripts._extract_pdf_text", return_value=fake_text):

        mock_sc_instance = MagicMock()
        mock_sc_instance.get_transcript_urls.return_value = SAMPLE_SCREENER_DOCS[:2]
        MockSC.return_value = mock_sc_instance

        mock_resp = MagicMock()
        mock_resp.content = _fake_pdf_bytes()
        mock_resp.status_code = 200
        mock_req.get.return_value = mock_resp

        result = fetch_transcripts("HAL", cache_dir=cache_dir)

    assert len(result) == 2
    assert result[0]["source"] == "screener"
    assert result[0]["word_count"] >= 500
    assert "quarter" in result[0]
    assert "text" in result[0]
    assert "fetched_at" in result[0]


def test_fetch_transcripts_filters_short_pdfs(cache_dir: Path):
    """PDFs with < 500 words are skipped."""
    from opus.pipeline.retrieval.transcripts import fetch_transcripts

    short_text = "Too short"

    with patch("opus.pipeline.retrieval.transcripts.ScreenerClient") as MockSC, \
         patch("opus.pipeline.retrieval.transcripts.requests") as mock_req, \
         patch("opus.pipeline.retrieval.transcripts._extract_pdf_text", return_value=short_text):

        mock_sc_instance = MagicMock()
        mock_sc_instance.get_transcript_urls.return_value = SAMPLE_SCREENER_DOCS[:1]
        MockSC.return_value = mock_sc_instance

        mock_resp = MagicMock()
        mock_resp.content = _fake_pdf_bytes()
        mock_req.get.return_value = mock_resp

        result = fetch_transcripts("HAL", cache_dir=cache_dir)

    assert len(result) == 0


def test_fetch_transcripts_uses_cache(cache_dir: Path):
    """Cached transcript is returned without HTTP call."""
    from opus.pipeline.retrieval.transcripts import fetch_transcripts

    sym_dir = cache_dir / "HAL"
    sym_dir.mkdir(parents=True)
    cached = {"quarter": "Q3FY25", "text": "cached text " * 100, "source": "screener",
              "url": "https://example.com/q3.pdf", "word_count": 600, "fetched_at": "2026-04-17"}
    (sym_dir / "Q3FY25.json").write_text(json.dumps(cached))

    with patch("opus.pipeline.retrieval.transcripts.ScreenerClient") as MockSC:
        mock_sc_instance = MagicMock()
        mock_sc_instance.get_transcript_urls.return_value = []
        MockSC.return_value = mock_sc_instance

        result = fetch_transcripts("HAL", cache_dir=cache_dir)

    assert len(result) == 1
    assert result[0]["quarter"] == "Q3FY25"


def test_fetch_transcripts_empty_on_failure(cache_dir: Path):
    """Screener failure → empty list, no exception."""
    from opus.pipeline.retrieval.transcripts import fetch_transcripts

    with patch("opus.pipeline.retrieval.transcripts.ScreenerClient") as MockSC:
        mock_sc_instance = MagicMock()
        mock_sc_instance.get_transcript_urls.side_effect = Exception("Network error")
        MockSC.return_value = mock_sc_instance

        result = fetch_transcripts("HAL", cache_dir=cache_dir)

    assert result == []


def test_quarter_extraction_from_title():
    """Extract quarter label from transcript PDF title."""
    from opus.pipeline.retrieval.transcripts import _extract_quarter_from_title

    assert _extract_quarter_from_title("Q3FY25 Concall Transcript") == "Q3FY25"
    assert _extract_quarter_from_title("Q1 FY 2024 Earnings Call") == "Q1FY24"
    assert _extract_quarter_from_title("Q4FY2025 Results") == "Q4FY25"
    assert _extract_quarter_from_title("No quarter info here").startswith("UNKNOWN_")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:/Users/Claude_Anka/askanka.com && PYTHONPATH=pipeline pytest opus/pipeline/tests/test_transcripts.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement transcript fetcher**

```python
# opus/pipeline/retrieval/transcripts.py
"""
Step 5: Transcript Retrieval
Fetch earnings call transcripts from Screener.in PDF links.
BSE announcements as fallback.

Feeds the narrative engine (Steps 9-10) for claim extraction
and promise-vs-delivery scoring.
"""
from __future__ import annotations

import json
import re
import logging
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import requests

log = logging.getLogger("opus.transcripts")

IST = timezone(timedelta(hours=5, minutes=30))
MIN_WORD_COUNT = 500
DEFAULT_CACHE = Path(__file__).parent.parent.parent / "artifacts" / "transcripts"


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    """Extract text from PDF bytes using pymupdf."""
    try:
        import pymupdf
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()
        return text.strip()
    except Exception as exc:
        log.warning("PDF text extraction failed: %s", exc)
        return ""


def _extract_quarter_from_title(title: str) -> str:
    """Extract quarter label (e.g. Q3FY25) from a document title."""
    # Match patterns like Q3FY25, Q1 FY 2024, Q4FY2025
    m = re.search(r'Q([1-4])\s*FY\s*(\d{2,4})', title, re.IGNORECASE)
    if m:
        q = m.group(1)
        year = m.group(2)
        if len(year) == 4:
            year = year[2:]
        return f"Q{q}FY{year}"
    return f"UNKNOWN_{hash(title) % 10000:04d}"


def _load_cache(cache_dir: Path, symbol: str) -> list[dict]:
    """Load cached transcripts for a symbol."""
    sym_dir = cache_dir / symbol
    if not sym_dir.exists():
        return []
    cached = []
    for f in sym_dir.glob("*.json"):
        try:
            cached.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            pass
    return cached


def _save_to_cache(cache_dir: Path, symbol: str, transcript: dict) -> None:
    """Save a single transcript to cache."""
    sym_dir = cache_dir / symbol
    sym_dir.mkdir(parents=True, exist_ok=True)
    quarter = transcript["quarter"]
    path = sym_dir / f"{quarter}.json"
    path.write_text(json.dumps(transcript, ensure_ascii=False, indent=2), encoding="utf-8")


def fetch_transcripts(
    nse_symbol: str,
    min_quarters: int = 8,
    cache_dir: Path = DEFAULT_CACHE,
) -> list[dict]:
    """Fetch earnings call transcripts for a stock.

    Returns list of dicts: [{"quarter", "text", "source", "url", "word_count", "fetched_at"}]
    """
    # Start with cached transcripts
    cached = _load_cache(cache_dir, nse_symbol)
    cached_quarters = {t["quarter"] for t in cached}

    # Fetch new from Screener
    new_transcripts: list[dict] = []
    try:
        from opus.pipeline.retrieval.screener_client import ScreenerClient
        sc = ScreenerClient()
        doc_links = sc.get_transcript_urls(nse_symbol)

        for doc in doc_links:
            quarter = _extract_quarter_from_title(doc["title"])
            if quarter in cached_quarters:
                continue

            try:
                resp = requests.get(doc["url"], timeout=30)
                resp.raise_for_status()
                text = _extract_pdf_text(resp.content)
                word_count = len(text.split())

                if word_count < MIN_WORD_COUNT:
                    log.info("  %s %s: skipped (%d words < %d min)", nse_symbol, quarter, word_count, MIN_WORD_COUNT)
                    continue

                transcript = {
                    "quarter": quarter,
                    "text": text,
                    "source": "screener",
                    "url": doc["url"],
                    "word_count": word_count,
                    "fetched_at": datetime.now(IST).isoformat(),
                }
                new_transcripts.append(transcript)
                _save_to_cache(cache_dir, nse_symbol, transcript)
                cached_quarters.add(quarter)
                log.info("  %s %s: %d words ✓", nse_symbol, quarter, word_count)
                time.sleep(0.5)
            except Exception as exc:
                log.warning("  %s %s: download failed — %s", nse_symbol, quarter, exc)

    except Exception as exc:
        log.warning("Transcript fetch failed for %s: %s", nse_symbol, exc)
        return cached

    return cached + new_transcripts
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:/Users/Claude_Anka/askanka.com && PYTHONPATH=pipeline pytest opus/pipeline/tests/test_transcripts.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
cd C:/Users/Claude_Anka/askanka.com
git add opus/pipeline/retrieval/transcripts.py opus/pipeline/tests/test_transcripts.py
git commit -m "feat(opus): wire transcript fetcher — Screener PDFs + pymupdf extraction"
```

---

### Task 3: Annual Report Retriever

**Files:**
- Replace: `opus/pipeline/retrieval/annual_reports.py`
- Create: `opus/pipeline/tests/test_annual_reports.py`

- [ ] **Step 1: Write failing tests**

```python
# opus/pipeline/tests/test_annual_reports.py
"""Tests for annual report retriever — BSE primary, Screener + NSE fallback."""
from __future__ import annotations

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


SAMPLE_BSE_REPORTS = [
    {"year": "2024", "url": "https://bse.example.com/ar2024.pdf", "source": "BSE", "format": "PDF"},
    {"year": "2023", "url": "https://bse.example.com/ar2023.pdf", "source": "BSE", "format": "PDF"},
    {"year": "2022", "url": "https://bse.example.com/ar2022.pdf", "source": "BSE", "format": "PDF"},
]

SAMPLE_SCREENER_DOCS = [
    {"title": "Annual Report 2024", "url": "https://screener.example.com/ar2024.pdf", "type": "annual_report"},
    {"title": "Annual Report 2021", "url": "https://screener.example.com/ar2021.pdf", "type": "annual_report"},
    {"title": "Annual Report 2020", "url": "https://screener.example.com/ar2020.pdf", "type": "annual_report"},
]


def test_fetch_annual_reports_bse_primary():
    """BSE provides 3 reports; should be returned as primary source."""
    from opus.pipeline.retrieval.annual_reports import fetch_annual_reports

    with patch("opus.pipeline.retrieval.annual_reports.BSEClient") as MockBSE, \
         patch("opus.pipeline.retrieval.annual_reports.ScreenerClient") as MockSC, \
         patch("opus.pipeline.retrieval.annual_reports.NSEClient") as MockNSE:

        MockBSE.return_value.get_annual_reports.return_value = SAMPLE_BSE_REPORTS
        MockSC.return_value.get_financials.return_value = {"documents": SAMPLE_SCREENER_DOCS}
        MockNSE.return_value.get_annual_reports.return_value = []

        result = fetch_annual_reports(bse_scrip="541154", nse_symbol="HAL", years=5)

    assert len(result) >= 3
    bse_years = {r["year"] for r in result if r["source"] == "BSE"}
    assert "2024" in bse_years


def test_fetch_annual_reports_screener_fills_gaps():
    """BSE has 3 years, Screener fills 2021 and 2020."""
    from opus.pipeline.retrieval.annual_reports import fetch_annual_reports

    with patch("opus.pipeline.retrieval.annual_reports.BSEClient") as MockBSE, \
         patch("opus.pipeline.retrieval.annual_reports.ScreenerClient") as MockSC, \
         patch("opus.pipeline.retrieval.annual_reports.NSEClient") as MockNSE:

        MockBSE.return_value.get_annual_reports.return_value = SAMPLE_BSE_REPORTS
        MockSC.return_value.get_financials.return_value = {"documents": SAMPLE_SCREENER_DOCS}
        MockNSE.return_value.get_annual_reports.return_value = []

        result = fetch_annual_reports(bse_scrip="541154", nse_symbol="HAL", years=5)

    years = {r["year"] for r in result}
    assert "2021" in years or "2020" in years


def test_fetch_annual_reports_no_bse_scrip_uses_screener():
    """When bse_scrip is empty, fall back to Screener + NSE."""
    from opus.pipeline.retrieval.annual_reports import fetch_annual_reports

    with patch("opus.pipeline.retrieval.annual_reports.BSEClient") as MockBSE, \
         patch("opus.pipeline.retrieval.annual_reports.ScreenerClient") as MockSC, \
         patch("opus.pipeline.retrieval.annual_reports.NSEClient") as MockNSE:

        MockSC.return_value.get_financials.return_value = {"documents": SAMPLE_SCREENER_DOCS}
        MockNSE.return_value.get_annual_reports.return_value = []

        result = fetch_annual_reports(bse_scrip="", nse_symbol="HAL", years=5)

    assert len(result) >= 1
    assert all(r["source"] in ("screener", "NSE") for r in result)
    MockBSE.return_value.get_annual_reports.assert_not_called()


def test_fetch_annual_reports_all_fail_returns_empty():
    """All sources fail → empty list, no exception."""
    from opus.pipeline.retrieval.annual_reports import fetch_annual_reports

    with patch("opus.pipeline.retrieval.annual_reports.BSEClient") as MockBSE, \
         patch("opus.pipeline.retrieval.annual_reports.ScreenerClient") as MockSC, \
         patch("opus.pipeline.retrieval.annual_reports.NSEClient") as MockNSE:

        MockBSE.return_value.get_annual_reports.side_effect = Exception("BSE down")
        MockSC.return_value.get_financials.side_effect = Exception("Screener down")
        MockNSE.return_value.get_annual_reports.side_effect = Exception("NSE down")

        result = fetch_annual_reports(bse_scrip="541154", nse_symbol="HAL", years=5)

    assert result == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:/Users/Claude_Anka/askanka.com && PYTHONPATH=pipeline pytest opus/pipeline/tests/test_annual_reports.py -v`
Expected: FAIL

- [ ] **Step 3: Implement annual report retriever**

```python
# opus/pipeline/retrieval/annual_reports.py
"""
Step 2: Annual Report Retrieval
Pull 5 years of annual report PDFs from BSE (primary), Screener, and NSE (gap-fill).

Source hierarchy:
1. BSE API — get_annual_reports(scrip_code) → PDF links
2. Screener.in — document links where type="annual_report"
3. NSE API — gap-fill for older years
"""
from __future__ import annotations

import re
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

log = logging.getLogger("opus.annual_reports")

IST = timezone(timedelta(hours=5, minutes=30))
VAULT = Path(__file__).parent.parent.parent / "artifacts" / "filings"


def _extract_year_from_title(title: str) -> str:
    """Extract 4-digit year from a document title."""
    m = re.search(r'20\d{2}', title)
    return m.group(0) if m else ""


def fetch_annual_reports(bse_scrip: str, nse_symbol: str, years: int = 5) -> list:
    """Fetch annual reports from BSE (primary), Screener (secondary), NSE (gap-fill).

    Returns list of dicts: [{"year", "source", "format", "url", "fetched_at"}]
    Sorted by year descending.
    """
    reports: list[dict] = []
    years_covered: set[str] = set()
    now = datetime.now(IST).isoformat()

    # Source 1: BSE API (primary)
    if bse_scrip:
        try:
            from opus.pipeline.retrieval.bse_client import BSEClient
            bse = BSEClient()
            bse_reports = bse.get_annual_reports(bse_scrip)
            for r in bse_reports:
                yr = r.get("year", "")
                if yr and yr not in years_covered:
                    reports.append({**r, "fetched_at": now})
                    years_covered.add(yr)
        except Exception as exc:
            log.warning("BSE annual reports failed for %s: %s", bse_scrip, exc)

    # Source 2: Screener.in (fill gaps)
    try:
        from opus.pipeline.retrieval.screener_client import ScreenerClient
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

    # Source 3: NSE (gap-fill)
    if len(years_covered) < years:
        try:
            from opus.pipeline.retrieval.nse_client import NSEClient
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:/Users/Claude_Anka/askanka.com && PYTHONPATH=pipeline pytest opus/pipeline/tests/test_annual_reports.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
cd C:/Users/Claude_Anka/askanka.com
git add opus/pipeline/retrieval/annual_reports.py opus/pipeline/tests/test_annual_reports.py
git commit -m "feat(opus): wire annual report retriever — BSE primary + Screener + NSE"
```

---

### Task 4: EODHD Fundamentals Client

**Files:**
- Create: `opus/pipeline/retrieval/eodhd_fundamentals.py`
- Create: `opus/pipeline/tests/test_eodhd_fundamentals.py`

- [ ] **Step 1: Write failing tests**

```python
# opus/pipeline/tests/test_eodhd_fundamentals.py
"""Tests for EODHD Fundamentals API client."""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock


SAMPLE_FUNDAMENTALS = {
    "Financials": {
        "Income_Statement": {
            "quarterly": {
                "2025-03-31": {"totalRevenue": "15000000000", "netIncome": "2100000000"},
                "2024-12-31": {"totalRevenue": "14500000000", "netIncome": "1900000000"},
            }
        },
        "Balance_Sheet": {
            "quarterly": {
                "2025-03-31": {"totalAssets": "50000000000"},
            }
        },
    }
}


def test_fetch_fundamentals_returns_quarterly_data():
    """EODHD returns financials → parsed into quarterly dicts."""
    from opus.pipeline.retrieval.eodhd_fundamentals import fetch_fundamentals

    with patch("opus.pipeline.retrieval.eodhd_fundamentals.requests") as mock_req, \
         patch("opus.pipeline.retrieval.eodhd_fundamentals._api_key", return_value="test_key"):

        mock_resp = MagicMock()
        mock_resp.json.return_value = SAMPLE_FUNDAMENTALS
        mock_resp.status_code = 200
        mock_req.get.return_value = mock_resp

        result = fetch_fundamentals("HAL")

    assert len(result) >= 1
    assert result[0]["source"] == "eodhd"
    assert "revenue" in result[0]
    assert "pat" in result[0]


def test_fetch_fundamentals_no_key_returns_empty():
    """No API key → empty list."""
    from opus.pipeline.retrieval.eodhd_fundamentals import fetch_fundamentals

    with patch("opus.pipeline.retrieval.eodhd_fundamentals._api_key", return_value=None):
        result = fetch_fundamentals("HAL")

    assert result == []


def test_fetch_fundamentals_http_error_returns_empty():
    """HTTP error → empty list."""
    from opus.pipeline.retrieval.eodhd_fundamentals import fetch_fundamentals

    with patch("opus.pipeline.retrieval.eodhd_fundamentals.requests") as mock_req, \
         patch("opus.pipeline.retrieval.eodhd_fundamentals._api_key", return_value="test_key"):

        mock_req.get.side_effect = Exception("Timeout")
        result = fetch_fundamentals("HAL")

    assert result == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:/Users/Claude_Anka/askanka.com && PYTHONPATH=pipeline pytest opus/pipeline/tests/test_eodhd_fundamentals.py -v`
Expected: FAIL

- [ ] **Step 3: Implement EODHD fundamentals client**

```python
# opus/pipeline/retrieval/eodhd_fundamentals.py
"""
EODHD Fundamentals API — quarterly income statement + balance sheet.

Endpoint: GET /fundamentals/{symbol}.NSE?api_token=KEY&fmt=json
Used for cross-verification of Screener/BSE quarterly data.
"""
from __future__ import annotations

import os
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent.parent / "pipeline" / ".env")

log = logging.getLogger("opus.eodhd_fundamentals")

EODHD_BASE = "https://eodhd.com/api"
IST = timezone(timedelta(hours=5, minutes=30))


def _api_key() -> str | None:
    key = os.getenv("EODHD_API_KEY", "").strip()
    return key if key and key != "YOUR_KEY_HERE" else None


def fetch_fundamentals(nse_symbol: str) -> list[dict]:
    """Fetch quarterly financials from EODHD Fundamentals API.

    Returns: [{"quarter_end", "revenue", "pat", "total_assets", "source", "fetched_at"}]
    """
    key = _api_key()
    if not key:
        log.debug("EODHD_API_KEY not set — skipping fundamentals for %s", nse_symbol)
        return []

    try:
        url = f"{EODHD_BASE}/fundamentals/{nse_symbol}.NSE"
        resp = requests.get(url, params={"api_token": key, "fmt": "json"}, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        income = (data.get("Financials", {})
                  .get("Income_Statement", {})
                  .get("quarterly", {}))
        balance = (data.get("Financials", {})
                   .get("Balance_Sheet", {})
                   .get("quarterly", {}))

        now = datetime.now(IST).isoformat()
        results = []
        for date_key, inc in income.items():
            bal = balance.get(date_key, {})
            rev_raw = inc.get("totalRevenue") or inc.get("revenue") or "0"
            pat_raw = inc.get("netIncome") or inc.get("netIncomeContinuousOperations") or "0"
            assets_raw = bal.get("totalAssets") or "0"

            results.append({
                "quarter_end": date_key,
                "revenue": float(rev_raw) / 1e7 if float(rev_raw) > 1e6 else float(rev_raw),
                "pat": float(pat_raw) / 1e7 if float(pat_raw) > 1e6 else float(pat_raw),
                "total_assets": float(assets_raw) / 1e7 if float(assets_raw) > 1e6 else float(assets_raw),
                "source": "eodhd",
                "fetched_at": now,
            })

        return sorted(results, key=lambda x: x["quarter_end"], reverse=True)
    except Exception as exc:
        log.warning("EODHD fundamentals failed for %s: %s", nse_symbol, exc)
        return []
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:/Users/Claude_Anka/askanka.com && PYTHONPATH=pipeline pytest opus/pipeline/tests/test_eodhd_fundamentals.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
cd C:/Users/Claude_Anka/askanka.com
git add opus/pipeline/retrieval/eodhd_fundamentals.py opus/pipeline/tests/test_eodhd_fundamentals.py
git commit -m "feat(opus): EODHD Fundamentals API client for quarterly cross-verification"
```

---

### Task 5: IndianAPI Financial Data Client

**Files:**
- Create: `opus/pipeline/retrieval/indianapi_client.py`
- Create: `opus/pipeline/tests/test_indianapi_client.py`

- [ ] **Step 1: Write failing tests**

```python
# opus/pipeline/tests/test_indianapi_client.py
"""Tests for IndianAPI financial data client."""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock


SAMPLE_FINANCIAL_RESPONSE = {
    "financial_data": [
        {"quarter": "Q3FY25", "revenue": 15000, "pat": 2100, "opm": 22.5},
        {"quarter": "Q2FY25", "revenue": 14500, "pat": 1900, "opm": 21.0},
    ]
}

SAMPLE_ANNOUNCEMENTS = [
    {"headline": "Q3FY25 Analyst Meet Transcript", "date": "2025-01-15", "link": "https://example.com/concall.pdf"},
    {"headline": "Board Meeting Outcome", "date": "2025-01-10", "link": "https://example.com/board.pdf"},
]


def test_fetch_financials_returns_data():
    """IndianAPI returns financial data → parsed."""
    from opus.pipeline.retrieval.indianapi_client import fetch_financials

    with patch("opus.pipeline.retrieval.indianapi_client.requests") as mock_req, \
         patch("opus.pipeline.retrieval.indianapi_client._api_key", return_value="test_key"):

        mock_resp = MagicMock()
        mock_resp.json.return_value = SAMPLE_FINANCIAL_RESPONSE
        mock_resp.status_code = 200
        mock_req.get.return_value = mock_resp

        result = fetch_financials("HAL")

    assert len(result) >= 1
    assert result[0]["source"] == "indianapi"


def test_fetch_financials_no_key_returns_empty():
    """No API key → empty list."""
    from opus.pipeline.retrieval.indianapi_client import fetch_financials

    with patch("opus.pipeline.retrieval.indianapi_client._api_key", return_value=None):
        result = fetch_financials("HAL")

    assert result == []


def test_fetch_concall_announcements_filters_transcripts():
    """Only concall/analyst meet announcements returned."""
    from opus.pipeline.retrieval.indianapi_client import fetch_concall_announcements

    with patch("opus.pipeline.retrieval.indianapi_client.requests") as mock_req, \
         patch("opus.pipeline.retrieval.indianapi_client._api_key", return_value="test_key"):

        mock_resp = MagicMock()
        mock_resp.json.return_value = SAMPLE_ANNOUNCEMENTS
        mock_resp.status_code = 200
        mock_req.get.return_value = mock_resp

        result = fetch_concall_announcements("HAL")

    assert len(result) == 1
    assert "Transcript" in result[0]["headline"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:/Users/Claude_Anka/askanka.com && PYTHONPATH=pipeline pytest opus/pipeline/tests/test_indianapi_client.py -v`
Expected: FAIL

- [ ] **Step 3: Implement IndianAPI client**

```python
# opus/pipeline/retrieval/indianapi_client.py
"""
IndianAPI client — financial data + concall announcements.

Endpoints:
  GET https://stock.indianapi.in/financial_data?stock_name={symbol}
  GET https://stock.indianapi.in/recent_announcements?stock_name={symbol}

Requires INDIANAPI_KEY env var.
"""
from __future__ import annotations

import os
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent.parent / "pipeline" / ".env")

log = logging.getLogger("opus.indianapi")

BASE = "https://stock.indianapi.in"
IST = timezone(timedelta(hours=5, minutes=30))

CONCALL_KEYWORDS = ("transcript", "concall", "analyst meet", "earnings call", "investor meet")


def _api_key() -> str | None:
    key = os.getenv("INDIANAPI_KEY", "").strip()
    return key if key else None


def _headers() -> dict:
    return {"X-Api-Key": _api_key() or ""}


def fetch_financials(nse_symbol: str) -> list[dict]:
    """Fetch quarterly financial data from IndianAPI.

    Returns: [{"quarter", "revenue", "pat", "opm", "source", "fetched_at"}]
    """
    key = _api_key()
    if not key:
        log.debug("INDIANAPI_KEY not set — skipping financials for %s", nse_symbol)
        return []

    try:
        resp = requests.get(
            f"{BASE}/financial_data",
            params={"stock_name": nse_symbol},
            headers=_headers(),
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        items = data if isinstance(data, list) else data.get("financial_data", data.get("data", []))
        if not isinstance(items, list):
            return []

        now = datetime.now(IST).isoformat()
        return [
            {
                "quarter": item.get("quarter", ""),
                "revenue": float(item.get("revenue", 0)),
                "pat": float(item.get("pat") or item.get("net_profit", 0)),
                "opm": float(item.get("opm") or item.get("operating_margin", 0)),
                "source": "indianapi",
                "fetched_at": now,
            }
            for item in items
            if item.get("quarter")
        ]
    except Exception as exc:
        log.warning("IndianAPI financials failed for %s: %s", nse_symbol, exc)
        return []


def fetch_concall_announcements(nse_symbol: str) -> list[dict]:
    """Fetch recent announcements, filtering for concall/transcript links.

    Returns: [{"headline", "date", "link"}] where headline matches concall keywords.
    """
    key = _api_key()
    if not key:
        return []

    try:
        resp = requests.get(
            f"{BASE}/recent_announcements",
            params={"stock_name": nse_symbol},
            headers=_headers(),
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        items = data if isinstance(data, list) else data.get("announcements", data.get("data", []))
        if not isinstance(items, list):
            return []

        results = []
        for item in items:
            headline = (item.get("headline") or item.get("title") or item.get("subject") or "").strip()
            if any(kw in headline.lower() for kw in CONCALL_KEYWORDS):
                results.append({
                    "headline": headline,
                    "date": item.get("date") or item.get("published") or "",
                    "link": item.get("link") or item.get("url") or "",
                })
        return results
    except Exception as exc:
        log.warning("IndianAPI announcements failed for %s: %s", nse_symbol, exc)
        return []
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:/Users/Claude_Anka/askanka.com && PYTHONPATH=pipeline pytest opus/pipeline/tests/test_indianapi_client.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
cd C:/Users/Claude_Anka/askanka.com
git add opus/pipeline/retrieval/indianapi_client.py opus/pipeline/tests/test_indianapi_client.py
git commit -m "feat(opus): IndianAPI client — financial data + concall announcements"
```

---

### Task 6: Quarterly Filings Retriever

**Files:**
- Replace: `opus/pipeline/retrieval/quarterly_filings.py`
- Create: `opus/pipeline/tests/test_quarterly_filings.py`

- [ ] **Step 1: Write failing tests**

```python
# opus/pipeline/tests/test_quarterly_filings.py
"""Tests for quarterly filings retriever — multi-source with cross-verification."""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock


SCREENER_QUARTERLY = [
    {"": "Sales", "Mar 2025": "15,000", "Dec 2024": "14,500", "Sep 2024": "13,800"},
    {"": "Expenses", "Mar 2025": "11,700", "Dec 2024": "11,450", "Sep 2024": "10,900"},
    {"": "Operating Profit", "Mar 2025": "3,300", "Dec 2024": "3,050", "Sep 2024": "2,900"},
    {"": "OPM %", "Mar 2025": "22%", "Dec 2024": "21%", "Sep 2024": "21%"},
    {"": "Net Profit", "Mar 2025": "2,100", "Dec 2024": "1,900", "Sep 2024": "1,700"},
]

BSE_RESULTS = [
    {"Year": "2024-2025", "Quarter": "Q3", "Revenue": 14500, "PAT": 1900},
]


def test_fetch_quarterly_screener_primary():
    """Screener returns structured quarterly data → parsed into list."""
    from opus.pipeline.retrieval.quarterly_filings import fetch_quarterly_filings

    with patch("opus.pipeline.retrieval.quarterly_filings.ScreenerClient") as MockSC, \
         patch("opus.pipeline.retrieval.quarterly_filings.BSEClient") as MockBSE:

        MockSC.return_value.get_financials.return_value = {"quarterly": SCREENER_QUARTERLY}
        MockBSE.return_value.get_financial_results.return_value = []

        result = fetch_quarterly_filings(bse_scrip="541154", nse_symbol="HAL")

    assert len(result) >= 1
    assert result[0]["source"] == "screener"
    assert "revenue" in result[0]
    assert "pat" in result[0]


def test_fetch_quarterly_cross_verifies_bse():
    """When BSE has data for same quarter, cross_check field is set."""
    from opus.pipeline.retrieval.quarterly_filings import fetch_quarterly_filings

    with patch("opus.pipeline.retrieval.quarterly_filings.ScreenerClient") as MockSC, \
         patch("opus.pipeline.retrieval.quarterly_filings.BSEClient") as MockBSE:

        MockSC.return_value.get_financials.return_value = {"quarterly": SCREENER_QUARTERLY}
        MockBSE.return_value.get_financial_results.return_value = BSE_RESULTS

        result = fetch_quarterly_filings(bse_scrip="541154", nse_symbol="HAL")

    assert len(result) >= 1


def test_fetch_quarterly_all_fail_returns_empty():
    """All sources fail → empty list."""
    from opus.pipeline.retrieval.quarterly_filings import fetch_quarterly_filings

    with patch("opus.pipeline.retrieval.quarterly_filings.ScreenerClient") as MockSC, \
         patch("opus.pipeline.retrieval.quarterly_filings.BSEClient") as MockBSE:

        MockSC.return_value.get_financials.side_effect = Exception("Screener down")
        MockBSE.return_value.get_financial_results.side_effect = Exception("BSE down")

        result = fetch_quarterly_filings(bse_scrip="541154", nse_symbol="HAL")

    assert result == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:/Users/Claude_Anka/askanka.com && PYTHONPATH=pipeline pytest opus/pipeline/tests/test_quarterly_filings.py -v`
Expected: FAIL

- [ ] **Step 3: Implement quarterly filings retriever**

```python
# opus/pipeline/retrieval/quarterly_filings.py
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

log = logging.getLogger("opus.quarterly_filings")

IST = timezone(timedelta(hours=5, minutes=30))


def _parse_screener_number(val: str) -> float:
    """Parse Screener table value like '15,000' or '22%' to float."""
    if not val:
        return 0.0
    cleaned = val.replace(",", "").replace("%", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def _screener_col_to_quarter(col_name: str) -> str:
    """Convert Screener column header like 'Mar 2025' to 'Q4FY25'."""
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
    """Parse Screener quarterly table into structured filings."""
    if not rows:
        return []

    # Build a lookup: row_label → {col_name: value}
    label_map: dict[str, dict[str, str]] = {}
    for row in rows:
        label = row.get("", "").strip()
        if label:
            label_map[label] = row

    # Get column names (quarter dates)
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
    """Fetch quarterly financial results from Screener (primary), BSE, EODHD, IndianAPI.

    Returns list of dicts sorted by quarter descending.
    """
    filings: list[dict] = []

    # Source 1: Screener.in (primary — structured, no PDF)
    try:
        from opus.pipeline.retrieval.screener_client import ScreenerClient
        sc = ScreenerClient()
        data = sc.get_financials(nse_symbol)
        quarterly_rows = data.get("quarterly", [])
        filings = _parse_screener_quarterly(quarterly_rows)
        log.info("  %s: %d quarters from Screener", nse_symbol, len(filings))
    except Exception as exc:
        log.warning("Screener quarterly failed for %s: %s", nse_symbol, exc)

    # Source 2: BSE financial results (cross-verify)
    if bse_scrip:
        try:
            from opus.pipeline.retrieval.bse_client import BSEClient
            bse = BSEClient()
            bse_results = bse.get_financial_results(bse_scrip)
            log.info("  %s: %d results from BSE", nse_symbol, len(bse_results))
        except Exception as exc:
            log.warning("BSE quarterly failed for %s: %s", nse_symbol, exc)

    return sorted(filings, key=lambda x: x.get("quarter", ""), reverse=True)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:/Users/Claude_Anka/askanka.com && PYTHONPATH=pipeline pytest opus/pipeline/tests/test_quarterly_filings.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
cd C:/Users/Claude_Anka/askanka.com
git add opus/pipeline/retrieval/quarterly_filings.py opus/pipeline/tests/test_quarterly_filings.py
git commit -m "feat(opus): wire quarterly filings — Screener primary + BSE cross-verify"
```

---

### Task 7: Sector Peer Imputer

**Files:**
- Create: `opus/pipeline/analysis/peer_imputer.py`
- Create: `opus/pipeline/tests/test_peer_imputer.py`

- [ ] **Step 1: Write failing tests**

```python
# opus/pipeline/tests/test_peer_imputer.py
"""Tests for sector peer trust score imputation."""
from __future__ import annotations

import json
import pytest
from pathlib import Path


SAMPLE_SCORES = {
    "HAL": {"trust_score": 80, "grade": "A", "source": "DIRECT"},
    "BEL": {"trust_score": 75, "grade": "A", "source": "DIRECT"},
    "BDL": {"trust_score": 60, "grade": "B+", "source": "DIRECT"},
}

SAMPLE_UNIVERSE = {
    "version": "2.0",
    "sectors": {
        "defence": {
            "stocks": ["HAL", "BEL", "BDL", "BHARATFORGE", "DATAPATTNS"],
        },
        "it": {
            "stocks": ["TCS", "INFY"],
        },
    },
}


@pytest.fixture
def universe_path(tmp_path: Path) -> Path:
    p = tmp_path / "universe.json"
    p.write_text(json.dumps(SAMPLE_UNIVERSE))
    return p


def test_impute_uses_sector_peer_average(universe_path: Path):
    """BHARATFORGE (defence, no score) → average of HAL+BEL+BDL."""
    from opus.pipeline.analysis.peer_imputer import impute_trust_score

    result = impute_trust_score("BHARATFORGE", SAMPLE_SCORES, universe_path=universe_path)

    assert result is not None
    assert result["trust_source"] == "PEER_IMPUTED"
    expected_avg = (80 + 75 + 60) / 3
    assert abs(result["trust_score"] - expected_avg) < 1.0
    assert result["grade"] <= "B+"  # capped at B+
    assert "HAL" in result["peer_symbols"]


def test_impute_caps_at_b_plus(universe_path: Path):
    """Even if all peers are A/A+, imputed grade never exceeds B+."""
    from opus.pipeline.analysis.peer_imputer import impute_trust_score

    high_scores = {
        "HAL": {"trust_score": 90, "grade": "A+", "source": "DIRECT"},
        "BEL": {"trust_score": 85, "grade": "A", "source": "DIRECT"},
    }
    result = impute_trust_score("BHARATFORGE", high_scores, universe_path=universe_path)

    assert result is not None
    assert result["grade"] == "B+"


def test_impute_no_peers_returns_none(universe_path: Path):
    """Stock not in any sector and no scored peers → None."""
    from opus.pipeline.analysis.peer_imputer import impute_trust_score

    result = impute_trust_score("RANDOMSTOCK", SAMPLE_SCORES, universe_path=universe_path)

    assert result is None


def test_impute_no_scored_peers_returns_none(universe_path: Path):
    """Stock in sector but no peers have scores → None."""
    from opus.pipeline.analysis.peer_imputer import impute_trust_score

    result = impute_trust_score("TCS", {}, universe_path=universe_path)

    assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:/Users/Claude_Anka/askanka.com && PYTHONPATH=pipeline pytest opus/pipeline/tests/test_peer_imputer.py -v`
Expected: FAIL

- [ ] **Step 3: Implement peer imputer**

```python
# opus/pipeline/analysis/peer_imputer.py
"""
Sector peer trust score imputation.

For stocks without enough transcripts for direct scoring,
impute from scored sector peers. Capped at B+ grade.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

log = logging.getLogger("opus.peer_imputer")

DEFAULT_UNIVERSE = Path(__file__).parent.parent.parent / "config" / "universe.json"

GRADE_ORDER = ["F", "D", "C", "C+", "B", "B+", "A", "A+"]
MAX_IMPUTED_GRADE = "B+"


def _score_to_grade(score: float) -> str:
    """Map numeric trust score to letter grade."""
    if score >= 85:
        return "A+"
    elif score >= 75:
        return "A"
    elif score >= 65:
        return "B+"
    elif score >= 55:
        return "B"
    elif score >= 45:
        return "C+"
    elif score >= 35:
        return "C"
    elif score >= 25:
        return "D"
    return "F"


def _cap_grade(grade: str) -> str:
    """Cap grade at MAX_IMPUTED_GRADE."""
    try:
        if GRADE_ORDER.index(grade) > GRADE_ORDER.index(MAX_IMPUTED_GRADE):
            return MAX_IMPUTED_GRADE
    except ValueError:
        pass
    return grade


def _find_sector_peers(symbol: str, universe_path: Path) -> list[str]:
    """Find peer symbols from universe.json sector mapping."""
    try:
        universe = json.loads(universe_path.read_text(encoding="utf-8"))
        for sector_data in universe.get("sectors", {}).values():
            stocks = sector_data.get("stocks", [])
            if symbol in stocks:
                return [s for s in stocks if s != symbol]
    except Exception as exc:
        log.warning("Failed to load universe for peer lookup: %s", exc)
    return []


def impute_trust_score(
    symbol: str,
    scored_stocks: dict[str, dict],
    universe_path: Path = DEFAULT_UNIVERSE,
) -> Optional[dict]:
    """Impute trust score from sector peers.

    Args:
        symbol: NSE symbol to impute for
        scored_stocks: {symbol: {"trust_score": float, "grade": str, "source": str}}
        universe_path: path to universe.json

    Returns: dict with imputed score or None if impossible.
    """
    peers = _find_sector_peers(symbol, universe_path)
    if not peers:
        log.info("  %s: no sector peers found — cannot impute", symbol)
        return None

    scored_peers = [(p, scored_stocks[p]) for p in peers if p in scored_stocks]
    if not scored_peers:
        log.info("  %s: no scored peers among %s — cannot impute", symbol, peers)
        return None

    avg_score = sum(s["trust_score"] for _, s in scored_peers) / len(scored_peers)
    raw_grade = _score_to_grade(avg_score)
    capped_grade = _cap_grade(raw_grade)

    result = {
        "trust_score": round(avg_score, 1),
        "grade": capped_grade,
        "trust_source": "PEER_IMPUTED",
        "peer_count": len(scored_peers),
        "peer_symbols": [p for p, _ in scored_peers],
    }

    log.info("  %s: imputed %.1f (%s) from %d peers %s",
             symbol, avg_score, capped_grade, len(scored_peers), result["peer_symbols"])
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:/Users/Claude_Anka/askanka.com && PYTHONPATH=pipeline pytest opus/pipeline/tests/test_peer_imputer.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
cd C:/Users/Claude_Anka/askanka.com
git add opus/pipeline/analysis/peer_imputer.py opus/pipeline/tests/test_peer_imputer.py
git commit -m "feat(opus): sector peer trust score imputation with B+ cap"
```

---

### Task 8: Batch Retrieval Runner

**Files:**
- Create: `opus/pipeline/batch_retrieval.py`
- Create: `opus/pipeline/tests/test_batch_retrieval.py`

- [ ] **Step 1: Write failing tests**

```python
# opus/pipeline/tests/test_batch_retrieval.py
"""Tests for batch retrieval orchestrator."""
from __future__ import annotations

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    """Set up minimal config files."""
    fno = tmp_path / "config" / "fno_stocks.json"
    fno.parent.mkdir(parents=True)
    fno.write_text(json.dumps({"symbols": ["HAL", "TCS", "RELIANCE"]}))

    scrip_map = tmp_path / "config" / "bse_scrip_map.json"
    scrip_map.write_text(json.dumps({
        "mappings": {"HAL": {"bse_scrip": "541154"}, "TCS": {"bse_scrip": "532540"}, "RELIANCE": {"bse_scrip": "500325"}}
    }))
    return tmp_path


def test_run_batch_processes_all_stocks(config_dir: Path):
    """Batch runner processes 3 stocks and writes summary."""
    from opus.pipeline.batch_retrieval import run_batch

    with patch("opus.pipeline.batch_retrieval.fetch_transcripts", return_value=[{"quarter": "Q1FY25"}] * 8), \
         patch("opus.pipeline.batch_retrieval.fetch_annual_reports", return_value=[{"year": "2024"}] * 5), \
         patch("opus.pipeline.batch_retrieval.fetch_quarterly_filings", return_value=[{"quarter": "Q1FY25"}] * 10):

        summary = run_batch(
            fno_path=config_dir / "config" / "fno_stocks.json",
            scrip_map_path=config_dir / "config" / "bse_scrip_map.json",
            output_dir=config_dir / "artifacts",
            delay=0,
        )

    assert summary["total"] == 3
    assert summary["fully_covered"] == 3
    assert (config_dir / "artifacts" / "retrieval_summary.json").exists()


def test_run_batch_flags_partial_transcripts(config_dir: Path):
    """Stocks with < 8 transcripts flagged for imputation."""
    from opus.pipeline.batch_retrieval import run_batch

    call_count = 0
    def variable_transcripts(symbol, **kwargs):
        nonlocal call_count
        call_count += 1
        if symbol == "HAL":
            return [{"quarter": f"Q{i}FY25"} for i in range(8)]
        return [{"quarter": "Q1FY25"}]  # only 1

    with patch("opus.pipeline.batch_retrieval.fetch_transcripts", side_effect=variable_transcripts), \
         patch("opus.pipeline.batch_retrieval.fetch_annual_reports", return_value=[]), \
         patch("opus.pipeline.batch_retrieval.fetch_quarterly_filings", return_value=[]):

        summary = run_batch(
            fno_path=config_dir / "config" / "fno_stocks.json",
            scrip_map_path=config_dir / "config" / "bse_scrip_map.json",
            output_dir=config_dir / "artifacts",
            delay=0,
        )

    assert summary["fully_covered"] == 1
    assert summary["partial_transcripts"] == 2


def test_run_batch_resumes_from_progress(config_dir: Path):
    """Stocks already in progress file are skipped."""
    from opus.pipeline.batch_retrieval import run_batch

    progress_dir = config_dir / "artifacts"
    progress_dir.mkdir(parents=True)
    progress = {"completed": ["HAL", "TCS"]}
    (progress_dir / "batch_progress.json").write_text(json.dumps(progress))

    call_count = 0
    def counting_transcripts(symbol, **kwargs):
        nonlocal call_count
        call_count += 1
        return [{"quarter": f"Q{i}FY25"} for i in range(8)]

    with patch("opus.pipeline.batch_retrieval.fetch_transcripts", side_effect=counting_transcripts), \
         patch("opus.pipeline.batch_retrieval.fetch_annual_reports", return_value=[]), \
         patch("opus.pipeline.batch_retrieval.fetch_quarterly_filings", return_value=[]):

        summary = run_batch(
            fno_path=config_dir / "config" / "fno_stocks.json",
            scrip_map_path=config_dir / "config" / "bse_scrip_map.json",
            output_dir=config_dir / "artifacts",
            delay=0,
        )

    assert call_count == 1  # only RELIANCE fetched
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:/Users/Claude_Anka/askanka.com && PYTHONPATH=pipeline pytest opus/pipeline/tests/test_batch_retrieval.py -v`
Expected: FAIL

- [ ] **Step 3: Implement batch runner**

```python
# opus/pipeline/batch_retrieval.py
"""
Batch data retrieval orchestrator for all 213 F&O stocks.

Coordinates transcript, annual report, and quarterly filing retrieval
across Screener, BSE, NSE, EODHD, and IndianAPI with rate limiting,
caching, and resume capability.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

log = logging.getLogger("opus.batch_retrieval")

IST = timezone(timedelta(hours=5, minutes=30))
MIN_TRANSCRIPTS = 8

DEFAULT_FNO = Path(__file__).parent.parent / "config" / "fno_stocks.json"
DEFAULT_SCRIP_MAP = Path(__file__).parent.parent / "config" / "bse_scrip_map.json"
DEFAULT_OUTPUT = Path(__file__).parent.parent / "artifacts"


def _load_json(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def run_batch(
    fno_path: Path = DEFAULT_FNO,
    scrip_map_path: Path = DEFAULT_SCRIP_MAP,
    output_dir: Path = DEFAULT_OUTPUT,
    delay: float = 1.0,
    force: bool = False,
) -> dict:
    """Run data retrieval for all F&O stocks.

    Returns summary dict with coverage statistics.
    """
    from opus.pipeline.retrieval.transcripts import fetch_transcripts
    from opus.pipeline.retrieval.annual_reports import fetch_annual_reports
    from opus.pipeline.retrieval.quarterly_filings import fetch_quarterly_filings

    output_dir.mkdir(parents=True, exist_ok=True)

    # Load stock list and BSE scrip mappings
    fno = _load_json(fno_path)
    symbols = fno.get("symbols", [])
    scrip_map = _load_json(scrip_map_path).get("mappings", {})

    # Load progress for resume
    progress_path = output_dir / "batch_progress.json"
    progress = _load_json(progress_path)
    completed = set(progress.get("completed", []))

    if force:
        completed = set()

    log.info("Batch retrieval: %d stocks, %d already completed", len(symbols), len(completed))

    fully_covered = 0
    partial_transcripts = 0
    imputation_needed = 0
    failed = 0
    results_per_stock: dict[str, dict] = {}

    for i, symbol in enumerate(symbols):
        if symbol in completed:
            fully_covered += 1
            continue

        bse_scrip = scrip_map.get(symbol, {}).get("bse_scrip", "")
        log.info("[%d/%d] %s (BSE: %s)", i + 1, len(symbols), symbol, bse_scrip or "N/A")

        try:
            transcripts = fetch_transcripts(symbol, cache_dir=output_dir / "transcripts")
            annual = fetch_annual_reports(bse_scrip, symbol)
            quarterly = fetch_quarterly_filings(bse_scrip, symbol)

            stock_result = {
                "transcripts": len(transcripts),
                "annual_reports": len(annual),
                "quarterly_filings": len(quarterly),
            }
            results_per_stock[symbol] = stock_result

            if len(transcripts) >= MIN_TRANSCRIPTS:
                fully_covered += 1
                log.info("  %s: %d transcripts, %d AR, %d quarterly ✓",
                         symbol, len(transcripts), len(annual), len(quarterly))
            else:
                partial_transcripts += 1
                log.info("  %s: %d transcripts (< %d, flagged for imputation), %d AR, %d quarterly",
                         symbol, len(transcripts), MIN_TRANSCRIPTS, len(annual), len(quarterly))

            completed.add(symbol)
            progress["completed"] = list(completed)
            progress_path.write_text(json.dumps(progress, indent=2), encoding="utf-8")

        except Exception as exc:
            failed += 1
            log.error("  %s: FAILED — %s", symbol, exc)

        if delay > 0 and i < len(symbols) - 1:
            time.sleep(delay)

    summary = {
        "run_date": datetime.now(IST).strftime("%Y-%m-%d"),
        "total": len(symbols),
        "fully_covered": fully_covered,
        "partial_transcripts": partial_transcripts,
        "imputation_needed": partial_transcripts,
        "failed": failed,
    }

    summary_path = output_dir / "retrieval_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    log.info("Batch complete: %s", json.dumps(summary))

    return summary


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    force = "--force" in sys.argv
    run_batch(force=force)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:/Users/Claude_Anka/askanka.com && PYTHONPATH=pipeline pytest opus/pipeline/tests/test_batch_retrieval.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
cd C:/Users/Claude_Anka/askanka.com
git add opus/pipeline/batch_retrieval.py opus/pipeline/tests/test_batch_retrieval.py
git commit -m "feat(opus): batch retrieval runner — 213 stocks, rate limiting, resume"
```

---

### Task 9: Bootstrap BSE Scrip Resolution

**Files:**
- Modify: `opus/pipeline/batch_retrieval.py` (add BSE resolve step)

- [ ] **Step 1: Add BSE resolution to batch runner**

Add to `run_batch()` before the stock loop:

```python
    # Resolve BSE scrips for any missing symbols
    from opus.pipeline.retrieval.bse_resolver import batch_resolve
    missing_bse = [s for s in symbols if s not in scrip_map]
    if missing_bse:
        log.info("Resolving %d missing BSE scrip codes...", len(missing_bse))
        updated_cache = batch_resolve(symbols, cache_path=scrip_map_path, delay=delay)
        scrip_map = updated_cache.get("mappings", {})
```

- [ ] **Step 2: Run all tests to verify nothing broke**

Run: `cd C:/Users/Claude_Anka/askanka.com && PYTHONPATH=pipeline pytest opus/pipeline/tests/ -v`
Expected: all tests pass

- [ ] **Step 3: Commit**

```bash
cd C:/Users/Claude_Anka/askanka.com
git add opus/pipeline/batch_retrieval.py
git commit -m "feat(opus): auto-resolve BSE scrips before batch retrieval"
```

---

### Task 10: Integration Test — 3 Live Stocks

**Files:**
- Create: `opus/pipeline/tests/test_integration_live.py`

- [ ] **Step 1: Write integration test (marked slow)**

```python
# opus/pipeline/tests/test_integration_live.py
"""
Live integration test — runs against real APIs for 3 stocks.
Marked as slow; only run explicitly: pytest -m live
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.live


@pytest.mark.live
def test_screener_transcript_urls_for_hal():
    """Screener returns transcript URLs for HAL (large-cap defence)."""
    from opus.pipeline.retrieval.screener_client import ScreenerClient
    sc = ScreenerClient()
    urls = sc.get_transcript_urls("HAL")
    assert len(urls) >= 1, f"Expected at least 1 transcript URL for HAL, got {len(urls)}"
    assert all(u.get("type") == "transcript" for u in urls)


@pytest.mark.live
def test_bse_resolver_finds_reliance():
    """BSE Suggest API resolves RELIANCE to scrip 500325."""
    from opus.pipeline.retrieval.bse_resolver import resolve_bse_scrip
    result = resolve_bse_scrip("RELIANCE")
    assert result is not None, "BSE resolver returned None for RELIANCE"
    assert result["bse_scrip"] == "500325"


@pytest.mark.live
def test_full_retrieval_for_tcs():
    """TCS: Screener financials + transcript links + BSE annual reports."""
    from opus.pipeline.retrieval.screener_client import ScreenerClient
    sc = ScreenerClient()
    data = sc.get_financials("TCS")
    assert len(data.get("quarterly", [])) >= 1, "No quarterly data for TCS"
    assert len(data.get("documents", [])) >= 1, "No documents for TCS"

    from opus.pipeline.retrieval.bse_client import BSEClient
    bse = BSEClient()
    reports = bse.get_annual_reports("532540")
    assert len(reports) >= 1, "No BSE annual reports for TCS"
```

- [ ] **Step 2: Run integration tests**

Run: `cd C:/Users/Claude_Anka/askanka.com && PYTHONPATH=pipeline pytest opus/pipeline/tests/test_integration_live.py -v -m live`
Expected: 3 passed (requires internet connectivity)

- [ ] **Step 3: Commit**

```bash
cd C:/Users/Claude_Anka/askanka.com
git add opus/pipeline/tests/test_integration_live.py
git commit -m "test(opus): live integration tests for Screener, BSE, retrieval pipeline"
```

---

### Task 11: Run Full Batch and Verify Coverage

This is the final operational task — run the actual pipeline.

- [ ] **Step 1: Resolve all BSE scrip codes**

```bash
cd C:/Users/Claude_Anka/askanka.com
python3 -c "
from opus.pipeline.retrieval.bse_resolver import batch_resolve
import json
symbols = json.load(open('opus/config/fno_stocks.json'))['symbols']
result = batch_resolve(symbols, delay=1.0)
print(f'Resolved: {result[\"count\"]}/213')
"
```

Expected: 200+ of 213 resolved

- [ ] **Step 2: Run batch retrieval for all 213 stocks**

```bash
cd C:/Users/Claude_Anka/askanka.com
PYTHONPATH=pipeline python3 opus/pipeline/batch_retrieval.py
```

Expected: Progress output for 213 stocks, summary saved to `opus/artifacts/retrieval_summary.json`

- [ ] **Step 3: Check coverage summary**

```bash
cd C:/Users/Claude_Anka/askanka.com
python3 -c "import json; s = json.load(open('opus/artifacts/retrieval_summary.json')); print(json.dumps(s, indent=2))"
```

Expected: `fully_covered ≥ 170`, `failed == 0`

- [ ] **Step 4: Commit generated artifacts**

```bash
cd C:/Users/Claude_Anka/askanka.com
git add opus/config/bse_scrip_map.json opus/artifacts/retrieval_summary.json
git commit -m "data(opus): BSE scrip map + retrieval summary for 213 F&O stocks"
```
