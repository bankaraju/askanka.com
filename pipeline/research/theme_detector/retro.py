"""Theme Detector v1 — retro evaluation harness.

Runs the detector weekly across a date range, accumulating state, and produces:
- weekly themes_<date>.json frames
- lifecycle_trajectory.csv (one row per theme-week)
- lead_time_summary.csv (per §8 reference cycle: first PRE_IGNITION date, RS-breakout date, lead_time_weeks)
- (optional) null_baseline.csv from a member-shuffle randomization

Design intent: post-COVID-from-2023 is the thematic premise (PROVENANCE.md
"pre-2022 retro deliberately not acquired"), so the natural retro window is
2023-05 → 2026-05 — 156 Sundays.

Coverage caveats baked into the output:
- B3 fii_drift, C2 cap_drift, C5 earnings_breadth — Trendlyne forward-only from
  2026-05-01; emit None throughout retro. Belief bucket is dominated by B5 alone
  during retro; confirmation bucket loses C2 + C5.
- C3 fo_inclusion — fno_universe_history.json starts 2024-01-31; emits None for
  all retro Sundays before 2025-01-31 (need 12m of history).
- B5 ipo_cluster — IPO calendar starts 2023-01-01; first ~6m of retro window
  (run_date < 2023-07) has truncated lookback.

Spec: docs/superpowers/specs/2026-05-01-theme-detector-design.md §8

Usage:
    python -m pipeline.research.theme_detector.retro \\
        --start 2023-05-07 --end 2026-04-26 \\
        --themes pipeline/research/theme_detector/themes_frozen.json \\
        --output-dir pipeline/data/research/theme_detector/retro \\
        [--null-shuffle]   # also run a member-shuffle null
"""
from __future__ import annotations

import argparse
import csv
import json
import random
from copy import deepcopy
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from pipeline.research.theme_detector.detector import run_detector
from pipeline.research.theme_detector.lifecycle import ThemeState

# §8 reference table (post-COVID-relevant cycles only — 7 of 8 from spec §8.1).
REFERENCE_CYCLES: list[dict[str, Any]] = [
    {"theme_id": "BANKS_PSU_REREATING",
     "ignition_quarter": "2022-Q2",
     "rs_breakout": date(2023, 4, 1),
     "should_pre_ignition_by": date(2022, 4, 1)},  # before retro start; just records target
    {"theme_id": "DEFENCE_WAR_ECONOMY",
     "ignition_quarter": "2022-Q3",
     "rs_breakout": date(2023, 7, 1),
     "should_pre_ignition_by": date(2022, 10, 1)},
    {"theme_id": "POWER_RENEWABLE_TRANSITION",
     "ignition_quarter": "2023-Q1",
     "rs_breakout": date(2024, 4, 1),
     "should_pre_ignition_by": date(2023, 4, 1)},
    {"theme_id": "DATA_CENTRES_ADJACENT",
     "ignition_quarter": "2024-Q3",
     "rs_breakout": date(2024, 10, 1),
     "should_pre_ignition_by": date(2024, 10, 1)},
    {"theme_id": "HOSPITALS_ROBOTICS_LEAN",
     "ignition_quarter": "2024-Q1",
     "rs_breakout": date(2024, 10, 1),
     "should_pre_ignition_by": date(2024, 4, 1)},
    {"theme_id": "QUICK_COMMERCE",
     "ignition_quarter": "2023-Q3",
     "rs_breakout": date(2024, 1, 1),
     "should_pre_ignition_by": date(2023, 10, 1)},
    {"theme_id": "CAPEX_PLI_BENEFICIARY",
     "ignition_quarter": "2022-H2",
     "rs_breakout": date(2023, 7, 1),
     "should_pre_ignition_by": date(2023, 1, 1)},
]


def iter_sundays(start: date, end: date):
    """Yield every Sunday inclusively between start and end."""
    d = start
    while d.weekday() != 6:  # 6 = Sunday
        d += timedelta(days=1)
    while d <= end:
        yield d
        d += timedelta(days=7)


def load_themes(themes_path: Path) -> list[dict]:
    return json.loads(themes_path.read_text(encoding="utf-8"))["themes"]


def shuffle_members_across_themes(themes: list[dict], rng: random.Random) -> list[dict]:
    """Member-shuffle null: randomize member->theme assignments while keeping
    per-theme size constant. Rule kind A only; rule kind B left untouched.
    """
    out = deepcopy(themes)
    pool: list[str] = []
    sizes: list[int] = []
    rule_a_idx: list[int] = []
    for i, t in enumerate(out):
        if t.get("rule_kind") == "A":
            members = list(t.get("rule_definition", {}).get("members", []))
            pool.extend(members)
            sizes.append(len(members))
            rule_a_idx.append(i)
    rng.shuffle(pool)
    cursor = 0
    for size, idx in zip(sizes, rule_a_idx):
        out[idx]["rule_definition"]["members"] = pool[cursor:cursor + size]
        cursor += size
    return out


