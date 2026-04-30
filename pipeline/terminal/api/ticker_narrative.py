"""GET /api/ticker/{ticker}/narrative — per-ticker context and event markers.

This is the "what we've done with this ticker before" endpoint that powers
the chart modal's narration panel and event-marker overlay. The user wanted
charts to be research artifacts, not just OHLC plots — so for any F&O
universe ticker we surface:

- closed Phase C signals (stop / target / time-stop verdicts)
- spread participation (ticker as long/short leg in regime spreads)
- pattern scanner hits (TA Fingerprint pattern qualifications)
- auto-detected major movements (|daily return| > 2sigma, volume > 3x avg)
- forthcoming earnings dates if within the next 14 days

Everything is read-only from existing files; no new data is generated.
The response is shaped for direct consumption by Lightweight Charts'
setMarkers() API plus a sidebar narration list.
"""
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()
logger = logging.getLogger(__name__)

_HERE = Path(__file__).resolve().parent.parent
_PIPELINE = _HERE.parent
_CLOSED_SIGNALS = _PIPELINE / "data" / "signals" / "closed_signals.json"
_OPEN_SIGNALS = _PIPELINE / "data" / "signals" / "open_signals.json"
_PHASE_C_LIVE = _PIPELINE / "data" / "research" / "phase_c" / "live_paper_ledger.json"
_PATTERNS_TODAY = _PIPELINE / "data" / "scanner" / "pattern_signals_today.json"
_PATTERNS_YDAY = _PIPELINE / "data" / "scanner" / "pattern_signals_yesterday.json"
_FNO_HIST = _PIPELINE / "data" / "fno_historical"
_EARNINGS = _PIPELINE / "data" / "earnings"

_NO_CACHE = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}


@router.get("/ticker/{ticker}/narrative")
def narrative(ticker: str):
    ticker = ticker.upper()
    markers = []
    summary = []

    markers.extend(_phase_c_markers(ticker, summary))
    markers.extend(_closed_signal_markers(ticker, summary))
    markers.extend(_open_signal_markers(ticker, summary))
    markers.extend(_pattern_markers(ticker, summary))
    movement_markers, movement_summary = _major_movement_markers(ticker)
    markers.extend(movement_markers)
    if movement_summary:
        summary.append(movement_summary)

    earnings_line = _earnings_line(ticker)
    if earnings_line:
        summary.append(earnings_line)

    markers.sort(key=lambda m: m.get("time", ""))

    return JSONResponse(
        {
            "ticker": ticker,
            "markers": markers,
            "summary": summary,
            "marker_count": len(markers),
        },
        headers=_NO_CACHE,
    )


def _read_json(p: Path):
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("read failed %s: %s", p, e)
        return None


def _phase_c_markers(ticker: str, summary: list) -> list:
    rows = _read_json(_PHASE_C_LIVE) or []
    out = []
    for r in rows:
        if (r.get("symbol") or "").upper() != ticker:
            continue
        date = r.get("date")
        if not date:
            continue
        side = r.get("side", "?")
        # Lightweight Charts marker shape: time, position, color, shape, text.
        # OPEN: arrow at the entry side. CLOSE: dot near the exit price.
        out.append({
            "time": date,
            "position": "belowBar" if side == "LONG" else "aboveBar",
            "color": "#2563eb",
            "shape": "arrowUp" if side == "LONG" else "arrowDown",
            "text": f"PhaseC {side} z={r.get('z_score', 0):.1f}",
            "kind": "phase_c_open",
        })
        if r.get("status") == "CLOSED" and r.get("exit_time"):
            exit_date = str(r["exit_time"])[:10]
            pnl = r.get("pnl_net_inr") or 0
            out.append({
                "time": exit_date,
                "position": "aboveBar",
                "color": "#10b981" if pnl >= 0 else "#ef4444",
                "shape": "circle",
                "text": f"PhaseC exit {r.get('exit_reason', '?')} ₹{pnl:+,.0f}",
                "kind": "phase_c_close",
            })
    if out:
        opens = [m for m in out if m["kind"] == "phase_c_open"]
        summary.append(f"Phase C: {len(opens)} signal(s) on this ticker.")
    return out


def _closed_signal_markers(ticker: str, summary: list) -> list:
    sigs = _read_json(_CLOSED_SIGNALS) or []
    out = []
    appearances = 0
    for s in sigs:
        legs_long = [l.get("ticker") for l in s.get("long_legs", [])]
        legs_short = [l.get("ticker") for l in s.get("short_legs", [])]
        if ticker not in legs_long and ticker not in legs_short:
            continue
        appearances += 1
        side = "LONG" if ticker in legs_long else "SHORT"
        open_ts = s.get("open_timestamp", "")[:10]
        if open_ts:
            out.append({
                "time": open_ts,
                "position": "belowBar" if side == "LONG" else "aboveBar",
                "color": "#8b5cf6",
                "shape": "arrowUp" if side == "LONG" else "arrowDown",
                "text": f"{s.get('spread_name', 'spread')} {side}",
                "kind": "spread_open",
            })
        close_ts = s.get("close_timestamp", "")[:10]
        if close_ts:
            # `final_pnl` is sometimes a number, sometimes a dict with
            # spread_pnl_pct + per-leg breakdown — depends on which engine
            # closed it. Coerce to a single % figure for the marker.
            raw = s.get("final_pnl")
            pnl = 0.0
            if isinstance(raw, (int, float)):
                pnl = float(raw)
            elif isinstance(raw, dict):
                v = raw.get("spread_pnl_pct")
                if isinstance(v, (int, float)):
                    pnl = float(v)
            out.append({
                "time": close_ts,
                "position": "aboveBar",
                "color": "#10b981" if pnl >= 0 else "#ef4444",
                "shape": "circle",
                "text": f"{s.get('spread_name', 'spread')} exit {pnl:+.2f}%",
                "kind": "spread_close",
            })
    if appearances:
        summary.append(
            f"Spreads: appeared as a leg in {appearances} closed regime spread(s)."
        )
    return out


