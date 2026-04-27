"""Tests for GET /api/research/phase-c-options-shadow.

Spec §11.3: endpoint returns {open_pairs, cumulative}.
Uses monkeypatch to point ledger path constants at tmp_path JSON files.
"""
import json
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_app(monkeypatch, options_rows, futures_rows, tmp_path):
    """Wire the router with patched ledger paths and return a TestClient."""
    opts_path = tmp_path / "options_ledger.json"
    futs_path = tmp_path / "futures_ledger.json"
    opts_path.write_text(json.dumps(options_rows), encoding="utf-8")
    futs_path.write_text(json.dumps(futures_rows), encoding="utf-8")

    import pipeline.terminal.api.research as mod
    monkeypatch.setattr(mod, "_PHASE_C_OPTIONS_LEDGER", opts_path)
    monkeypatch.setattr(mod, "_PHASE_C_FUTURES_LEDGER", futs_path)

    from pipeline.terminal.api.research import router
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _open_row(**overrides):
    base = {
        "signal_id": "2026-04-29_RELIANCE_0935",
        "date": "2026-04-29",
        "symbol": "RELIANCE",
        "side": "LONG",
        "option_type": "CE",
        "expiry_date": "2026-05-29",
        "is_expiry_day": False,
        "drift_vs_rent_tier": "EXPERIMENTAL",
        "strike": 2400,
        "tradingsymbol": "RELIANCE25MAY2400CE",
        "entry_mid": 120.75,
        "entry_iv": 0.276,
        "entry_delta": 0.51,
        "status": "OPEN",
    }
    base.update(overrides)
    return base


def _closed_row(**overrides):
    base = {
        "signal_id": "2026-04-28_INFY_0945",
        "date": "2026-04-28",
        "symbol": "INFY",
        "side": "LONG",
        "option_type": "CE",
        "expiry_date": "2026-05-29",
        "is_expiry_day": False,
        "drift_vs_rent_tier": "EXPERIMENTAL",
        "strike": 1500,
        "tradingsymbol": "INFY25MAY1500CE",
        "entry_mid": 55.0,
        "entry_iv": 0.22,
        "entry_delta": 0.48,
        "status": "CLOSED",
        "pnl_net_pct": 0.02,
    }
    base.update(overrides)
    return base


