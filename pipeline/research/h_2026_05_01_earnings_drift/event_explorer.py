"""H-2026-05-01-EARNINGS-DRIFT v1 — descriptive event-driven explorer.

Universe: NIFTY Bank + NIFTY IT (per SectorMapper Banks + IT_Services).
Window: 2021-05-01 -> 2024-04-30 (entry / event dates). Holdout 2024-05+ reserved.
Cost: locked 15-20 bps round-trip per reference_cost_regime_overlay.md.

For each quarterly earnings event:
  - Compute 15 pre-event factors (volume/momentum/peer/macro/regime/trust/structural)
  - Compute post-event close-to-close return at H in {1,3,5,10,21}
  - Compute synthetic option overlay payoffs via pipeline.options_pricer
    for {long ATM call, long ATM put, long ATM straddle, stock futures}
    at the same horizons
  - Stratify by direction proxy (event-day excess return positive/negative)

Outputs:
  - event_factors.csv  (one row per event, all factors + 5x return horizons)
  - options_ledger.csv (one row per event x structure x horizon)
  - cohort_summary.json (cohort breakdowns at locked cost)

Data sources (all confirmed available 2026-05-01):
  - pipeline/data/earnings_calendar/history.parquet (55,953 events 2002+)
  - pipeline/data/fno_historical/{TICKER}.csv (daily OHLCV 5y)
  - pipeline/data/fno_historical/INDIAVIX.csv (India VIX daily)
  - EODHD eod /INR.FOREX (USD/INR daily)
  - EODHD eod /IN10Y.GBOND (India 10Y yield daily)
  - pipeline/data/research/etf_v3/regime_tape_5y_pit.csv (PIT regime)
  - pipeline/scorecard_v2.sector_mapper.SectorMapper (sector mapping)
  - opus/artifacts/{TICKER}/trust_score.json (today's snapshot, PIT caveat)
  - pipeline/options_pricer (BS pricer for synthetic option overlay)

Notes / caveats acknowledged in v1:
  - FII/DII flow data is forward-only since 2026-04-16 -> NOT included in 5y backtest
  - Beat/miss labels not in EODHD plan -> proxy via event-day excess return
  - News sentiment asymmetric (IT yes, Banks no) -> deferred to v1.5
  - OI/PCR history forward-only -> deferred to v2 with infra backfill
  - Trust score is today snapshot, not PIT -> HARKing risk acknowledged
"""
from __future__ import annotations

import json
import math
import os
import statistics
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests

REPO = Path(__file__).resolve().parent.parent.parent.parent
HERE = Path(__file__).resolve().parent
FNO_DIR = REPO / "pipeline" / "data" / "fno_historical"
EARN_PARQUET = REPO / "pipeline" / "data" / "earnings_calendar" / "history.parquet"
REGIME_TAPE = REPO / "pipeline" / "data" / "research" / "etf_v3" / "regime_tape_5y_pit.csv"
TRUST_DIR = REPO / "opus" / "artifacts"
ENV_FILE = REPO / "pipeline" / ".env"
EODHD_API = "https://eodhd.com/api"
EODHD_CACHE = HERE / "_eodhd_cache"

OUT_FACTORS_CSV = HERE / "event_factors.csv"
OUT_OPTIONS_CSV = HERE / "options_ledger.csv"
OUT_SUMMARY_JSON = HERE / "cohort_summary.json"

WINDOW_START = "2021-05-01"
WINDOW_END = "2024-04-30"
HOLD_HORIZONS = (1, 3, 5, 10, 21)
COST_BPS_LEVELS = (15.0, 20.0, 30.0)
SPEC_THRESHOLD_NET_BPS = 25.0
PRE_EVENT_LOOKBACK = 5
MOMENTUM_MED = 21
MOMENTUM_LONG = 126
VOL_LOOKBACK = 21
VOLUME_BASELINE = 60
DEFAULT_RFR = 0.07  # India 10Y avg, fallback if EODHD fetch fails
DEFAULT_DTE = 22  # days to monthly expiry (rough monthly), used by synthetic option pricer


def _eodhd_key() -> str | None:
    k = os.environ.get("EODHD_API_KEY")
    if k:
        return k
    if ENV_FILE.is_file():
        for ln in ENV_FILE.read_text(encoding="utf-8", errors="ignore").splitlines():
            if ln.strip().startswith("EODHD_API_KEY="):
                return ln.split("=", 1)[1].strip()
    return None


