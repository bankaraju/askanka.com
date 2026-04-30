"""Alpha decay monitor — daily verdict per live basket.

Reads three ledger schemas:
  1. pipeline/data/signals/closed_signals.json — deprecated INDIA_SPREAD_PAIRS
     basket trades fired live in paper from news triggers.
  2. pipeline/data/research/h_2026_04_27_secrsi/recommendations.csv — SECRSI
     intraday sector RS pair, leg-level CSV.
  3. pipeline/data/research/<hypothesis>/recommendations.csv — generic
     pre-registered hypothesis ledger format.

Verdict logic per basket
------------------------
  rolling_window     = last 30 trading days of closed trades
  rolling_sharpe     = mean / std of per-trade pnl_bps (degenerate-safe)
  is_sharpe          = frozen at pre-registration time (registry entry)
                       or 0.0 for deprecated baskets (Task #24 FAIL'd)
  ratio              = rolling_sharpe / max(0.1, abs(is_sharpe))
                       — 0.1 floor avoids divide-by-zero blow-ups when IS is 0

  HEALTHY            ratio >= 0.7
  WATCH              0.3 <= ratio < 0.7
  DECAYING           0.0 <= ratio < 0.3
  KILL               ratio < 0.0  (forward Sharpe negative)
  INSUFFICIENT_N     n_closed < 10 in window — no verdict

Output
------
  pipeline/data/research/alpha_decay/decay_<YYYY-MM-DD>.json
"""
from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable

REPO = Path(__file__).resolve().parents[3]
SIGNALS_CLOSED = REPO / "pipeline" / "data" / "signals" / "closed_signals.json"
HYPOTHESIS_REGISTRY = REPO / "docs" / "superpowers" / "hypothesis-registry.jsonl"
OUT_DIR = REPO / "pipeline" / "data" / "research" / "alpha_decay"
ROLLING_TRADING_DAYS = 30
MIN_N_FOR_VERDICT = 10
SHARPE_FLOOR = 0.1


@dataclass(frozen=True)
class BasketTrade:
    basket: str
    pnl_bps: float
    close_dt: datetime
    source: str  # which ledger it came from


@dataclass(frozen=True)
class DecayVerdict:
    basket: str
    n_closed: int
    rolling_mean_bps: float
    rolling_std_bps: float
    rolling_sharpe: float
    is_sharpe: float
    ratio: float
    verdict: str
    window_start: str
    window_end: str
    sources: list[str]


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    s = str(value)
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f",
                "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s[:len(fmt) + 4 if "%f" in fmt else len(fmt)], fmt)
        except ValueError:
            continue
    # ISO with TZ — try fromisoformat after stripping TZ
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=None)
    except (ValueError, TypeError):
        return None


