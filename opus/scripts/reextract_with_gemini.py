"""Re-extract narratives from cached ar_text files using Gemini (free).

For each symbol:
1. Skip if no ar_text_*.txt cache files exist.
2. Backup existing narratives.json -> .json.bak
3. For each year's cached AR text, call Gemini with NARRATIVE_EXTRACTION_PROMPT.
4. Apply _filter_vague_guidance.
5. Save new narratives.json.

No PDF parsing, no Claude calls. Free via Gemini Flash.
"""
import json
import sys
import shutil
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from run_trust_score import (
    ARTIFACTS,
    NARRATIVE_EXTRACTION_PROMPT,
    call_llm,
    _filter_vague_guidance,
)


def reextract_one(symbol: str, max_chars_per_year: int = 500000) -> dict:
    """Re-extract narratives for one symbol from cached ar_text files."""
    sym_dir = ARTIFACTS / symbol
    if not sym_dir.is_dir():
        return {"symbol": symbol, "error": "no artifact dir"}

    ar_files = sorted(sym_dir.glob("ar_text_*.txt"))
    if not ar_files:
        return {"symbol": symbol, "error": "no ar_text cache"}

    # Backup existing narratives.json
    narr_path = sym_dir / "narratives.json"
    if narr_path.exists():
        shutil.copy2(narr_path, narr_path.with_suffix(".json.gemini-bak"))

    new_narratives = []
    pre_total = 0
    post_total = 0
    errors = []

    for ar_file in ar_files:
        year = ar_file.stem.replace("ar_text_", "")
        text = ar_file.read_text(encoding="utf-8", errors="replace")
        if len(text) < 5000:
            errors.append(f"{year}: text too short ({len(text)} chars)")
            continue

        # Build prompt with the AR text appended
        prompt = (
            NARRATIVE_EXTRACTION_PROMPT
            + "\n\n## ANNUAL REPORT TEXT\n\n"
            + text[:max_chars_per_year]
        )

        try:
            response = call_llm(prompt, max_tokens=16384, role="extraction")
        except Exception as e:
            errors.append(f"{year}: llm call failed: {e}")
            continue

        # Strip markdown fences if present
        response_text = response.strip()
        if response_text.startswith("```"):
            response_text = response_text.split("\n", 1)[1]
            if response_text.endswith("```"):
                response_text = response_text[:-3]

        try:
            parsed = json.loads(response_text)
        except json.JSONDecodeError as e:
            errors.append(f"{year}: JSON parse failed: {e}")
            (sym_dir / f"narrative_raw_gemini_{year}.txt").write_text(
                response[:3000], encoding="utf-8"
            )
            continue

        items = parsed.get("guidance", parsed.get("claims", []))
        pre_total += len(items)
        filtered = _filter_vague_guidance(items)
        post_total += len(filtered)

        narr_entry = {
            "source_year": year,
            "source_file": f"ar_text_{year}.txt",
            "guidance": filtered,
            "actuals_reported": parsed.get("actuals_reported", {}),
            "risks_disclosed": parsed.get("risks_disclosed", []),
            "overall_tone": parsed.get("overall_tone", "?"),
        }
        new_narratives.append(narr_entry)

    # Save new narratives.json
    narr_path.write_text(
        json.dumps(new_narratives, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return {
        "symbol": symbol,
        "years": len(new_narratives),
        "pre_filter": pre_total,
        "post_filter": post_total,
        "errors": errors,
    }


# Stocks to re-extract (gap stocks with ar_text cache, excludes M&M, MCX which have no cache)
GAP_WITH_CACHE = [
    "GODFRYPHLP", "HAVELLS", "HDFCAMC", "IDEA", "INDIANB", "KFINTECH",
    "MANAPPURAM", "MARUTI", "NAUKRI", "NHPC", "NMDC", "NUVAMA", "NYKAA",
    "OBEROIRLTY", "PHOENIXLTD", "RELIANCE", "RVNL", "SBILIFE", "SWIGGY",
    "TRENT", "UPL", "VEDL", "LUPIN", "CANBK", "OFSS", "UNIONBANK", "VMM",
]


def main():
    if len(sys.argv) > 1:
        if sys.argv[1] == "--all":
            symbols = GAP_WITH_CACHE
        else:
            symbols = sys.argv[1:]
    else:
        print("usage: python scripts/reextract_with_gemini.py <SYMBOL> [<SYMBOL>...]")
        print("       python scripts/reextract_with_gemini.py --all")
        sys.exit(1)

    print(f"Re-extracting {len(symbols)} stocks via Gemini Flash (free tier)")
    print("=" * 78)

    results = []
    for i, sym in enumerate(symbols, 1):
        print(f"[{i:2}/{len(symbols)}] {sym}...", end=" ", flush=True)
        t0 = time.time()
        try:
            r = reextract_one(sym)
        except Exception as e:
            r = {"symbol": sym, "error": f"unhandled: {e}"}
        dt = time.time() - t0
        results.append(r)
        if "error" in r:
            print(f"ERROR: {r['error']} ({dt:.1f}s)")
        else:
            err_str = f" | errors: {len(r['errors'])}" if r['errors'] else ""
            print(
                f"years={r['years']} pre={r['pre_filter']} post={r['post_filter']}"
                f"{err_str} ({dt:.1f}s)"
            )
            for e in r["errors"]:
                print(f"        {e[:100]}")

    print("\n" + "=" * 78)
    print("SUMMARY")
    print("=" * 78)
    successful = [r for r in results if "error" not in r]
    failed = [r for r in results if "error" in r]
    print(f"Total:      {len(results)}")
    print(f"Successful: {len(successful)}")
    print(f"Failed:     {len(failed)}")
    print()
    if successful:
        print("Per-symbol post-filter item counts:")
        for r in sorted(successful, key=lambda x: -x["post_filter"]):
            mark = "+++" if r["post_filter"] >= 5 else ("---" if r["post_filter"] == 0 else "~~~")
            print(f"  {mark} {r['symbol']:12} years={r['years']} pre={r['pre_filter']:3} -> post={r['post_filter']:3}")

    summary_path = ROOT / "artifacts" / "reextract_summary.json"
    summary_path.write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\nSaved summary to {summary_path}")


if __name__ == "__main__":
    main()