def _eodhd_eod_cached(symbol: str) -> pd.DataFrame:
    EODHD_CACHE.mkdir(exist_ok=True)
    cache = EODHD_CACHE / f"eod_{symbol.replace('.', '_')}.csv"
    if cache.exists():
        df = pd.read_csv(cache, parse_dates=["date"])
        return df.set_index("date")
    key = _eodhd_key()
    if not key:
        return pd.DataFrame()
    r = requests.get(f"{EODHD_API}/eod/{symbol}", params={
        "api_token": key, "fmt": "json",
        "from": "2021-01-01", "to": "2024-12-31",
    }, timeout=60)
    if r.status_code != 200:
        return pd.DataFrame()
    rows = r.json()
    if not isinstance(rows, list) or not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    df = df[["date", "close"]].rename(columns={"close": symbol}).set_index("date")
    df.to_csv(cache)
    return df


def _load_closes() -> pd.DataFrame:
    series = []
    for f in FNO_DIR.glob("*.csv"):
        sym = f.stem.upper()
        try:
            df = pd.read_csv(f)
        except Exception:
            continue
        if "Date" not in df.columns or "Close" not in df.columns:
            continue
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        df = df.dropna(subset=["Date", "Close"]).sort_values("Date")
        if df.empty:
            continue
        series.append(df.set_index("Date")["Close"].rename(sym))
    closes = pd.concat(series, axis=1).sort_index()
    closes = closes[~closes.index.duplicated(keep="first")]
    return closes


def _load_volumes() -> pd.DataFrame:
    series = []
    for f in FNO_DIR.glob("*.csv"):
        sym = f.stem.upper()
        try:
            df = pd.read_csv(f)
        except Exception:
            continue
        if "Date" not in df.columns or "Volume" not in df.columns:
            continue
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        df = df.dropna(subset=["Date", "Volume"]).sort_values("Date")
        if df.empty:
            continue
        series.append(df.set_index("Date")["Volume"].rename(sym))
    vol = pd.concat(series, axis=1).sort_index()
    vol = vol[~vol.index.duplicated(keep="first")]
    return vol


def _load_regime_tape() -> pd.Series:
    df = pd.read_csv(REGIME_TAPE)
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date")["regime"]


def _load_sector_map(symbols: list[str]) -> tuple[dict, dict]:
    from pipeline.scorecard_v2.sector_mapper import SectorMapper
    full_map = SectorMapper().map_all()
    sym_to_sector: dict[str, str] = {}
    by_sector: dict[str, list[str]] = {}
    for sym in symbols:
        info = full_map.get(sym) or full_map.get(sym.upper())
        if not info:
            continue
        sec = info.get("sector")
        if not sec:
            continue
        sym_to_sector[sym] = sec
        by_sector.setdefault(sec, []).append(sym)
    return sym_to_sector, by_sector


def _load_trust_scores() -> dict[str, float]:
    """Today's snapshot only — PIT caveat. Returns ticker -> trust_score_pct."""
    out = {}
    if not TRUST_DIR.is_dir():
        return out
    for tk_dir in TRUST_DIR.iterdir():
        if not tk_dir.is_dir():
            continue
        ts = tk_dir / "trust_score.json"
        if not ts.is_file():
            continue
        try:
            j = json.loads(ts.read_text(encoding="utf-8"))
            score = j.get("trust_score_pct")
            if score is not None:
                out[tk_dir.name.upper()] = float(score)
        except Exception:
            continue
    return out


def _load_earnings(universe: list[str]) -> pd.DataFrame:
    df = pd.read_parquet(EARN_PARQUET)
    df["event_date"] = pd.to_datetime(df["event_date"])
    df = df[(df["event_date"] >= WINDOW_START) & (df["event_date"] <= WINDOW_END)]
    df = df[df["symbol"].str.upper().isin([u.upper() for u in universe])]
    df = df.drop_duplicates(subset=["symbol", "event_date"])
    return df.sort_values(["symbol", "event_date"]).reset_index(drop=True)


def _trust_tier(pct: float | None) -> str:
    if pct is None or pd.isna(pct):
        return "UNKNOWN"
    if pct >= 60:
        return "HIGH"
    if pct >= 40:
        return "MEDIUM"
    return "LOW"


