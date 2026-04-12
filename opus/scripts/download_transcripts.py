"""Download + extract concall transcripts from BSE URLs listed in transcripts.json.

For each symbol:
- Reads artifacts/<SYMBOL>/transcripts.json (list of {title, url, type})
- Downloads the first N transcripts (most recent first)
- Extracts text via pymupdf
- Caches text to artifacts/<SYMBOL>/concall_text_<N>.txt
- Combines into concall_text.txt for scoring consumption

No LLM calls. Just HTTP + PDF parsing. Free.
"""
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ART = ROOT / "artifacts"

# Use the primary clone's copied lib/ for pymupdf + requests
_LIB = Path("C:/Users/Claude_Anka/askanka.com/pipeline/lib")
if _LIB.exists() and str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

import requests
import pymupdf  # noqa: E402

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/pdf,*/*",
}

MAX_PER_STOCK = 3  # download latest 3 concalls per stock
TIMEOUT = 30


def fetch_pdf(url: str) -> bytes:
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    return r.content


def extract_pdf_text(pdf_bytes: bytes, max_chars: int = 80000) -> str:
    """Extract and clean text from PDF bytes. Cap per-transcript chars."""
    try:
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    except Exception as e:
        return f"[PDF open failed: {e}]"
    parts = []
    total = 0
    for page_num in range(doc.page_count):
        if total >= max_chars:
            break
        try:
            text = doc[page_num].get_text()
        except Exception:
            continue
        parts.append(text)
        total += len(text)
    doc.close()
    return "\n".join(parts)[:max_chars]


def process_symbol(symbol: str, limit: int = MAX_PER_STOCK) -> dict:
    sym_dir = ART / symbol
    tr_path = sym_dir / "transcripts.json"
    if not tr_path.exists():
        return {"symbol": symbol, "error": "no transcripts.json"}

    try:
        transcripts = json.loads(tr_path.read_text(encoding="utf-8"))
    except Exception as e:
        return {"symbol": symbol, "error": f"parse: {e}"}

    if not isinstance(transcripts, list) or not transcripts:
        return {"symbol": symbol, "error": "empty transcripts list"}

    # Take the latest N (list is assumed newest-first — BSE filings typically)
    slice_ = transcripts[:limit]

    texts = []
    errors = []
    for i, entry in enumerate(slice_, 1):
        url = entry.get("url", "")
        if not url:
            errors.append(f"item {i}: no url")
            continue
        cache_path = sym_dir / f"concall_text_{i:02d}.txt"
        if cache_path.exists() and cache_path.stat().st_size > 1000:
            # Use cached
            text = cache_path.read_text(encoding="utf-8", errors="replace")
        else:
            try:
                pdf = fetch_pdf(url)
            except Exception as e:
                errors.append(f"item {i} fetch: {e}")
                continue
            text = extract_pdf_text(pdf)
            if len(text) < 500:
                errors.append(f"item {i}: extracted too little ({len(text)} chars)")
                continue
            cache_path.write_text(text, encoding="utf-8")
        texts.append(f"## CONCALL {i}\n\n{text}")

    combined = "\n\n---\n\n".join(texts)
    if combined:
        combined_path = sym_dir / "concall_text.txt"
        combined_path.write_text(combined, encoding="utf-8")

    return {
        "symbol": symbol,
        "concalls_fetched": len(texts),
        "total_chars": len(combined),
        "errors": errors,
    }


STUCK = [
    "INDIANB", "MANAPPURAM", "HDFCAMC", "KFINTECH", "SBILIFE",
    "OBEROIRLTY", "PHOENIXLTD", "RVNL", "LUPIN", "SWIGGY", "NUVAMA",
    # TRENT has no transcripts.json — skipped automatically via error path
    "TRENT",
]


def main():
    if len(sys.argv) > 1:
        if sys.argv[1] == "--stuck":
            symbols = STUCK
        else:
            symbols = sys.argv[1:]
    else:
        print("usage: python scripts/download_transcripts.py <SYMBOL> [<SYMBOL>...]")
        print("       python scripts/download_transcripts.py --stuck")
        sys.exit(1)

    print(f"Downloading concall text for {len(symbols)} stocks (max {MAX_PER_STOCK} per stock)")
    print("=" * 78)

    results = []
    for i, sym in enumerate(symbols, 1):
        print(f"[{i:2}/{len(symbols)}] {sym}...", end=" ", flush=True)
        t0 = time.time()
        try:
            r = process_symbol(sym)
        except Exception as e:
            r = {"symbol": sym, "error": f"unhandled: {e}"}
        dt = time.time() - t0
        results.append(r)
        if "error" in r:
            print(f"ERROR: {r['error']} ({dt:.1f}s)")
        else:
            chars_kb = r["total_chars"] // 1024
            err_str = f" | errors: {len(r['errors'])}" if r['errors'] else ""
            print(f"{r['concalls_fetched']} concalls, {chars_kb}KB total{err_str} ({dt:.1f}s)")
            for e in r.get("errors", []):
                print(f"        {e[:100]}")

        # Small delay to be polite to BSE
        time.sleep(0.5)

    # Summary
    print(f"\n{'='*78}\nSUMMARY")
    ok = [r for r in results if "error" not in r]
    fail = [r for r in results if "error" in r]
    print(f"Successful: {len(ok)}")
    print(f"Failed:     {len(fail)}")
    if ok:
        total_kb = sum(r["total_chars"] for r in ok) // 1024
        print(f"Total text cached: {total_kb}KB")


if __name__ == "__main__":
    main()
