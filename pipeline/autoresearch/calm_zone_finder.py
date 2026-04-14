"""Find the optimal CALM ZONE — the no-war no-stress baseline from ETF data."""
import json
import numpy as np
import pandas as pd
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from eodhd_client import fetch_eod_series

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

# Load data
print("Loading ETF universe...")
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
print(f"Data: {len(combined)} days x {len(combined.columns)} assets")

# Load optimal weights
weights = json.loads(Path(__file__).parent.joinpath("etf_optimal_weights.json").read_text())["optimal_weights"]

# Compute composite signal for each day
daily_returns = pd.DataFrame({c: combined[c].pct_change() * 100 for c in feature_cols}).dropna()
composite = pd.Series(0.0, index=daily_returns.index)
for col in feature_cols:
    if col in weights:
        composite += daily_returns[col] * weights[col]

nifty_ret = combined["nifty"].pct_change() * 100

# Period analysis
periods = {
    "Calm 2023 (Apr-Sep)": ("2023-04-01", "2023-09-30"),
    "Gaza Oct 2023": ("2023-10-07", "2023-12-31"),
    "Calm 2024 (Jan-Jun)": ("2024-01-01", "2024-06-30"),
    "Election vol 2024": ("2024-07-01", "2024-11-30"),
    "Calm 2025 (Jan-Jun)": ("2025-01-01", "2025-06-30"),
    "Pre-Iran buildup": ("2025-07-01", "2025-12-31"),
    "Iran War Wk 1-3": ("2026-03-01", "2026-03-21"),
    "Iran War Wk 4-6": ("2026-03-22", "2026-04-06"),
    "Ceasefire": ("2026-04-07", "2026-04-08"),
}

print(f"\n{'='*75}")
print("COMPOSITE SIGNAL BY REGIME PERIOD")
print(f"{'='*75}")
print(f"{'Period':35s} {'Avg Signal':>12s} {'Nifty Avg':>12s} {'Days':>6s} {'Zone':>10s}")
print("-" * 78)

for label, (start, end) in periods.items():
    mask = (composite.index >= start) & (composite.index <= end)
    ps = composite[mask]
    pn = nifty_ret.reindex(ps.index)
    if len(ps) < 3:
        continue
    avg = ps.mean()
    navg = pn.mean()
    zone = "RISK-ON" if avg > 0.3 else "NEUTRAL+" if avg > 0.05 else "NEUTRAL" if avg > -0.05 else "CAUTION" if avg > -0.3 else "RISK-OFF"
    print(f"  {label:33s} {avg:+12.4f} {navg:+11.4f}% {len(ps):>6d} {zone:>10s}")

# THE CALM ZONE
calm_masks = [
    (composite.index >= "2023-04-01") & (composite.index <= "2023-09-30"),
    (composite.index >= "2024-01-01") & (composite.index <= "2024-06-30"),
    (composite.index >= "2025-01-01") & (composite.index <= "2025-06-30"),
]
calm_all = pd.concat([composite[m] for m in calm_masks])

calm_center = calm_all.mean()
calm_band = calm_all.std()

print(f"\n{'='*75}")
print("THE CALM ZONE (NO WAR, NO STRESS) — DATA-DRIVEN BASELINE")
print(f"{'='*75}")
print(f"Calm period days: {len(calm_all)}")
print(f"Calm signal mean: {calm_center:+.4f}")
print(f"Calm signal std:  {calm_band:.4f}")
print(f"Calm range: [{calm_center - calm_band:+.4f}, {calm_center + calm_band:+.4f}]")

print(f"\nZONE THRESHOLDS (from historical calm baseline):")
print(f"  RISK-OFF:  < {calm_center - 2*calm_band:+.4f} (extreme stress)")
print(f"  CAUTION:   {calm_center - 2*calm_band:+.4f} to {calm_center - calm_band:+.4f}")
print(f"  NEUTRAL:   {calm_center - calm_band:+.4f} to {calm_center + calm_band:+.4f} (the calm zone)")
print(f"  RISK-ON:   {calm_center + calm_band:+.4f} to {calm_center + 2*calm_band:+.4f}")
print(f"  EUPHORIA:  > {calm_center + 2*calm_band:+.4f} (extreme greed)")

# Forward validation
print(f"\n{'='*75}")
print("FORWARD VALIDATION — does the zone predict Nifty next-day?")
print(f"{'='*75}")

for zone_label, low, high in [
    ("RISK-OFF", -999, calm_center - 2*calm_band),
    ("CAUTION", calm_center - 2*calm_band, calm_center - calm_band),
    ("NEUTRAL", calm_center - calm_band, calm_center + calm_band),
    ("RISK-ON", calm_center + calm_band, calm_center + 2*calm_band),
    ("EUPHORIA", calm_center + 2*calm_band, 999),
]:
    mask = (composite >= low) & (composite < high)
    zone_nifty = nifty_ret.shift(-1).reindex(composite[mask].index).dropna()
    if len(zone_nifty) < 5:
        continue
    avg_next = zone_nifty.mean()
    win_rate = (zone_nifty > 0).mean() * 100
    print(f"  {zone_label:12s}: {len(zone_nifty):4d} days | Nifty next day: {avg_next:+.3f}% | Up rate: {win_rate:.0f}%")

# TODAY
today_signal = float(composite.iloc[-1])
print(f"\n{'='*75}")
print(f"TODAY'S SIGNAL: {today_signal:+.4f}")
if today_signal < calm_center - 2*calm_band:
    zone = "RISK-OFF"
elif today_signal < calm_center - calm_band:
    zone = "CAUTION"
elif today_signal < calm_center + calm_band:
    zone = "NEUTRAL (calm zone)"
elif today_signal < calm_center + 2*calm_band:
    zone = "RISK-ON"
else:
    zone = "EUPHORIA"
print(f"ZONE: {zone}")
print(f"Distance from calm center: {today_signal - calm_center:+.4f} ({(today_signal - calm_center)/calm_band:.1f} std)")
print(f"{'='*75}")

# Save
results = {
    "calm_center": round(calm_center, 4),
    "calm_band": round(calm_band, 4),
    "zones": {
        "risk_off": round(calm_center - 2*calm_band, 4),
        "caution": round(calm_center - calm_band, 4),
        "neutral_low": round(calm_center - calm_band, 4),
        "neutral_high": round(calm_center + calm_band, 4),
        "risk_on": round(calm_center + calm_band, 4),
        "euphoria": round(calm_center + 2*calm_band, 4),
    },
    "today_signal": round(today_signal, 4),
    "today_zone": zone,
}
Path(__file__).parent.joinpath("calm_zone_analysis.json").write_text(
    json.dumps(results, indent=2), encoding="utf-8")
print("\nSaved to autoresearch/calm_zone_analysis.json")
