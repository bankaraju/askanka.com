"""
Random Expiry Baseline — Null Model for Pinning Strategy
Generates 1,000+ random mock strategies to test if pinning's
performance is statistically significant or just small-sample luck.

Two baselines:
  1. Random Strike: same expiry days, random strikes (not GEX-based)
  2. Random Calendar: random dates, random strikes

Compares pinning strategy's Sharpe/return to the random distribution.
If pinning > 95th percentile → real edge. Near median → chance.
"""

import json
import sys
import numpy as np
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

IST = timezone(timedelta(hours=5, minutes=30))


def run_random_baseline(n_simulations: int = 1000):
    from kite_client import get_kite, resolve_token
    kite = get_kite()

    nifty_token = resolve_token("NIFTY 50")
    vix_token = resolve_token("INDIA VIX")

    # Get same Thursdays as pinning backtest
    today = datetime.now(IST).date()
    thursdays = []
    d = today
    while len(thursdays) < 8:
        d -= timedelta(days=1)
        if d.weekday() == 3:
            thursdays.append(d)

    # Fetch intraday data for all Thursdays
    expiry_data = {}
    for thurs in thursdays:
        try:
            candles = kite.historical_data(nifty_token, str(thurs), str(thurs), "5minute")
            if candles and len(candles) > 30:
                expiry_data[str(thurs)] = candles

            vix_candles = kite.historical_data(vix_token, str(thurs), str(thurs), "5minute")
            if vix_candles:
                expiry_data[f"{thurs}_vix"] = float(vix_candles[0]["open"])
        except Exception:
            pass

    valid_dates = [d for d in expiry_data if "_vix" not in d]
    print(f"Expiry days with data: {len(valid_dates)}")

    if len(valid_dates) < 3:
        print("Not enough data for baseline")
        return

    # Also fetch non-Thursday data for Random Calendar baseline
    all_trading_days = {}
    from_date = (today - timedelta(days=60)).strftime("%Y-%m-%d")
    to_date = today.strftime("%Y-%m-%d")
    try:
        daily = kite.historical_data(nifty_token, from_date, to_date, "day")
        for c in daily:
            d = str(c["date"])[:10]
            all_trading_days[d] = float(c["close"])
    except Exception:
        pass

    non_thursdays = [d for d in all_trading_days if datetime.strptime(d, "%Y-%m-%d").weekday() != 3]
    print(f"Non-Thursday trading days: {len(non_thursdays)}")

    # ── PINNING STRATEGY RESULTS (reference) ──
    # From our backtest: champion = 10AM entry, VIX>18, 1x stop
    pinning_pnls = []
    step = 50

    for date_str in valid_dates:
        candles = expiry_data[date_str]
        vix = expiry_data.get(f"{date_str}_vix", 20)

        if vix < 18:
            continue

        closes = [float(c["close"]) for c in candles]
        times = [c["date"] for c in candles]

        # Find 10AM candle
        entry_idx = None
        for i, t in enumerate(times):
            t_str = str(t)
            if "10:00" in t_str or "10:05" in t_str:
                entry_idx = i
                break
        if entry_idx is None:
            entry_idx = 5  # Fallback

        entry_price = closes[entry_idx]
        pin_strike = round(entry_price / step) * step
        close_price = closes[-1]

        # Premium
        hours_left = 5.5
        premium_pct = min(2.0, 0.5 * np.sqrt(hours_left) * (vix / 15))
        premium_pts = pin_strike * premium_pct / 100

        # Max adverse
        remaining = closes[entry_idx:]
        max_adverse = max(abs(c - pin_strike) for c in remaining)

        # 1x stop
        stop_hit = max_adverse > premium_pts
        if stop_hit:
            pnl = 0  # Stopped at breakeven
        else:
            pnl = (premium_pts - abs(close_price - pin_strike)) / pin_strike * 100

        # Subtract costs
        pnl -= 0.25  # Estimated costs

        pinning_pnls.append(pnl)

    if not pinning_pnls:
        print("No pinning trades after VIX filter")
        return

    pinning_avg = np.mean(pinning_pnls)
    pinning_sharpe = np.mean(pinning_pnls) / max(np.std(pinning_pnls), 0.01)
    pinning_win = sum(1 for p in pinning_pnls if p > 0) / len(pinning_pnls) * 100

    print(f"\n=== PINNING STRATEGY (reference) ===")
    print(f"Trades: {len(pinning_pnls)} | Win: {pinning_win:.0f}% | Avg: {pinning_avg:+.3f}% | Sharpe: {pinning_sharpe:.3f}")

    # ── RANDOM STRIKE BASELINE ──
    print(f"\nRunning {n_simulations} Random Strike simulations...")
    random_strike_sharpes = []
    random_strike_avgs = []
    random_strike_wins = []

    for sim in range(n_simulations):
        pnls = []
        for date_str in valid_dates:
            candles = expiry_data[date_str]
            vix = expiry_data.get(f"{date_str}_vix", 20)
            if vix < 18:
                continue

            closes = [float(c["close"]) for c in candles]
            entry_idx = min(5, len(closes) - 10)
            entry_price = closes[entry_idx]

            # RANDOM strike (not GEX-based)
            random_offset = np.random.choice(range(-200, 201, 50))
            random_strike = round(entry_price / step) * step + random_offset
            close_price = closes[-1]

            hours_left = 5.5
            premium_pct = min(2.0, 0.5 * np.sqrt(hours_left) * (vix / 15))
            premium_pts = random_strike * premium_pct / 100

            remaining = closes[entry_idx:]
            max_adverse = max(abs(c - random_strike) for c in remaining)

            stop_hit = max_adverse > premium_pts
            if stop_hit:
                pnl = 0
            else:
                pnl = (premium_pts - abs(close_price - random_strike)) / random_strike * 100
            pnl -= 0.25

            pnls.append(pnl)

        if len(pnls) >= 2:
            random_strike_sharpes.append(np.mean(pnls) / max(np.std(pnls), 0.01))
            random_strike_avgs.append(np.mean(pnls))
            random_strike_wins.append(sum(1 for p in pnls if p > 0) / len(pnls) * 100)

    # ── RANDOM CALENDAR BASELINE ──
    print(f"Running {n_simulations} Random Calendar simulations...")
    random_cal_sharpes = []
    random_cal_avgs = []

    for sim in range(n_simulations):
        # Pick M random dates (same number as pinning trades)
        M = len(pinning_pnls)
        if len(non_thursdays) < M:
            M = len(non_thursdays)
        random_dates = np.random.choice(non_thursdays, size=M, replace=False)

        pnls = []
        for rd in random_dates:
            # Use daily close as proxy (we don't have minute data for non-Thursdays)
            close = all_trading_days.get(rd, 0)
            if close <= 0:
                continue

            random_strike = round(close / step) * step
            # Simulate straddle P&L with random distance
            random_dist = abs(np.random.normal(0, close * 0.008))  # ~0.8% std dev
            premium = close * 0.015  # ~1.5% premium estimate

            pnl = (premium - random_dist) / close * 100 - 0.25
            pnls.append(pnl)

        if len(pnls) >= 2:
            random_cal_sharpes.append(np.mean(pnls) / max(np.std(pnls), 0.01))
            random_cal_avgs.append(np.mean(pnls))

    # ── RESULTS ──
    print(f"\n{'='*60}")
    print("RANDOM EXPIRY BASELINE RESULTS")
    print(f"{'='*60}")

    # Random Strike
    rs_sharpes = np.array(random_strike_sharpes)
    rs_avgs = np.array(random_strike_avgs)
    pinning_sharpe_pctile = (rs_sharpes < pinning_sharpe).mean() * 100
    pinning_avg_pctile = (rs_avgs < pinning_avg).mean() * 100

    print(f"\nRandom Strike Baseline ({len(rs_sharpes)} simulations):")
    print(f"  Sharpe distribution: 5th={np.percentile(rs_sharpes, 5):.3f} | 50th={np.percentile(rs_sharpes, 50):.3f} | 95th={np.percentile(rs_sharpes, 95):.3f}")
    print(f"  Avg P&L distribution: 5th={np.percentile(rs_avgs, 5):+.3f}% | 50th={np.percentile(rs_avgs, 50):+.3f}% | 95th={np.percentile(rs_avgs, 95):+.3f}%")
    print(f"  PINNING Sharpe: {pinning_sharpe:.3f} → {pinning_sharpe_pctile:.0f}th percentile")
    print(f"  PINNING Avg P&L: {pinning_avg:+.3f}% → {pinning_avg_pctile:.0f}th percentile")

    # Random Calendar
    rc_sharpes = np.array(random_cal_sharpes)
    rc_avgs = np.array(random_cal_avgs)
    pinning_cal_pctile = (rc_sharpes < pinning_sharpe).mean() * 100

    print(f"\nRandom Calendar Baseline ({len(rc_sharpes)} simulations):")
    print(f"  Sharpe distribution: 5th={np.percentile(rc_sharpes, 5):.3f} | 50th={np.percentile(rc_sharpes, 50):.3f} | 95th={np.percentile(rc_sharpes, 95):.3f}")
    print(f"  PINNING Sharpe: {pinning_sharpe:.3f} → {pinning_cal_pctile:.0f}th percentile")

    # Verdict
    print(f"\n{'='*60}")
    print("VERDICT")
    print(f"{'='*60}")
    if pinning_sharpe_pctile >= 95:
        print(f"✅ Pinning strategy at {pinning_sharpe_pctile:.0f}th percentile vs random strikes → REAL EDGE")
    elif pinning_sharpe_pctile >= 75:
        print(f"🟡 Pinning strategy at {pinning_sharpe_pctile:.0f}th percentile → PROMISING but needs more data")
    else:
        print(f"🔴 Pinning strategy at {pinning_sharpe_pctile:.0f}th percentile → INDISTINGUISHABLE from random")

    # Save results
    results = {
        "pinning": {"sharpe": round(pinning_sharpe, 3), "avg_pnl": round(pinning_avg, 3),
                    "win_rate": round(pinning_win, 1), "n_trades": len(pinning_pnls)},
        "random_strike": {
            "n_sims": len(rs_sharpes),
            "sharpe_5th": round(float(np.percentile(rs_sharpes, 5)), 3),
            "sharpe_50th": round(float(np.percentile(rs_sharpes, 50)), 3),
            "sharpe_95th": round(float(np.percentile(rs_sharpes, 95)), 3),
            "pinning_percentile": round(pinning_sharpe_pctile, 1),
        },
        "random_calendar": {
            "n_sims": len(rc_sharpes),
            "sharpe_5th": round(float(np.percentile(rc_sharpes, 5)), 3),
            "sharpe_50th": round(float(np.percentile(rc_sharpes, 50)), 3),
            "sharpe_95th": round(float(np.percentile(rc_sharpes, 95)), 3),
            "pinning_percentile": round(pinning_cal_pctile, 1),
        },
        "verdict": "REAL_EDGE" if pinning_sharpe_pctile >= 95 else "PROMISING" if pinning_sharpe_pctile >= 75 else "NOT_SIGNIFICANT",
        "timestamp": datetime.now(IST).isoformat(),
    }

    Path(__file__).parent.joinpath("random_baseline_results.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nSaved to autoresearch/random_baseline_results.json")

    return results


if __name__ == "__main__":
    run_random_baseline(n_simulations=1000)
