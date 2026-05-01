"""Contract tests for H-2026-05-01-phase-c-mr-karpathy-v1 engine skeleton.

Locks the public surface so future edits don't accidentally drift from the spec
without an explicit code change in this test file.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from pipeline.research.h_2026_05_01_phase_c_mr_karpathy import (
    HOLDOUT_CLOSE,
    HOLDOUT_EXTEND_TO,
    HOLDOUT_OPEN,
    HYPOTHESIS_ID,
    MIN_HOLDOUT_N,
    SPEC_REF,
)
from pipeline.research.h_2026_05_01_phase_c_mr_karpathy import event_day_skip
from pipeline.research.h_2026_05_01_phase_c_mr_karpathy.feature_library import (
    FEATURE_NAMES,
    SnapContext,
    compute_features,
)
from pipeline.research.h_2026_05_01_phase_c_mr_karpathy.mr_engine import (
    ATR_MULTIPLIER,
    NOTIONAL_INR_PER_LEG,
    SNAP_GRID_IST,
    TIME_STOP_IST,
    holdout_meta,
    summarize,
    trade_from_close,
    Trade,
)
from pipeline.research.h_2026_05_01_phase_c_mr_karpathy.mr_signal_generator import (
    KarpathyCell,
    Signal,
    _direction_for_mean_revert,
    feature_subset_size,
    feature_universe,
    generate_signal,
)
from pipeline.research.h_2026_05_01_phase_c_mr_karpathy.karpathy_search import (
    ALPHA_GRID,
    BH_FDR_ALPHA,
    FRAGILITY_HALF_SHARPE_MIN,
    MARGIN_DELTA_SHARPE_MIN,
    THRESHOLD_GRID,
    TRAIN_CLOSE,
    TRAIN_HALF_SPLIT,
    TRAIN_OPEN,
    feature_subset_combinations,
    grid_size,
)


REPO = Path(__file__).resolve().parents[3]


# ---- §1 hypothesis identity ------------------------------------------------

def test_hypothesis_id_locked():
    assert HYPOTHESIS_ID == "H-2026-05-01-phase-c-mr-karpathy-v1"


def test_spec_ref_exists():
    assert (REPO / SPEC_REF).is_file()


def test_holdout_window_locked():
    assert HOLDOUT_OPEN == "2026-05-04"
    assert HOLDOUT_CLOSE == "2026-08-01"
    assert HOLDOUT_EXTEND_TO == "2026-10-31"
    assert MIN_HOLDOUT_N == 100


def test_registered_in_jsonl():
    reg = REPO / "docs" / "superpowers" / "hypothesis-registry.jsonl"
    assert reg.is_file()
    found = False
    for line in reg.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("hypothesis_id") == HYPOTHESIS_ID:
            assert row["terminal_state"] == "PRE_REGISTERED"
            assert row["holdout_window"] == [HOLDOUT_OPEN, HOLDOUT_CLOSE]
            assert row["min_holdout_observations"] == MIN_HOLDOUT_N
            assert row["single_touch_locked"] is True
            found = True
    assert found, "registry row missing"


# ---- §3 universe frozen ----------------------------------------------------

def test_frozen_universe_present_and_100():
    p = REPO / "pipeline" / "research" / "h_2026_05_01_phase_c_mr_karpathy" / "universe_frozen.json"
    assert p.is_file()
    payload = json.loads(p.read_text(encoding="utf-8"))
    assert payload["count"] == 100
    assert len(payload["tickers"]) == 100
    # Top by ADV cap should be HDFCBANK on the 2026-04-30 snapshot
    assert payload["tickers"][0] == "HDFCBANK"


# ---- §4.1 event calendar ---------------------------------------------------

def test_event_calendar_present():
    p = REPO / "pipeline" / "research" / "h_2026_05_01_phase_c_mr_karpathy" / "event_calendar.json"
    assert p.is_file()


def test_event_calendar_includes_2024_06_04_election():
    cal = json.loads(
        (REPO / "pipeline" / "research" / "h_2026_05_01_phase_c_mr_karpathy"
         / "event_calendar.json").read_text(encoding="utf-8")
    )
    dates = {e["date"] for e in cal["events"] if e["type"] == "ELECTION_RESULTS"}
    assert "2024-06-04" in dates


def test_event_day_skip_buffer_window():
    event_day_skip.reload_calendar()
    # Election day +/- 1
    assert event_day_skip.is_event_day("2024-06-03")
    assert event_day_skip.is_event_day("2024-06-04")
    assert event_day_skip.is_event_day("2024-06-05")
    # Non-event date
    assert not event_day_skip.is_event_day("2024-07-15")


# ---- §5 feature library ----------------------------------------------------

def test_feature_names_count_8():
    assert len(FEATURE_NAMES) == 8


def test_feature_names_include_all_8_spec_fields():
    expected = {
        "xs_dispersion_1100",
        "realized_implied_gap",
        "breadth_pct_above_20dma",
        "event_day_flag",
        "sector_rs_zscore",
        "xsec_corr_delta_5d",
        "vwap_dev_zscore",
        "news_density_zscore",
    }
    assert set(FEATURE_NAMES) == expected


def test_compute_features_returns_8_keys_even_with_empty_ctx():
    ctx = SnapContext(
        date="2026-05-04",
        snap_t="11:00:00",
        ticker="RELIANCE",
        sector="ENERGY",
        snap_px=2950.0,
        intraday_ret_pct=-1.5,
    )
    feats = compute_features(ctx)
    assert set(feats.keys()) == set(FEATURE_NAMES)


def test_event_day_flag_is_binary():
    ctx_yes = SnapContext(
        date="2024-06-04", snap_t="11:00:00", ticker="X",
        sector="S", snap_px=100.0, intraday_ret_pct=0.0, is_event_day=True,
    )
    ctx_no = SnapContext(
        date="2024-07-15", snap_t="11:00:00", ticker="X",
        sector="S", snap_px=100.0, intraday_ret_pct=0.0, is_event_day=False,
    )
    assert compute_features(ctx_yes)["event_day_flag"] == 1.0
    assert compute_features(ctx_no)["event_day_flag"] == 0.0


# ---- §6 signal generator ---------------------------------------------------

def test_feature_subset_size_is_six():
    assert feature_subset_size() == 6


def test_feature_universe_is_eight():
    assert len(feature_universe()) == 8


def test_direction_for_mean_revert_signs():
    assert _direction_for_mean_revert(5.0) == "SHORT"     # overshoot up -> revert down
    assert _direction_for_mean_revert(-5.0) == "LONG"     # overshoot down -> revert up
    assert _direction_for_mean_revert(0.0) is None
    assert _direction_for_mean_revert(float("nan")) is None


def _make_ctx(date="2026-05-05", **kw):
    base = dict(
        date=date,
        snap_t="11:00:00",
        ticker="RELIANCE",
        sector="ENERGY",
        snap_px=2950.0,
        intraday_ret_pct=-2.5,
    )
    base.update(kw)
    return SnapContext(**base)


def test_generate_signal_filters_non_possible_opportunity():
    sig = generate_signal(
        _make_ctx(),
        z_score=4.5,
        expected_ret_pct=0.5,
        classification="OPPORTUNITY_LAG",
        cell=None,
    )
    assert sig is None


def test_generate_signal_filters_low_abs_z():
    sig = generate_signal(
        _make_ctx(),
        z_score=2.5,
        expected_ret_pct=0.5,
        classification="POSSIBLE_OPPORTUNITY",
        cell=None,
    )
    assert sig is None


def test_generate_signal_filters_event_day(monkeypatch):
    monkeypatch.setattr(
        "pipeline.research.h_2026_05_01_phase_c_mr_karpathy.mr_signal_generator.is_event_day",
        lambda d: True,
    )
    monkeypatch.setattr(
        "pipeline.research.h_2026_05_01_phase_c_mr_karpathy.mr_signal_generator.regime_for_date",
        lambda d: "RISK-ON",
    )
    monkeypatch.setattr(
        "pipeline.research.h_2026_05_01_phase_c_mr_karpathy.mr_signal_generator.regime_allowed",
        lambda d: True,
    )
    sig = generate_signal(
        _make_ctx(),
        z_score=-4.5,
        expected_ret_pct=0.5,
        classification="POSSIBLE_OPPORTUNITY",
        cell=None,
    )
    assert sig is None


def test_generate_signal_filters_neutral_regime(monkeypatch):
    monkeypatch.setattr(
        "pipeline.research.h_2026_05_01_phase_c_mr_karpathy.mr_signal_generator.is_event_day",
        lambda d: False,
    )
    monkeypatch.setattr(
        "pipeline.research.h_2026_05_01_phase_c_mr_karpathy.mr_signal_generator.regime_for_date",
        lambda d: "NEUTRAL",
    )
    monkeypatch.setattr(
        "pipeline.research.h_2026_05_01_phase_c_mr_karpathy.mr_signal_generator.regime_allowed",
        lambda d: False,
    )
    sig = generate_signal(
        _make_ctx(),
        z_score=-4.5,
        expected_ret_pct=0.5,
        classification="POSSIBLE_OPPORTUNITY",
        cell=None,
    )
    assert sig is None


def test_generate_signal_passes_no_qualifier(monkeypatch):
    monkeypatch.setattr(
        "pipeline.research.h_2026_05_01_phase_c_mr_karpathy.mr_signal_generator.is_event_day",
        lambda d: False,
    )
    monkeypatch.setattr(
        "pipeline.research.h_2026_05_01_phase_c_mr_karpathy.mr_signal_generator.regime_for_date",
        lambda d: "RISK-ON",
    )
    monkeypatch.setattr(
        "pipeline.research.h_2026_05_01_phase_c_mr_karpathy.mr_signal_generator.regime_allowed",
        lambda d: True,
    )
    sig = generate_signal(
        _make_ctx(),
        z_score=-4.5,
        expected_ret_pct=0.5,
        classification="POSSIBLE_OPPORTUNITY",
        cell=None,
    )
    assert sig is not None
    assert sig.side == "LONG"
    assert sig.regime == "RISK-ON"
    assert sig.classification == "POSSIBLE_OPPORTUNITY"


def test_generate_signal_filters_below_qualifier_threshold(monkeypatch):
    monkeypatch.setattr(
        "pipeline.research.h_2026_05_01_phase_c_mr_karpathy.mr_signal_generator.is_event_day",
        lambda d: False,
    )
    monkeypatch.setattr(
        "pipeline.research.h_2026_05_01_phase_c_mr_karpathy.mr_signal_generator.regime_for_date",
        lambda d: "CAUTION",
    )
    monkeypatch.setattr(
        "pipeline.research.h_2026_05_01_phase_c_mr_karpathy.mr_signal_generator.regime_allowed",
        lambda d: True,
    )
    cell = KarpathyCell(
        feature_subset=("event_day_flag",),
        coefficients={"event_day_flag": 1.0},
        intercept=0.0,
        threshold=0.5,        # need >= 0.5; but event_day_flag = 0 -> score 0
        chosen_at="2026-05-01T07:23:00+05:30",
    )
    sig = generate_signal(
        _make_ctx(),
        z_score=-4.5,
        expected_ret_pct=0.5,
        classification="POSSIBLE_OPPORTUNITY",
        cell=cell,
    )
    assert sig is None


# ---- §7 trade rules + engine helpers --------------------------------------

def test_snap_grid_locked_to_19_steps_09_30_to_14_00():
    assert SNAP_GRID_IST[0] == "09:30:00"
    assert SNAP_GRID_IST[-1] == "14:00:00"
    assert len(SNAP_GRID_IST) == 19
    # 15-minute step
    assert SNAP_GRID_IST[1] == "09:45:00"


def test_time_stop_is_1430_ist():
    assert TIME_STOP_IST == "14:30:00"


def test_atr_multiplier_two():
    assert ATR_MULTIPLIER == 2.0


def test_notional_50000_per_leg():
    assert NOTIONAL_INR_PER_LEG == 50_000


def test_trade_from_close_long_pnl_positive_after_revert():
    sig = Signal(
        hypothesis_id=HYPOTHESIS_ID,
        date="2026-05-05", snap_t="11:00:00", ticker="RELIANCE",
        sector="ENERGY", snap_px=2900.0, intraday_ret_pct=-2.5,
        z_score=-4.5, expected_ret_pct=0.5,
        classification="POSSIBLE_OPPORTUNITY", side="LONG", regime="RISK-ON",
    )
    t = trade_from_close(sig, exit_px=2929.0, exit_t="14:30:00", exit_reason="TIME_STOP_1430")
    # +1% gross = +100 bps; minus 10 bps S0 cost = +90 bps
    assert math.isclose(t.pnl_bps_S0, 1.0 / 2900.0 * 10000.0 * 29 - 10.0, rel_tol=1e-3)


def test_trade_from_close_short_pnl_inverts():
    sig = Signal(
        hypothesis_id=HYPOTHESIS_ID,
        date="2026-05-05", snap_t="11:00:00", ticker="RELIANCE",
        sector="ENERGY", snap_px=2900.0, intraday_ret_pct=2.5,
        z_score=4.5, expected_ret_pct=0.5,
        classification="POSSIBLE_OPPORTUNITY", side="SHORT", regime="RISK-ON",
    )
    t = trade_from_close(sig, exit_px=2871.0, exit_t="14:30:00", exit_reason="TIME_STOP_1430")
    # SHORT entry 2900 exit 2871 = +29 INR per share -> ~+100 bps pre-cost
    assert t.pnl_bps_S0 > 0


def test_summarize_handles_empty():
    assert summarize([], "S1")["n"] == 0


def test_summarize_signs_correct():
    trades = [
        Trade(HYPOTHESIS_ID, "2026-05-05", "11:00:00", "X", "Y", "LONG", "RISK-ON",
              100.0, 101.0, "14:30:00", "TIME_STOP_1430", -4.5, -2.5,
              90.0, 70.0, 50.0),
        Trade(HYPOTHESIS_ID, "2026-05-06", "11:00:00", "X", "Y", "LONG", "CAUTION",
              100.0, 99.5, "14:30:00", "TIME_STOP_1430", -4.5, -2.5,
              -60.0, -80.0, -100.0),
    ]
    s = summarize(trades, "S0")
    assert s["n"] == 2
    assert math.isclose(s["mean_bps"], (90.0 - 60.0) / 2, rel_tol=1e-6)


def test_holdout_meta_keys():
    m = holdout_meta()
    assert m["hypothesis_id"] == HYPOTHESIS_ID
    assert m["holdout_open"] == HOLDOUT_OPEN
    assert m["holdout_close"] == HOLDOUT_CLOSE
    assert m["min_n"] == MIN_HOLDOUT_N


# ---- §8 karpathy search constants ------------------------------------------

def test_grid_size_is_448():
    assert grid_size() == 28 * 4 * 4
    assert grid_size() == 448


def test_alpha_threshold_grids_locked():
    assert ALPHA_GRID == (0.001, 0.01, 0.1, 1.0)
    assert THRESHOLD_GRID == (0.0, 0.1, 0.2, 0.3)


def test_train_window_locked():
    assert TRAIN_OPEN == "2021-05-01"
    assert TRAIN_CLOSE == "2024-04-30"
    assert TRAIN_HALF_SPLIT == "2022-10-31"


def test_search_constants_locked():
    assert BH_FDR_ALPHA == 0.05
    assert FRAGILITY_HALF_SHARPE_MIN == 0.5
    assert MARGIN_DELTA_SHARPE_MIN == 0.3


def test_28_subsets_of_size_6():
    subs = feature_subset_combinations()
    assert len(subs) == 28
    for s in subs:
        assert len(s) == 6
        for name in s:
            assert name in FEATURE_NAMES


# ---- §9 verdict skeleton ---------------------------------------------------

def test_verdict_writer_skeleton_runs():
    from pipeline.research.h_2026_05_01_phase_c_mr_karpathy.verdict_writer import run as verdict_run

    v = verdict_run(verdict_date="2026-05-01")
    assert v.hypothesis_id == HYPOTHESIS_ID
    # Empty ledger -> AUTO_EXTEND (still before HOLDOUT_EXTEND_TO)
    assert v.decision == "AUTO_EXTEND"
    assert v.n == 0


def test_holdout_runner_public_api(monkeypatch, tmp_path):
    """Lock the public surface: open_today / close_today / run_for_date all return
    a summary dict with the canonical keys, and short-circuit when the regime
    label is missing (no cache I/O incurred)."""
    from pipeline.research.h_2026_05_01_phase_c_mr_karpathy import holdout_runner

    # Force the regime lookup to None to trigger the skip_reason short-circuit
    # (the failure test). Caches are NOT loaded -- the runner returns instantly.
    monkeypatch.setattr(holdout_runner, "regime_for_date", lambda d: None)
    monkeypatch.setattr(holdout_runner, "regime_allowed", lambda d: False)
    monkeypatch.setattr(holdout_runner, "is_event_day", lambda d: False)
    # Skip cache loading entirely
    monkeypatch.setattr(
        holdout_runner,
        "_load_today_minute_and_daily",
        lambda universe, *, date_str=None: ({}, {}, 0),
    )
    # Redirect ledger to tmp_path so the test never writes the real ledger
    monkeypatch.setattr(holdout_runner, "LEDGER_PATH", tmp_path / "rec.csv")
    monkeypatch.setattr(holdout_runner, "RUN_LOG_PATH", tmp_path / "run_log.jsonl")
    monkeypatch.setattr(holdout_runner, "LEDGER_DIR", tmp_path)

    open_summary = holdout_runner.open_today("2026-05-04")
    close_summary = holdout_runner.close_today("2026-05-04")

    for s in (open_summary, close_summary):
        assert s["hypothesis_id"] == HYPOTHESIS_ID
        assert s["date"] == "2026-05-04"
        assert "regime" in s
        assert "skip_reason" in s
        assert "n_rows" in s
        assert "in_holdout" in s
        assert "karpathy_cell_loaded" in s
    assert open_summary["skip_reason"] == "regime_label_unavailable"
    assert open_summary["n_rows"] == 0


# ---- §11 holdout window membership ----------------------------------------

def test_holdout_membership():
    from pipeline.research.h_2026_05_01_phase_c_mr_karpathy import holdout_runner
    assert holdout_runner.is_in_holdout("2026-05-04")
    assert holdout_runner.is_in_holdout("2026-08-01")
    assert holdout_runner.is_in_holdout("2026-10-31")
    assert not holdout_runner.is_in_holdout("2026-05-03")
    assert not holdout_runner.is_in_holdout("2026-11-01")


def test_run_one_day_fires_synthetic_mean_revert(monkeypatch, tmp_path):
    """End-to-end engine integration: a synthetic |z|=-5 down-move on a RISK-ON
    day with no event collision must produce one LONG row with non-empty exit.

    This bypasses the 100-ticker cache loader and proves the gates + classifier
    + simulate_exit + ledger composition all wire together correctly.
    """
    from pipeline.research.h_2026_05_01_phase_c_mr_karpathy import holdout_runner

    target_date = "2026-03-30"  # known RISK-ON in PIT tape, no event

    # Single-ticker synthetic 5m bar set covering 09:30 -> 14:30 on target_date.
    # Open at 100, snap 09:30 closes at 90 (-10%) -> intraday_ret -0.10.
    # Profile mean=0, std=0.02 -> z = -0.10 / 0.02 = -5.0, classification
    # POSSIBLE_OPPORTUNITY (mean-revert), side=LONG.
    bars = []
    for h, m in [(9, 30), (9, 45), (10, 0), (12, 0), (14, 0), (14, 30)]:
        bars.append({
            "time": f"{h:02d}:{m:02d}:00",
            "open": 90.0, "high": 92.0, "low": 89.5,
            "close": 91.0 if h > 9 or m > 30 else 90.0,
        })
    minute_cache = {"FAKE": {target_date: bars}}
    daily_cache = {"FAKE": [
        {"date": "2026-03-27", "high": 102.0, "low": 99.0, "close": 100.0},
        # 30 days of synthetic daily history for ATR(14)
        *[{"date": f"2026-02-{d:02d}", "high": 102.0, "low": 99.0, "close": 100.0}
          for d in range(1, 28)],
    ]}
    profile = {"FAKE": {"RISK-ON": {
        "expected_return": 0.001,   # tiny positive; actual is -10% (opposite sign)
        "std_return": 0.02,         # -> z = (-0.10 - 0.001)/0.02 ~ -5.05; opposite-sign + |z|>=4 -> POSSIBLE_OPPORTUNITY
        "hit_rate": 0.5,
        "n": 100,
    }}}

    monkeypatch.setattr(holdout_runner, "_load_universe", lambda: ["FAKE"])
    monkeypatch.setattr(holdout_runner, "_load_profile", lambda: profile)
    monkeypatch.setattr(holdout_runner, "_load_sector_map", lambda: {"FAKE": "TEST"})
    monkeypatch.setattr(
        holdout_runner,
        "_load_today_minute_and_daily",
        lambda universe, *, date_str=None: (minute_cache, daily_cache, 0),
    )
    monkeypatch.setattr(holdout_runner, "regime_for_date", lambda d: "RISK-ON")
    monkeypatch.setattr(holdout_runner, "regime_allowed", lambda d: True)
    monkeypatch.setattr(holdout_runner, "is_event_day", lambda d: False)
    monkeypatch.setattr(holdout_runner, "LEDGER_PATH", tmp_path / "rec.csv")
    monkeypatch.setattr(holdout_runner, "RUN_LOG_PATH", tmp_path / "run_log.jsonl")
    monkeypatch.setattr(holdout_runner, "LEDGER_DIR", tmp_path)

    summary = holdout_runner.run_for_date(target_date, force=True)
    assert summary["regime"] == "RISK-ON"
    assert summary["skip_reason"] is None
    assert summary["n_rows"] == 1, f"expected 1 row, got {summary}"

    # Verify the ledger row landed
    import csv as _csv
    with (tmp_path / "rec.csv").open() as fp:
        rows = list(_csv.DictReader(fp))
    assert len(rows) == 1
    row = rows[0]
    assert row["ticker"] == "FAKE"
    assert row["regime"] == "RISK-ON"
    assert row["side"] == "LONG"
    assert float(row["z_score"]) <= -4.0
    assert row["exit_reason"] in {"TIME_STOP", "ATR_STOP"}
    assert row["pnl_bps_S0"] != ""


def test_extension_window():
    from pipeline.research.h_2026_05_01_phase_c_mr_karpathy import holdout_runner
    assert holdout_runner.is_in_extension("2026-08-15")
    assert holdout_runner.is_in_extension("2026-10-31")
    assert not holdout_runner.is_in_extension("2026-08-01")
    assert not holdout_runner.is_in_extension("2026-11-01")
