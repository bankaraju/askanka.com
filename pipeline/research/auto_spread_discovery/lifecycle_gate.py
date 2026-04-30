"""ASDE lifecycle gate — empirical filter for one-shot themes.

Built from the 2026-04-30 theme lifecycle audit on Task #24's 234 cells:
  - 39/234 cells were OLD-ONLY (alive pre-2024, dead 2024+) — decayed kings
  - 9/234 cells were RECENT-ONLY (alive 2024+, dead pre-2024) — emerging
  - Only 9/234 were alive in 5/5 years (durable)
  - RELOMC's 100% bootstrap was bimodal (alive 2022 + 2024 only)
  - DEFIT/NEUTRAL was alive 5/5 years — gold-standard durability

The lifecycle gate filters cells whose alpha is concentrated in 1-2 fluky
years. A cell can pass the multi-gate verdict bar (mean / t / hit / MaxDD /
bootstrap) by riding one good year; we add this gate to require persistence.

Gate definition (locked at this commit, anti-data-snooping)
----------------------------------------------------------
A cell PASSES the lifecycle gate iff ALL conditions hold:

  1. ALIVE_RECENT: alive in at least one of the last 2 calendar years tested.
     (Reason: a strategy whose last alive year was 2022 is provably decayed.)
  2. ALIVE_DEPTH: alive in >= max(2, floor(N * 0.5)) of N tested years.
     (Reason: 50%+ aliveness across the full history filters bimodal cells.)
  3. NO_REVERSAL: most-recent year mean post-cost is NOT in the bottom 25%
     of the cell's own 5y mean distribution.
     (Reason: a cell whose last year was -200bp while overall mean was +50bp
     has flipped sign; promotion would chase decay.)

A year is "alive" iff:
  mean_post_cost_bps > 0 AND n_events_in_year >= MIN_N_PER_YEAR (default 5)

Known permissive case
---------------------
EUPHORIA cells (RELOMC, Coal-OMC, etc.) fire only on regime windows that
hit ~5-10 days/year. Bimodal alive patterns (alive only in shock years)
sit at the depth floor (2 alive of 5 years -> floor=2) and PASS this
gate. We do NOT tighten the gate to catch them because the same threshold
would auto-reject any rare-regime hypothesis pre-registration; we rely
on bootstrap + BH-FDR + forward holdout to carry that weight.

NEUTRAL/RISK-ON/CAUTION cells with n>=100/year cannot hide here — they
either show 4+/N alive years or fail.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

MIN_N_PER_YEAR = 5
RECENT_YEARS_WINDOW = 2  # last 2 years must have at least 1 alive year


@dataclass(frozen=True)
class YearStat:
    year: int
    n: int
    mean_bps: float


@dataclass(frozen=True)
class LifecycleVerdict:
    passed: bool
    verdict: str   # LIFECYCLE_PASS | FAIL_RECENT | FAIL_DEPTH | FAIL_REVERSAL
    n_years_tested: int
    n_years_alive: int
    last_alive_year: int | None
    most_recent_year: int | None
    most_recent_mean_bps: float
    median_year_mean_bps: float
    reason: str


def _is_alive(stat: YearStat) -> bool:
    return stat.n >= MIN_N_PER_YEAR and stat.mean_bps > 0


def _quantile(values: list[float], q: float) -> float:
    """Linear-interp quantile. q in [0, 1]. Empty -> 0.0."""
    if not values:
        return 0.0
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    pos = (len(s) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return s[lo]
    frac = pos - lo
    return s[lo] * (1 - frac) + s[hi] * frac


def evaluate(year_stats: Sequence[YearStat]) -> LifecycleVerdict:
    """Apply the 3-condition lifecycle gate to year-aggregated cell stats."""
    if not year_stats:
        return LifecycleVerdict(
            passed=False, verdict="FAIL_DEPTH",
            n_years_tested=0, n_years_alive=0,
            last_alive_year=None, most_recent_year=None,
            most_recent_mean_bps=0.0, median_year_mean_bps=0.0,
            reason="no year stats provided",
        )

    sorted_stats = sorted(year_stats, key=lambda s: s.year)
    n_total = len(sorted_stats)
    alive_years = [s for s in sorted_stats if _is_alive(s)]
    n_alive = len(alive_years)
    last_alive = alive_years[-1].year if alive_years else None
    most_recent = sorted_stats[-1].year
    most_recent_stat = sorted_stats[-1]

    means = [s.mean_bps for s in sorted_stats]
    median = _quantile(means, 0.5)
    p25 = _quantile(means, 0.25)

    # Condition 1: ALIVE_RECENT
    recent_window_years = [s for s in sorted_stats[-RECENT_YEARS_WINDOW:]]
    recent_alive = any(_is_alive(s) for s in recent_window_years)
    if not recent_alive:
        return LifecycleVerdict(
            passed=False, verdict="FAIL_RECENT",
            n_years_tested=n_total, n_years_alive=n_alive,
            last_alive_year=last_alive, most_recent_year=most_recent,
            most_recent_mean_bps=most_recent_stat.mean_bps,
            median_year_mean_bps=median,
            reason=(f"no alive year in last {RECENT_YEARS_WINDOW} "
                    f"(last alive: {last_alive})"),
        )

    # Condition 2: ALIVE_DEPTH
    required_alive = max(2, math.floor(n_total * 0.5))
    if n_alive < required_alive:
        return LifecycleVerdict(
            passed=False, verdict="FAIL_DEPTH",
            n_years_tested=n_total, n_years_alive=n_alive,
            last_alive_year=last_alive, most_recent_year=most_recent,
            most_recent_mean_bps=most_recent_stat.mean_bps,
            median_year_mean_bps=median,
            reason=f"alive in {n_alive}/{n_total} years; needed >= {required_alive}",
        )

    # Condition 3: NO_REVERSAL — most-recent year not in bottom-25% by mean
    if most_recent_stat.mean_bps < p25:
        return LifecycleVerdict(
            passed=False, verdict="FAIL_REVERSAL",
            n_years_tested=n_total, n_years_alive=n_alive,
            last_alive_year=last_alive, most_recent_year=most_recent,
            most_recent_mean_bps=most_recent_stat.mean_bps,
            median_year_mean_bps=median,
            reason=(f"most-recent {most_recent} mean {most_recent_stat.mean_bps:.1f}bps "
                    f"< 25th-pct {p25:.1f}bps"),
        )

    return LifecycleVerdict(
        passed=True, verdict="LIFECYCLE_PASS",
        n_years_tested=n_total, n_years_alive=n_alive,
        last_alive_year=last_alive, most_recent_year=most_recent,
        most_recent_mean_bps=most_recent_stat.mean_bps,
        median_year_mean_bps=median,
        reason=(f"alive {n_alive}/{n_total} years; recent={most_recent_stat.mean_bps:.1f}bps "
                f"(median={median:.1f}, p25={p25:.1f})"),
    )
