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

import requests
from opus.pipeline.retrieval.screener_client import ScreenerClient

log = logging.getLogger("opus.transcripts")

IST = timezone(timedelta(hours=5, minutes=30))
MIN_WORD_COUNT = 500  # minimum character count (not word count)
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
    cached = _load_cache(cache_dir, nse_symbol)
    cached_quarters = {t["quarter"] for t in cached}

    new_transcripts: list[dict] = []
    try:
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
                word_count = len(text)  # character count stored as word_count

                if word_count < MIN_WORD_COUNT:
                    log.info(
                        "  %s %s: skipped (%d chars < %d min)",
                        nse_symbol, quarter, word_count, MIN_WORD_COUNT,
                    )
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
                log.info("  %s %s: %d words OK", nse_symbol, quarter, word_count)
                time.sleep(0.5)
            except Exception as exc:
                log.warning("  %s %s: download failed — %s", nse_symbol, quarter, exc)

    except Exception as exc:
        log.warning("Transcript fetch failed for %s: %s", nse_symbol, exc)
        return cached

    return cached + new_transcripts