def _open_signal_markers(ticker: str, summary: list) -> list:
    sigs = _read_json(_OPEN_SIGNALS) or []
    out = []
    for s in sigs:
        legs_long = [l.get("ticker") for l in s.get("long_legs", [])]
        legs_short = [l.get("ticker") for l in s.get("short_legs", [])]
        if ticker not in legs_long and ticker not in legs_short:
            continue
        side = "LONG" if ticker in legs_long else "SHORT"
        open_ts = s.get("open_timestamp", "")[:10]
        if not open_ts:
            continue
        out.append({
            "time": open_ts,
            "position": "belowBar" if side == "LONG" else "aboveBar",
            "color": "#f59e0b",
            "shape": "arrowUp" if side == "LONG" else "arrowDown",
            "text": f"{s.get('spread_name', 'spread')} {side} OPEN",
            "kind": "spread_open_live",
        })
        summary.append(
            f"Live: currently a {side} leg in {s.get('spread_name', 'spread')}."
        )
    return out


def _pattern_markers(ticker: str, summary: list) -> list:
    out = []
    for p, label in ((_PATTERNS_TODAY, "today"), (_PATTERNS_YDAY, "yesterday")):
        d = _read_json(p) or {}
        as_of = (d.get("as_of") or "")[:10]
        for row in d.get("top_10", []) or []:
            if (row.get("ticker") or "").upper() != ticker:
                continue
            out.append({
                "time": as_of,
                "position": "aboveBar",
                "color": "#0ea5e9",
                "shape": "square",
                "text": f"Pattern {row.get('pattern', '?')}",
                "kind": "pattern_hit",
            })
            summary.append(
                f"Pattern Scanner ({label}): qualified for {row.get('pattern', '?')}."
            )
    return out


def _major_movement_markers(ticker: str) -> tuple[list, str]:
    """Auto-flag |daily return| > 2 sigma and volume > 3x 20-day average.

    Reads the same fno_historical CSV the chart endpoint reads, so the
    markers always align with what's drawn. Last 200 trading days.
    """
    csv = _FNO_HIST / f"{ticker}.csv"
    if not csv.exists():
        return [], ""
    try:
        import pandas as pd
        df = pd.read_csv(csv).tail(220)
        if df.empty or len(df) < 30:
            return [], ""
        df["ret"] = df["Close"].pct_change()
        sigma = df["ret"].std()
        vol_avg = df["Volume"].rolling(20).mean()
        out = []
        gap_count = 0
        vol_count = 0
        for _, r in df.tail(200).iterrows():
            d = str(r.get("Date", ""))[:10]
            if not d:
                continue
            ret = r["ret"]
            v = r["Volume"]
            avg_v = vol_avg.loc[r.name] if r.name in vol_avg.index else None
            big_move = pd.notna(ret) and sigma > 0 and abs(ret) > 2 * sigma
            big_vol = (
                pd.notna(v) and pd.notna(avg_v) and avg_v > 0 and v > 3 * avg_v
            )
            if big_move:
                gap_count += 1
                out.append({
                    "time": d,
                    "position": "aboveBar" if ret > 0 else "belowBar",
                    "color": "#f97316",
                    "shape": "circle",
                    "text": f"{ret * 100:+.1f}% (>2σ)",
                    "kind": "major_move",
                })
            if big_vol and not big_move:
                vol_count += 1
                out.append({
                    "time": d,
                    "position": "belowBar",
                    "color": "#a855f7",
                    "shape": "circle",
                    "text": f"vol {v / avg_v:.1f}x avg",
                    "kind": "volume_spike",
                })
        bits = []
        if gap_count:
            bits.append(f"{gap_count} >2σ moves")
        if vol_count:
            bits.append(f"{vol_count} volume spikes")
        line = "Major movements (200d): " + ", ".join(bits) + "." if bits else ""
        return out, line
    except Exception as e:
        logger.warning("major-movement scan failed for %s: %s", ticker, e)
        return [], ""


def _earnings_line(ticker: str) -> str:
    """If a corporate-action parquet exists and has an upcoming-14d row for
    this ticker, surface it. Silent on absence — earnings collection is
    best-effort across the universe."""
    if not _EARNINGS.exists():
        return ""
    try:
        import pandas as pd
        files = sorted(_EARNINGS.glob("*.parquet"))
        if not files:
            return ""
        df = pd.read_parquet(files[-1])
        col_sym = next(
            (c for c in df.columns if c.lower() in ("symbol", "ticker", "sym")), None
        )
        col_dt = next(
            (c for c in df.columns if "date" in c.lower() or "ex_date" in c.lower()),
            None,
        )
        if not col_sym or not col_dt:
            return ""
        sub = df[df[col_sym].astype(str).str.upper() == ticker]
        if sub.empty:
            return ""
        today = datetime.now().date()
        for _, r in sub.iterrows():
            try:
                d = pd.to_datetime(r[col_dt]).date()
                delta = (d - today).days
                if 0 <= delta <= 14:
                    return f"Earnings: {d.isoformat()} ({delta}d away)."
            except Exception:
                continue
        return ""
    except Exception as e:
        logger.warning("earnings lookup failed for %s: %s", ticker, e)
        return ""
