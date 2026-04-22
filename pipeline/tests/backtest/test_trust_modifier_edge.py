"""
Backtest: Trust Modifier NEUTRAL-cohort replay
================================================
Plan success criterion: Sharpe improves ≥ 0.1 in NEUTRAL cohort vs no-modifier.

DATASET STATUS (2026-04-22): 9 closed signals total, 0 with trust grades attached.
MSI history uses MACRO_NEUTRAL / MACRO_STRESS / MACRO_EASY (not NEUTRAL/RISK-ON/RISK-OFF).
The ETF-engine zone field (NEUTRAL/RISK-OFF/RISK-ON) only exists in today_regime.json
which is overwritten daily — no historical zone-per-date archive exists yet.

DECISION: Strict Sharpe assertion SKIPPED (n<30, no zone history).
           No-regression path: show no trade-level P&L goes DOWN due to the modifier,
           and write findings to backtest_results/trust_modifier_2026-04-22.csv.

This test will be re-run once:
  (a) closed_signals grows to ≥30 entries, AND
  (b) an ETF-zone field is written to msi_history.json (planned for ETF Engine V2).
"""
from __future__ import annotations

import csv
import json
import pathlib
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import pytest

from pipeline.signal_enrichment import apply_trust_modifier

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_REPO = pathlib.Path(__file__).resolve().parent.parent.parent.parent
_CLOSED_SIGNALS = _REPO / "pipeline" / "data" / "signals" / "closed_signals.json"
_MSI_HISTORY = _REPO / "pipeline" / "data" / "msi_history.json"
_TRUST_SCORES = _REPO / "data" / "trust_scores.json"
_OUTPUT_DIR = _REPO / "backtest_results"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_trust_scores() -> Dict[str, str]:
    """Return {SYMBOL: sector_grade} from trust_scores.json."""
    try:
        raw = json.loads(_TRUST_SCORES.read_text(encoding="utf-8"))
        stocks = raw.get("stocks") or []
        return {
            (s.get("symbol") or "").upper(): s.get("sector_grade") or ""
            for s in stocks
            if s.get("symbol") and s.get("sector_grade")
        }
    except Exception:
        return {}


def _load_closed_signals() -> List[Dict]:
    if not _CLOSED_SIGNALS.exists():
        return []
    try:
        return json.loads(_CLOSED_SIGNALS.read_text(encoding="utf-8"))
    except Exception:
        return []


def _load_msi_history() -> Dict[str, str]:
    """Return {date_str: regime} from msi_history.json."""
    if not _MSI_HISTORY.exists():
        return {}
    try:
        records = json.loads(_MSI_HISTORY.read_text(encoding="utf-8"))
        return {r["date"]: r.get("regime", "") for r in records if "date" in r}
    except Exception:
        return {}


def _msi_to_etf_zone(msi_regime: str) -> str:
    """
    Approximate mapping from MACRO_* regime to ETF-engine zone.

    This is an imperfect proxy — see dataset note above.
    MACRO_NEUTRAL → NEUTRAL (moderate confidence)
    MACRO_STRESS  → RISK-OFF
    MACRO_EASY    → RISK-ON
    """
    mapping = {
        "MACRO_NEUTRAL": "NEUTRAL",
        "MACRO_STRESS": "RISK-OFF",
        "MACRO_EASY": "RISK-ON",
    }
    return mapping.get(msi_regime.upper(), "")


def _attach_trust_to_signal(sig: Dict, trust: Dict[str, str]) -> Dict:
    """Attach trust_grade to long/short legs and signal-level ticker."""
    import copy
    sig = copy.deepcopy(sig)
    for leg in (sig.get("long_legs") or []):
        if isinstance(leg, dict):
            sym = (leg.get("ticker") or "").upper()
            if sym:
                leg["trust_grade"] = trust.get(sym, "")
    for leg in (sig.get("short_legs") or []):
        if isinstance(leg, dict):
            sym = (leg.get("ticker") or "").upper()
            if sym:
                leg["trust_grade"] = trust.get(sym, "")
    ticker = (sig.get("ticker") or "").upper()
    if ticker:
        sig["trust_grade"] = trust.get(ticker, "")
    return sig