def run_retro(
    themes: list[dict],
    start: date,
    end: date,
    output_dir: Path,
    label: str = "real",
) -> list[dict[str, Any]]:
    """Run weekly detector over [start, end], accumulating state. Writes
    themes_<date>.json frames. Returns the trajectory rows."""
    output_dir.mkdir(parents=True, exist_ok=True)
    states: dict[str, ThemeState] = {}
    rows: list[dict[str, Any]] = []
    sundays = list(iter_sundays(start, end))
    for i, sunday in enumerate(sundays):
        result = run_detector(sunday, themes, states)
        states = result["next_states"]
        out = result["output"]
        if label == "real":
            (output_dir / f"themes_{sunday}.json").write_text(
                json.dumps(out, indent=2), encoding="utf-8"
            )
        for t in out["themes"]:
            rows.append({
                "label": label,
                "week": sunday.isoformat(),
                "week_idx": i,
                "theme_id": t["theme_id"],
                "lifecycle_stage": t["lifecycle_stage"],
                "lifecycle_stage_age_weeks": t["lifecycle_stage_age_weeks"],
                "belief_score": t["belief_score"],
                "confirmation_score": t["confirmation_score"],
                "credibility_penalty": t["credibility_penalty"],
                "current_strength": t["current_strength"],
                "first_pre_ignition_date": t["first_pre_ignition_date"],
                "first_ignition_date": t["first_ignition_date"],
            })
    return rows


def lead_time_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """For each §8 reference cycle, find first PRE_IGNITION date in retro and
    compute lead_time_weeks vs RS-breakout."""
    by_theme: dict[str, list[dict]] = {}
    for r in rows:
        if r["label"] != "real":
            continue
        by_theme.setdefault(r["theme_id"], []).append(r)

    out: list[dict[str, Any]] = []
    for ref in REFERENCE_CYCLES:
        tid = ref["theme_id"]
        weeks = sorted(by_theme.get(tid, []), key=lambda x: x["week"])
        first_pre = next((w for w in weeks if w["lifecycle_stage"] == "PRE_IGNITION"), None)
        first_ign = next((w for w in weeks if w["lifecycle_stage"] == "IGNITION"), None)

        first_pre_date = (
            datetime.fromisoformat(first_pre["week"]).date() if first_pre else None
        )
        first_ign_date = (
            datetime.fromisoformat(first_ign["week"]).date() if first_ign else None
        )
        rs_breakout = ref["rs_breakout"]

        lead_pre_weeks: int | None = None
        if first_pre_date is not None:
            lead_pre_weeks = (rs_breakout - first_pre_date).days // 7

        out.append({
            "theme_id": tid,
            "ignition_quarter_spec": ref["ignition_quarter"],
            "rs_breakout_spec": rs_breakout.isoformat(),
            "first_pre_ignition_retro": first_pre_date.isoformat() if first_pre_date else None,
            "first_ignition_retro": first_ign_date.isoformat() if first_ign_date else None,
            "lead_time_pre_to_rs_weeks": lead_pre_weeks,
            "gate_a_4w_pass": (
                lead_pre_weeks is not None and lead_pre_weeks >= 4
            ) if lead_pre_weeks is not None else None,
        })
    return out


def write_csv(path: Path, rows: list[dict[str, Any]]):
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def stage_count_summary(rows: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    """Per-week stage counts grouped by label."""
    out: dict[str, dict[str, int]] = {}
    for r in rows:
        key = f"{r['label']}|{r['week']}"
        out.setdefault(key, {"DORMANT": 0, "PRE_IGNITION": 0, "IGNITION": 0,
                             "MATURE": 0, "DECAY": 0, "FALSE_POSITIVE": 0})
        out[key][r["lifecycle_stage"]] += 1
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--start", required=True, help="YYYY-MM-DD")
    p.add_argument("--end", required=True, help="YYYY-MM-DD")
    p.add_argument("--themes", required=True, type=Path)
    p.add_argument("--output-dir", required=True, type=Path)
    p.add_argument("--null-shuffle", action="store_true",
                   help="Also run a member-shuffle null (1 run, seed=42)")
    args = p.parse_args()

    start = datetime.strptime(args.start, "%Y-%m-%d").date()
    end = datetime.strptime(args.end, "%Y-%m-%d").date()
    themes = load_themes(args.themes)

    print(f"[retro] real run: {start}..{end}")
    real_rows = run_retro(themes, start, end, args.output_dir / "weekly", label="real")
    print(f"[retro] real run: {len(real_rows)} theme-week rows written")

    if args.null_shuffle:
        rng = random.Random(42)
        shuffled = shuffle_members_across_themes(themes, rng)
        print(f"[retro] null run (member-shuffle, seed=42): {start}..{end}")
        null_rows = run_retro(shuffled, start, end, args.output_dir / "null_weekly", label="null_shuffle")
        print(f"[retro] null run: {len(null_rows)} theme-week rows written")
    else:
        null_rows = []

    all_rows = real_rows + null_rows
    write_csv(args.output_dir / "lifecycle_trajectory.csv", all_rows)
    print(f"[retro] wrote lifecycle_trajectory.csv ({len(all_rows)} rows)")

    summary = lead_time_summary(real_rows)
    write_csv(args.output_dir / "lead_time_summary.csv", summary)
    print(f"[retro] wrote lead_time_summary.csv ({len(summary)} reference cycles)")
    for s in summary:
        gate = "PASS" if s["gate_a_4w_pass"] else "FAIL"
        print(f"  {s['theme_id']:30} gate_a_4w={gate:4} "
              f"lead={s['lead_time_pre_to_rs_weeks']}w "
              f"first_pre={s['first_pre_ignition_retro']} rs_break={s['rs_breakout_spec']}")


if __name__ == "__main__":
    main()
