"""End-to-end smoke for the H-2026-04-24-003 runner.

Generates a 40-event synthetic panel that straddles the v2 train/test cutoff
(2025-05-31), monkeypatches the price/regime/vix/nifty loaders, and runs
the full orchestration with tiny budgets (n_shuffles=20, 3-point alpha grid).

Asserts: gate_checklist.json emits with hypothesis_id == 'H-2026-04-24-003'
and a decision in {PASS, FAIL, PARTIAL}. Metric values are not checked --
the point is to exercise the full pipeline without errors, not to validate
alpha on synthetic data.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from pipeline.autoresearch.phase_c_cross_sectional import runner as R


def _build_synthetic_panel() -> dict:
    """Return a dict bundle of synthetic inputs for the runner.

    - 40 events across 4 tickers, 30 pre-2025-05-31 (train) + 10 post (test).
    - z_panel with 500 business days of history so min_history_days=60 gate passes.
    - regime_history, vix_series, nifty_returns aligned on the same index.
    - Each event has same-sign z on T and T-1 at |z|>=3 so the asymmetric
      filter (current>=3, prior>=2) keeps every event.
    """
    rng = np.random.default_rng(42)
    tickers = ["ATKR", "BTKR", "CTKR", "DTKR"]
    dates = pd.bdate_range("2023-06-01", "2026-04-23")
    z_panel = pd.DataFrame(
        rng.standard_normal((len(dates), len(tickers))) * 0.5,
        index=dates, columns=tickers,
    )

    # Select every 10th business day (~2 weeks apart) from the panel index so
    # each event date is guaranteed to exist in z_panel.index. 30 pre-cutoff
    # (train, <=2025-05-31) + 10 post-cutoff (test, >2025-05-31).
    pre_cut = dates[(dates >= "2024-01-02") & (dates <= "2025-05-20")][::10][:30]
    post_cut = dates[(dates >= "2025-07-01") & (dates <= "2026-04-23")][::10][:10]
    event_dates = list(pre_cut) + list(post_cut)
    event_dates = event_dates[:40]

    rows = []
    for i, d in enumerate(event_dates):
        tkr = tickers[i % len(tickers)]
        sign = 1 if i % 2 == 0 else -1
        z_t = 3.1 * sign
        z_prev = 3.0 * sign
        # stamp these onto the z_panel so the filter's T / T-1 checks pass
        z_panel.loc[d, tkr] = z_t
        d_prev = dates[dates.get_loc(d) - 1]
        z_panel.loc[d_prev, tkr] = z_prev
        rows.append({
            "ticker": tkr,
            "date": d,
            "z": z_t,
            "today_resid": 0.03 * sign,
            "today_ret": 0.04 * sign,
            "next_resid": 0.005 * sign,
            "next_ret": 0.5 * sign + rng.normal(0, 0.3),
            "direction": "UP" if sign > 0 else "DOWN",
            "actual_return_pct": 4.0 * sign,
            "expected_return_pct": 0.3 * sign,
        })
    events_df = pd.DataFrame(rows)

    regime_history = pd.DataFrame({"regime": ["NEUTRAL"] * len(dates)}, index=dates)
    vix_series = pd.Series(15.0, index=dates)
    nifty_returns = pd.Series(rng.normal(0, 0.5, len(dates)), index=dates)

    # sector map: at least 3 tickers per sector so feature_builder's <3 guard
    # does not zero everything. Put A/B/C in "SectorX", D in "SectorY" (and
    # SectorY will hit the <3 safeguard -- that is fine, it just zeroes).
    sector_map = {"ATKR": "SectorX", "BTKR": "SectorX", "CTKR": "SectorX",
                  "DTKR": "SectorY"}

    return {
        "events": events_df, "z_panel": z_panel, "regime": regime_history,
        "vix": vix_series, "nifty": nifty_returns, "sector_map": sector_map,
    }


def test_smoke_happy_path(tmp_path, monkeypatch):
    bundle = _build_synthetic_panel()

    monkeypatch.setattr(R, "_load_parent_events", lambda _p: bundle["events"])
    # load_price_panel, load_sector_map, compute_residuals live in the runner
    # module as top-level imports -- monkeypatch them on the runner namespace.
    monkeypatch.setattr(R, "load_price_panel", lambda tickers: bundle["z_panel"])
    monkeypatch.setattr(R, "load_sector_map", lambda: bundle["sector_map"])
    monkeypatch.setattr(
        R, "compute_residuals",
        lambda panel, sm: (pd.DataFrame(), pd.DataFrame(), bundle["z_panel"]),
    )
    monkeypatch.setattr(R, "_load_regime_history", lambda: bundle["regime"])
    monkeypatch.setattr(R, "_load_vix_series", lambda: bundle["vix"])
    monkeypatch.setattr(R, "_load_nifty_returns", lambda: bundle["nifty"])

    # Force tickers discovery to return our synthetic set. _FNO_DIR.glob hits
    # the real disk; monkey _FNO_DIR to a tmp dir with fake CSV files.
    ticker_dir = tmp_path / "fake_fno"
    ticker_dir.mkdir()
    for tkr in bundle["sector_map"]:
        (ticker_dir / f"{tkr}.csv").write_text("Date,Close\n2024-01-01,100\n")
    monkeypatch.setattr(R, "_FNO_DIR", ticker_dir)

    out_dir = tmp_path / "smoke_run"
    # Manifest builder sha256s events_path; create a stub so it exists on disk.
    events_path = tmp_path / "unused.json"
    events_path.write_text("{}")
    result = R.run(
        events_path=events_path,
        out_dir=out_dir,
        n_shuffles=20,
        n_workers=1,
        seed=42,
        alpha_grid=np.logspace(-3, 0, 3),
        z_threshold_current=3.0,
        z_threshold_prior=3.0,  # synthetic events stamped at |z|>=3 on both days
        persistence_days=2,
        min_history_days=5,
    )

    assert (out_dir / "gate_checklist.json").exists()
    gc = json.loads((out_dir / "gate_checklist.json").read_text())
    assert gc["hypothesis_id"] == "H-2026-04-24-003"
    assert gc["decision"] in {"PASS", "FAIL", "PARTIAL"}