def _load_closed_signals() -> list[BasketTrade]:
    if not SIGNALS_CLOSED.is_file():
        return []
    try:
        rows = json.loads(SIGNALS_CLOSED.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    out: list[BasketTrade] = []
    for r in rows:
        # closed_signals.json status is the *exit reason* (STOPPED_OUT_ZCROSS,
        # STOPPED_OUT_TIME, STOPPED_OUT_TRAIL, STOPPED_OUT, closed). Treat any
        # entry with a close_timestamp + spread_pnl_pct as closed.
        spread = r.get("spread_name") or r.get("strategy_id")
        if not spread:
            continue
        # Phase C single-stock opportunities are tracked elsewhere
        # (live_paper_ledger.json) — exclude them from the spread-basket
        # decay monitor.
        if str(spread).startswith("Phase C:"):
            continue
        pnl_pct = (r.get("final_pnl") or {}).get("spread_pnl_pct")
        if pnl_pct is None:
            continue
        close_dt = _parse_dt(r.get("close_timestamp") or r.get("exit_timestamp"))
        if close_dt is None:
            continue
        out.append(BasketTrade(
            basket=str(spread).strip(),
            pnl_bps=float(pnl_pct) * 100.0,  # pct -> bps
            close_dt=close_dt,
            source="closed_signals.json",
        ))
    return out


def _load_secrsi_basket() -> list[BasketTrade]:
    """SECRSI emits leg-level rows; aggregate to one trade per basket_id."""
    p = REPO / "pipeline" / "data" / "research" / "h_2026_04_27_secrsi" / "recommendations.csv"
    if not p.is_file():
        return []
    by_basket: dict[str, list[tuple[float, float, datetime | None]]] = {}
    with p.open(encoding="utf-8", newline="") as fp:
        for row in csv.DictReader(fp):
            if (row.get("status") or "").upper() != "CLOSED":
                continue
            try:
                pnl = float(row["pnl_pct"])
                w = float(row.get("weight", "0.0"))
            except (ValueError, KeyError, TypeError):
                continue
            ct = _parse_dt(row.get("exit_time"))
            by_basket.setdefault(row["basket_id"], []).append((pnl, w, ct))
    out: list[BasketTrade] = []
    for bid, legs in by_basket.items():
        # weighted basket pnl; respect leg side via sign already in row.pnl_pct
        total_w = sum(abs(w) for _, w, _ in legs) or 1.0
        basket_pnl_pct = sum(pnl * abs(w) for pnl, w, _ in legs) / total_w
        ct = max((c for _, _, c in legs if c is not None), default=None)
        if ct is None:
            continue
        out.append(BasketTrade(
            basket="SECRSI",
            pnl_bps=basket_pnl_pct * 100.0,
            close_dt=ct,
            source=str(p.relative_to(REPO)).replace("\\", "/"),
        ))
    return out


def _load_hypothesis_ledger(name: str, path: Path, basket_label: str) -> list[BasketTrade]:
    """Generic per-hypothesis recommendations.csv reader.

    Schema variation across hypotheses; we look for status=CLOSED + pnl_pct
    + exit_time/close_timestamp. If a basket_id-style column exists, aggregate
    legs equal-weight. Otherwise treat each row as a basket trade.
    """
    if not path.is_file():
        return []
    out_legs: dict[str, list[tuple[float, datetime | None]]] = {}
    by_row: list[tuple[float, datetime | None]] = []
    with path.open(encoding="utf-8", newline="") as fp:
        reader = csv.DictReader(fp)
        cols = reader.fieldnames or []
        has_basket_id = "basket_id" in cols
        for row in reader:
            if (row.get("status") or "").upper() != "CLOSED":
                continue
            pnl_str = row.get("pnl_pct") or row.get("pnl_bps")
            try:
                pnl = float(pnl_str)
            except (ValueError, TypeError):
                continue
            # if column was bps, keep bps; if pct, multiply
            in_bps = (row.get("pnl_bps") is not None) and (row.get("pnl_pct") is None)
            pnl_bps = pnl if in_bps else pnl * 100.0
            ct = _parse_dt(row.get("exit_time") or row.get("close_timestamp")
                           or row.get("close_date") or row.get("exit_date"))
            if has_basket_id:
                out_legs.setdefault(row["basket_id"], []).append((pnl_bps, ct))
            else:
                by_row.append((pnl_bps, ct))
    out: list[BasketTrade] = []
    src = str(path.relative_to(REPO)).replace("\\", "/")
    if has_basket_id:
        for bid, legs in out_legs.items():
            mean_bps = sum(p for p, _ in legs) / len(legs)
            ct = max((c for _, c in legs if c is not None), default=None)
            if ct is None:
                continue
            out.append(BasketTrade(basket=basket_label, pnl_bps=mean_bps,
                                   close_dt=ct, source=src))
    else:
        for pnl_bps, ct in by_row:
            if ct is None:
                continue
            out.append(BasketTrade(basket=basket_label, pnl_bps=pnl_bps,
                                   close_dt=ct, source=src))
    return out


_HYPOTHESIS_LEDGERS: dict[str, str] = {
    # basket_label -> recommendations.csv subdir
    "RELOMC-EUPHORIA": "h_2026_04_30_relomc",
    "DEFIT-NEUTRAL": "h_2026_04_30_defence_momentum/defit",
    "DEFAU-RISKON": "h_2026_04_30_defence_momentum/defau",
    "PDR-BNK-NBFC": "h_2026_04_30_pdr_bnk_nbfc",
    "H_2026_04_26_001": "h_2026_04_26_001",
}


def _load_all_trades() -> list[BasketTrade]:
    out: list[BasketTrade] = []
    out.extend(_load_closed_signals())
    out.extend(_load_secrsi_basket())
    research = REPO / "pipeline" / "data" / "research"
    for label, subdir in _HYPOTHESIS_LEDGERS.items():
        p = research / subdir / "recommendations.csv"
        out.extend(_load_hypothesis_ledger(label, p, label))
    return out


def _is_sharpe_lookup() -> dict[str, float]:
    """Read frozen IS Sharpe per basket from hypothesis-registry.jsonl.

    Deprecated INDIA_SPREAD_PAIRS baskets have no registry entry — assume IS
    Sharpe = 0.0 (Task #24 FAIL means we believe there is no edge; any
    positive forward Sharpe IS the news). Pre-registered baskets store
    their IS Sharpe in the entry's `parameters.is_sharpe_at_registration`
    field (added in Task #33+).
    """
    out: dict[str, float] = {}
    if not HYPOTHESIS_REGISTRY.is_file():
        return out
    for ln in HYPOTHESIS_REGISTRY.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            ent = json.loads(ln)
        except json.JSONDecodeError:
            continue
        hid = ent.get("hypothesis_id") or ""
        params = ent.get("parameters") or {}
        sharpe = params.get("is_sharpe_at_registration")
        if sharpe is None:
            continue
        # Map registry hypothesis_id to our basket_label space
        for label in _HYPOTHESIS_LEDGERS:
            if label.replace("-", "_").upper() in hid.upper():
                out[label] = float(sharpe)
                break
    return out


def _verdict_for(ratio: float) -> str:
    if ratio >= 0.7:
        return "HEALTHY"
    if ratio >= 0.3:
        return "WATCH"
    if ratio >= 0.0:
        return "DECAYING"
    return "KILL"


def compute_verdicts(
    trades: Iterable[BasketTrade],
    *,
    today: date | None = None,
    is_sharpe_overrides: dict[str, float] | None = None,
) -> list[DecayVerdict]:
    today = today or date.today()
    window_start_dt = datetime.combine(today - timedelta(days=ROLLING_TRADING_DAYS * 7 // 5), datetime.min.time())
    is_lookup = dict(_is_sharpe_lookup())
    if is_sharpe_overrides:
        is_lookup.update(is_sharpe_overrides)

    by_basket: dict[str, list[BasketTrade]] = {}
    for t in trades:
        if t.close_dt < window_start_dt:
            continue
        by_basket.setdefault(t.basket, []).append(t)

    out: list[DecayVerdict] = []
    for basket, group in sorted(by_basket.items()):
        n = len(group)
        sources = sorted({g.source for g in group})
        ws = min(g.close_dt for g in group).date().isoformat() if group else ""
        we = max(g.close_dt for g in group).date().isoformat() if group else ""
        if n < MIN_N_FOR_VERDICT:
            out.append(DecayVerdict(
                basket=basket, n_closed=n,
                rolling_mean_bps=0.0, rolling_std_bps=0.0, rolling_sharpe=0.0,
                is_sharpe=is_lookup.get(basket, 0.0), ratio=0.0,
                verdict="INSUFFICIENT_N",
                window_start=ws, window_end=we, sources=sources,
            ))
            continue
        bps = [g.pnl_bps for g in group]
        mean_bps = sum(bps) / n
        var_bps = sum((b - mean_bps) ** 2 for b in bps) / max(1, n - 1)
        std_bps = math.sqrt(var_bps) if var_bps > 0 else 0.0
        rolling_sharpe = (mean_bps / std_bps) if std_bps > 1e-9 else 0.0
        is_sharpe = is_lookup.get(basket, 0.0)
        denom = max(SHARPE_FLOOR, abs(is_sharpe))
        # If is_sharpe == 0 (deprecated): use rolling_sharpe sign relative to floor
        if abs(is_sharpe) < 1e-9:
            ratio = rolling_sharpe / SHARPE_FLOOR
        else:
            ratio = rolling_sharpe / denom
        out.append(DecayVerdict(
            basket=basket, n_closed=n,
            rolling_mean_bps=round(mean_bps, 2),
            rolling_std_bps=round(std_bps, 2),
            rolling_sharpe=round(rolling_sharpe, 3),
            is_sharpe=round(is_sharpe, 3),
            ratio=round(ratio, 3),
            verdict=_verdict_for(ratio),
            window_start=ws, window_end=we, sources=sources,
        ))
    return out


def main() -> int:
    today = date.today()
    trades = _load_all_trades()
    verdicts = compute_verdicts(trades, today=today)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"decay_{today.isoformat()}.json"
    payload = {
        "computed_at": datetime.utcnow().isoformat() + "Z",
        "today": today.isoformat(),
        "rolling_window_trading_days": ROLLING_TRADING_DAYS,
        "min_n_for_verdict": MIN_N_FOR_VERDICT,
        "n_baskets": len(verdicts),
        "by_verdict": _verdict_counts(verdicts),
        "verdicts": [asdict(v) for v in verdicts],
    }
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"alpha-decay -> {out_path}")
    for v in verdicts:
        if v.verdict in ("KILL", "DECAYING"):
            print(f"  {v.verdict:14s} {v.basket:35s} n={v.n_closed:3d} "
                  f"mean={v.rolling_mean_bps:+8.1f}bps "
                  f"sharpe={v.rolling_sharpe:+.2f} ratio={v.ratio:+.2f}")
    return 0


def _verdict_counts(verdicts: Iterable[DecayVerdict]) -> dict[str, int]:
    out: dict[str, int] = {}
    for v in verdicts:
        out[v.verdict] = out.get(v.verdict, 0) + 1
    return out


if __name__ == "__main__":
    raise SystemExit(main())