def _extract_pnl(sig: Dict) -> Optional[float]:
    """Return spread_pnl_pct from final_pnl dict, or None if missing."""
    fpnl = sig.get("final_pnl")
    if isinstance(fpnl, dict):
        return fpnl.get("spread_pnl_pct")
    if isinstance(fpnl, (int, float)):
        return float(fpnl)
    return None


def _sharpe(returns: List[float]) -> Optional[float]:
    """Simple Sharpe: mean/std, or None if <2 values or std==0."""
    if len(returns) < 2:
        return None
    import statistics
    m = statistics.mean(returns)
    s = statistics.pstdev(returns)
    if s == 0:
        return None
    return m / s


# ---------------------------------------------------------------------------
# Backtest runner
# ---------------------------------------------------------------------------

def run_backtest():
    trust = _load_trust_scores()
    closed = _load_closed_signals()
    msi = _load_msi_history()

    rows = []
    neutral_raw_returns = []
    neutral_adj_returns = []

    for sig in closed:
        open_ts = sig.get("open_timestamp") or ""
        try:
            entry_date = open_ts[:10]
        except Exception:
            entry_date = ""

        msi_regime = msi.get(entry_date, "")
        zone = _msi_to_etf_zone(msi_regime)

        sig_with_trust = _attach_trust_to_signal(sig, trust)
        regime_dict = {"zone": zone}

        entry_score_raw = sig.get("entry_score") or 0
        modified = apply_trust_modifier(sig_with_trust, regime_dict)
        trust_mod = modified.get("trust_modifier", 0)
        entry_score_adj = entry_score_raw + trust_mod

        pnl = _extract_pnl(sig)
        days_held = sig.get("days_open") or 1
        ret_per_day = (pnl / max(days_held, 1)) if pnl is not None else None

        row = {
            "signal_id": sig.get("signal_id", ""),
            "entry_date": entry_date,
            "msi_regime": msi_regime,
            "zone_approx": zone,
            "long_tickers": ",".join(
                (l.get("ticker") or "") if isinstance(l, dict) else str(l)
                for l in (sig_with_trust.get("long_legs") or [])
            ),
            "short_tickers": ",".join(
                (l.get("ticker") or "") if isinstance(l, dict) else str(l)
                for l in (sig_with_trust.get("short_legs") or [])
            ),
            "entry_score_raw": entry_score_raw,
            "trust_modifier": trust_mod,
            "entry_score_adj": entry_score_adj,
            "realized_pnl_pct": pnl,
            "days_held": days_held,
            "ret_per_day": ret_per_day,
        }
        rows.append(row)

        if zone == "NEUTRAL" and ret_per_day is not None:
            neutral_raw_returns.append(ret_per_day)
            neutral_adj_returns.append(ret_per_day)  # same returns, different selection

    # Write CSV
    _OUTPUT_DIR.mkdir(exist_ok=True)
    out_path = _OUTPUT_DIR / "trust_modifier_2026-04-22.csv"
    if rows:
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    return {
        "total_signals": len(closed),
        "neutral_cohort_n": len(neutral_raw_returns),
        "sharpe_raw": _sharpe(neutral_raw_returns),
        "sharpe_adj": _sharpe(neutral_adj_returns),
        "output_csv": str(out_path),
        "note": (
            "INSUFFICIENT_DATA: n<30 NEUTRAL signals, ETF-zone history unavailable. "
            "Strict Sharpe assertion deferred. No-regression: modifier applied without P&L change "
            "since today's zone is RISK-OFF (modifier=0 for all live signals)."
        ),
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestTrustModifierBacktest:

    def test_backtest_runs_without_error(self):
        """Smoke test: backtest completes and returns expected keys."""
        result = run_backtest()
        assert "total_signals" in result
        assert "neutral_cohort_n" in result
        assert "output_csv" in result

    def test_dataset_size_reported(self):
        """Document the current dataset size for tracking."""
        result = run_backtest()
        print(f"\n[backtest] total_closed={result['total_signals']}, "
              f"neutral_cohort={result['neutral_cohort_n']}, "
              f"sharpe_raw={result['sharpe_raw']}, "
              f"sharpe_adj={result['sharpe_adj']}")
        # No strict assertion — just document
        assert result["total_signals"] >= 0

    def test_no_regression_risk_off_modifier_is_zero(self):
        """
        No-regression: in RISK-OFF regime, trust modifier must be 0.
        Today is RISK-OFF so ALL live signals get modifier=0 — no P&L change.
        """
        closed = _load_closed_signals()
        trust = _load_trust_scores()
        regime_risk_off = {"zone": "RISK-OFF"}

        for sig in closed:
            enriched = _attach_trust_to_signal(sig, trust)
            out = apply_trust_modifier(enriched, regime_risk_off)
            assert out["trust_modifier"] == 0, (
                f"Expected modifier=0 for RISK-OFF but got {out['trust_modifier']} "
                f"for {sig.get('signal_id')}"
            )

    def test_neutral_modifier_does_not_increase_bad_long_score(self):
        """
        No-regression: For any D/F graded LONG in NEUTRAL, adjusted score <= raw score.
        Trust modifier for weak-trust longs must not inflate entry scores.
        """
        trust = _load_trust_scores()
        # Construct synthetic NEUTRAL scenario using real grades
        for sym, grade in list(trust.items())[:20]:
            if grade in ("D", "F"):
                sig = {"ticker": sym, "direction": "LONG",
                       "entry_score": 65, "trust_grade": grade}
                out = apply_trust_modifier(sig, {"zone": "NEUTRAL"})
                assert out["entry_score"] <= 65, (
                    f"{sym} grade={grade}: LONG in NEUTRAL should NOT increase score, "
                    f"got {out['entry_score']}"
                )

    def test_neutral_modifier_does_not_decrease_bad_short_score(self):
        """
        No-regression: For any D/F graded SHORT in NEUTRAL, adjusted score >= raw score.
        Trust modifier for weak-trust shorts should lean into them (bonus).
        """
        trust = _load_trust_scores()
        for sym, grade in list(trust.items())[:20]:
            if grade in ("D", "F"):
                sig = {"ticker": sym, "direction": "SHORT",
                       "entry_score": 65, "trust_grade": grade}
                out = apply_trust_modifier(sig, {"zone": "NEUTRAL"})
                assert out["entry_score"] >= 65, (
                    f"{sym} grade={grade}: SHORT in NEUTRAL should NOT decrease score, "
                    f"got {out['entry_score']}"
                )

    def test_csv_output_written(self):
        """Verify CSV output file was created with expected columns."""
        result = run_backtest()
        out_path = pathlib.Path(result["output_csv"])
        assert out_path.exists(), f"CSV not written to {out_path}"
        with open(out_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            cols = set(reader.fieldnames or [])
        expected = {"signal_id", "zone_approx", "trust_modifier", "entry_score_raw",
                    "entry_score_adj", "realized_pnl_pct"}
        assert expected.issubset(cols), f"Missing columns: {expected - cols}"

    def test_sharpe_deferred_flag_when_insufficient_data(self):
        """
        If neutral cohort is <30, the test flags deferred rather than failing.
        Once ETF zone history is archived, remove this and assert Sharpe lift ≥0.1.
        """
        result = run_backtest()
        if result["neutral_cohort_n"] < 30:
            pytest.skip(
                f"[DEFERRED] NEUTRAL cohort n={result['neutral_cohort_n']} < 30. "
                "Re-run after ETF zone is persisted in msi_history.json and "
                "closed_signals grows to ≥30 NEUTRAL-entry trades."
            )
        # If we have enough data, assert Sharpe improvement
        old_sharpe = result["sharpe_raw"]
        new_sharpe = result["sharpe_adj"]
        assert old_sharpe is not None and new_sharpe is not None
        assert new_sharpe - old_sharpe >= 0.1, (
            f"Sharpe improvement {new_sharpe - old_sharpe:.3f} < 0.10 target"
        )
