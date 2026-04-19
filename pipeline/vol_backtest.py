"""
Retrospective vol model validation — EWMA expected move vs actual next-day move.

For each stock CSV in alpha_test_cache/:
  - Rolling 30-day EWMA vol at each date t (no lookahead: window = closes[t-30:t])
  - BS-price a 1-day ATM straddle → expected_move_pct
  - Compare vs actual |close[t+1] - close[t]| / close[t]

Outputs:
  - MAPE  — mean absolute % error between expected and actual move
  - hit_rate — fraction of days actual move stayed within 1-sigma band
  - vol_scalar — median(actual/expected); <1 = model over-estimates vol

Run: python -m pipeline.vol_backtest
"""
from __future__ import annotations

import csv
import json
import logging
import math
import statistics
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

_DEFAULT_CACHE_DIR = Path(__file__).resolve().parent / "data" / "alpha_test_cache"
_DEFAULT_OUTPUT = Path(__file__).resolve().parent / "data" / "vol_backtest_results.json"
_MIN_ROWS = 32  # need 30-day window + at least one valid t+1 observation


# ---------------------------------------------------------------------------
# CSV loader
# ---------------------------------------------------------------------------

def _load_closes(csv_path: Path) -> list[dict]:
    """Return list of {date: str, close: float} sorted ascending by date."""
    rows = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                close = float(row["Close"])
                if close <= 0:
                    continue
                rows.append({"date": row["Date"].strip(), "close": close})
            except (KeyError, ValueError):
                continue
    def _date_sort_key(date_str: str) -> str:
        """Normalize date to YYYY-MM-DD string for reliable lexicographic sort.

        Real CSVs use ISO format; test data may use pseudo-dates — in all cases
        the string comparison is correct because the format is YYYY-MM-DD (or
        similarly left-zero-padded) so lexicographic == chronological order.
        """
        try:
            return datetime.strptime(date_str, "%Y-%m-%d").strftime("%Y-%m-%d")
        except ValueError:
            return date_str  # Already a comparable string (e.g. YYYYMMDD)

    rows.sort(key=lambda r: _date_sort_key(r["date"]))
    return rows


# ---------------------------------------------------------------------------
# Black-Scholes straddle helper (inline to avoid circular import quirks)
# ---------------------------------------------------------------------------

def _bs_straddle(S: float, sigma: float, T: float = 1 / 365, r: float = 0.065) -> float:
    """ATM straddle price = BS call + BS put with K=S."""
    if sigma <= 0 or T <= 0 or S <= 0:
        return 0.0
    try:
        from pipeline.options_pricer import bs_call_price, bs_put_price
        return bs_call_price(S, S, T, sigma, r) + bs_put_price(S, S, T, sigma, r)
    except Exception:
        # Inline fallback so tests don't fail on import issues
        sqrt_T = math.sqrt(T)
        d1 = (math.log(1.0) + (r + 0.5 * sigma ** 2) * T) / (sigma * sqrt_T)  # K=S → log(S/K)=0
        d2 = d1 - sigma * sqrt_T
        from math import erf
        def _cdf(x):
            return 0.5 * (1 + erf(x / math.sqrt(2)))
        call = S * _cdf(d1) - S * math.exp(-r * T) * _cdf(d2)
        put = call + S * math.exp(-r * T) - S  # put-call parity
        return call + put


# ---------------------------------------------------------------------------
# Per-stock backtest
# ---------------------------------------------------------------------------