def _futures_row(**overrides):
    base = {
        "signal_time": "2026-04-29 09:35:00",
        "date": "2026-04-29",
        "symbol": "RELIANCE",
        "side": "LONG",
        "entry_px": 2380.0,
        "status": "OPEN",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_endpoint_empty_ledgers(tmp_path, monkeypatch):
    """Both files missing -> 200 with empty open_pairs and zeroed cumulative."""
    import pipeline.terminal.api.research as mod
    monkeypatch.setattr(mod, "_PHASE_C_OPTIONS_LEDGER", tmp_path / "no_opts.json")
    monkeypatch.setattr(mod, "_PHASE_C_FUTURES_LEDGER", tmp_path / "no_futs.json")

    from pipeline.terminal.api.research import router
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    r = client.get("/research/phase-c-options-shadow")
    assert r.status_code == 200
    data = r.json()
    assert data["open_pairs"] == []
    cum = data["cumulative"]
    assert cum["n_closed"] == 0
    assert cum["n_unmatched"] == 0
    assert cum["by_tier"] == {}
    # by_expiry_day must have "true" and "false" keys with zero values
    assert cum["by_expiry_day"]["true"]["n"] == 0
    assert cum["by_expiry_day"]["false"]["n"] == 0


def test_endpoint_open_pairs_projected(tmp_path, monkeypatch):
    """2 OPEN rows + 1 CLOSED row -> only 2 OPEN appear in open_pairs."""
    rows = [
        _open_row(signal_id="2026-04-29_RELIANCE_0935"),
        _open_row(signal_id="2026-04-29_INFY_0940", symbol="INFY"),
        _closed_row(),
    ]
    client = _make_app(monkeypatch, rows, [], tmp_path)

    r = client.get("/research/phase-c-options-shadow")
    assert r.status_code == 200
    data = r.json()
    assert len(data["open_pairs"]) == 2
    ids = {p["signal_id"] for p in data["open_pairs"]}
    assert "2026-04-29_RELIANCE_0935" in ids
    assert "2026-04-29_INFY_0940" in ids
    # OPEN rows must have null pnl fields
    for p in data["open_pairs"]:
        assert p["futures_pnl_pct"] is None
        assert p["options_pnl_pct"] is None


def test_endpoint_cumulative_groups_by_tier(tmp_path, monkeypatch):
    """CLOSED rows with various tiers -> by_tier correct n, win_rate, mean."""
    rows = [
        _closed_row(signal_id="A", drift_vs_rent_tier="HIGH-ALPHA SYNTHETIC",
                    pnl_net_pct=0.02),
        _closed_row(signal_id="B", drift_vs_rent_tier="HIGH-ALPHA SYNTHETIC",
                    pnl_net_pct=-0.01),
        _closed_row(signal_id="C", drift_vs_rent_tier="EXPERIMENTAL",
                    pnl_net_pct=0.005),
    ]
    client = _make_app(monkeypatch, rows, [], tmp_path)

    r = client.get("/research/phase-c-options-shadow")
    data = r.json()
    cum = data["cumulative"]
    assert cum["n_closed"] == 3
    ha = cum["by_tier"]["HIGH-ALPHA SYNTHETIC"]
    assert ha["n"] == 2
    # 1 win (0.02 > 0), 1 loss (-0.01 <= 0) -> win_rate = 0.5
    assert ha["win_rate"] == pytest.approx(0.5)
    assert ha["mean_options_pnl_pct"] == pytest.approx((0.02 + (-0.01)) / 2)
    exp = cum["by_tier"]["EXPERIMENTAL"]
    assert exp["n"] == 1
    assert exp["win_rate"] == pytest.approx(1.0)


def test_endpoint_cumulative_groups_by_expiry_day(tmp_path, monkeypatch):
    """Mix of expiry-day true/false -> by_expiry_day correct."""
    rows = [
        _closed_row(signal_id="X1", is_expiry_day=True, pnl_net_pct=0.03),
        _closed_row(signal_id="X2", is_expiry_day=True, pnl_net_pct=0.01),
        _closed_row(signal_id="X3", is_expiry_day=False, pnl_net_pct=-0.005),
    ]
    client = _make_app(monkeypatch, rows, [], tmp_path)

    r = client.get("/research/phase-c-options-shadow")
    data = r.json()
    by_exp = data["cumulative"]["by_expiry_day"]
    assert by_exp["true"]["n"] == 2
    assert by_exp["true"]["win_rate"] == pytest.approx(1.0)
    assert by_exp["false"]["n"] == 1
    assert by_exp["false"]["win_rate"] == pytest.approx(0.0)


def test_endpoint_unmatched_count(tmp_path, monkeypatch):
    """CLOSED options row with signal_id X; futures ledger has no matching row -> n_unmatched=1."""
    opts = [_closed_row(signal_id="2026-04-28_INFY_0945")]
    # Futures ledger empty -> no matching futures row
    futs = []
    client = _make_app(monkeypatch, opts, futs, tmp_path)

    r = client.get("/research/phase-c-options-shadow")
    data = r.json()
    assert data["cumulative"]["n_unmatched"] == 1


def test_endpoint_uses_build_signal_id_for_futures(tmp_path, monkeypatch):
    """Futures row at signal_time 2026-04-29 09:35:00 symbol RELIANCE
    should match options row with signal_id 2026-04-29_RELIANCE_0935.
    n_unmatched must be 0."""
    opts = [_closed_row(signal_id="2026-04-29_RELIANCE_0935",
                        symbol="RELIANCE", date="2026-04-29")]
    futs = [_futures_row(signal_time="2026-04-29 09:35:00",
                         date="2026-04-29", symbol="RELIANCE",
                         status="CLOSED", exit_px=2400.0)]
    client = _make_app(monkeypatch, opts, futs, tmp_path)

    r = client.get("/research/phase-c-options-shadow")
    data = r.json()
    assert data["cumulative"]["n_unmatched"] == 0


def test_endpoint_skipped_liquidity_excluded_from_cumulative(tmp_path, monkeypatch):
    """SKIPPED_LIQUIDITY rows must not appear in n_closed or by_tier."""
    rows = [
        _closed_row(signal_id="A", pnl_net_pct=0.01),
        {**_closed_row(signal_id="B"), "status": "SKIPPED_LIQUIDITY"},
    ]
    client = _make_app(monkeypatch, rows, [], tmp_path)

    r = client.get("/research/phase-c-options-shadow")
    data = r.json()
    assert data["cumulative"]["n_closed"] == 1


def test_endpoint_open_pair_includes_strike(tmp_path, monkeypatch):
    """OPEN row with strike=2400 must surface strike on the projected open_pairs entry.

    Regression guard for T9 code-review finding: JS card interpolates p.strike
    but _project_open_pair previously omitted the field, causing empty strikes
    in production (surfaced at commit 7c53f5e).
    """
    rows = [_open_row(strike=2400)]
    client = _make_app(monkeypatch, rows, [], tmp_path)

    r = client.get("/research/phase-c-options-shadow")
    assert r.status_code == 200
    data = r.json()
    assert len(data["open_pairs"]) == 1
    assert data["open_pairs"][0]["strike"] == 2400
