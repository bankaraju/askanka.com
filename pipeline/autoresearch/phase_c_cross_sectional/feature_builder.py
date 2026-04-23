"""Feature matrix construction for H-2026-04-24-003.

Produces the 236-column feature vector per the spec §Feature Set.
No look-ahead: all features are computed from data at or before T close.
The broken stock's own z_peer_<ticker> column is zeroed (self-dropped).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


REGIME_ORDER = ("RISK_OFF", "NEUTRAL", "RISK_ON")


def build_feature_matrix(
    events_df: pd.DataFrame,
    z_panel: pd.DataFrame,
    regime_history: pd.DataFrame,
    vix_series: pd.Series,
    *,
    broad_sector: dict,
) -> tuple[pd.DataFrame, pd.Series, list[str]]:
    """Build (X, y, feature_names) for the events in events_df.

    Parameters
    ----------
    events_df
        Persistent events (output of event_filter.filter_persistent_breaks).
    z_panel
        Wide z-score panel (dates x tickers).
    regime_history
        DataFrame indexed by date with column 'regime' in REGIME_ORDER.
    vix_series
        Series indexed by date with VIX close values.
    broad_sector
        Ticker -> broad sector string. Tickers missing from this map are
        assigned sector 'Unmapped' (does not contribute to sector means).

    Returns
    -------
    X : DataFrame indexed like events_df with 236-column feature matrix.
    y : Series indexed like events_df with next_ret labels (percent).
    feature_names : list[str] column order.
    """
    if events_df.empty:
        raise ValueError("events_df is empty; nothing to build features from")

    ev = events_df.copy()
    ev["date"] = pd.to_datetime(ev["date"])

    all_tickers = sorted(z_panel.columns)
    sectors = sorted(set(broad_sector.values()) - {"Unmapped"})

    peer_cols = [f"z_peer_{t}" for t in all_tickers]
    sector_cols = [f"sector_mean_{s}" for s in sectors]
    regime_cols = [f"regime_{r}" for r in REGIME_ORDER]
    feature_names = (
        peer_cols + sector_cols + ["vix_close"] + regime_cols
        + ["z_self_T", "z_self_T_minus_1", "break_direction"]
    )

    rows = []
    y_values = []
    idx = []
    for row in ev.itertuples(index=True):
        t = pd.Timestamp(row.date)
        tkr = row.ticker
        # --- peer z's ---
        if t not in z_panel.index:
            raise KeyError(f"z_panel missing date {t.date()} for event {tkr}")
        peer_z = z_panel.loc[t].reindex(all_tickers).fillna(0.0).astype(float)
        peer_z.loc[tkr] = 0.0  # self-drop
        # --- sector means (exclude self ticker from its sector's mean) ---
        sec_vals = {}
        for sec in sectors:
            tickers_in_sec = [tt for tt, s in broad_sector.items() if s == sec and tt != tkr]
            if len(tickers_in_sec) < 3:
                sec_vals[sec] = 0.0  # noisy-denominator safeguard per spec
            else:
                sec_z = z_panel.loc[t].reindex(tickers_in_sec).dropna()
                sec_vals[sec] = float(sec_z.mean()) if len(sec_z) >= 3 else 0.0
        # --- market context ---
        vix = float(vix_series.loc[t]) if t in vix_series.index else 0.0
        regime = (
            regime_history.loc[t, "regime"]
            if t in regime_history.index else "NEUTRAL"
        )
        regime_one_hot = {f"regime_{r}": int(r == regime) for r in REGIME_ORDER}
        # --- self z's ---
        z_self_T = float(row.z)
        col_before = z_panel[tkr].loc[z_panel.index < t].dropna()
        z_self_Tm1 = float(col_before.iloc[-1]) if len(col_before) else 0.0
        # --- break direction ---
        direction = 1 if z_self_T > 0 else -1

        feature_row = {}
        for ticker, val in peer_z.items():
            feature_row[f"z_peer_{ticker}"] = val
        for sec, val in sec_vals.items():
            feature_row[f"sector_mean_{sec}"] = val
        feature_row["vix_close"] = vix
        feature_row.update(regime_one_hot)
        feature_row["z_self_T"] = z_self_T
        feature_row["z_self_T_minus_1"] = z_self_Tm1
        feature_row["break_direction"] = direction

        rows.append(feature_row)
        y_values.append(float(row.next_ret))
        idx.append(row.Index)

    X = pd.DataFrame(rows, index=idx, columns=feature_names).astype(float)
    y = pd.Series(y_values, index=idx, name="next_ret_pct")
    return X, y, feature_names
