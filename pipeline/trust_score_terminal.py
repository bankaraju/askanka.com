"""
Trust Score Terminal — CLI dashboard for all OPUS ANKA trust scores.

Usage:
    python trust_score_terminal.py              # Full scorecard
    python trust_score_terminal.py --top 20     # Top 20 by score
    python trust_score_terminal.py --grade A+   # Filter by grade
    python trust_score_terminal.py --sector defence  # Filter by sector
"""
import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ARTIFACTS = REPO / "opus" / "artifacts"
UNIVERSE = REPO / "opus" / "config" / "universe.json"
FINGERPRINTS = REPO / "pipeline" / "data" / "ta_fingerprints"


def load_all_scores() -> list[dict]:
    scores = []
    sector_map = {}
    if UNIVERSE.exists():
        try:
            uni = json.loads(UNIVERSE.read_text(encoding="utf-8"))
            for s in uni.get("stocks", []):
                sector_map[s["symbol"]] = s.get("sector", "")
        except Exception:
            pass

    for sym_dir in sorted(ARTIFACTS.iterdir()):
        if not sym_dir.is_dir() or sym_dir.name == "transcripts":
            continue
        ts_path = sym_dir / "trust_score.json"
        if not ts_path.exists():
            continue
        try:
            data = json.loads(ts_path.read_text(encoding="utf-8"))
        except Exception:
            continue

        grade = data.get("trust_score_grade", "?")
        pct = data.get("trust_score_pct", 0)

        fp_path = FINGERPRINTS / f"{sym_dir.name}.json"
        ta_personality = ""
        ta_best = ""
        if fp_path.exists():
            try:
                fp = json.loads(fp_path.read_text(encoding="utf-8"))
                ta_personality = fp.get("personality", "")
                ta_best = fp.get("best_pattern", "")
            except Exception:
                pass

        scores.append({
            "symbol": sym_dir.name,
            "grade": grade,
            "score": pct,
            "sector": sector_map.get(sym_dir.name, ""),
            "trajectory": data.get("credibility_trajectory", ""),
            "guidance_scored": data.get("guidance_scored", 0),
            "delivery_rate": data.get("delivery_rate", 0),
            "red_flag": (data.get("biggest_red_flag") or "")[:80],
            "strength": (data.get("biggest_strength") or "")[:80],
            "ta_personality": ta_personality,
            "ta_best": ta_best,
        })
    return scores


GRADE_ORDER = {"A+": 0, "A": 1, "B+": 2, "B": 3, "C+": 4, "C": 5, "D": 6, "F": 7, "?": 8}


def print_table(stocks: list[dict], title: str = "ANKA Trust Scores"):
    print(f"\n{'=' * 100}")
    print(f"  {title}")
    print(f"  {len(stocks)} stocks | {ARTIFACTS}")
    print(f"{'=' * 100}")

    if not stocks:
        print("  No stocks found.")
        return

    header = f"{'SYMBOL':15s} {'GRADE':6s} {'SCORE':>6s} {'TRAJ':>8s} {'ITEMS':>5s} {'SECTOR':20s} {'TA TYPE':18s}"
    print(f"  {header}")
    print(f"  {'-' * 95}")

    for s in stocks:
        grade = s["grade"]
        if grade in ("A+", "A"):
            tone = "\033[92m"  # green
        elif grade in ("B+", "B"):
            tone = "\033[93m"  # yellow
        elif grade in ("C+", "C", "D"):
            tone = "\033[91m"  # red
        elif grade == "F":
            tone = "\033[31m"  # dark red
        else:
            tone = "\033[90m"  # gray
        reset = "\033[0m"

        traj_icon = {"improving": "+", "stable": "=", "deteriorating": "-"}.get(s["trajectory"], "?")
        sector_short = s["sector"][:20] if s["sector"] else ""
        ta = s["ta_personality"][:18] if s["ta_personality"] else ""

        print(f"  {tone}{s['symbol']:15s} {grade:6s} {s['score']:>5.1f}% {traj_icon:>8s} {s['guidance_scored']:>5d} {reset}{sector_short:20s} {ta:18s}")

    print(f"\n  {'=' * 95}")
    grades = Counter(s["grade"] for s in stocks)
    parts = []
    for g in ["A+", "A", "B+", "B", "C+", "C", "D", "F", "?"]:
        if grades.get(g, 0) > 0:
            parts.append(f"{g}: {grades[g]}")
    print(f"  Distribution: {' | '.join(parts)}")

    scored = [s for s in stocks if s["grade"] not in ("?", "")]
    if scored:
        avg = sum(s["score"] for s in scored) / len(scored)
        print(f"  Average score: {avg:.1f}% ({len(scored)} scored)")
    print()


def main():
    args = sys.argv[1:]
    stocks = load_all_scores()

    top_n = None
    grade_filter = None
    sector_filter = None

    i = 0
    while i < len(args):
        if args[i] == "--top" and i + 1 < len(args):
            top_n = int(args[i + 1])
            i += 2
        elif args[i] == "--grade" and i + 1 < len(args):
            grade_filter = args[i + 1].upper()
            i += 2
        elif args[i] == "--sector" and i + 1 < len(args):
            sector_filter = args[i + 1].lower()
            i += 2
        else:
            i += 1

    title = "ANKA Trust Scores — Full Universe"

    if grade_filter:
        stocks = [s for s in stocks if s["grade"] == grade_filter]
        title = f"ANKA Trust Scores — Grade {grade_filter}"

    if sector_filter:
        stocks = [s for s in stocks if sector_filter in s["sector"].lower()]
        title = f"ANKA Trust Scores — Sector: {sector_filter}"

    stocks.sort(key=lambda s: (GRADE_ORDER.get(s["grade"], 99), -s["score"]))

    if top_n:
        stocks = stocks[:top_n]
        title += f" (Top {top_n})"

    print_table(stocks, title)


if __name__ == "__main__":
    main()
