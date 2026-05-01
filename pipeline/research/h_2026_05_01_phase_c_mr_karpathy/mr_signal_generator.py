"""Mean-revert signal generator for H-2026-05-01-phase-c-mr-karpathy-v1.

Strategy-gate-tracked filename per pipeline/scripts/hooks/strategy_patterns.txt
(*_signal_generator.py). Registered in docs/superpowers/hypothesis-registry.jsonl
under hypothesis_id H-2026-05-01-phase-c-mr-karpathy-v1.

Spec: docs/superpowers/specs/2026-05-01-phase-c-mr-karpathy-v1-design.md (section 6)

Pipeline:
  1. Phase-C |z|>=4 vs PIT (ticker, regime) profile -> POSSIBLE_OPPORTUNITY classifier
  2. Regime gate: keep only {RISK-ON, CAUTION}
  3. Event-day skip: drop +/- 1 day around RBI / FOMC / Election / Budget / GST
  4. Karpathy qualifier: 6-of-8 Lasso linear score >= threshold
  5. First-touch dedup per (date, ticker)

Outputs a list[Signal]; the engine consumes these into trades.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from . import HYPOTHESIS_ID
from .event_day_skip import is_event_day
from .feature_library import FEATURE_NAMES, SnapContext, compute_features
from .regime_gate import is_allowed as regime_allowed, regime_for_date

CHOSEN_CELL_PATH = Path(__file__).resolve().parent / "karpathy_chosen_cell.json"


@dataclass(frozen=True)
class Signal:
    """One mean-revert candidate that survived the full pipeline."""
    hypothesis_id: str
    date: str
    snap_t: str
    ticker: str
    sector: str | None
    snap_px: float
    intraday_ret_pct: float
    z_score: float
    expected_ret_pct: float
    classification: str               # always "POSSIBLE_OPPORTUNITY"
    side: str                         # "LONG" or "SHORT"
    regime: str                       # "RISK-ON" or "CAUTION"
    feature_values: dict[str, float] = field(default_factory=dict)
    qualifier_score: float = 0.0
    qualifier_threshold: float = 0.0


@dataclass(frozen=True)
class KarpathyCell:
    """The chosen Lasso cell — feature subset + coefficients + threshold."""
    feature_subset: tuple[str, ...]
    coefficients: dict[str, float]
    intercept: float
    threshold: float
    chosen_at: str

    @classmethod
    def load(cls, path: Path = CHOSEN_CELL_PATH) -> "KarpathyCell | None":
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return cls(
            feature_subset=tuple(payload.get("feature_subset", [])),
            coefficients=dict(payload.get("coefficients", {})),
            intercept=float(payload.get("intercept", 0.0)),
            threshold=float(payload.get("threshold", 0.0)),
            chosen_at=str(payload.get("chosen_at", "")),
        )


def _direction_for_mean_revert(z: float) -> str | None:
    """Side that bets on reversion: opposite to the (over)shoot direction.

    z > 0 => stock moved UP more than expected => SHORT (revert down).
    z < 0 => stock moved DOWN more than expected => LONG (revert up).
    Returns None if z is exactly 0 or NaN.
    """
    if z != z:
        return None
    if z > 0:
        return "SHORT"
    if z < 0:
        return "LONG"
    return None


def _qualifier_score(features: dict[str, float], cell: KarpathyCell) -> float | None:
    """Linear score = intercept + sum(coef * feature) over the chosen subset.

    Returns None if any feature in the chosen subset is NaN — caller drops the trade.
    """
    score = cell.intercept
    for name in cell.feature_subset:
        v = features.get(name)
        if v is None or v != v:
            return None
        coef = cell.coefficients.get(name, 0.0)
        score += coef * v
    return score


def generate_signal(
    ctx: SnapContext,
    *,
    z_score: float,
    expected_ret_pct: float,
    classification: str,
    cell: KarpathyCell | None,
) -> Signal | None:
    """Apply gates 2-4 to a single Phase-C classified candidate.

    Returns None if the candidate is filtered. Returns a Signal otherwise.
    """
    if classification != "POSSIBLE_OPPORTUNITY":
        return None
    if abs(z_score) < 4.0:
        return None

    regime = regime_for_date(ctx.date)
    if regime is None or not regime_allowed(ctx.date):
        return None

    if is_event_day(ctx.date):
        return None

    side = _direction_for_mean_revert(z_score)
    if side is None:
        return None

    features = compute_features(ctx)

    qualifier_score = 0.0
    qualifier_threshold = 0.0
    if cell is not None:
        score = _qualifier_score(features, cell)
        if score is None:
            return None
        if score < cell.threshold:
            return None
        qualifier_score = score
        qualifier_threshold = cell.threshold

    return Signal(
        hypothesis_id=HYPOTHESIS_ID,
        date=ctx.date,
        snap_t=ctx.snap_t,
        ticker=ctx.ticker,
        sector=ctx.sector,
        snap_px=ctx.snap_px,
        intraday_ret_pct=ctx.intraday_ret_pct,
        z_score=z_score,
        expected_ret_pct=expected_ret_pct,
        classification=classification,
        side=side,
        regime=regime,
        feature_values=features,
        qualifier_score=qualifier_score,
        qualifier_threshold=qualifier_threshold,
    )


def feature_subset_size() -> int:
    """Return 6 — the number of features the Karpathy search picks from FEATURE_NAMES."""
    return 6


def feature_universe() -> tuple[str, ...]:
    """Return the locked 8-feature universe."""
    return FEATURE_NAMES
