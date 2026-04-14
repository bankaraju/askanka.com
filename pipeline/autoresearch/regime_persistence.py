"""
AutoResearch — Regime Persistence & Break Detection
Answers: how long do regimes last? What lookback is optimal?
When does calm break? How fast does India react?

Not 1-day signals. SUSTAINED regime states.
"""

import json
import sys
import numpy as np
import pandas as pd
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from eodhd_client import fetch_eod_series


def load_composite():
    """Load ETF data and compute composite signal."""
    etfs = {
        "ITA.US": "defence", "XLE.US": "energy", "XLF.US": "financials",
        "XLK.US": "tech", "XLV.US": "healthcare", "XLP.US": "staples",
        "XLI.US": "industrials", "EEM.US": "em", "EWZ.US": "brazil",
        "INDA.US": "india_etf", "FXI.US": "china", "EWJ.US": "japan",
        "EFA.US": "developed", "USO.US": "oil", "UNG.US": "natgas",
        "SLV.US": "silver", "DBA.US": "agriculture", "HYG.US": "high_yield",
        "LQD.US": "ig_bond", "TLT.US": "treasury", "IEF.US": "mid_treasury",
        "UUP.US": "dollar", "FXE.US": "euro", "FXY.US": "yen",
        "SPY.US": "sp500", "GLD.US": "gold", "VIX.INDX": "vix",
        "KBE.US": "kbw_bank", "KRE.US": "regional_bank",
        "JETS.US": "airlines", "ARKK.US": "innovation",
        "NSEI.INDX": "nifty",
    }

    all_data = {}
    for sym, name in etfs.items():
        try:
            data = fetch_eod_series(sym, days=1095)
            if data and len(data) > 200:
                df = pd.DataFrame(data)
                df["date"] = pd.to_datetime(df["date"])
                df = df.set_index("date").sort_index()
                col = "adjusted_close" if "adjusted_close" in df.columns else "close"
                all_data[name] = df[col].astype(float)
        except Exception:
            pass

    combined = pd.DataFrame(all_data).dropna()
    feature_cols = [c for c in combined.columns if c != "nifty"]

    weights = json.loads(Path(__file__).parent.joinpath("etf_optimal_weights.json").read_text())["optimal_weights"]

    daily_returns = pd.DataFrame({c: combined[c].pct_change() * 100 for c in feature_cols}).dropna()
    composite = pd.Series(0.0, index=daily_returns.index)
    for col in feature_cols:
        if col in weights:
            composite += daily_returns[col] * weights[col]

    nifty_ret = combined["nifty"].pct_change() * 100
    return composite, nifty_ret, combined


