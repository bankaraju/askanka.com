"""Frozen 8-feature library for the Phase C MR Karpathy v1 engine.

Spec section 5. The Karpathy random search picks 6 of these 8 as the active
feature subset for the qualifier model.

All features are computed PIT — only data dated <= snap_day is used.

Public API: ``compute_features(snap_ctx) -> dict[str, float]``.

The feature dict is consumed by ``mr_signal_generator.qualify``.

NOTE: This is a SKELETON. The eight functions below establish the contract;
each individual computer is intentionally minimal and is fleshed out by the
karpathy_search runner before holdout open. Tests in
``pipeline/tests/research/test_h_2026_05_01_feature_library.py`` lock the
contract and will fail-fast on signature drift.
"""
from __future__ import annotations

from dataclasses import dataclass


FEATURE_NAMES: tuple[str, ...] = (
    "xs_dispersion_1100",        # 5.1
    "realized_implied_gap",      # 5.2
    "breadth_pct_above_20dma",   # 5.3
    "event_day_flag",            # 5.4
    "sector_rs_zscore",          # 5.5
    "xsec_corr_delta_5d",        # 5.6
    "vwap_dev_zscore",           # 5.7
    "news_density_zscore",       # 5.8
)


@dataclass(frozen=True)
class SnapContext:
    """Inputs needed to compute the 8 features at a single (date, ticker, snap_t).

    Held by the engine and passed into compute_features for each candidate trade.
    """
    date: str           # YYYY-MM-DD
    snap_t: str         # HH:MM:SS
    ticker: str
    sector: str | None
    snap_px: float
    intraday_ret_pct: float          # (snap_px - prev_close) / prev_close * 100
    universe_returns: dict[str, float] | None = None  # ticker -> intraday_ret_pct at snap_t
    sector_returns: dict[str, float] | None = None    # sector -> intraday_ret_pct at snap_t
    sector_returns_5d: list[dict[str, float]] | None = None  # last 5 days same map
    sector_rs_history_20d: list[float] | None = None  # last-20d sector intraday %chg at snap_t
    breadth_above_20dma_pct: float | None = None
    india_vix: float | None = None                    # snap-day open level
    realized_30min_atr_pct: float | None = None       # first 30 min realised ATR%
    cumulative_vwap_at_snap: float | None = None
    atr_14_pit: float | None = None
    news_count_24h: int | None = None
    news_count_60d_history: list[int] | None = None
    is_event_day: bool = False


def compute_features(ctx: SnapContext) -> dict[str, float]:
    """Compute all 8 features as a {name: value} dict.

    Missing inputs propagate as NaN-equivalent (math.nan via float('nan'));
    the qualifier downstream skips trades whose required-subset features are NaN.
    """
    return {
        "xs_dispersion_1100": _xs_dispersion_1100(ctx),
        "realized_implied_gap": _realized_implied_gap(ctx),
        "breadth_pct_above_20dma": _breadth_pct_above_20dma(ctx),
        "event_day_flag": _event_day_flag(ctx),
        "sector_rs_zscore": _sector_rs_zscore(ctx),
        "xsec_corr_delta_5d": _xsec_corr_delta_5d(ctx),
        "vwap_dev_zscore": _vwap_dev_zscore(ctx),
        "news_density_zscore": _news_density_zscore(ctx),
    }


# ---- 5.1 cross-sectional dispersion -----------------------------------------

def _xs_dispersion_1100(ctx: SnapContext) -> float:
    """std of universe intraday %chg-from-open at snap_t."""
    if not ctx.universe_returns:
        return float("nan")
    values = [v for v in ctx.universe_returns.values() if v == v]  # drop NaN
    if len(values) < 5:
        return float("nan")
    mean = sum(values) / len(values)
    var = sum((v - mean) ** 2 for v in values) / max(len(values) - 1, 1)
    return var ** 0.5


# ---- 5.2 realized vs implied vol gap ----------------------------------------

def _realized_implied_gap(ctx: SnapContext) -> float:
    """(realised 30min ATR%) / (VIX scaled to 30min)."""
    if ctx.india_vix is None or ctx.realized_30min_atr_pct is None:
        return float("nan")
    if ctx.india_vix <= 0:
        return float("nan")
    # VIX is annualised %; scale to 30-min: sqrt(30 / (252 * 6.25 * 60))
    scale = (30.0 / (252.0 * 6.25 * 60.0)) ** 0.5
    implied_30min = ctx.india_vix * scale
    if implied_30min <= 0:
        return float("nan")
    return ctx.realized_30min_atr_pct / implied_30min


# ---- 5.3 NIFTY-200 breadth --------------------------------------------------

def _breadth_pct_above_20dma(ctx: SnapContext) -> float:
    if ctx.breadth_above_20dma_pct is None:
        return float("nan")
    return float(ctx.breadth_above_20dma_pct)


# ---- 5.4 event-day binary flag ---------------------------------------------

def _event_day_flag(ctx: SnapContext) -> float:
    return 1.0 if ctx.is_event_day else 0.0


# ---- 5.5 sector RS z-score --------------------------------------------------

def _sector_rs_zscore(ctx: SnapContext) -> float:
    if (ctx.sector is None
            or not ctx.sector_returns
            or ctx.sector_rs_history_20d is None
            or ctx.sector not in ctx.sector_returns):
        return float("nan")
    today_val = ctx.sector_returns[ctx.sector]
    hist = [v for v in ctx.sector_rs_history_20d if v == v]
    if len(hist) < 5:
        return float("nan")
    mean = sum(hist) / len(hist)
    var = sum((v - mean) ** 2 for v in hist) / max(len(hist) - 1, 1)
    sd = var ** 0.5
    if sd == 0:
        return float("nan")
    return (today_val - mean) / sd


# ---- 5.6 cross-sector correlation delta ------------------------------------

def _xsec_corr_delta_5d(ctx: SnapContext) -> float:
    """today's pairwise sector-return correlation - trailing 5d mean of same.

    Skeleton: returns NaN until the engine wires sector_returns + sector_returns_5d.
    Full computation uses Pearson over the 8 sector intraday returns vs equally-weighted
    universe return, averaged pairwise.
    """
    if not ctx.sector_returns or not ctx.sector_returns_5d:
        return float("nan")
    # Skeleton placeholder: fall through to NaN until karpathy_search wires the
    # full pairwise computation. The signature is locked.
    return float("nan")


# ---- 5.7 VWAP deviation z-score --------------------------------------------

def _vwap_dev_zscore(ctx: SnapContext) -> float:
    if (ctx.cumulative_vwap_at_snap is None
            or ctx.atr_14_pit is None
            or ctx.atr_14_pit <= 0):
        return float("nan")
    return (ctx.snap_px - ctx.cumulative_vwap_at_snap) / ctx.atr_14_pit


# ---- 5.8 news density z-score ----------------------------------------------

def _news_density_zscore(ctx: SnapContext) -> float:
    if ctx.news_count_24h is None or not ctx.news_count_60d_history:
        return float("nan")
    hist = [float(v) for v in ctx.news_count_60d_history]
    if len(hist) < 10:
        return float("nan")
    mean = sum(hist) / len(hist)
    var = sum((v - mean) ** 2 for v in hist) / max(len(hist) - 1, 1)
    sd = var ** 0.5
    if sd == 0:
        return float("nan")
    return (float(ctx.news_count_24h) - mean) / sd