def _liquidity_decile(adv_value: float, sector_advs: list[float]) -> int:
    if not sector_advs:
        return 5
    sorted_advs = sorted(sector_advs)
    rank = sum(1 for v in sorted_advs if v <= adv_value)
    return max(1, min(10, int(round(10 * rank / len(sorted_advs)))))


def _days_to_monthly_expiry(d: pd.Timestamp) -> int:
    """Indian F&O monthly expiry = last Thursday of month. Days until next."""
    year, month = d.year, d.month
    last_day = (pd.Timestamp(year=year, month=month, day=1) + pd.offsets.MonthEnd(0))
    last_thu = last_day - pd.Timedelta(days=(last_day.weekday() - 3) % 7)
    if d <= last_thu:
        return (last_thu - d).days
    next_month = d + pd.offsets.MonthBegin(1)
    last_day_next = next_month + pd.offsets.MonthEnd(0)
    last_thu_next = last_day_next - pd.Timedelta(days=(last_day_next.weekday() - 3) % 7)
    return (last_thu_next - d).days


def _compute_event_factors(
    event_row: dict,
    closes: pd.DataFrame,
    volumes: pd.DataFrame,
    vix: pd.Series,
    usd_inr: pd.Series,
    in10y: pd.Series,
    regime: pd.Series,
    sector_constituents: list[str],
    trust_scores: dict,
    sector_advs: dict,
) -> dict | None:
    sym = event_row["symbol"].upper()
    event_dt = event_row["event_date"]
    if sym not in closes.columns:
        return None
    sym_closes = closes[sym].dropna()
    if event_dt not in sym_closes.index:
        # nearest trading day on or after event_dt
        candidates = sym_closes.index[sym_closes.index >= event_dt]
        if candidates.empty:
            return None
        event_dt = candidates[0]
    idx = sym_closes.index.get_loc(event_dt)
    if idx < max(MOMENTUM_LONG, VOLUME_BASELINE) + PRE_EVENT_LOOKBACK:
        return None  # not enough lookback

    t_minus_1 = sym_closes.index[idx - 1] if idx > 0 else event_dt
    t_minus_5 = sym_closes.index[idx - PRE_EVENT_LOOKBACK]
    t_minus_21 = sym_closes.index[idx - MOMENTUM_MED]
    t_minus_126 = sym_closes.index[idx - MOMENTUM_LONG]

    # --- price factors ---
    price_t1 = float(sym_closes.iloc[idx - 1])
    price_t5 = float(sym_closes.iloc[idx - PRE_EVENT_LOOKBACK])
    price_t21 = float(sym_closes.iloc[idx - MOMENTUM_MED])
    price_t126 = float(sym_closes.iloc[idx - MOMENTUM_LONG])
    short_mom = (price_t1 / price_t5 - 1) * 10000
    med_mom = (price_t1 / price_t21 - 1) * 10000
    long_mom = (price_t1 / price_t126 - 1) * 10000

    # realized vol 21d on log returns
    log_rets = np.log(sym_closes.iloc[idx - VOL_LOOKBACK : idx] / sym_closes.iloc[idx - VOL_LOOKBACK - 1 : idx - 1].values)
    realized_vol_21d_pct = float(log_rets.std() * math.sqrt(252) * 100)

    # --- volume factors ---
    if sym not in volumes.columns:
        vol_z = float("nan")
    else:
        vol_series = volumes[sym].dropna()
        if event_dt not in vol_series.index:
            cands = vol_series.index[vol_series.index >= event_dt]
            if cands.empty:
                return None
            ev2 = cands[0]
            v_idx = vol_series.index.get_loc(ev2)
        else:
            v_idx = vol_series.index.get_loc(event_dt)
        if v_idx < VOLUME_BASELINE + PRE_EVENT_LOOKBACK:
            return None
        baseline = vol_series.iloc[v_idx - VOLUME_BASELINE - PRE_EVENT_LOOKBACK : v_idx - PRE_EVENT_LOOKBACK]
        recent = vol_series.iloc[v_idx - PRE_EVENT_LOOKBACK : v_idx]
        b_mean = baseline.mean()
        b_std = baseline.std()
        recent_mean = recent.mean()
        vol_z = float((recent_mean - b_mean) / b_std) if b_std > 0 else 0.0

    # --- peer / sector factors ---
    peer_syms = [p for p in sector_constituents if p != sym and p in closes.columns]
    peer_drift_bps = float("nan")
    sector_drift_bps = float("nan")
    peer_dispersion_bps = float("nan")
    if peer_syms:
        peer_rets = []
        for p in peer_syms:
            ps = closes[p].dropna()
            if event_dt not in ps.index:
                continue
            p_idx = ps.index.get_loc(event_dt)
            if p_idx < PRE_EVENT_LOOKBACK:
                continue
            r = (ps.iloc[p_idx - 1] / ps.iloc[p_idx - PRE_EVENT_LOOKBACK] - 1) * 10000
            peer_rets.append(float(r))
        if peer_rets:
            peer_drift_bps = float(np.mean(peer_rets))
            sector_drift_bps = peer_drift_bps  # equal-weight sector ≈ mean of peers
            if len(peer_rets) > 1:
                peer_dispersion_bps = float(np.std(peer_rets, ddof=0))

    # --- vol regime: India VIX ---
    vix_t1 = float("nan")
    if not vix.empty:
        vix_idx = vix.index[vix.index <= t_minus_1]
        if not vix_idx.empty:
            vix_t1 = float(vix.loc[vix_idx[-1]])

    # --- macro: USD/INR + India 10Y ---
    usdinr_change_bps = float("nan")
    in10y_change_bps = float("nan")
    if not usd_inr.empty:
        usd_avail_idx = usd_inr.index[usd_inr.index <= t_minus_1]
        usd_lookback_idx = usd_inr.index[usd_inr.index <= t_minus_5]
        if len(usd_avail_idx) > 0 and len(usd_lookback_idx) > 0:
            t1_v = float(usd_inr.loc[usd_avail_idx[-1]])
            t5_v = float(usd_inr.loc[usd_lookback_idx[-1]])
            if t5_v > 0:
                usdinr_change_bps = (t1_v / t5_v - 1) * 10000
    if not in10y.empty:
        y_avail_idx = in10y.index[in10y.index <= t_minus_1]
        y_lookback_idx = in10y.index[in10y.index <= t_minus_5]
        if len(y_avail_idx) > 0 and len(y_lookback_idx) > 0:
            t1_v = float(in10y.loc[y_avail_idx[-1]])
            t5_v = float(in10y.loc[y_lookback_idx[-1]])
            in10y_change_bps = (t1_v - t5_v) * 100  # yields in pct, change in bps

    # --- regime ---
    reg_idx = regime.index[regime.index <= t_minus_1]
    regime_label = str(regime.loc[reg_idx[-1]]) if not reg_idx.empty else "UNKNOWN"

    # --- trust + structural ---
    trust_pct = trust_scores.get(sym)
    trust_tier = _trust_tier(trust_pct)
    sector_adv_list = sector_advs.get("__all__", [])
    sym_adv = sector_advs.get(sym, 0.0)
    liq_decile = _liquidity_decile(sym_adv, sector_adv_list)
    dte = _days_to_monthly_expiry(event_dt)
    quarter = ((event_dt.month - 1) // 3) + 1

    # --- post-event returns ---
    post_returns = {}
    for h in HOLD_HORIZONS:
        if idx + h >= len(sym_closes):
            post_returns[h] = float("nan")
            continue
        # entry T-1 close, exit T+h close (treats event_dt = T as the announcement day)
        # so h=1 means hold from T-1 to T (1 day), h=21 = T-1 to T+20 (21 trading days)
        entry_p = price_t1
        exit_p = float(sym_closes.iloc[idx + h - 1])
        if entry_p > 0:
            post_returns[h] = (exit_p / entry_p - 1) * 10000
        else:
            post_returns[h] = float("nan")

    # event-day excess return = stock T+1 vs T-1 minus sector avg same period
    if idx + 1 < len(sym_closes):
        stock_event_ret = (float(sym_closes.iloc[idx]) / price_t1 - 1) * 10000
    else:
        stock_event_ret = float("nan")
    sector_event_ret = float("nan")
    if peer_syms:
        peer_event_rets = []
        for p in peer_syms:
            ps = closes[p].dropna()
            if event_dt not in ps.index:
                continue
            p_idx = ps.index.get_loc(event_dt)
            if p_idx < 1:
                continue
            r = (float(ps.iloc[p_idx]) / float(ps.iloc[p_idx - 1]) - 1) * 10000
            peer_event_rets.append(r)
        if peer_event_rets:
            sector_event_ret = float(np.mean(peer_event_rets))
    excess_event_ret = (stock_event_ret - sector_event_ret) if (not np.isnan(stock_event_ret) and not np.isnan(sector_event_ret)) else float("nan")
    direction_proxy = "BEAT_LIKE" if (not np.isnan(excess_event_ret) and excess_event_ret > 0) else (
        "MISS_LIKE" if (not np.isnan(excess_event_ret) and excess_event_ret < 0) else "UNKNOWN"
    )

    out = dict(
        symbol=sym,
        event_date=event_dt.strftime("%Y-%m-%d"),
        sector=event_row.get("__sector"),
        # pre-event flow
        volume_z=round(vol_z, 4),
        short_mom_bps=round(short_mom, 2),
        med_mom_bps=round(med_mom, 2),
        long_mom_bps=round(long_mom, 2),
        # peer/sector
        peer_drift_bps=round(peer_drift_bps, 2) if not np.isnan(peer_drift_bps) else None,
        sector_drift_bps=round(sector_drift_bps, 2) if not np.isnan(sector_drift_bps) else None,
        peer_dispersion_bps=round(peer_dispersion_bps, 2) if not np.isnan(peer_dispersion_bps) else None,
        # vol regime
        realized_vol_21d_pct=round(realized_vol_21d_pct, 4),
        vix_t1=round(vix_t1, 2) if not np.isnan(vix_t1) else None,
        # macro
        usdinr_change_5d_bps=round(usdinr_change_bps, 2) if not np.isnan(usdinr_change_bps) else None,
        in10y_change_5d_bps=round(in10y_change_bps, 2) if not np.isnan(in10y_change_bps) else None,
        # fundamental
        trust_score_pct=trust_pct,
        trust_tier=trust_tier,
        # structural
        liq_decile=liq_decile,
        dte_monthly_exp=dte,
        quarter=quarter,
        # outcome proxies
        stock_event_ret_bps=round(stock_event_ret, 2) if not np.isnan(stock_event_ret) else None,
        sector_event_ret_bps=round(sector_event_ret, 2) if not np.isnan(sector_event_ret) else None,
        excess_event_ret_bps=round(excess_event_ret, 2) if not np.isnan(excess_event_ret) else None,
        direction_proxy=direction_proxy,
        # regime
        regime=regime_label,
        # post-event holds
        **{f"ret_h{h}_bps": round(post_returns[h], 2) if not np.isnan(post_returns[h]) else None
           for h in HOLD_HORIZONS},
        # internal
        _entry_price=price_t1,
        _realized_vol=realized_vol_21d_pct / 100,
    )
    return out


def _option_premium(S: float, K: float, sigma: float, T: float, r: float, kind: str) -> float:
    from pipeline.options_pricer import bs_call_price, bs_put_price
    if kind == "C":
        return bs_call_price(S, K, T, sigma, r)
    return bs_put_price(S, K, T, sigma, r)


def _option_overlay(event: dict, closes: pd.DataFrame) -> list[dict]:
    sym = event["symbol"]
    if sym not in closes.columns:
        return []
    S = event["_entry_price"]
    sigma = max(0.05, event["_realized_vol"])  # floor at 5% vol
    K = S  # ATM
    T_to_expiry = max(DEFAULT_DTE / 252, 1 / 252)
    r = DEFAULT_RFR
    call_premium = _option_premium(S, K, sigma, T_to_expiry, r, "C")
    put_premium = _option_premium(S, K, sigma, T_to_expiry, r, "P")
    straddle_premium = call_premium + put_premium

    sym_closes = closes[sym].dropna()
    event_dt = pd.to_datetime(event["event_date"])
    candidates = sym_closes.index[sym_closes.index >= event_dt]
    if candidates.empty:
        return []
    event_idx = sym_closes.index.get_loc(candidates[0])

    rows = []
    for h in HOLD_HORIZONS:
        if event_idx + h - 1 >= len(sym_closes):
            continue
        exit_S = float(sym_closes.iloc[event_idx + h - 1])
        # compute remaining time-to-expiry at exit
        exit_T = max((DEFAULT_DTE - h) / 252, 1 / 252)
        if exit_T <= 1 / 252:
            # close to expiry, intrinsic
            exit_call = max(exit_S - K, 0.0)
            exit_put = max(K - exit_S, 0.0)
        else:
            exit_call = _option_premium(exit_S, K, sigma, exit_T, r, "C")
            exit_put = _option_premium(exit_S, K, sigma, exit_T, r, "P")
        exit_straddle = exit_call + exit_put
        # P&L per unit
        pnl_futures_bps = (exit_S / S - 1) * 10000
        pnl_call_bps = ((exit_call - call_premium) / call_premium * 10000) if call_premium > 0 else 0.0
        pnl_put_bps = ((exit_put - put_premium) / put_premium * 10000) if put_premium > 0 else 0.0
        pnl_straddle_bps = ((exit_straddle - straddle_premium) / straddle_premium * 10000) if straddle_premium > 0 else 0.0
        # capital efficiency: option premium as % of underlying notional
        call_premium_pct_notional = call_premium / S * 100
        put_premium_pct_notional = put_premium / S * 100
        rows.append(dict(
            symbol=sym, event_date=event["event_date"], horizon=h, regime=event["regime"],
            direction_proxy=event["direction_proxy"], trust_tier=event["trust_tier"],
            entry_S=round(S, 2), exit_S=round(exit_S, 2),
            call_entry_premium=round(call_premium, 2), call_exit=round(exit_call, 2),
            put_entry_premium=round(put_premium, 2), put_exit=round(exit_put, 2),
            straddle_entry_premium=round(straddle_premium, 2), straddle_exit=round(exit_straddle, 2),
            pnl_futures_bps=round(pnl_futures_bps, 2),
            pnl_long_call_bps=round(pnl_call_bps, 2),
            pnl_long_put_bps=round(pnl_put_bps, 2),
            pnl_long_straddle_bps=round(pnl_straddle_bps, 2),
            call_premium_pct_S=round(call_premium_pct_notional, 3),
            put_premium_pct_S=round(put_premium_pct_notional, 3),
        ))
    return rows


def _summarise_returns(rows: list[float]) -> dict:
    if not rows:
        return dict(n=0)
    n = len(rows)
    mu = statistics.mean(rows)
    sd = statistics.pstdev(rows) if n > 1 else 0.0
    sharpe = mu / sd if sd > 0 else 0.0
    out = dict(
        n=n,
        mean_bps_gross=round(mu, 2),
        std_bps=round(sd, 2),
        hit_gross=round(sum(1 for v in rows if v > 0) / n, 4),
        sharpe_per_event_gross=round(sharpe, 4),
    )
    for c in COST_BPS_LEVELS:
        net = [v - c for v in rows]
        mn = statistics.mean(net)
        sn = statistics.pstdev(net) if n > 1 else 0.0
        sh_n = mn / sn if sn > 0 else 0.0
        out[f"mean_bps_net_{int(c)}bps"] = round(mn, 2)
        out[f"hit_net_{int(c)}bps"] = round(sum(1 for v in net if v > 0) / n, 4)
        out[f"sharpe_per_event_net_{int(c)}bps"] = round(sh_n, 4)
    return out


def _quintile_cohorts(events: list[dict], factor: str, h: int) -> list[dict]:
    valid = [e for e in events if e.get(factor) is not None and e.get(f"ret_h{h}_bps") is not None]
    if len(valid) < 25:
        return []
    sorted_valid = sorted(valid, key=lambda e: e[factor])
    n = len(sorted_valid)
    boundaries = [int(n * q / 5) for q in range(6)]
    out = []
    for q in range(5):
        sub = sorted_valid[boundaries[q]: boundaries[q + 1]]
        rets = [e[f"ret_h{h}_bps"] for e in sub]
        s = _summarise_returns(rets)
        s["quintile"] = q + 1
        s["factor_min"] = round(sub[0][factor], 4) if sub else None
        s["factor_max"] = round(sub[-1][factor], 4) if sub else None
        out.append(s)
    return out


def main() -> None:
    print("H-2026-05-01-EARNINGS-DRIFT v1 — descriptive event explorer")
    print(f"window {WINDOW_START} -> {WINDOW_END}, locked cost regime 15-20 bps")

    print("\n[1/8] loading daily closes...")
    closes = _load_closes()
    print(f"  {closes.shape[1]} tickers x {closes.shape[0]} bars")

    print("[2/8] loading daily volumes...")
    volumes = _load_volumes()
    print(f"  {volumes.shape[1]} tickers x {volumes.shape[0]} bars")

    print("[3/8] loading regime tape...")
    regime = _load_regime_tape()
    print(f"  {len(regime)} days, range {regime.index.min().date()} -> {regime.index.max().date()}")

    print("[4/8] loading sector map...")
    sym_to_sector, by_sector = _load_sector_map(closes.columns.tolist())
    universe_banks = by_sector.get("Banks", [])
    universe_it = by_sector.get("IT_Services", [])
    universe = universe_banks + universe_it
    print(f"  Banks: {len(universe_banks)} ({universe_banks})")
    print(f"  IT_Services: {len(universe_it)} ({universe_it})")
    print(f"  total universe: {len(universe)}")

    print("[5/8] loading trust scores (today snapshot)...")
    trust_scores = _load_trust_scores()
    print(f"  {len(trust_scores)} stocks scored")

    print("[6/8] loading earnings calendar...")
    earnings = _load_earnings(universe)
    print(f"  {len(earnings)} events in window")
    print(f"  per-ticker counts: {earnings['symbol'].value_counts().head(10).to_dict()}")

    print("[7/8] loading auxiliary series (VIX, USD/INR, IN10Y)...")
    vix = pd.Series(dtype=float)
    if (FNO_DIR / "INDIAVIX.csv").exists():
        vdf = pd.read_csv(FNO_DIR / "INDIAVIX.csv")
        vdf["Date"] = pd.to_datetime(vdf["Date"], errors="coerce")
        vdf = vdf.dropna(subset=["Date", "Close"]).sort_values("Date")
        vix = vdf.set_index("Date")["Close"]
    print(f"  VIX: {len(vix)} bars")

    usd_inr_df = _eodhd_eod_cached("INR.FOREX")
    usd_inr = usd_inr_df["INR.FOREX"] if not usd_inr_df.empty else pd.Series(dtype=float)
    print(f"  USD/INR: {len(usd_inr)} bars")

    in10y_df = _eodhd_eod_cached("IN10Y.GBOND")
    in10y = in10y_df["IN10Y.GBOND"] if not in10y_df.empty else pd.Series(dtype=float)
    print(f"  IN10Y yield: {len(in10y)} bars")

    # ADV per stock for liquidity tier (60d before earnings is good enough for a tier)
    adv_lookback = volumes.iloc[-60:].mean()
    sector_advs = {"__all__": [adv_lookback.get(s, 0.0) for s in universe if s in adv_lookback.index]}
    for s in universe:
        sector_advs[s] = float(adv_lookback.get(s, 0.0))

    print("\n[8/8] computing factors per event...")
    event_rows: list[dict] = []
    skipped = 0
    for i, row in earnings.iterrows():
        sym = row["symbol"].upper()
        sector = sym_to_sector.get(sym)
        if not sector:
            skipped += 1
            continue
        sector_constituents = by_sector.get(sector, [])
        ev = dict(row)
        ev["__sector"] = sector
        feats = _compute_event_factors(
            ev, closes, volumes, vix, usd_inr, in10y, regime,
            sector_constituents, trust_scores, sector_advs,
        )
        if feats is None:
            skipped += 1
            continue
        event_rows.append(feats)
        if (i + 1) % 50 == 0:
            print(f"  ...{i + 1}/{len(earnings)} processed ({len(event_rows)} kept, {skipped} skipped)")
    print(f"  done: {len(event_rows)} events with factors, {skipped} skipped")

    if event_rows:
        df = pd.DataFrame(event_rows)
        df_persist = df.drop(columns=[c for c in df.columns if c.startswith("_")])
        df_persist.to_csv(OUT_FACTORS_CSV, index=False)
        print(f"  -> {OUT_FACTORS_CSV.name} ({len(df_persist)} rows)")

    # ---- Option overlay ----
    print("\n[OVERLAY] computing synthetic option payoffs (Station 6.5 BS pricer)...")
    overlay_rows = []
    for ev in event_rows:
        overlay_rows.extend(_option_overlay(ev, closes))
    if overlay_rows:
        odf = pd.DataFrame(overlay_rows)
        odf.to_csv(OUT_OPTIONS_CSV, index=False)
        print(f"  {len(overlay_rows)} option-leg rows -> {OUT_OPTIONS_CSV.name}")

    # ---- Cohort analysis ----
    print("\n=== HEADLINE: stock-futures returns at each horizon (full universe, all events) ===")
    summary = dict(
        meta=dict(
            window=[WINDOW_START, WINDOW_END],
            universe_banks=len(universe_banks),
            universe_it=len(universe_it),
            n_events=len(event_rows),
            cost_bps_levels=list(COST_BPS_LEVELS),
            cost_regime_locked_band="15-20 bps round-trip per reference_cost_regime_overlay.md (2026-05-01)",
            spec_threshold_net_bps=SPEC_THRESHOLD_NET_BPS,
            hold_horizons=list(HOLD_HORIZONS),
            stage="Stage_A_descriptive",
            note="Beat/miss proxied via event-day excess return (T-1 to T close vs sector). FII/DII forward-only -> excluded. Trust score is today snapshot, PIT caveat acknowledged.",
        ),
        headline_by_horizon=dict(),
        cohorts_by_factor_h5=dict(),
        cohorts_by_direction=dict(),
        options_by_direction_h5=dict(),
    )

    for h in HOLD_HORIZONS:
        rets = [e[f"ret_h{h}_bps"] for e in event_rows if e.get(f"ret_h{h}_bps") is not None]
        s = _summarise_returns(rets)
        summary["headline_by_horizon"][f"H{h}"] = s
        print(f"  H={h:>2}  n={s['n']:>4}  gross={s['mean_bps_gross']:+8.2f}  "
              f"net@15={s['mean_bps_net_15bps']:+8.2f}  net@20={s['mean_bps_net_20bps']:+8.2f}  "
              f"shrp_net@20={s['sharpe_per_event_net_20bps']:+.3f}  hit@20={s['hit_net_20bps']:.3f}")

    print("\n=== DIRECTION-STRATIFIED returns at H=5 (futures) ===")
    for direction in ("BEAT_LIKE", "MISS_LIKE", "UNKNOWN"):
        sub = [e for e in event_rows if e.get("direction_proxy") == direction]
        rets = [e["ret_h5_bps"] for e in sub if e.get("ret_h5_bps") is not None]
        s = _summarise_returns(rets)
        summary["cohorts_by_direction"][direction] = s
        if s.get("n", 0):
            print(f"  {direction:>10}  n={s['n']:>4}  gross={s['mean_bps_gross']:+8.2f}  "
                  f"net@20={s['mean_bps_net_20bps']:+8.2f}  shrp_net@20={s['sharpe_per_event_net_20bps']:+.3f}  hit@20={s['hit_net_20bps']:.3f}")

    print("\n=== UNIVARIATE QUINTILE COHORTS at H=5 (top vs bottom quintile reveals direction) ===")
    factors_to_test = (
        "volume_z", "short_mom_bps", "med_mom_bps", "long_mom_bps",
        "peer_drift_bps", "realized_vol_21d_pct", "vix_t1", "trust_score_pct",
        "usdinr_change_5d_bps", "in10y_change_5d_bps",
    )
    for factor in factors_to_test:
        cohorts = _quintile_cohorts(event_rows, factor, 5)
        if cohorts:
            summary["cohorts_by_factor_h5"][factor] = cohorts
            top = cohorts[-1]
            bot = cohorts[0]
            spread = top["mean_bps_gross"] - bot["mean_bps_gross"]
            print(f"  {factor:>26}  Q1 net@20={bot['mean_bps_net_20bps']:+7.2f}  "
                  f"Q5 net@20={top['mean_bps_net_20bps']:+7.2f}  Q5-Q1 spread={spread:+7.2f}")

    print("\n=== OPTION OVERLAY at H=5 by direction proxy ===")
    if overlay_rows:
        for direction in ("BEAT_LIKE", "MISS_LIKE"):
            sub = [r for r in overlay_rows if r["horizon"] == 5 and r["direction_proxy"] == direction]
            if not sub:
                continue
            for col in ("pnl_futures_bps", "pnl_long_call_bps", "pnl_long_put_bps", "pnl_long_straddle_bps"):
                rets = [r[col] for r in sub]
                s = _summarise_returns(rets)
                summary["options_by_direction_h5"].setdefault(direction, {})[col] = s
                print(f"  {direction:>10}  {col:>22}  n={s['n']:>4}  gross={s['mean_bps_gross']:+9.2f}  "
                      f"shrp_g={s['sharpe_per_event_gross']:+.3f}  hit_g={s['hit_gross']:.3f}")

    OUT_SUMMARY_JSON.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"\n-> {OUT_SUMMARY_JSON.name}")


if __name__ == "__main__":
    main()
