"""PDR-BNK-NBFC forward-shadow paper-trade driver (H-2026-04-30-PDR-BNK-NBFC).

Spec: docs/superpowers/specs/2026-04-30-pdr-banks-nbfc-design.md

Three CLI subcommands run during the holdout window 2026-05-01 -> 2026-08-31
(auto-extend to 2026-12-31 if n < 40):

    python -m pipeline.research.h_2026_04_30_pdr_bnk_nbfc.forward_shadow capture-opens
        09:16 IST. Fetches Kite LTP for the F&O subset of Banks +
        NBFC_HFC sectors and writes to
        ``pipeline/data/research/h_2026_04_30_pdr_bnk_nbfc/opens/<date>.json``.

    python -m pipeline.research.h_2026_04_30_pdr_bnk_nbfc.forward_shadow basket-open
        11:00 IST. Reads today's opens, fetches Kite LTP, computes
        sector-mean returns and divergence Z over the 60-day rolling
        panel. If |Z| > 1.0, opens 4-leg basket (LONG laggard top-2
        by liquidity, SHORT leader top-2). Idempotent on basket_id.

    python -m pipeline.research.h_2026_04_30_pdr_bnk_nbfc.forward_shadow basket-close [--date YYYY-MM-DD]
        14:25 IST. Closes all OPEN legs from `--date` (default today)
        at Kite LTP with exit_reason=TIME_STOP.
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Optional

from pipeline.research.h_2026_04_30_pdr_bnk_nbfc.divergence import compute_divergence_z
from pipeline.research.h_2026_04_30_pdr_bnk_nbfc.liquidity import top_n_by_traded_value

log = logging.getLogger("anka.pdr_bnk_nbfc.forward_shadow")

_IST = timezone(timedelta(hours=5, minutes=30))
_REPO_ROOT = Path(__file__).resolve().parents[3]
_PIPELINE_DIR = _REPO_ROOT / "pipeline"
_RESEARCH_DIR = _PIPELINE_DIR / "data" / "research" / "h_2026_04_30_pdr_bnk_nbfc"
_OPENS_DIR = _RESEARCH_DIR / "opens"
_DIAG_PATH = _RESEARCH_DIR / "diagnostics.csv"
_RECS_PATH = _RESEARCH_DIR / "recommendations.csv"
_FNO_HIST = _PIPELINE_DIR / "data" / "fno_historical"
_CANONICAL_UNIVERSE = _PIPELINE_DIR / "data" / "canonical_fno_research_v3.json"
_TODAY_REGIME_PATH = _PIPELINE_DIR / "data" / "today_regime.json"

# Hypothesis lock - DO NOT change during holdout (single_touch_locked).
SECTOR_A = "Banks"          # paired against
SECTOR_B = "NBFC_HFC"
K_SIGMA = 1.0
N_PER_LEG = 2
ATR_WINDOW = 14
ATR_MULT = 2.0
HOLDOUT_START = date(2026, 5, 1)
HOLDOUT_END_PRIMARY = date(2026, 8, 31)
HOLDOUT_END_AUTO_EXTEND = date(2026, 12, 31)
MIN_HOLDOUT_N = 40

_CSV_COLUMNS = [
    "basket_id", "leg_id", "ticker", "date", "sector",
    "side", "weight",
    "z_score", "divergence_bps", "rolling_std_bps", "regime",
    "entry_time", "entry_px", "atr_14", "stop_px",
    "exit_time", "exit_px", "exit_reason", "pnl_pct", "status",
    "regime_pit_corrected", "regime_correction_reason",
]

_DIAG_COLUMNS = [
    "date", "captured_at", "z_score", "divergence_bps",
    "rolling_mean_bps", "rolling_std_bps", "sigma_rows_used",
    "n_a", "n_b", "leader_sector", "laggard_sector",
    "decision", "decision_reason",
]


def _today_iso() -> str:
    return datetime.now(_IST).date().isoformat()


def _now_iso() -> str:
    return datetime.now(_IST).strftime("%Y-%m-%dT%H:%M:%S+05:30")


def _basket_id(date_iso: str) -> str:
    return f"PDR-BNK-NBFC-{date_iso}"


def _leg_id(date_iso: str, ticker: str, side: str) -> str:
    return f"PDR-BNK-NBFC-{date_iso}-{ticker}-{side}"


def _holdout_end_today(today: date) -> date:
    rows = _read_recs()
    n = sum(1 for r in rows if r.get("status") == "CLOSED")
    if today <= HOLDOUT_END_PRIMARY:
        return HOLDOUT_END_PRIMARY
    if n < MIN_HOLDOUT_N:
        return HOLDOUT_END_AUTO_EXTEND
    return HOLDOUT_END_PRIMARY


def _in_holdout(d: date) -> bool:
    if d < HOLDOUT_START:
        return False
    return d <= _holdout_end_today(d)


# ---- Live data wrappers (lazy-imported so tests can stub) -----------------

def _fetch_ltp(symbols: list[str]) -> dict[str, float]:
    if not symbols:
        return {}
    from pipeline.kite_client import fetch_ltp
    return fetch_ltp(symbols)


def _compute_atr_stop(symbol: str, direction: str) -> dict:
    from pipeline.atr_stops import compute_atr_stop
    return compute_atr_stop(symbol, direction, window=ATR_WINDOW, mult=ATR_MULT)


def _load_universe() -> list[str]:
    if not _CANONICAL_UNIVERSE.is_file():
        log.error("canonical_fno_research_v3.json not found at %s", _CANONICAL_UNIVERSE)
        return []
    doc = json.loads(_CANONICAL_UNIVERSE.read_text(encoding="utf-8"))
    return list(doc.get("tickers", []))


def _load_sector_map() -> dict[str, str]:
    try:
        from pipeline.scorecard_v2.sector_mapper import SectorMapper
    except Exception as exc:
        log.error("SectorMapper import failed: %s", exc)
        return {}
    sm = SectorMapper()
    full = sm.map_all()
    return {sym: meta.get("sector", "") for sym, meta in full.items()}


def _load_today_regime() -> str:
    if not _TODAY_REGIME_PATH.is_file():
        return "UNKNOWN"
    try:
        d = json.loads(_TODAY_REGIME_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "UNKNOWN"
    return (d.get("zone") or d.get("regime") or d.get("regime_zone") or "UNKNOWN")


# ---- CSV ledger I/O -------------------------------------------------------

def _read_recs() -> list[dict]:
    if not _RECS_PATH.is_file():
        return []
    with _RECS_PATH.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _write_recs(rows: list[dict]) -> None:
    _RECS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _RECS_PATH.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_CSV_COLUMNS)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k, "") for k in _CSV_COLUMNS})


def _append_rows(new_rows: list[dict]) -> None:
    if not new_rows:
        return
    _RECS_PATH.parent.mkdir(parents=True, exist_ok=True)
    exists = _RECS_PATH.is_file()
    with _RECS_PATH.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_CSV_COLUMNS)
        if not exists:
            writer.writeheader()
        for r in new_rows:
            writer.writerow({k: r.get(k, "") for k in _CSV_COLUMNS})


def _append_diagnostic(row: dict) -> None:
    _RECS_PATH.parent.mkdir(parents=True, exist_ok=True)
    exists = _DIAG_PATH.is_file()
    with _DIAG_PATH.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_DIAG_COLUMNS)
        if not exists:
            writer.writeheader()
        writer.writerow({k: row.get(k, "") for k in _DIAG_COLUMNS})


# ---- capture-opens --------------------------------------------------------

def _sector_universe(sector_map: dict[str, str], target: str, universe: Iterable[str]) -> list[str]:
    return [t for t in universe if sector_map.get(t) == target]


def cmd_capture_opens() -> int:
    today = _today_iso()
    universe = _load_universe()
    sector_map = _load_sector_map()
    if not universe or not sector_map:
        log.error("capture-opens: missing universe or sector map")
        return 1

    members = _sector_universe(sector_map, SECTOR_A, universe) + _sector_universe(sector_map, SECTOR_B, universe)
    if not members:
        log.error("capture-opens: no Banks/NBFC_HFC members resolved")
        return 1

    log.info("capture-opens: fetching LTP for %d Banks+NBFC_HFC tickers", len(members))
    prices = _fetch_ltp(members)
    if not prices:
        log.error("capture-opens: no opens fetched (Kite session?)")
        return 1

    _OPENS_DIR.mkdir(parents=True, exist_ok=True)
    out = _OPENS_DIR / f"{today}.json"
    out.write_text(json.dumps({
        "date": today,
        "captured_at": _now_iso(),
        "sector_a": SECTOR_A,
        "sector_b": SECTOR_B,
        "n_requested": len(members),
        "n_fetched": len(prices),
        "prices": prices,
    }, indent=2), encoding="utf-8")
    log.info("capture-opens: wrote %d/%d to %s", len(prices), len(members), out)
    return 0


def _load_opens(date_iso: str) -> dict[str, float]:
    p = _OPENS_DIR / f"{date_iso}.json"
    if not p.is_file():
        return {}
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    raw = doc.get("prices", {}) or {}
    return {k: float(v) for k, v in raw.items() if v is not None}


# ---- basket-open ----------------------------------------------------------

def _build_open_rows(
    *,
    today: str,
    laggard_sector: str,
    leader_sector: str,
    laggard_picks: list[str],
    leader_picks: list[str],
    z: float,
    divergence_bps: float,
    rolling_std_bps: float,
    regime: str,
    prices_now: dict[str, float],
) -> list[dict]:
    now = _now_iso()
    bid = _basket_id(today)
    rows: list[dict] = []

    long_w = 0.5  # 1/2 longs, 1/2 shorts; basket sums to 0
    short_w = -0.5

    for tkr in laggard_picks:
        px = prices_now.get(tkr)
        if px is None or px <= 0:
            log.error("basket-open: missing LTP for LONG %s", tkr)
            return []
        atr_info = _compute_atr_stop(tkr, "LONG")
        rows.append(_make_row(
            bid, today, tkr, laggard_sector, "LONG", long_w,
            float(px), atr_info, z, divergence_bps, rolling_std_bps, regime, now,
        ))
    for tkr in leader_picks:
        px = prices_now.get(tkr)
        if px is None or px <= 0:
            log.error("basket-open: missing LTP for SHORT %s", tkr)
            return []
        atr_info = _compute_atr_stop(tkr, "SHORT")
        rows.append(_make_row(
            bid, today, tkr, leader_sector, "SHORT", short_w,
            float(px), atr_info, z, divergence_bps, rolling_std_bps, regime, now,
        ))
    return rows


def _make_row(
    bid: str, today: str, tkr: str, sector: str, side: str, weight: float,
    entry_px: float, atr_info: dict,
    z: float, div_bps: float, rstd_bps: float, regime: str, now: str,
) -> dict:
    return {
        "basket_id": bid,
        "leg_id": _leg_id(today, tkr, side),
        "ticker": tkr,
        "date": today,
        "sector": sector,
        "side": side,
        "weight": f"{weight:.4f}",
        "z_score": f"{z:.4f}",
        "divergence_bps": f"{div_bps:.2f}",
        "rolling_std_bps": f"{rstd_bps:.2f}",
        "regime": regime,
        "entry_time": now,
        "entry_px": f"{entry_px:.4f}",
        "atr_14": "" if atr_info.get("atr_14") is None else f"{atr_info['atr_14']:.4f}",
        "stop_px": "" if atr_info.get("stop_price") is None else f"{atr_info['stop_price']:.4f}",
        "exit_time": "",
        "exit_px": "",
        "exit_reason": "",
        "pnl_pct": "",
        "status": "OPEN",
        "regime_pit_corrected": "",
        "regime_correction_reason": "",
    }


def cmd_basket_open() -> int:
    today = _today_iso()
    today_d = date.fromisoformat(today)
    if not _in_holdout(today_d):
        log.info("basket-open: %s outside holdout — no-op", today)
        return 0

    existing = _read_recs()
    if any(r.get("basket_id") == _basket_id(today) for r in existing):
        log.info("basket-open: basket %s already opened — skipping", _basket_id(today))
        return 0

    prices_open = _load_opens(today)
    if not prices_open:
        log.error("basket-open: opens file missing for %s — run capture-opens first", today)
        return 1

    universe = _load_universe()
    sector_map = _load_sector_map()
    if not universe or not sector_map:
        log.error("basket-open: missing universe or sector map")
        return 1

    a_members = _sector_universe(sector_map, SECTOR_A, universe)
    b_members = _sector_universe(sector_map, SECTOR_B, universe)
    if not a_members or not b_members:
        log.error("basket-open: empty sector members for %s or %s", SECTOR_A, SECTOR_B)
        return 1

    members = a_members + b_members
    log.info("basket-open: fetching LTP for %d members", len(members))
    prices_now = _fetch_ltp(members)
    if not prices_now:
        log.error("basket-open: no LTP fetched")
        return 1

    div = compute_divergence_z(
        sector_a_members=a_members,
        sector_b_members=b_members,
        prices_open=prices_open,
        prices_at_signal=prices_now,
        fno_hist_dir=_FNO_HIST,
    )
    z = div.get("z")
    div_bps = (div.get("divergence") or 0.0) * 10000.0
    rstd_bps = (div.get("rolling_std") or 0.0) * 10000.0
    rmean_bps = (div.get("rolling_mean") or 0.0) * 10000.0
    regime = _load_today_regime()

    diag = {
        "date": today,
        "captured_at": _now_iso(),
        "z_score": "" if z is None else f"{z:.4f}",
        "divergence_bps": f"{div_bps:.2f}",
        "rolling_mean_bps": f"{rmean_bps:.2f}",
        "rolling_std_bps": f"{rstd_bps:.2f}",
        "sigma_rows_used": div.get("sigma_rows_used", 0),
        "n_a": div.get("n_a", 0),
        "n_b": div.get("n_b", 0),
        "leader_sector": "",
        "laggard_sector": "",
        "decision": "NO_TRADE",
        "decision_reason": "",
    }

    if z is None:
        diag["decision_reason"] = "no_z_insufficient_panel_or_intraday_data"
        _append_diagnostic(diag)
        log.info("basket-open: %s — z unavailable, skipping", today)
        return 0
    if abs(z) < K_SIGMA:
        diag["decision_reason"] = f"abs_z_{abs(z):.3f}_below_threshold_{K_SIGMA}"
        _append_diagnostic(diag)
        log.info("basket-open: %s — |z|=%.3f < %.1f, no trade", today, abs(z), K_SIGMA)
        return 0

    # Mean-reversion direction:
    #   z > 0  => sector_a (Banks) is leader  => SHORT Banks, LONG NBFC_HFC
    #   z < 0  => sector_a (Banks) is laggard => LONG Banks, SHORT NBFC_HFC
    if z > 0:
        leader_sector, leader_members = SECTOR_A, a_members
        laggard_sector, laggard_members = SECTOR_B, b_members
    else:
        leader_sector, leader_members = SECTOR_B, b_members
        laggard_sector, laggard_members = SECTOR_A, a_members

    laggard_picks = top_n_by_traded_value(
        sector_target=laggard_sector, sector_map=sector_map,
        fno_hist_dir=_FNO_HIST, universe=universe, n=N_PER_LEG,
    )
    leader_picks = top_n_by_traded_value(
        sector_target=leader_sector, sector_map=sector_map,
        fno_hist_dir=_FNO_HIST, universe=universe, n=N_PER_LEG,
    )
    if len(laggard_picks) < N_PER_LEG or len(leader_picks) < N_PER_LEG:
        diag["leader_sector"] = leader_sector
        diag["laggard_sector"] = laggard_sector
        diag["decision_reason"] = f"insufficient_picks_long={len(laggard_picks)}_short={len(leader_picks)}"
        _append_diagnostic(diag)
        log.error("basket-open: insufficient liquidity picks — long=%s short=%s",
                  laggard_picks, leader_picks)
        return 1

    rows = _build_open_rows(
        today=today,
        laggard_sector=laggard_sector,
        leader_sector=leader_sector,
        laggard_picks=laggard_picks,
        leader_picks=leader_picks,
        z=float(z),
        divergence_bps=div_bps,
        rolling_std_bps=rstd_bps,
        regime=regime,
        prices_now=prices_now,
    )
    if not rows:
        return 1
    _append_rows(rows)

    diag["leader_sector"] = leader_sector
    diag["laggard_sector"] = laggard_sector
    diag["decision"] = "TRADE"
    diag["decision_reason"] = f"abs_z_{abs(z):.3f}_>=_{K_SIGMA}_long_{laggard_sector}_short_{leader_sector}"
    _append_diagnostic(diag)
    log.info("basket-open: %s — z=%.3f, LONG %s%s SHORT %s%s",
             today, z, laggard_sector, laggard_picks, leader_sector, leader_picks)
    return 0


# ---- basket-close ---------------------------------------------------------

def _pnl_pct(side: str, entry: float, exit_: float) -> float:
    if entry <= 0:
        return 0.0
    raw = (exit_ - entry) / entry * 100.0
    return raw if side == "LONG" else -raw


def cmd_basket_close(target_date_iso: Optional[str] = None) -> int:
    today = target_date_iso or _today_iso()
    rows = _read_recs()
    open_rows = [r for r in rows if r.get("date") == today and r.get("status") == "OPEN"]
    if not open_rows:
        log.info("basket-close: no OPEN legs for %s — nothing to do", today)
        return 0

    tickers = sorted({r["ticker"] for r in open_rows})
    log.info("basket-close: fetching LTP for %d open legs on %s", len(tickers), today)
    ltp = _fetch_ltp(tickers)
    if not ltp:
        log.error("basket-close: no LTP fetched")
        return 1

    now = _now_iso()
    closed = 0
    for r in rows:
        if r.get("date") != today or r.get("status") != "OPEN":
            continue
        ticker = r["ticker"]
        side = r["side"]
        exit_px = ltp.get(ticker)
        if exit_px is None or exit_px <= 0:
            log.warning("basket-close: missing LTP for %s — leaving OPEN", ticker)
            continue
        try:
            entry_px = float(r["entry_px"])
        except (TypeError, ValueError):
            continue
        pnl = _pnl_pct(side, entry_px, float(exit_px))
        r["exit_time"] = now
        r["exit_px"] = f"{float(exit_px):.4f}"
        r["exit_reason"] = "TIME_STOP"
        r["pnl_pct"] = f"{pnl:.4f}"
        r["status"] = "CLOSED"
        closed += 1

    _write_recs(rows)
    log.info("basket-close: closed %d legs for %s", closed, today)
    return 0


# ---- entrypoint -----------------------------------------------------------

def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="pdr_bnk_nbfc.forward_shadow")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("capture-opens")
    sub.add_parser("basket-open")
    p_close = sub.add_parser("basket-close")
    p_close.add_argument("--date", default=None, help="YYYY-MM-DD; default = today IST")

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    if args.cmd == "capture-opens":
        return cmd_capture_opens()
    if args.cmd == "basket-open":
        return cmd_basket_open()
    if args.cmd == "basket-close":
        return cmd_basket_close(args.date)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
