"""Theme lifecycle audit — do baskets play their part and die?

Reads Task #24 per_event_modeB CSV (5y, 48,048 events across 234 cells)
and computes year-by-year mean post-cost return per (basket, regime, hold).

Hypothesis under check: alpha themes have lifecycles. A basket that printed
+200bp in 2022 may print -100bp in 2025 because the regime that birthed it
ended. Hand-curated baskets pin themselves to themes that already peaked.

Output
------
pipeline/data/research/theme_lifecycle/lifecycle_<date>.csv
  cell_id, basket, regime, hold, year, n, mean_bps, std_bps, hit_pct, alive
pipeline/data/research/theme_lifecycle/lifecycle_<date>.md
  Per-cell lifecycle narrative for top hand-curated cells +
  the 1 PASS + the 4 borderline (per the bootstrap addendum).
"""
from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SRC = REPO / "pipeline" / "data" / "research" / "india_spread_pairs_backtest" / \
      "per_event_modeB_2026-04-30.csv"
OUT_DIR = REPO / "pipeline" / "data" / "research" / "theme_lifecycle"

# Cells of interest from the bootstrap addendum
HEADLINE_CELLS = [
    ("Reliance vs OMCs", "EUPHORIA", 5),       # 1 PASS
    ("EV Plays vs ICE Auto", "EUPHORIA", 5),   # FAIL_BH_FDR, 100% boot
    ("Defence vs IT", "NEUTRAL", 3),           # FAIL_BH_FDR, 98% boot
    ("Defence vs IT", "NEUTRAL", 5),           # near-pass, hit-rate
    ("Defence vs Auto", "NEUTRAL", 3),         # FAIL_BH_FDR, 88% boot
    ("Defence vs Auto", "NEUTRAL", 5),         # FAIL_HITRATE, 86.5% boot
    ("Coal vs OMCs", "EUPHORIA", 3),
    ("Coal vs OMCs", "EUPHORIA", 5),
    ("PSU Energy vs Private", "RISK-OFF", 5),
]


def _alive(mean_bps: float, n: int) -> bool:
    """A cell is 'alive' in a year if mean post-cost > 0 AND n >= 5."""
    return mean_bps > 0 and n >= 5


