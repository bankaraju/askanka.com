"""DSL grammar v1 — validator, compiler, family-size enumerator."""
from __future__ import annotations

from dataclasses import dataclass

from pipeline.autoresearch.regime_autoresearch.constants import REGIMES

FEATURES: tuple[str, ...] = (
    # v1 features (20)
    "ret_1d", "ret_5d", "ret_20d", "ret_60d", "mom_ratio_20_60",
    "vol_20d", "vol_percentile_252d", "vol_of_vol_60d",
    "resid_vs_sector_1d", "z_resid_vs_sector_20d", "beta_nifty_60d",
    "days_from_52w_high", "dist_from_52w_high_pct",
    "beta_vix_60d", "macro_composite_60d_corr",
    "adv_20d", "adv_percentile_252d", "turnover_ratio_20d",
    "trust_score", "trust_sector_rank",
    # v2 features (14) — Task 4
    "return_1d", "return_5d", "return_60d",
    "skewness_20d", "kurtosis_20d",
    "volume_zscore_20d", "turnover_percentile_252d", "volume_trend_5d",
    "excess_return_vs_sector_20d", "rank_in_sector_20d_return",
    "peer_spread_zscore_20d", "correlation_to_sector_60d",
    "residual_return_5d", "adv_ratio_to_sector_mean_20d",
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
    """True if proposal fits the grammar. Raises ValueError with reason otherwise.

    The grid IS the grammar: threshold_value MUST be a member of the enumerated
    grid (ABSOLUTE_THRESHOLD_GRID or K_GRID). This is a hard constraint, not a
    hint — the entire purpose of the DSL is to have a countable family size
    (28,800 non-pair points) so BH-FDR q=0.1 can apply the correct multiplicity
    correction. If validate() accepts off-grid values, the space is infinite
    and the false-discovery-rate math is wrong.
    """
    if p.construction_type not in CONSTRUCTION_TYPES:
        raise ValueError(f"unknown construction_type: {p.construction_type}")
    if p.feature not in FEATURES:
        raise ValueError(f"unknown feature: {p.feature}")
    if p.threshold_op not in THRESHOLD_OPS:
        raise ValueError(f"unknown threshold_op: {p.threshold_op}")
    if p.regime not in REGIMES:
        raise ValueError(f"regime must be one of {REGIMES}")
    if p.hold_horizon not in HOLD_HORIZONS:
        raise ValueError(f"hold_horizon must be one of {HOLD_HORIZONS}")
    if p.construction_type == "pair" and not p.pair_id:
        raise ValueError("pair construction requires pair_id")
    if p.construction_type != "pair" and p.pair_id is not None:
        raise ValueError("pair_id only valid when construction_type == 'pair'")
    # Strict grid membership — the grid IS the grammar.
    if p.threshold_op in ("top_k", "bottom_k"):
        if p.threshold_value not in K_GRID:
            raise ValueError(
                f"threshold_value {p.threshold_value} not in K_GRID {K_GRID}"
            )
    else:
        if p.threshold_value not in ABSOLUTE_THRESHOLD_GRID:
            raise ValueError(
                f"threshold_value {p.threshold_value} not in "
                f"ABSOLUTE_THRESHOLD_GRID {ABSOLUTE_THRESHOLD_GRID}"
            )
    return True


def enumerate_family_size(include_pairs: bool = False, n_pairs: int = 0) -> int:
    """Cardinality of the grammar for multiplicity accounting.

    non_pair = 3 non-pair constructions × 20 features × 4 ops × 8 thresholds × 3 holds × 5 regimes = 28,800
    pair (if include_pairs) = 1 × 20 × 4 × 8 × 3 × 5 × n_pairs
    """
    non_pair = 3 * len(FEATURES) * len(THRESHOLD_OPS) * len(ABSOLUTE_THRESHOLD_GRID) * len(HOLD_HORIZONS) * len(REGIMES)
    if not include_pairs:
        return non_pair
    if n_pairs < 1:
        raise ValueError(f"include_pairs=True requires n_pairs >= 1; got {n_pairs}")
    pair = len(FEATURES) * len(THRESHOLD_OPS) * len(ABSOLUTE_THRESHOLD_GRID) * len(HOLD_HORIZONS) * len(REGIMES) * n_pairs
    return non_pair + pair
