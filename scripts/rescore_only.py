"""Re-score a single symbol using existing narratives.json + financial_analysis.json.

No re-extraction, no PDF parsing, no Claude narrative calls.
Only invokes score_promises() + calculate_trust_score() with the current
SCORING_PROMPT_TEMPLATE to measure the impact of prompt changes cheaply.

Backs up existing guidance_scorecard.json and trust_score.json to .bak
before overwriting. Prints a before/after summary.
"""
import json
import sys
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from run_trust_score import score_promises, calculate_trust_score, ARTIFACTS, _filter_vague_guidance


def main(symbol: str):
    out_dir = ARTIFACTS / symbol
    narr_path = out_dir / "narratives.json"
    fin_path = out_dir / "financial_analysis.json"
    gs_path = out_dir / "guidance_scorecard.json"
    ts_path = out_dir / "trust_score.json"

    if not narr_path.exists():
        print(f"ERROR: {narr_path} not found")
        return 1
    if not fin_path.exists():
        print(f"ERROR: {fin_path} not found")
        return 1

    narratives = json.loads(narr_path.read_text(encoding="utf-8"))
    financials = json.loads(fin_path.read_text(encoding="utf-8"))

    # Re-apply the (patched) filter to each year-block's guidance list.
    # This simulates what would happen if extraction had been re-run with the
    # new filter, without actually re-calling the AR extraction LLM.
    pre_filter_total = 0
    post_filter_total = 0
    for narr in narratives:
        items = narr.get("guidance", narr.get("claims", []))
        pre_filter_total += len(items)
        narr["guidance"] = _filter_vague_guidance(items)
        post_filter_total += len(narr["guidance"])
    print(f"\nFilter re-applied: {pre_filter_total} -> {post_filter_total} items "
          f"({pre_filter_total - post_filter_total} dropped by Patch 1)")

    before_ts = json.loads(ts_path.read_text(encoding="utf-8")) if ts_path.exists() else {}
    before_gs = json.loads(gs_path.read_text(encoding="utf-8")) if gs_path.exists() else {}
    before_summary = before_gs.get("summary", {})

    print(f"\n{'='*70}")
    print(f"  RE-SCORE TEST — {symbol}")
    print(f"{'='*70}")
    print(f"\nBEFORE (existing files):")
    print(f"  verdict:                {before_ts.get('verdict')}")
    print(f"  trust_score_pct:        {before_ts.get('trust_score_pct')}")
    print(f"  total_guidance_items:   {before_ts.get('total_guidance_items')}")
    print(f"  guidance_scored:        {before_ts.get('guidance_scored')}")
    print(f"  detail:                 {before_ts.get('detail', '')[:100]}")
    print(f"  breakdown:              too_early={before_summary.get('too_early')} "
          f"unverifiable={before_summary.get('unverifiable')} "
          f"delivered={before_summary.get('delivered')} "
          f"missed={before_summary.get('missed')} "
          f"partial={before_summary.get('partially_delivered')}")

    # Backup
    if gs_path.exists():
        shutil.copy2(gs_path, gs_path.with_suffix(".json.bak"))
    if ts_path.exists():
        shutil.copy2(ts_path, ts_path.with_suffix(".json.bak"))
    print(f"\n(backed up existing files to .bak)")

    print(f"\nRunning score_promises() with patched prompt...")
    scoring = score_promises(symbol, financials, narratives)
    if "error" in scoring:
        print(f"\nSCORING ERROR: {scoring['error']}")
        if "raw" in scoring:
            print(f"  raw: {scoring['raw'][:500]}")
        return 2

    gs_path.write_text(json.dumps(scoring, indent=2, ensure_ascii=False), encoding="utf-8")

    premium = calculate_trust_score(scoring, financials)
    ts_path.write_text(json.dumps(premium, indent=2, ensure_ascii=False), encoding="utf-8")

    after_summary = scoring.get("summary", {})
    print(f"\nAFTER (new patched scoring):")
    print(f"  verdict:                {premium.get('verdict')}")
    print(f"  trust_score_pct:        {premium.get('trust_score_pct')}")
    print(f"  trust_score_grade:      {premium.get('trust_score_grade')}")
    print(f"  total_guidance_items:   {premium.get('total_guidance_items')}")
    print(f"  guidance_scored:        {premium.get('guidance_scored')}")
    print(f"  detail:                 {premium.get('detail', '')[:200]}")
    print(f"  breakdown:              too_early={after_summary.get('too_early')} "
          f"unverifiable={after_summary.get('unverifiable')} "
          f"delivered={after_summary.get('delivered')} "
          f"missed={after_summary.get('missed')} "
          f"partial={after_summary.get('partially_delivered')} "
          f"exceeded={after_summary.get('exceeded')}")

    print(f"\nDELTA:")
    print(f"  verdict:     {before_ts.get('verdict')} -> {premium.get('verdict')}")
    print(f"  scoreable:   {before_ts.get('guidance_scored')} -> {premium.get('guidance_scored')}")
    print(f"  too_early:   {before_summary.get('too_early')} -> {after_summary.get('too_early')}")
    print(f"  unverifiable:{before_summary.get('unverifiable')} -> {after_summary.get('unverifiable')}")

    unblocked = premium.get("verdict") != "INSUFFICIENT_DATA"
    print(f"\nVERDICT FLIPPED? {'YES — Patch 2 works' if unblocked else 'NO — still INSUFFICIENT_DATA'}")
    return 0 if unblocked else 3


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python scripts/rescore_only.py <SYMBOL>")
        sys.exit(1)
    sys.exit(main(sys.argv[1]))