def backtest_single_stock(csv_path: Path) -> dict:
    """Run rolling EWMA vol backtest for a single CSV.

    Returns:
        dict with keys: ticker, observations, mape_pct, hit_rate, vol_scalar,
                        daily_samples (list of per-day dicts)
    """
    from pipeline.vol_engine import compute_ewma_vol

    ticker = csv_path.stem
    rows = _load_closes(csv_path)

    empty = {
        "ticker": ticker,
        "observations": 0,
        "mape_pct": None,
        "hit_rate": None,
        "vol_scalar": None,
        "daily_samples": [],
    }

    if len(rows) < _MIN_ROWS:
        return empty

    samples = []
    closes = [r["close"] for r in rows]

    # t iterates over valid anchor points: need window closes[t-30:t] + close[t+1]
    # We need at least 30 prices before t, so t starts at index 30.
    # We need close[t+1], so t goes up to len-2.
    for t in range(30, len(rows) - 1):
        window = closes[t - 30: t]  # 30 closes ending at t-1 (NOT including t)
        S = closes[t]               # today's close — used as strike and spot

        try:
            ann_vol = compute_ewma_vol(window, span=30)
        except Exception:
            continue

        # Expected move from ATM straddle (1-day expiry)
        straddle = _bs_straddle(S, ann_vol)
        expected_move_pct = (straddle / S) * 100.0

        # Actual next-day move
        S_next = closes[t + 1]
        actual_move_pct = abs(S_next - S) / S * 100.0

        # 1-sigma daily band from EWMA vol
        daily_sigma_pct = (ann_vol / math.sqrt(252)) * 100.0
        within_1sigma = actual_move_pct <= daily_sigma_pct

        samples.append({
            "date": rows[t]["date"],
            "close": S,
            "ann_vol": round(ann_vol, 6),
            "expected_move_pct": round(expected_move_pct, 4),
            "actual_move_pct": round(actual_move_pct, 4),
            "daily_sigma_pct": round(daily_sigma_pct, 4),
            "within_1sigma": within_1sigma,
        })

    if not samples:
        return empty

    mape_values = [abs(s["expected_move_pct"] - s["actual_move_pct"]) for s in samples]
    mape_pct = statistics.mean(mape_values)

    hit_rate = sum(1 for s in samples if s["within_1sigma"]) / len(samples)

    # vol_scalar: median(actual / expected); >1 means model underestimates, <1 over-estimates
    scalars = [
        s["actual_move_pct"] / s["expected_move_pct"]
        for s in samples
        if s["expected_move_pct"] > 0
    ]
    vol_scalar = statistics.median(scalars) if scalars else None

    return {
        "ticker": ticker,
        "observations": len(samples),
        "mape_pct": round(mape_pct, 4),
        "hit_rate": round(hit_rate, 4),
        "vol_scalar": round(vol_scalar, 4) if vol_scalar is not None else None,
        "daily_samples": samples,
    }


# ---------------------------------------------------------------------------
# Full backtest across all CSVs in cache_dir
# ---------------------------------------------------------------------------

def run_full_backtest(cache_dir: Path) -> dict:
    """Run backtest for every CSV in cache_dir; aggregate across all stocks.

    Returns:
        dict with keys: stocks_tested, total_observations, aggregate (dict),
                        per_stock (list of per-stock result dicts)
    """
    csv_files = sorted(cache_dir.glob("*.csv"))

    if not csv_files:
        return {
            "stocks_tested": 0,
            "total_observations": 0,
            "aggregate": {},
            "per_stock": [],
        }

    per_stock = []
    for csv_path in csv_files:
        result = backtest_single_stock(csv_path)
        per_stock.append(result)
        log.info("Backtested %s: %d obs, MAPE=%.2f%%, hit_rate=%.2f",
                 result["ticker"], result["observations"],
                 result["mape_pct"] or 0, result["hit_rate"] or 0)

    valid = [s for s in per_stock if s["observations"] > 0]

    if not valid:
        return {
            "stocks_tested": len(per_stock),
            "total_observations": 0,
            "aggregate": {},
            "per_stock": per_stock,
        }

    total_obs = sum(s["observations"] for s in valid)

    # Weighted aggregate (weight = observation count)
    def _weighted_mean(field: str) -> float:
        return sum(s[field] * s["observations"] for s in valid if s[field] is not None) / total_obs

    agg_mape = _weighted_mean("mape_pct")

    # sigma_band_hit_rate: pool all samples
    all_samples = [samp for s in valid for samp in s["daily_samples"]]
    sigma_hit = sum(1 for samp in all_samples if samp["within_1sigma"]) / len(all_samples)

    # vol_scalar: median of per-stock medians
    scalars = [s["vol_scalar"] for s in valid if s["vol_scalar"] is not None]
    agg_scalar = statistics.median(scalars) if scalars else None

    return {
        "stocks_tested": len(per_stock),
        "total_observations": total_obs,
        "aggregate": {
            "mape_pct": round(agg_mape, 4),
            "sigma_band_hit_rate": round(sigma_hit, 4),
            "vol_scalar": round(agg_scalar, 4) if agg_scalar is not None else None,
        },
        "per_stock": per_stock,
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cache_dir = _DEFAULT_CACHE_DIR
    if not cache_dir.exists():
        log.error("alpha_test_cache not found: %s", cache_dir)
        return

    log.info("Running vol backtest across %s …", cache_dir)
    result = run_full_backtest(cache_dir)

    # Strip daily_samples from output to keep JSON manageable
    for s in result.get("per_stock", []):
        s.pop("daily_samples", None)

    result["generated_at"] = datetime.now().isoformat()

    _DEFAULT_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(_DEFAULT_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    agg = result.get("aggregate", {})
    log.info(
        "Done. stocks=%d obs=%d MAPE=%.2f%% hit_rate=%.1f%% scalar=%.3f",
        result["stocks_tested"],
        result["total_observations"],
        agg.get("mape_pct") or 0,
        (agg.get("sigma_band_hit_rate") or 0) * 100,
        agg.get("vol_scalar") or 0,
    )
    log.info("Results saved to %s", _DEFAULT_OUTPUT)


if __name__ == "__main__":
    main()