def run_analysis():
    print("=" * 70)
    print("REGIME PERSISTENCE & BREAK DETECTION")
    print("How long do regimes last? What lookback is optimal?")
    print("=" * 70)

    composite, nifty_ret, raw = load_composite()
    print(f"Data: {len(composite)} days")

    # ═══ EXPERIMENT 1: Optimal rolling lookback ═══
    print(f"\n{'='*70}")
    print("EXPERIMENT 1: What lookback window best predicts Nifty?")
    print("Testing: 1, 3, 5, 7, 10, 15, 21 day rolling averages")
    print(f"{'='*70}")

    best_lookback = 1
    best_accuracy = 0

    for lookback in [1, 2, 3, 5, 7, 10, 15, 21, 30]:
        rolling_signal = composite.rolling(lookback).mean()
        pred = (rolling_signal > 0).astype(int)
        actual = (nifty_ret.shift(-1) > 0).astype(int)

        common = pred.dropna().index.intersection(actual.dropna().index)
        if len(common) < 50:
            continue

        acc = (pred.loc[common] == actual.loc[common]).mean() * 100

        # Also compute Sharpe of following the signal
        returns = nifty_ret.shift(-1).loc[common]
        long_ret = returns[rolling_signal.loc[common] > 0]
        short_ret = -returns[rolling_signal.loc[common] < 0]
        all_ret = pd.concat([long_ret, short_ret])
        sharpe = all_ret.mean() / max(all_ret.std(), 0.01) * np.sqrt(252) if len(all_ret) > 10 else 0

        marker = " *** BEST ***" if acc > best_accuracy else ""
        if acc > best_accuracy:
            best_accuracy = acc
            best_lookback = lookback
        print(f"  {lookback:2d}-day: acc {acc:.1f}% | Sharpe {sharpe:.2f}{marker}")

    print(f"\nOptimal lookback: {best_lookback} days ({best_accuracy:.1f}% accuracy)")

    # ═══ EXPERIMENT 2: Regime duration — how long does each zone last? ═══
    print(f"\n{'='*70}")
    print("EXPERIMENT 2: How long do regimes persist?")
    print(f"{'='*70}")

    # Use optimal lookback for regime classification
    smooth = composite.rolling(best_lookback).mean().dropna()
    calm_center = 0.0953  # From calm_zone_analysis
    calm_band = 3.8974

    zones = pd.Series("NEUTRAL", index=smooth.index)
    zones[smooth < calm_center - 2 * calm_band] = "RISK-OFF"
    zones[(smooth >= calm_center - 2 * calm_band) & (smooth < calm_center - calm_band)] = "CAUTION"
    zones[(smooth >= calm_center + calm_band) & (smooth < calm_center + 2 * calm_band)] = "RISK-ON"
    zones[smooth >= calm_center + 2 * calm_band] = "EUPHORIA"

    # Compute streak lengths
    streaks = []
    current_zone = zones.iloc[0]
    current_start = zones.index[0]
    current_len = 1

    for i in range(1, len(zones)):
        if zones.iloc[i] == current_zone:
            current_len += 1
        else:
            streaks.append({
                "zone": current_zone,
                "start": str(current_start.date()),
                "end": str(zones.index[i - 1].date()),
                "days": current_len,
            })
            current_zone = zones.iloc[i]
            current_start = zones.index[i]
            current_len = 1

    streaks.append({"zone": current_zone, "start": str(current_start.date()),
                    "end": str(zones.index[-1].date()), "days": current_len})

    # Statistics per zone
    for z in ["RISK-OFF", "CAUTION", "NEUTRAL", "RISK-ON", "EUPHORIA"]:
        z_streaks = [s for s in streaks if s["zone"] == z]
        if not z_streaks:
            continue
        durations = [s["days"] for s in z_streaks]
        total_days = sum(durations)
        print(f"\n  {z}:")
        print(f"    Occurrences: {len(z_streaks)}")
        print(f"    Total days: {total_days} ({total_days/len(zones)*100:.0f}% of time)")
        print(f"    Avg duration: {np.mean(durations):.0f} days")
        print(f"    Shortest: {min(durations)} days | Longest: {max(durations)} days")
        if len(z_streaks) <= 10:
            for s in z_streaks:
                print(f"      {s['start']} to {s['end']} ({s['days']} days)")

    # ═══ EXPERIMENT 3: Calm break detection — what precedes a break? ═══
    print(f"\n{'='*70}")
    print("EXPERIMENT 3: What happens BEFORE calm breaks?")
    print(f"{'='*70}")

    # Find transitions from NEUTRAL to CAUTION or RISK-OFF
    breaks = []
    for i in range(1, len(zones)):
        if zones.iloc[i - 1] == "NEUTRAL" and zones.iloc[i] in ("CAUTION", "RISK-OFF"):
            break_date = zones.index[i]

            # Look at signal 5 days before break
            lookback_idx = max(0, i - 5)
            pre_break_signal = smooth.iloc[lookback_idx:i]
            pre_break_slope = (pre_break_signal.iloc[-1] - pre_break_signal.iloc[0]) / len(pre_break_signal)

            # Nifty performance in 5 days after break
            fwd_idx = min(len(nifty_ret) - 1, i + 5)
            post_break_nifty = nifty_ret.iloc[i:fwd_idx + 1].sum()

            breaks.append({
                "date": str(break_date.date()),
                "to_zone": zones.iloc[i],
                "signal_at_break": round(float(smooth.iloc[i]), 2),
                "pre_break_slope": round(float(pre_break_slope), 4),
                "nifty_5d_after": round(float(post_break_nifty), 2),
            })

    print(f"  Total calm→stress breaks: {len(breaks)}")
    for b in breaks:
        emoji = "🔴" if b["nifty_5d_after"] < -1 else "🟡" if b["nifty_5d_after"] < 0 else "🟢"
        print(f"    {emoji} {b['date']} → {b['to_zone']} | signal: {b['signal_at_break']:+.2f} | slope: {b['pre_break_slope']:+.4f} | Nifty 5d: {b['nifty_5d_after']:+.2f}%")

    if breaks:
        avg_nifty_after = np.mean([b["nifty_5d_after"] for b in breaks])
        avg_slope = np.mean([b["pre_break_slope"] for b in breaks])
        print(f"\n  Average Nifty 5d after calm break: {avg_nifty_after:+.2f}%")
        print(f"  Average pre-break slope: {avg_slope:+.4f}")
        print(f"  Early warning: slope < {avg_slope:.4f} suggests calm is about to break")

    # ═══ EXPERIMENT 4: India lag — how fast does India follow global signal? ═══
    print(f"\n{'='*70}")
    print("EXPERIMENT 4: India's lag behind global signal")
    print(f"{'='*70}")

    for lag in [0, 1, 2, 3, 5]:
        lagged_signal = smooth.shift(lag)
        pred = (lagged_signal > 0).astype(int)
        actual = (nifty_ret > 0).astype(int)
        common = pred.dropna().index.intersection(actual.dropna().index)
        if len(common) < 50:
            continue
        acc = (pred.loc[common] == actual.loc[common]).mean() * 100
        print(f"  Lag {lag} days: accuracy {acc:.1f}% ({'best' if lag == 0 else ''})")

    # ═══ TODAY's regime assessment ═══
    today_smooth = float(smooth.iloc[-1])
    today_zone = str(zones.iloc[-1])
    days_in_zone = 1
    for i in range(len(zones) - 2, -1, -1):
        if zones.iloc[i] == today_zone:
            days_in_zone += 1
        else:
            break

    print(f"\n{'='*70}")
    print("TODAY'S REGIME ASSESSMENT")
    print(f"{'='*70}")
    print(f"  Signal ({best_lookback}d avg): {today_smooth:+.4f}")
    print(f"  Zone: {today_zone}")
    print(f"  Days in current zone: {days_in_zone}")
    print(f"  Optimal lookback: {best_lookback} days")
    print(f"  Regime is {'ESTABLISHED' if days_in_zone >= 3 else 'NEW — wait for confirmation'}")

    # Save
    results = {
        "optimal_lookback": best_lookback,
        "optimal_accuracy": round(best_accuracy, 1),
        "today_signal_smoothed": round(today_smooth, 4),
        "today_zone": today_zone,
        "days_in_zone": days_in_zone,
        "calm_breaks": breaks,
        "zone_streaks_summary": {z: {"count": len([s for s in streaks if s["zone"] == z]),
                                     "avg_days": round(np.mean([s["days"] for s in streaks if s["zone"] == z]), 0) if [s for s in streaks if s["zone"] == z] else 0}
                                 for z in ["RISK-OFF", "CAUTION", "NEUTRAL", "RISK-ON", "EUPHORIA"]},
    }
    Path(__file__).parent.joinpath("regime_persistence_results.json").write_text(
        json.dumps(results, indent=2, default=str), encoding="utf-8")
    print("\nSaved to autoresearch/regime_persistence_results.json")


if __name__ == "__main__":
    run_analysis()