def main() -> int:
    if not SRC.is_file():
        print(f"ERROR: per-event CSV not found at {SRC}")
        return 1

    by_cell_year: dict[tuple[str, str, int, int], list[float]] = defaultdict(list)
    with SRC.open(encoding="utf-8", newline="") as fp:
        for row in csv.DictReader(fp):
            try:
                bps = float(row["pnl_post_20bp_bps"])
                hold = int(row["hold_days"])
                year = int(row["open_date"][:4])
            except (ValueError, KeyError):
                continue
            key = (row["basket_name"], row["regime"], hold, year)
            by_cell_year[key].append(bps)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    csv_out = OUT_DIR / f"lifecycle_{today}.csv"
    md_out = OUT_DIR / f"lifecycle_{today}.md"

    rows_csv: list[dict] = []
    for (basket, regime, hold, year), bps_list in sorted(by_cell_year.items()):
        n = len(bps_list)
        mean_bps = sum(bps_list) / n if n else 0.0
        var = sum((b - mean_bps) ** 2 for b in bps_list) / max(1, n - 1)
        std_bps = math.sqrt(var) if var > 0 else 0.0
        hit = sum(1 for b in bps_list if b > 0) / n if n else 0.0
        rows_csv.append({
            "basket": basket, "regime": regime, "hold": hold, "year": year,
            "n": n, "mean_bps": round(mean_bps, 1),
            "std_bps": round(std_bps, 1), "hit_pct": round(100 * hit, 1),
            "alive": _alive(mean_bps, n),
        })

    with csv_out.open("w", encoding="utf-8", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=list(rows_csv[0].keys()))
        writer.writeheader()
        writer.writerows(rows_csv)

    # Per-cell narrative for headline cells
    md_lines = [
        "# Theme lifecycle audit",
        f"Computed {today} from Task #24 5y per-event Mode B (48,048 events).",
        "",
        "## Headline cells — year-by-year",
        "",
        "Reading: each row is one calendar year. Mean is post-cost (20bp). 'Alive' = mean>0 AND n>=5.",
        "",
    ]

    for basket, regime, hold in HEADLINE_CELLS:
        md_lines.append(f"### {basket} / {regime} / {hold}d")
        md_lines.append("")
        md_lines.append("| Year | n | mean(bps) | std | hit% | alive? |")
        md_lines.append("|---|---|---|---|---|---|")
        cell_rows = [r for r in rows_csv if r["basket"] == basket
                     and r["regime"] == regime and r["hold"] == hold]
        cell_rows.sort(key=lambda r: r["year"])
        years_alive = []
        for r in cell_rows:
            mark = "ALIVE" if r["alive"] else "dead"
            md_lines.append(
                f"| {r['year']} | {r['n']} | {r['mean_bps']:+.1f} | {r['std_bps']:.0f} | "
                f"{r['hit_pct']}% | {mark} |"
            )
            if r["alive"]:
                years_alive.append(r["year"])
        md_lines.append("")
        if years_alive:
            md_lines.append(f"**Lifecycle:** alive {min(years_alive)}–{max(years_alive)} "
                            f"({len(years_alive)} of {len(cell_rows)} years).")
        else:
            md_lines.append("**Lifecycle:** never alive (or always n<5).")
        md_lines.append("")

    # Aggregate: across all 234 cells, what fraction has stable alpha across years?
    all_cells = defaultdict(list)
    for r in rows_csv:
        all_cells[(r["basket"], r["regime"], r["hold"])].append(r)
    cells_alive_5_5 = sum(1 for rows in all_cells.values()
                          if sum(1 for r in rows if r["alive"]) == 5)
    cells_alive_4_5 = sum(1 for rows in all_cells.values()
                          if sum(1 for r in rows if r["alive"]) >= 4)
    cells_alive_3_5 = sum(1 for rows in all_cells.values()
                          if sum(1 for r in rows if r["alive"]) >= 3)
    cells_alive_only_recent = sum(1 for rows in all_cells.values()
                                  if all(r["alive"] for r in rows if r["year"] >= 2024)
                                  and not all(r["alive"] for r in rows if r["year"] < 2024))
    cells_alive_only_old = sum(1 for rows in all_cells.values()
                               if all(r["alive"] for r in rows if r["year"] < 2024)
                               and not any(r["alive"] for r in rows if r["year"] >= 2024))

    md_lines += [
        "## Aggregate lifecycle picture (234 cells, 5y)",
        "",
        f"- Always alive (5/5 years): **{cells_alive_5_5}** cells",
        f"- Alive 4+/5 years: **{cells_alive_4_5}** cells",
        f"- Alive 3+/5 years: **{cells_alive_3_5}** cells",
        f"- ALIVE-RECENT-ONLY (2024+ alive, pre-2024 dead): **{cells_alive_only_recent}** cells "
        "  ← emerging themes",
        f"- ALIVE-OLD-ONLY (pre-2024 alive, 2024+ dead): **{cells_alive_only_old}** cells "
        "  ← decayed kings",
        "",
        "## Reading",
        "",
        "If `cells_alive_5_5` is small (single digits), themes really do come and go — ",
        "ASDE needs to weight recent-year evidence more heavily and decay monitor must run aggressively.",
        "",
        "If `cells_alive_only_recent` >> `cells_alive_only_old`, the alpha space is *expanding* ",
        "(new themes emerging faster than old ones die). Promotion cadence should accelerate.",
        "",
        "If `cells_alive_only_old` >> `cells_alive_only_recent`, the alpha space is *contracting* ",
        "(themes are getting arbed away). Forward shadows must be longer to filter survivors.",
    ]
    md_out.write_text("\n".join(md_lines), encoding="utf-8")

    print(f"lifecycle CSV  -> {csv_out}")
    print(f"lifecycle MD   -> {md_out}")
    print(f"  always alive (5/5): {cells_alive_5_5}")
    print(f"  alive 4+/5:        {cells_alive_4_5}")
    print(f"  alive 3+/5:        {cells_alive_3_5}")
    print(f"  recent-only:       {cells_alive_only_recent}")
    print(f"  old-only:          {cells_alive_only_old}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
