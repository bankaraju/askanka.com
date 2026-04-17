"""
TA Daily Scanner — check live prices against each stock's fingerprint card.
Runs at 15:35 IST daily.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas as pd
from ta_indicators import bollinger, macd, rsi, atr, ema, sma, volume_spike

log = logging.getLogger("anka.ta_scanner")

IST = timezone(timedelta(hours=5, minutes=30))
DEFAULT_FINGERPRINTS = Path(__file__).parent / "data" / "ta_fingerprints"
DEFAULT_HISTORICAL = Path(__file__).parent / "data" / "ta_historical"
DEFAULT_OUTPUT = Path(__file__).parent / "data" / "ta_alerts.json"


def _load_fingerprint(symbol: str, fingerprint_dir: Path) -> dict | None:
    path = fingerprint_dir / f"{symbol}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _load_ohlcv(symbol: str, historical_dir: Path) -> pd.DataFrame | None:
    path = historical_dir / f"{symbol}.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path, parse_dates=["Date"])
    return df.sort_values("Date").reset_index(drop=True)


def _check_pattern_proximity(pattern: str, df: pd.DataFrame) -> dict | None:
    if len(df) < 50:
        return None

    close = df["Close"].astype(float)
    last = close.iloc[-1]

    if pattern == "BB_SQUEEZE":
        bb = bollinger(df)
        bw = bb["bandwidth"]
        bw_min20 = bw.rolling(20, min_periods=20).min()
        if pd.notna(bw.iloc[-1]) and pd.notna(bw_min20.iloc[-2]):
            if bw.iloc[-1] <= bw_min20.iloc[-2]:
                return {"status": "TRIGGERED", "detail": f"bandwidth={bw.iloc[-1]:.4f}"}
            ratio = bw.iloc[-1] / max(bw_min20.iloc[-2], 0.0001)
            if ratio < 1.1:
                return {"status": "APPROACHING", "proximity_pct": round((ratio - 1) * 100, 1)}

    elif pattern == "DMA200_CROSS_UP":
        e200 = ema(close, 200)
        if pd.notna(e200.iloc[-1]):
            prev = close.iloc[-2] if len(close) > 1 else last
            if prev <= e200.iloc[-2] and last > e200.iloc[-1]:
                return {"status": "TRIGGERED", "detail": f"ema200={e200.iloc[-1]:.1f}"}
            dist = (last - e200.iloc[-1]) / e200.iloc[-1] * 100
            if -2.0 < dist < 0:
                return {"status": "APPROACHING", "proximity_pct": round(abs(dist), 1)}

    elif pattern == "RSI_OVERSOLD_BOUNCE":
        r = rsi(df)
        if pd.notna(r.iloc[-1]) and pd.notna(r.iloc[-2]):
            if r.iloc[-2] < 30 and r.iloc[-1] >= 30:
                return {"status": "TRIGGERED", "detail": f"rsi={r.iloc[-1]:.1f}"}
            if 30 <= r.iloc[-1] <= 35:
                return {"status": "APPROACHING", "proximity_pct": round(r.iloc[-1] - 30, 1)}

    elif pattern == "MACD_CROSS_UP":
        m = macd(df)
        ml, sl = m["macd_line"], m["signal_line"]
        if pd.notna(ml.iloc[-1]) and pd.notna(sl.iloc[-1]):
            if ml.iloc[-2] <= sl.iloc[-2] and ml.iloc[-1] > sl.iloc[-1]:
                return {"status": "TRIGGERED", "detail": "macd crossed signal"}
            gap = (ml.iloc[-1] - sl.iloc[-1]) / max(abs(sl.iloc[-1]), 0.01)
            if -0.05 < gap < 0:
                return {"status": "APPROACHING", "proximity_pct": round(abs(gap) * 100, 1)}

    elif pattern == "VOL_BREAKOUT":
        vs = volume_spike(df)
        high_20 = close.rolling(20, min_periods=20).max().shift(1)
        if vs.iloc[-1] and last > high_20.iloc[-1]:
            return {"status": "TRIGGERED", "detail": "vol_spike + new 20d high"}

    elif pattern == "ATR_COMPRESSION":
        a = atr(df)
        a_avg = sma(a, 50)
        if pd.notna(a.iloc[-1]) and pd.notna(a_avg.iloc[-1]):
            if a.iloc[-1] < 0.5 * a_avg.iloc[-1]:
                return {"status": "TRIGGERED", "detail": f"atr={a.iloc[-1]:.2f}"}

    return None


def scan_stock(
    symbol: str,
    fingerprint_dir: Path = DEFAULT_FINGERPRINTS,
    historical_dir: Path = DEFAULT_HISTORICAL,
) -> list[dict]:
    fp = _load_fingerprint(symbol, fingerprint_dir)
    if not fp:
        return []

    df = _load_ohlcv(symbol, historical_dir)
    if df is None or df.empty:
        return []

    alerts = []
    for entry in fp.get("fingerprint", []):
        pattern = entry["pattern"]
        result = _check_pattern_proximity(pattern, df)
        if result:
            alerts.append({
                "symbol": symbol,
                "pattern": pattern,
                "status": result["status"],
                "proximity_pct": result.get("proximity_pct"),
                "detail": result.get("detail"),
                "historical_win_rate": entry.get("win_rate_5d", 0),
                "historical_avg_return": entry.get("avg_return_5d", 0),
                "occurrences": entry.get("occurrences", 0),
                "direction": entry.get("direction", "LONG"),
                "current_price": float(df["Close"].iloc[-1]),
            })

    return alerts


def scan_all(
    symbols: list[str] | None = None,
    fingerprint_dir: Path = DEFAULT_FINGERPRINTS,
    historical_dir: Path = DEFAULT_HISTORICAL,
    output_path: Path = DEFAULT_OUTPUT,
) -> dict:
    if symbols is None:
        symbols = [f.stem for f in fingerprint_dir.glob("*.json")]

    all_alerts = []
    for sym in symbols:
        alerts = scan_stock(sym, fingerprint_dir, historical_dir)
        all_alerts.extend(alerts)

    output = {
        "date": datetime.now(IST).strftime("%Y-%m-%d"),
        "scanned": len(symbols),
        "alerts": sorted(all_alerts, key=lambda a: (-a["historical_win_rate"], a["symbol"])),
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info("TA scan: %d stocks, %d alerts", len(symbols), len(all_alerts))

    return output


if __name__ == "__main__":
    import sys, logging
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    scan_all()
