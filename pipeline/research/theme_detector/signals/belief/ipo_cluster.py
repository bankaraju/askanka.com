"""B5 — IPO cluster.

Per-theme signal: count of main-board IPOs landing in the same Tier-1 sector /
sub-sector as the theme within a rolling 6-month window, normalized to [0, 1].

v1 implementation (2026-05-01):
    n_ipos = count of mainboard IPOs in [run_date - 180d, run_date - 7d] that
             match the theme via keyword inference (see THEME_KEYWORDS below)
             OR whose STOCK CODE is already in the theme's authored membership
    score = min(1.0, n_ipos / 3.0)

The /3.0 anchor: 3+ same-sector mainboard IPOs in 6m is unambiguous cluster
evidence; 0 IPOs is silence; intermediate values scale linearly. The choice of
3 is a v1 heuristic — calibration is Phase 2.

Trendlyne IPO calendar carries NO sector tag, only COMPANY NAME + STOCK CODE.
Keyword inference is fragile by design: false positives (e.g., a generic
"Industries" name landing inside CAPEX_PLI_BENEFICIARY) inflate, false negatives
(e.g., a defence-services SME mainboard listing without "defence" in its name)
deflate. v2 fix is per-IPO sector inference via EODHD/IndianAPI tags after the
artifact backfill (memory: 64/273 canonical F&O lack indianapi_stock.json — IPO
coverage will be even thinner).

Returns None when:
- theme is rule_kind=B (no fixed members AND v1 lacks predicate evaluator), OR
- IPO calendar is missing.

Returns 0.0 (not None) when calendar is present but no IPOs match — silence is
data, signals "no fresh listings expanding this theme."

Data source: pipeline/data/trendlyne/raw_exports/ipo_calendar/listed_ipos_*.csv
PIT cutoff: listing_date <= run_date - 7d (per spec §3.1 B5).

Spec: docs/superpowers/specs/2026-05-01-theme-detector-design.md §3.1 (B5)
"""
from __future__ import annotations

from datetime import date, timedelta

from pipeline.research.theme_detector.data_loaders import load_ipo_calendar
from pipeline.research.theme_detector.signals.base import Signal, SignalResult

WINDOW_DAYS = 180  # rolling 6m
ANCHOR_N = 3.0     # n IPOs at which score saturates to 1.0

# Per-theme keyword inference for v1. Match is ANY-of (case-insensitive
# substring on COMPANY NAME or STOCK CODE). Empty list -> theme is keyword-blind
# (handled by member-list fallback only).
THEME_KEYWORDS: dict[str, list[str]] = {
    "BANKS_DIGITAL_TAILWIND": ["bank"],
    "BANKS_PSU_REREATING": ["bank"],
    "IT_AI_HEADWIND_MASS": ["technologies", "infotech", "software", "consult", "tech "],
    "IT_AI_TAILWIND_ER_AND_D": [
        "technologies", "engineering", "elxsi", "fractal",
        "analytics", "capillary", "excelsoft",
    ],
    "DEFENCE_WAR_ECONOMY": [
        "defence", "defense", "shipyard", "aerospace",
        "ordnance", "bharat dynamics",
    ],
    "HOSPITALS_ROBOTICS_LEAN": [
        "hospital", "healthcare", "medi ", "kidney", "ivf",
        "nephro", "park medi",
    ],
    "DATA_CENTRES_ADJACENT": ["data centre", "data center", "datacentr"],
    "NEW_ECONOMY_LISTINGS_2020_22_COHORT": [],  # rule_kind B handled separately
    "POWER_RENEWABLE_TRANSITION": [
        "power", "renewable", "solar", "wind", "photovoltaic",
        "energy", "clean max", "emmvee",
    ],
    "CAPEX_PLI_BENEFICIARY": [
        "engineering", "industries", "capital", "mechatronics",
        "siemens", "abb", "automation",
    ],
    "QUICK_COMMERCE": [
        "zomato", "delhivery", "swiggy", "blinkit", "shadowfax",
        "lenskart", "meesho", "pine labs", "groww", "lens",
        "physicswallah", "delivery", "logistic", "commerce",
    ],
    "EVS_AND_AUTO_TECH": [
        "auto", "motor", "electric ", "tenneco", "battery",
        "vehicle",
    ],
}


class IPOClusterSignal(Signal):
    signal_id = "B5_ipo_cluster"
    bucket = "belief"

    def compute_for_theme(self, theme: dict, run_date: date) -> SignalResult:
        members = list(theme.get("rule_definition", {}).get("members", []))
        rule_kind = theme.get("rule_kind", "A")
        theme_id = theme["theme_id"]

        if rule_kind == "B" and not members:
            return SignalResult(
                theme_id=theme_id,
                signal_id=self.signal_id,
                score=None,
                notes="rule_kind_b_filter_predicate_unsupported_at_v1",
            )

        cal = load_ipo_calendar(run_date)
        if cal is None:
            return SignalResult(
                theme_id=theme_id,
                signal_id=self.signal_id,
                score=None,
                notes="data_unavailable: IPO calendar missing",
            )

        cutoff_hi = run_date - timedelta(days=7)
        cutoff_lo = run_date - timedelta(days=WINDOW_DAYS)
        recent = cal[
            cal["is_mainboard"]
            & (cal["listing_date"] >= cutoff_lo)
            & (cal["listing_date"] <= cutoff_hi)
        ]

        keywords = [k.lower() for k in THEME_KEYWORDS.get(theme_id, [])]
        member_set = {m.upper() for m in members}

        names = recent["COMPANY NAME"].astype(str).str.lower()
        codes = recent["STOCK CODE"].astype(str).str.upper()

        kw_match = (
            names.apply(lambda s: any(k in s for k in keywords))
            if keywords else names.apply(lambda _: False)
        )
        member_match = codes.isin(member_set) if member_set else codes.apply(lambda _: False)

        matched = recent[kw_match | member_match]
        n = len(matched)
        score = min(1.0, n / ANCHOR_N)

        notes = (
            f"n_mainboard_ipos_6m={n} (window={cutoff_lo}..{cutoff_hi}, "
            f"keywords={len(keywords)}, members={len(member_set)})"
        )
        return SignalResult(
            theme_id=theme_id,
            signal_id=self.signal_id,
            score=float(score),
            notes=notes,
        )
