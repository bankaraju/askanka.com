"""Time-of-day analyzer — slice the 1,029 NIFR triggers by entry snap_t to
test whether a simple time-of-day gate alone lifts the family into
registration territory.

Reads horizon_trades.csv (filter to variant=VWAP_TOUCH, horizon_D=0 → one
row per trigger) and tabulates same-day-touch rate, mean bps gross/net,
and Sharpe per trade by:
  - per-snap exact buckets (10:00, 10:15, 10:30, ..., 14:00)
  - 30-minute coarse buckets
  - cumulative "fire only before HH:MM" gates

The decision: if "before 11:30" or similar gate produces ≥+25 bps net S1
mean with hit ≥55% and Sharpe per trade ≥0.15, the time-of-day-gated
family is registration-eligible and we don't need the same-day-touch
classifier.
"""
from __future__ import annotations

import csv
import json
import math
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
TRADES_CSV = HERE / "horizon_trades.csv"
OUT_JSON = HERE / "tod_summary.json"

EXACT_SNAPS = (
    "10:00:00",
    "10:15:00",
    "10:30:00",
    "10:45:00",
    "11:00:00",
    "11:15:00",
    "11:30:00",
    "11:45:00",
    "12:00:00",
    "12:15:00",
    "12:30:00",
    "12:45:00",
    "13:00:00",
    "13:15:00",
    "13:30:00",
    "13:45:00",
    "14:00:00",
)
COARSE_BUCKETS = (
    ("10:00-10:30", ("10:00:00", "10:15:00")),
    ("10:30-11:00", ("10:30:00", "10:45:00")),
    ("11:00-11:30", ("11:00:00", "11:15:00")),
    ("11:30-12:00", ("11:30:00", "11:45:00")),
    ("12:00-12:30", ("12:00:00", "12:15:00")),
    ("12:30-13:00", ("12:30:00", "12:45:00")),
    ("13:00-13:30", ("13:00:00", "13:15:00")),
    ("13:30-14:00", ("13:30:00", "13:45:00", "14:00:00")),
)
CUMULATIVE_CUTOFFS = (
    "10:30:00",
    "11:00:00",
    "11:30:00",
    "12:00:00",
    "12:30:00",
    "13:00:00",
    "13:30:00",
    "14:00:00",
    "14:15:00",  # all
)

COST_BPS_S1 = 30.0


def _stats(rows: list[dict]) -> dict:
    if not rows:
        return dict(n=0)
    n = len(rows)
    n_touched = sum(1 for r in rows if r["outcome"] == "VWAP_TOUCH")
    gross = [float(r["bps_gross"]) for r in rows]
    net_s1 = [float(r["bps_net_s1"]) for r in rows]
    hits_gross = [1 if v > 0 else 0 for v in gross]
    hits_net = [1 if v > 0 else 0 for v in net_s1]

    mu_g = statistics.mean(gross)
    sd_g = statistics.pstdev(gross) if n > 1 else 0.0
    sharpe_g = (mu_g / sd_g) if sd_g > 0 else 0.0
    mu_n = statistics.mean(net_s1)
    sd_n = statistics.pstdev(net_s1) if n > 1 else 0.0
    sharpe_n = (mu_n / sd_n) if sd_n > 0 else 0.0

    touched_rows = [r for r in rows if r["outcome"] == "VWAP_TOUCH"]
    no_touch_rows = [r for r in rows if r["outcome"] == "FORCE_CLOSE_NO_TOUCH"]
    cond = {}
    for label, slice_rows in (("touched", touched_rows), ("no_touch", no_touch_rows)):
        if not slice_rows:
            cond[label] = dict(n=0)
            continue
        sg = [float(r["bps_gross"]) for r in slice_rows]
        cond[label] = dict(
            n=len(slice_rows),
            mean_bps_gross=round(statistics.mean(sg), 3),
            hit_rate_gross=round(
                sum(1 for v in sg if v > 0) / len(sg), 4
            ),
        )

    return dict(
        n=n,
        touch_rate=round(n_touched / n, 4),
        mean_bps_gross=round(mu_g, 3),
        mean_bps_net_s1=round(mu_n, 3),
        hit_rate_gross=round(sum(hits_gross) / n, 4),
        hit_rate_net_s1=round(sum(hits_net) / n, 4),
        sharpe_per_trade_gross=round(sharpe_g, 4),
        sharpe_per_trade_net_s1=round(sharpe_n, 4),
        conditional=cond,
    )


def main() -> None:
    all_rows: list[dict] = []
    with TRADES_CSV.open("r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            if row.get("variant") != "VWAP_TOUCH":
                continue
            if int(row.get("horizon_D", "-1")) != 0:
                continue
            all_rows.append(row)
    print(f"loaded {len(all_rows)} D0 VWAP_TOUCH rows from {TRADES_CSV.name}")

    by_exact = {}
    for snap in EXACT_SNAPS:
        slice_rows = [r for r in all_rows if r["snap_t"] == snap]
        by_exact[snap] = _stats(slice_rows)

    by_coarse = {}
    for label, snaps in COARSE_BUCKETS:
        slice_rows = [r for r in all_rows if r["snap_t"] in snaps]
        by_coarse[label] = _stats(slice_rows)

    cumulative_before = {}
    for cutoff in CUMULATIVE_CUTOFFS:
        slice_rows = [r for r in all_rows if r["snap_t"] < cutoff]
        cumulative_before[f"before_{cutoff}"] = _stats(slice_rows)

    by_side_under_1130 = {}
    for side in ("LONG", "SHORT"):
        slice_rows = [r for r in all_rows if r["snap_t"] < "11:30:00" and r["side"] == side]
        by_side_under_1130[side] = _stats(slice_rows)

    by_sector_under_1130 = {}
    sectors = sorted({r.get("sector", "") for r in all_rows if r.get("sector")})
    for sector in sectors:
        slice_rows = [
            r for r in all_rows if r["snap_t"] < "11:30:00" and r.get("sector") == sector
        ]
        by_sector_under_1130[sector] = _stats(slice_rows)

    summary = dict(
        by_exact_snap=by_exact,
        by_coarse_30min=by_coarse,
        cumulative_before=cumulative_before,
        by_side_under_1130=by_side_under_1130,
        by_sector_under_1130=by_sector_under_1130,
        meta=dict(
            n_input_d0_triggers=len(all_rows),
            cost_bps_s1=COST_BPS_S1,
            note=(
                "rows here = one per trigger (variant=VWAP_TOUCH, horizon_D=0). "
                "outcome=VWAP_TOUCH means same-day touch happened; "
                "outcome=FORCE_CLOSE_NO_TOUCH means session ended without touch. "
                "conditional.touched.* = stats on the same-day-touch arm only."
            ),
        ),
    )

    OUT_JSON.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"wrote -> {OUT_JSON.name}")


if __name__ == "__main__":
    main()
