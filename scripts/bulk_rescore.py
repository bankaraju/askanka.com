"""Run rescore_only.py logic across a list of symbols, collect results.

All scoring runs route through Gemini 2.5 Flash (free tier) via call_llm.
No Claude Haiku calls — extraction is not re-run.
"""
import json
import sys
import shutil
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from run_trust_score import score_promises, calculate_trust_score, ARTIFACTS, _filter_vague_guidance

# All 29 stocks in the gap, grouped. We run rich + sparse. Skip empty/no-file.
RICH = [
    "GODFRYPHLP", "HAVELLS", "HDFCAMC", "IDEA", "INDIANB", "KFINTECH",
    "MANAPPURAM", "MARUTI", "NAUKRI", "NHPC", "NMDC", "NUVAMA",
    "NYKAA", "OBEROIRLTY", "PHOENIXLTD", "RELIANCE", "RVNL", "SBILIFE",
    "SWIGGY", "TRENT", "UPL", "VEDL",
]
SPARSE = ["LUPIN"]

def rescore_one(symbol: str) -> dict:
    """Re-run score_promises + calculate_trust_score for one symbol."""
    out_dir = ARTIFACTS / symbol
    narr_path = out_dir / "narratives.json"
    fin_path = out_dir / "financial_analysis.json"
    gs_path = out_dir / "guidance_scorecard.json"
    ts_path = out_dir / "trust_score.json"

    if not narr_path.exists() or not fin_path.exists():
        return {"symbol": symbol, "error": "missing narratives or financial_analysis"}

    try:
        narratives = json.loads(narr_path.read_text(encoding="utf-8"))
        financials = json.loads(fin_path.read_text(encoding="utf-8"))
    except Exception as e:
        return {"symbol": symbol, "error": f"load failed: {e}"}

    # Snapshot "before" from existing trust_score.json
    before = {}
    if ts_path.exists():
        try:
            bts = json.loads(ts_path.read_text(encoding="utf-8"))
            before = {
                "verdict": bts.get("verdict"),
                "scored": bts.get("guidance_scored"),
                "total": bts.get("total_guidance_items"),
            }
        except Exception:
            pass

    # Re-apply the (patched) filter in-memory
    pre_items = 0
    for narr in narratives:
        items = narr.get("guidance", narr.get("claims", []))
        pre_items += len(items)
        narr["guidance"] = _filter_vague_guidance(items)

    post_items = sum(len(n.get("guidance", [])) for n in narratives)

    if post_items == 0:
        return {"symbol": symbol, "error": f"0 items after filter (from {pre_items})"}

    # Backup
    if gs_path.exists():
        shutil.copy2(gs_path, gs_path.with_suffix(".json.bak"))
    if ts_path.exists():
        shutil.copy2(ts_path, ts_path.with_suffix(".json.bak"))

    try:
        scoring = score_promises(symbol, financials, narratives)
    except Exception as e:
        return {"symbol": symbol, "error": f"score_promises raised: {e}"}

    if "error" in scoring:
        return {"symbol": symbol, "error": f"scoring: {scoring['error']}"}

    try:
        premium = calculate_trust_score(scoring, financials)
    except Exception as e:
        return {"symbol": symbol, "error": f"calculate_trust_score raised: {e}"}

    # Write updated artifacts
    gs_path.write_text(json.dumps(scoring, indent=2, ensure_ascii=False), encoding="utf-8")
    ts_path.write_text(json.dumps(premium, indent=2, ensure_ascii=False), encoding="utf-8")

    summary = scoring.get("summary", {})
    return {
        "symbol": symbol,
        "pre_items": pre_items,
        "post_items": post_items,
        "before_verdict": before.get("verdict"),
        "after_verdict": premium.get("verdict"),
        "after_scored": premium.get("guidance_scored"),
        "after_too_early": summary.get("too_early"),
        "after_unverifiable": summary.get("unverifiable"),
        "after_delivered": summary.get("delivered"),
        "after_partial": summary.get("partially_delivered"),
        "after_missed": summary.get("missed"),
        "flipped": premium.get("verdict") != "INSUFFICIENT_DATA",
        "grade": premium.get("trust_score_grade"),
    }


def main():
    symbols = RICH + SPARSE
    print(f"Re-scoring {len(symbols)} stocks via Gemini (free tier)...")
    print(f"{'='*80}\n")
    results = []
    for i, sym in enumerate(symbols, 1):
        if i > 1:
            time.sleep(7)  # stay under Gemini free tier TPM (1M/min) for ~80K-per-call prompts
        print(f"[{i:2}/{len(symbols)}] {sym}...", end=" ", flush=True)
        t0 = time.time()
        r = rescore_one(sym)
        dt = time.time() - t0
        results.append(r)
        if "error" in r:
            print(f"ERROR: {r['error']} ({dt:.1f}s)")
        else:
            flip = "FLIP" if r["flipped"] else "stuck"
            print(f"{flip} | items {r['pre_items']}->{r['post_items']} | "
                  f"scored={r['after_scored']} te={r['after_too_early']} uv={r['after_unverifiable']} "
                  f"p={r['after_partial']} d={r['after_delivered']} m={r['after_missed']} "
                  f"| {r.get('after_verdict','?')[:20]} ({dt:.1f}s)")

    # Summary
    print(f"\n{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}")
    flipped = [r for r in results if r.get("flipped")]
    stuck = [r for r in results if "error" not in r and not r.get("flipped")]
    errored = [r for r in results if "error" in r]
    print(f"Total:   {len(results)}")
    print(f"Flipped: {len(flipped)} ({len(flipped)/len(results)*100:.0f}%)")
    print(f"Stuck:   {len(stuck)}")
    print(f"Errors:  {len(errored)}")
    print()
    if flipped:
        print("FLIPPED stocks:")
        for r in flipped:
            print(f"  {r['symbol']:12} scored={r['after_scored']:2} grade={r.get('grade','?')} {r.get('after_verdict','?')[:30]}")
    print()
    if stuck:
        print("STUCK stocks (scoreable vs min 5 threshold):")
        for r in stuck:
            gap = 5 - (r.get("after_scored") or 0)
            print(f"  {r['symbol']:12} scored={r['after_scored']:2} gap={gap} te={r['after_too_early']} uv={r['after_unverifiable']}")
    print()
    if errored:
        print("ERRORED:")
        for r in errored:
            print(f"  {r['symbol']:12} {r['error'][:80]}")

    # Save machine-readable summary
    summary_path = ROOT / "artifacts" / "bulk_rescore_summary.json"
    summary_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved machine-readable summary to: {summary_path}")


if __name__ == "__main__":
    main()
