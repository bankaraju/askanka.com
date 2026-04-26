"""Tests for the Tier 1 permutation null framework.

Spec: docs/superpowers/specs/2026-04-26-sigma-break-mechanical-v1-design.md
Module: pipeline/autoresearch/mechanical_replay/perm_null_t1.py

These tests use synthetic candidate-pool CSVs only — no live data.
"""
from __future__ import annotations

import csv
from pathlib import Path

import pytest

from pipeline.autoresearch.mechanical_replay import perm_null_t1


def _write_csv(path: Path, rows: list[dict]) -> None:
    fieldnames = ["signal_id", "ticker", "date", "regime", "classification",
                  "sector", "side", "exit_reason", "pnl_pct", "abs_z", "z_bucket"]
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            full = {k: r.get(k, "") for k in fieldnames}
            w.writerow(full)


def _row(ticker: str, date: str, pnl_pct: float, abs_z: float) -> dict:
    return {
        "signal_id": f"BRK-{date}-{ticker}",
        "ticker": ticker,
        "date": date,
        "regime": "NEUTRAL",
        "classification": "POSSIBLE_OPPORTUNITY",
        "sector": "Test",
        "side": "LONG",
        "exit_reason": "TIME_STOP",
        "pnl_pct": pnl_pct,
        "abs_z": abs_z,
        "z_bucket": "[2.0,3.0)" if abs_z >= 2.0 else "<2.0",
    }


# ---------------------------------------------------------------------------
# Test 1 — observed at the maximum should be extreme (p ~ 0)
# ---------------------------------------------------------------------------

def test_p_value_zero_when_observed_is_max(tmp_path: Path) -> None:
    """If every >=2σ trade is a winner AND the wider candidate pool is
    half losers, sampling 42 random rows should very rarely hit 100%."""
    rows: list[dict] = []
    # 42 winners on >=2σ slice
    for i in range(42):
        rows.append(_row(f"TKR{i:03d}", f"2026-01-{(i % 28) + 1:02d}", 1.0, 2.5))
    # 346 candidate-pool rows, half winners
    for i in range(346):
        pnl = 1.0 if i % 2 == 0 else -1.0
        # Use mix of different tickers to avoid one ticker dominating
        rows.append(_row(f"PCAND{i:03d}", f"2026-02-{(i % 27) + 1:02d}", pnl, 0.5))

    csv_path = tmp_path / "synthetic_max.csv"
    _write_csv(csv_path, rows)

    out = perm_null_t1.main(
        in_sample_csv=csv_path,
        n_perms=20_000,
        seed=42,
    )

    assert out["n_observed_trades"] == 42
    assert out["observed_hit_rate_pct"] == pytest.approx(100.0, abs=1e-6)
    p_a = out["null_a_random_sampling"]["p_value"]
    assert p_a < 0.001, (
        f"Null A p-value should be very small when observed is the maximum, got {p_a}"
    )


# ---------------------------------------------------------------------------
# Test 2 — observed at population median should be a non-event (p > 0.4)
# ---------------------------------------------------------------------------

def test_p_value_one_when_observed_at_population_median(tmp_path: Path) -> None:
    """If the >=2σ slice has exactly the same hit rate as the candidate pool,
    a random sample should beat it about half the time, so p_A should be near 0.5."""
    rows: list[dict] = []
    # 42 sigma trades, ~50% hit rate (21 wins / 21 losses)
    for i in range(42):
        pnl = 1.0 if i % 2 == 0 else -1.0
        rows.append(_row(f"SIG{i:03d}", f"2026-01-{(i % 28) + 1:02d}", pnl, 2.5))
    # 346 candidate rows with ~50% hit rate as well (so observed == population median)
    for i in range(346):
        pnl = 1.0 if i % 2 == 0 else -1.0
        rows.append(_row(f"P{i:03d}", f"2026-02-{(i % 27) + 1:02d}", pnl, 0.5))

    csv_path = tmp_path / "synthetic_median.csv"
    _write_csv(csv_path, rows)

    out = perm_null_t1.main(
        in_sample_csv=csv_path,
        n_perms=20_000,
        seed=7,
    )

    assert out["n_observed_trades"] == 42
    assert out["observed_hit_rate_pct"] == pytest.approx(50.0, abs=1e-6)
    p_a = out["null_a_random_sampling"]["p_value"]
    # When observed equals the population median, P(perm >= observed) should be
    # near 0.5; well above 0.4 in either direction.
    assert p_a > 0.4, (
        f"Null A p-value should be near 0.5 when observed is at median, got {p_a}"
    )


# ---------------------------------------------------------------------------
# Test 3 — Null B drops tickers with insufficient days
# ---------------------------------------------------------------------------

def test_null_b_drops_tickers_with_insufficient_days(tmp_path: Path) -> None:
    """Tickers with < min_ticker_days candidate-day P&Ls must be dropped."""
    rows: list[dict] = []
    # Sigma trade for TICKER_A — has 10 candidate days (eligible)
    rows.append(_row("TICKER_A", "2026-01-01", 1.0, 2.5))
    # Sigma trade for TICKER_B — only has 2 candidate days (must be dropped)
    rows.append(_row("TICKER_B", "2026-01-02", 1.0, 2.5))

    # TICKER_A has 10 sub-2σ candidate days
    for d in range(10):
        rows.append(_row("TICKER_A", f"2026-02-{d+1:02d}", 1.0 if d % 2 else -1.0, 0.5))
    # TICKER_B only has 1 additional candidate day (so total = 2)
    rows.append(_row("TICKER_B", "2026-02-01", -1.0, 0.5))

    csv_path = tmp_path / "synthetic_drop.csv"
    _write_csv(csv_path, rows)

    out = perm_null_t1.main(
        in_sample_csv=csv_path,
        n_perms=1_000,
        seed=99,
        min_ticker_days=5,
    )

    nb = out["null_b_within_ticker_shuffle"]
    assert nb["n_tickers_dropped_due_to_insufficient_days"] == 1
    assert nb["n_effective"] == 1
    dropped = {d["ticker"]: d["pool_size"] for d in nb["dropped_tickers"]}
    assert "TICKER_B" in dropped
    assert dropped["TICKER_B"] == 2
