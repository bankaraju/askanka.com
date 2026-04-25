"""Quick base-rate sanity check for forensic card v2 insider channel.

Compares the 4σ-event insider rate against a same-universe random null:
1774 random (ticker, date) pairs from the same ticker set and date range.

If the lift = (event_rate / base_rate) is ~1.0, insider activity is null.
"""
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
INS = REPO / "pipeline" / "data" / "insider_trades"
CARD = REPO / "pipeline" / "autoresearch" / "forensics" / "output" / "correlation_break_4sigma_v2.csv"


def main():
    ins = pd.concat([pd.read_parquet(p) for p in sorted(INS.glob("*.parquet"))], ignore_index=True)
    ins["effective_date"] = ins["acq_from_date"].fillna(ins["intimation_date"]).fillna(ins["filing_date"])
    ins["effective_date"] = pd.to_datetime(ins["effective_date"]).dt.normalize()
    ins = ins.dropna(subset=["effective_date", "symbol"])
    print(f"Total insider filings: {len(ins)}")

    card = pd.read_csv(CARD)
    card["date"] = pd.to_datetime(card["date"])
    print(f"Card events: {len(card)}")

    tickers_in_card = card["ticker"].unique()
    bdays = pd.bdate_range(card["date"].min(), card["date"].max())
    print(f"Distinct tickers in card: {len(tickers_in_card)}")
    print(f"Bday universe: {len(bdays)} days {bdays[0].date()} to {bdays[-1].date()}")

    ins_by_sym = {sym: g.sort_values("effective_date") for sym, g in ins.groupby("symbol")}

    def has_window(sym, d, promoter_only=False):
        g = ins_by_sym.get(sym)
        if g is None or g.empty:
            return False
        lo = (d + pd.tseries.offsets.BDay(-3)).normalize()
        hi = (d + pd.tseries.offsets.BDay(1)).normalize()
        win = g[(g["effective_date"] >= lo) & (g["effective_date"] <= hi)]
        if promoter_only:
            return win["person_category"].isin(["Promoters", "Promoter Group"]).any()
        return not win.empty

    np.random.seed(42)
    n = 1774
    random_tickers = np.random.choice(tickers_in_card, n, replace=True)
    random_dates = np.random.choice(bdays, n, replace=True)

    hit_any = sum(has_window(t, pd.Timestamp(d)) for t, d in zip(random_tickers, random_dates))
    hit_prom = sum(has_window(t, pd.Timestamp(d), promoter_only=True) for t, d in zip(random_tickers, random_dates))

    print(f"\nBASE-RATE (random ticker, random date, n={n}):")
    print(f"  any insider in T-3..T+1 : {hit_any/n:.1%}  ({hit_any}/{n})")
    print(f"  any promoter in window  : {hit_prom/n:.1%}  ({hit_prom}/{n})")

    break_any = card["insider_trade_window"].astype(bool).mean()
    break_prom = card["insider_promoter_window"].astype(bool).mean()
    print(f"\n4-SIGMA EVENT RATES (n=1774):")
    print(f"  any insider             : {break_any:.1%}")
    print(f"  any promoter            : {break_prom:.1%}")

    print(f"\nLIFT (event / base):")
    print(f"  any insider             : {break_any / (hit_any/n):.2f}x")
    if hit_prom:
        print(f"  any promoter            : {break_prom / (hit_prom/n):.2f}x")
    else:
        print(f"  any promoter            : base rate 0, lift undefined")


if __name__ == "__main__":
    main()
