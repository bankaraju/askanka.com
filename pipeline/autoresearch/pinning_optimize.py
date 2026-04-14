"""
AutoResearch — Pinning Straddle Parameter Optimization
Tests every combination of: entry time × VIX threshold × pin distance × stop multiplier
across NIFTY, BANKNIFTY, FINNIFTY on last 7 expiry Thursdays.
Finds the champion parameter set by Sharpe ratio.
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

IST = timezone(timedelta(hours=5, minutes=30))


def run_optimization():
    from kite_client import get_kite, resolve_token
    kite = get_kite()

    tokens = {
        "NIFTY": {"token": resolve_token("NIFTY 50"), "step": 50},
        "BANKNIFTY": {"token": resolve_token("NIFTY BANK"), "step": 100},
        "FINNIFTY": {"token": resolve_token("NIFTY FIN SERVICE"), "step": 50},
    }
    vix_token = resolve_token("INDIA VIX")

    # Last 8 Thursdays
    today = datetime.now(IST).date()
    thursdays = []
    d = today
    while len(thursdays) < 8:
        d -= timedelta(days=1)
        if d.weekday() == 3:
            thursdays.append(d)

    # Parameters to test
    entry_times = ["09:20", "10:00", "11:00", "12:00", "13:00", "14:00", "14:30"]
    vix_thresholds = [0, 12, 15, 18, 20, 22, 25]
    stop_multipliers = [1.0, 1.5, 2.0, 2.5, 3.0]
    pin_distance_filters = [999, 1.0, 0.5, 0.3]

    all_experiments = []

    for index_name, cfg in tokens.items():
        if not cfg["token"]:
            continue
        for thurs in thursdays:
            try:
                candles = kite.historical_data(cfg["token"], str(thurs), str(thurs), "5minute")
                if not candles or len(candles) < 50:
                    continue

                df = pd.DataFrame(candles)
                df["time"] = pd.to_datetime(df["date"]).dt.strftime("%H:%M")
                df["close_val"] = df["close"].astype(float)
                close_price = float(df.iloc[-1]["close_val"])

                # VIX
                try:
                    vix_candles = kite.historical_data(vix_token, str(thurs), str(thurs), "5minute")
                    open_vix = float(pd.DataFrame(vix_candles).iloc[0]["open"]) if vix_candles else 20
                except Exception:
                    open_vix = 20

                for entry_time in entry_times:
                    entry_candle = df[df["time"] >= entry_time].head(1)
                    if entry_candle.empty:
                        continue

                    entry_price = float(entry_candle.iloc[0]["close_val"])
                    entry_idx = entry_candle.index[0]
                    step = cfg["step"]
                    pin_strike = round(entry_price / step) * step
                    pin_dist_pct = abs(entry_price - pin_strike) / entry_price * 100

                    hours_left = max(0.1, 15.5 - int(entry_time[:2]) - int(entry_time[3:]) / 60)
                    base_prem_pct = min(2.5, 0.5 * np.sqrt(hours_left) * (open_vix / 15))
                    premium_pts = pin_strike * base_prem_pct / 100

                    remaining = df.iloc[entry_idx:]
                    if len(remaining) < 5:
                        continue

                    distances = (remaining["close_val"] - pin_strike).abs()
                    max_adverse = float(distances.max())
                    final_distance = abs(close_price - pin_strike)

                    for vix_min in vix_thresholds:
                        if open_vix < vix_min:
                            continue

                        for pin_filter in pin_distance_filters:
                            if pin_dist_pct > pin_filter:
                                continue

                            for stop_mult in stop_multipliers:
                                stop_level = premium_pts * stop_mult
                                stop_hit = max_adverse > stop_level

                                if stop_hit:
                                    pnl_pts = premium_pts - stop_level
                                else:
                                    pnl_pts = premium_pts - final_distance

                                pnl_pct = pnl_pts / pin_strike * 100

                                all_experiments.append({
                                    "index": index_name,
                                    "date": str(thurs),
                                    "entry_time": entry_time,
                                    "vix_min": vix_min,
                                    "pin_filter": pin_filter,
                                    "stop_mult": stop_mult,
                                    "open_vix": round(open_vix, 1),
                                    "premium_pct": round(base_prem_pct, 2),
                                    "pnl_pct": round(pnl_pct, 3),
                                    "stop_hit": stop_hit,
                                    "win": pnl_pct > 0,
                                })
            except Exception:
                continue

    print(f"Total experiments: {len(all_experiments)}")

    df_exp = pd.DataFrame(all_experiments)

    # Find best parameters
    combos = df_exp.groupby(["entry_time", "vix_min", "pin_filter", "stop_mult"]).agg(
        n=("win", "count"),
        wins=("win", "sum"),
        avg_pnl=("pnl_pct", "mean"),
        std_pnl=("pnl_pct", "std"),
        max_loss=("pnl_pct", "min"),
        stops=("stop_hit", "sum"),
    ).reset_index()

    combos["win_pct"] = (combos["wins"] / combos["n"] * 100).round(1)
    combos["sharpe"] = (combos["avg_pnl"] / combos["std_pnl"].clip(lower=0.01)).round(3)

    # Minimum 10 trades
    combos = combos[combos["n"] >= 10]

    best = combos.sort_values("sharpe", ascending=False).head(15)

    print(f"\n{'='*90}")
    print("TOP 15 PARAMETER COMBINATIONS (sorted by Sharpe)")
    print(f"{'='*90}")
    print(f"{'Entry':>7s} {'VIX>':>5s} {'Pin<':>5s} {'Stop':>5s} | {'N':>4s} {'Win%':>5s} {'AvgPnL':>7s} {'Sharpe':>7s} {'MaxLoss':>8s} {'Stops':>5s}")
    print("-" * 90)

    for _, row in best.iterrows():
        print(f"{row['entry_time']:>7s} {row['vix_min']:>5.0f} {row['pin_filter']:>5.1f} {row['stop_mult']:>5.1f} | "
              f"{row['n']:>4.0f} {row['win_pct']:>5.1f} {row['avg_pnl']:>+6.3f}% {row['sharpe']:>7.3f} {row['max_loss']:>+7.3f}% {row['stops']:>5.0f}")

    champion = best.iloc[0]
    print(f"\n{'='*50}")
    print(f"CHAMPION PARAMETERS:")
    print(f"{'='*50}")
    print(f"  Entry time:       {champion['entry_time']}")
    print(f"  VIX minimum:      {champion['vix_min']:.0f}")
    print(f"  Pin distance:     <{champion['pin_filter']:.1f}%")
    print(f"  Stop loss:        {champion['stop_mult']:.1f}x premium")
    print(f"  Win rate:         {champion['win_pct']:.0f}% ({champion['wins']:.0f}/{champion['n']:.0f})")
    print(f"  Avg P&L:          {champion['avg_pnl']:+.3f}%")
    print(f"  Sharpe:           {champion['sharpe']:.3f}")
    print(f"  Max single loss:  {champion['max_loss']:+.3f}%")
    print(f"  Stop hits:        {champion['stops']:.0f}")

    # Also find best per index
    print(f"\n{'='*50}")
    print("BEST PER INDEX:")
    print(f"{'='*50}")
    for idx in ["NIFTY", "BANKNIFTY", "FINNIFTY"]:
        idx_exp = df_exp[df_exp["index"] == idx]
        if idx_exp.empty:
            continue
        idx_combos = idx_exp.groupby(["entry_time", "vix_min", "stop_mult"]).agg(
            n=("win", "count"), wins=("win", "sum"), avg_pnl=("pnl_pct", "mean"),
            std_pnl=("pnl_pct", "std"),
        ).reset_index()
        idx_combos["sharpe"] = (idx_combos["avg_pnl"] / idx_combos["std_pnl"].clip(lower=0.01)).round(3)
        idx_combos = idx_combos[idx_combos["n"] >= 3]
        if idx_combos.empty:
            continue
        top = idx_combos.sort_values("sharpe", ascending=False).iloc[0]
        print(f"  {idx}: entry={top['entry_time']} VIX>{top['vix_min']:.0f} stop={top['stop_mult']:.1f}x "
              f"| {top['wins']:.0f}/{top['n']:.0f} wins ({top['wins']/top['n']*100:.0f}%) "
              f"| avg {top['avg_pnl']:+.3f}% | sharpe {top['sharpe']:.3f}")

    # Save
    output = {
        "champion": {k: float(v) if isinstance(v, (np.integer, np.floating)) else v
                     for k, v in champion.to_dict().items()},
        "top_15": [{k: float(v) if isinstance(v, (np.integer, np.floating)) else v
                    for k, v in row.items()} for _, row in best.iterrows()],
        "total_experiments": len(all_experiments),
        "timestamp": datetime.now(IST).isoformat(),
    }
    out_path = Path(__file__).parent / "pinning_optimization_results.json"
    out_path.write_text(json.dumps(output, indent=2, default=str), encoding="utf-8")
    print(f"\nSaved to {out_path}")

    return output


if __name__ == "__main__":
    run_optimization()
