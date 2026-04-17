"""Bridge: convert new transcript JSON cache → concall_text.txt for scorer.

Reads from: opus/artifacts/transcripts/{symbol}/{quarter}.json
Writes to:  opus/artifacts/{symbol}/concall_text.txt

No downloads, no API calls. Just reshapes cached text into the format
that run_trust_score.py expects (plain text, sections separated by ---).
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TRANSCRIPT_CACHE = ROOT / "artifacts" / "transcripts"
ARTIFACTS = ROOT / "artifacts"

MAX_CHARS = 80_000


def wire_symbol(symbol: str, force: bool = False) -> dict:
    cache_dir = TRANSCRIPT_CACHE / symbol
    target_dir = ARTIFACTS / symbol
    target_path = target_dir / "concall_text.txt"

    if not cache_dir.exists():
        return {"symbol": symbol, "status": "no_cache"}

    if target_path.exists() and not force:
        return {"symbol": symbol, "status": "already_exists", "size_kb": target_path.stat().st_size // 1024}

    transcripts = []
    for f in sorted(cache_dir.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            quarter = data.get("quarter", f.stem)
            text = data.get("text", "")
            word_count = data.get("word_count", len(text.split()))
            if word_count >= 200:
                transcripts.append((quarter, text))
        except Exception:
            continue

    if not transcripts:
        return {"symbol": symbol, "status": "no_valid_transcripts"}

    sections = []
    for quarter, text in transcripts:
        sections.append(f"## CONCALL — {quarter}\n\n{text}")

    combined = "\n\n---\n\n".join(sections)
    if len(combined) > MAX_CHARS:
        combined = combined[:MAX_CHARS] + "\n\n[... truncated ...]"

    target_dir.mkdir(parents=True, exist_ok=True)
    target_path.write_text(combined, encoding="utf-8")

    return {
        "symbol": symbol,
        "status": "wired",
        "quarters": len(transcripts),
        "size_kb": len(combined) // 1024,
    }


def main():
    force = "--force" in sys.argv
    symbols = [d.name for d in sorted(TRANSCRIPT_CACHE.iterdir()) if d.is_dir()]

    print(f"Wiring {len(symbols)} stocks from transcript cache -> concall_text.txt")
    if force:
        print("  --force: overwriting existing files")
    print("=" * 70)

    stats = {"wired": 0, "already_exists": 0, "no_valid_transcripts": 0, "no_cache": 0}
    total_kb = 0

    for i, sym in enumerate(symbols, 1):
        r = wire_symbol(sym, force=force)
        status = r["status"]
        stats[status] = stats.get(status, 0) + 1

        if status == "wired":
            total_kb += r.get("size_kb", 0)
            print(f"  [{i:3}/{len(symbols)}] {sym:15s} -> {r['quarters']} quarters, {r['size_kb']}KB")
        elif status == "already_exists":
            print(f"  [{i:3}/{len(symbols)}] {sym:15s} — already exists ({r.get('size_kb', 0)}KB)")

    print(f"\n{'=' * 70}")
    print(f"Wired:      {stats['wired']}")
    print(f"Existed:    {stats['already_exists']}")
    print(f"No text:    {stats['no_valid_transcripts']}")
    print(f"Total new:  {total_kb}KB")


if __name__ == "__main__":
    main()
