"""DSL grammar v1 — validator, compiler, family-size enumerator."""
from __future__ import annotations

from dataclasses import dataclass

from pipeline.autoresearch.regime_autoresearch.constants import REGIMES

FEATURES: tuple[str, ...] = (
    "ret_1d", "ret_5d", "ret_20d", "ret_60d", "mom_ratio_20_60",
    "vol_20d", "vol_percentile_252d", "vol_of_vol_60d",
    "resid_vs_sector_1d", "z_resid_vs_sector_20d", "beta_nifty_60d",
    "days_from_52w_high", "dist_from_52w_high_pct",
    "beta_vix_60d", "macro_composite_60d_corr",
    "adv_20d", "adv_percentile_252d", "turnover_ratio_20d",
    "trust_score", "trust_sector_rank",
)

THRESHOLD_OPS: tuple[str, ...] = (">", "<", "top_k", "bottom_k")

# Feature-specific threshold grids — 8 points each. The DSL keeps them simple:
# absolute-level thresholds for `>`/`<`, k-values for `top_k`/`bottom_k`.
ABSOLUTE_THRESHOLD_GRID: tuple[float, ...] = (-2.0, -1.0, -0.5, 0.0, 0.5, 1.0, 2.0, 3.0)
K_GRID: tuple[int, ...] = (3, 5, 10, 15, 20, 25, 30, 40)

HOLD_HORIZONS: tuple[int, ...] = (1, 5, 20)
CONSTRUCTION_TYPES: tuple[str, ...] = (
    "single_long", "single_short", "long_short_basket", "pair",
)


@dataclass(frozen=True)
class Proposal:
    construction_type: str
    feature: str
    threshold_op: str
    threshold_value: float
    hold_horizon: int
    regime: str
    pair_id: str | None


def validate(p: Proposal) -> bool:
    """True if proposal fits the grammar. Raises ValueError with reason otherwise."""
    if p.construction_type not in CONSTRUCTION_TYPES:
        raise ValueError(f"unknown construction_type: {p.construction_type}")
    if p.feature not in FEATURES:
        raise ValueError(f"unknown feature: {p.feature}")
    if p.threshold_op not in THRESHOLD_OPS:
        raise ValueError(f"unknown threshold_op: {p.threshold_op}")
    if p.hold_horizon not in HOLD_HORIZONS:
        raise ValueError(f"hold_horizon must be one of {HOLD_HORIZONS}")
    if p.regime not in REGIMES:
        raise ValueError(f"regime must be one of {REGIMES}")
    if p.construction_type == "pair" and not p.pair_id:
        raise ValueError("pair construction requires pair_id")
    if p.construction_type != "pair" and p.pair_id is not None:
        raise ValueError("pair_id only valid when construction_type == 'pair'")
    # Threshold grids (ABSOLUTE_THRESHOLD_GRID, K_GRID) are enumeration aids for
    # the proposer and the family-size cardinality — `validate` accepts any
    # numeric threshold since the proposer may interpolate between grid points.
    if p.threshold_op in ("top_k", "bottom_k"):
        if not isinstance(p.threshold_value, (int, float)) or p.threshold_value <= 0:
            raise ValueError(f"k-op requires positive threshold_value (grid hint: {K_GRID})")
    return True


def enumerate_family_size(include_pairs: bool = False, n_pairs: int = 0) -> int:
    """Cardinality of the grammar for multiplicity accounting."""
    non_pair = 3 * len(FEATURES) * len(THRESHOLD_OPS) * 8 * len(HOLD_HORIZONS) * len(REGIMES)
    if not include_pairs:
        return non_pair
    pair = 1 * len(FEATURES) * len(THRESHOLD_OPS) * 8 * len(HOLD_HORIZONS) * len(REGIMES) * max(n_pairs, 1)
    return non_pair + pair
