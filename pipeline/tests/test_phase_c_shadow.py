"""Tests for the Phase C F3 live shadow driver."""
from __future__ import annotations

import json

import pandas as pd
import pytest

from pipeline import phase_c_shadow
from pipeline.research.phase_c_backtest import live_paper


def _breaks_doc(rows: list[dict], date: str = "2026-04-22") -> dict:
    return {
        "date": date,
        "scan_time": f"{date} 09:25:00",
        "breaks": rows,
    }


def test_filter_opportunity_drops_non_opportunity():
    rows = [
        {"symbol": "A", "classification": "OPPORTUNITY_LAG"},
        {"symbol": "B", "classification": "POSSIBLE_OPPORTUNITY"},
        {"symbol": "C", "classification": "UNCERTAIN"},
        {"symbol": "D", "classification": "WARNING"},
    ]
    kept = phase_c_shadow._filter_opportunity(rows)
    assert [b["symbol"] for b in kept] == ["A"]


def test_side_from_expected_long_positive():
    assert phase_c_shadow._side_from_expected(0.5) == "LONG"
    assert phase_c_shadow._side_from_expected(0.0) == "LONG"


def test_side_from_expected_short_negative():
    assert phase_c_shadow._side_from_expected(-0.2) == "SHORT"


def test_build_open_signals_happy_path():
    doc = _breaks_doc([
        {"symbol": "ACME", "classification": "OPPORTUNITY_LAG",
         "expected_return": 0.8, "z_score": 2.4},
        {"symbol": "FOO", "classification": "OPPORTUNITY_LAG",
         "expected_return": -0.6, "z_score": -1.9},
    ])
    ltp = {"ACME": 100.0, "FOO": 200.0}
    df = phase_c_shadow.build_open_signals(doc, ltp)
    assert len(df) == 2
    assert set(df["symbol"]) == {"ACME", "FOO"}
    acme = df[df["symbol"] == "ACME"].iloc[0]
    assert acme["side"] == "LONG"
    assert acme["entry_px"] == pytest.approx(100.0)
    assert acme["date"] == "2026-04-22"
    assert acme["signal_time"] == "2026-04-22 09:25:00"
    assert acme["stop_pct"] == pytest.approx(0.02)
    assert acme["target_pct"] == pytest.approx(0.01)
    foo = df[df["symbol"] == "FOO"].iloc[0]
    assert foo["side"] == "SHORT"


def test_build_open_signals_skips_symbols_missing_ltp():
    doc = _breaks_doc([
        {"symbol": "A", "classification": "OPPORTUNITY_LAG", "expected_return": 0.5, "z_score": 2.0},
        {"symbol": "B", "classification": "OPPORTUNITY_LAG", "expected_return": 0.5, "z_score": 2.0},
    ])
    ltp = {"A": 100.0}  # B is missing
    df = phase_c_shadow.build_open_signals(doc, ltp)
    assert list(df["symbol"]) == ["A"]


def test_build_open_signals_skips_rows_with_missing_expected_return():
    doc = _breaks_doc([
        {"symbol": "A", "classification": "OPPORTUNITY_LAG", "expected_return": None, "z_score": 2.0},
        {"symbol": "B", "classification": "OPPORTUNITY_LAG", "expected_return": 0.5, "z_score": 2.0},
    ])
    ltp = {"A": 100.0, "B": 200.0}
    df = phase_c_shadow.build_open_signals(doc, ltp)
    assert list(df["symbol"]) == ["B"]


def test_build_open_signals_empty_breaks_returns_empty_df():
    df = phase_c_shadow.build_open_signals(_breaks_doc([]), {})
    assert df.empty


def test_cmd_open_with_no_breaks_file(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(phase_c_shadow, "_BREAKS_PATH", tmp_path / "missing.json")
    with caplog.at_level("INFO"):
        rc = phase_c_shadow.cmd_open()
    assert rc == 0
    assert any("no breaks doc" in r.message for r in caplog.records)


def test_cmd_open_happy_path(tmp_path, monkeypatch):
    # Stub the breaks file
    breaks_path = tmp_path / "correlation_breaks.json"
    breaks_path.write_text(json.dumps(_breaks_doc([
        {"symbol": "ACME", "classification": "OPPORTUNITY_LAG",
         "expected_return": 0.5, "z_score": 2.0},
    ])), encoding="utf-8")
    monkeypatch.setattr(phase_c_shadow, "_BREAKS_PATH", breaks_path)

    # Stub Kite
    monkeypatch.setattr(phase_c_shadow, "_fetch_ltp", lambda syms: {"ACME": 123.0})

    # Stub ledger path
    ledger_path = tmp_path / "ledger.json"
    monkeypatch.setattr(live_paper, "_LEDGER_PATH", ledger_path)

    rc = phase_c_shadow.cmd_open()
    assert rc == 0
    data = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert len(data) == 1
    assert data[0]["symbol"] == "ACME"
    assert data[0]["status"] == "OPEN"
    assert data[0]["entry_px"] == 123.0
    assert data[0]["side"] == "LONG"


def test_cmd_open_idempotent_on_second_run(tmp_path, monkeypatch):
    breaks_path = tmp_path / "correlation_breaks.json"
    breaks_path.write_text(json.dumps(_breaks_doc([
        {"symbol": "ACME", "classification": "OPPORTUNITY_LAG",
         "expected_return": 0.5, "z_score": 2.0},
    ])), encoding="utf-8")
    monkeypatch.setattr(phase_c_shadow, "_BREAKS_PATH", breaks_path)
    monkeypatch.setattr(phase_c_shadow, "_fetch_ltp", lambda syms: {"ACME": 100.0})
    ledger_path = tmp_path / "ledger.json"
    monkeypatch.setattr(live_paper, "_LEDGER_PATH", ledger_path)

    phase_c_shadow.cmd_open()
    phase_c_shadow.cmd_open()  # second call same session

    data = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert len(data) == 1


def test_cmd_close_happy_path(tmp_path, monkeypatch):
    ledger_path = tmp_path / "ledger.json"
    monkeypatch.setattr(live_paper, "_LEDGER_PATH", ledger_path)

    # Seed ledger with one OPEN entry
    signals = pd.DataFrame([{
        "date": "2026-04-22", "signal_time": "2026-04-22 09:25:00",
        "symbol": "ACME", "side": "LONG", "z_score": 2.0,
        "stop_pct": 0.02, "target_pct": 0.01, "entry_px": 100.0,
    }])
    live_paper.record_opens(signals)

    monkeypatch.setattr(phase_c_shadow, "_fetch_ltp", lambda syms: {"ACME": 102.0})

    rc = phase_c_shadow.cmd_close(date_override="2026-04-22")
    assert rc == 0

    data = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert data[0]["status"] == "CLOSED"
    assert data[0]["exit_px"] == 102.0
    # LONG, +2% on ₹50k notional = ₹1000 gross
    assert data[0]["pnl_gross_inr"] == pytest.approx(1000.0)


def test_cmd_close_no_open_positions_returns_zero(tmp_path, monkeypatch, caplog):
    ledger_path = tmp_path / "ledger.json"
    monkeypatch.setattr(live_paper, "_LEDGER_PATH", ledger_path)
    # No signals yet — ledger is empty
    with caplog.at_level("INFO"):
        rc = phase_c_shadow.cmd_close(date_override="2026-04-22")
    assert rc == 0
    assert any("no OPEN entries" in r.message for r in caplog.records)


def test_cmd_close_ltp_failure_leaves_ledger_untouched(tmp_path, monkeypatch):
    ledger_path = tmp_path / "ledger.json"
    monkeypatch.setattr(live_paper, "_LEDGER_PATH", ledger_path)
    signals = pd.DataFrame([{
        "date": "2026-04-22", "signal_time": "2026-04-22 09:25:00",
        "symbol": "ACME", "side": "LONG", "z_score": 2.0,
        "stop_pct": 0.02, "target_pct": 0.01, "entry_px": 100.0,
    }])
    live_paper.record_opens(signals)

    monkeypatch.setattr(phase_c_shadow, "_fetch_ltp", lambda syms: {})
    rc = phase_c_shadow.cmd_close(date_override="2026-04-22")
    assert rc == 1

    data = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert data[0]["status"] == "OPEN"  # unchanged


# ---------------------------------------------------------------------------
# T5: sidecar wiring tests
# ---------------------------------------------------------------------------

def _make_breaks_path(tmp_path, rows=None, date="2026-04-27"):
    """Write a correlation_breaks.json with the given rows and return the path."""
    if rows is None:
        rows = [
            {"symbol": "ACME", "classification": "OPPORTUNITY_LAG",
             "expected_return": 0.5, "z_score": 2.0},
            {"symbol": "FOO", "classification": "OPPORTUNITY_LAG",
             "expected_return": -0.4, "z_score": -2.1},
        ]
    p = tmp_path / "correlation_breaks.json"
    p.write_text(json.dumps(_breaks_doc(rows, date)), encoding="utf-8")
    return p


def test_cmd_open_calls_sidecar_for_each_signal(tmp_path, monkeypatch):
    """open_options_pair must be called once per signal row that enters live_paper."""
    from unittest.mock import patch, MagicMock

    breaks_path = _make_breaks_path(tmp_path)
    monkeypatch.setattr(phase_c_shadow, "_BREAKS_PATH", breaks_path)
    monkeypatch.setattr(phase_c_shadow, "_fetch_ltp",
                        lambda syms: {"ACME": 100.0, "FOO": 200.0})
    ledger_path = tmp_path / "ledger.json"
    monkeypatch.setattr(live_paper, "_LEDGER_PATH", ledger_path)

    mock_open_pair = MagicMock(return_value={"status": "OPEN"})
    with patch("pipeline.phase_c_options_shadow.open_options_pair", mock_open_pair):
        rc = phase_c_shadow.cmd_open()

    assert rc == 0
    assert mock_open_pair.call_count == 2
    call_args = [c.args[0] for c in mock_open_pair.call_args_list]
    symbols_called = {a["symbol"] for a in call_args}
    assert symbols_called == {"ACME", "FOO"}
    for row_dict in call_args:
        for key in ("symbol", "side", "signal_time", "date", "entry_px"):
            assert key in row_dict, f"expected key {key!r} in sidecar row"


def test_cmd_open_continues_when_sidecar_raises(tmp_path, monkeypatch):
    """If sidecar raises, cmd_open still returns 0 and record_opens was called."""
    from unittest.mock import patch, MagicMock

    breaks_path = _make_breaks_path(tmp_path)
    monkeypatch.setattr(phase_c_shadow, "_BREAKS_PATH", breaks_path)
    monkeypatch.setattr(phase_c_shadow, "_fetch_ltp",
                        lambda syms: {"ACME": 100.0, "FOO": 200.0})
    ledger_path = tmp_path / "ledger.json"
    monkeypatch.setattr(live_paper, "_LEDGER_PATH", ledger_path)

    mock_open_pair = MagicMock(side_effect=RuntimeError("boom"))
    with patch("pipeline.phase_c_options_shadow.open_options_pair", mock_open_pair):
        rc = phase_c_shadow.cmd_open()

    assert rc == 0
    # Futures ledger must still have entries
    data = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert len(data) == 2
    assert all(r["status"] == "OPEN" for r in data)


def test_cmd_open_sidecar_runs_after_record_opens(tmp_path, monkeypatch):
    """record_opens must be called before any open_options_pair call."""
    from unittest.mock import patch, MagicMock, call

    call_order: list[str] = []

    breaks_path = _make_breaks_path(
        tmp_path,
        rows=[{"symbol": "ACME", "classification": "OPPORTUNITY_LAG",
               "expected_return": 0.5, "z_score": 2.0}],
    )
    monkeypatch.setattr(phase_c_shadow, "_BREAKS_PATH", breaks_path)
    monkeypatch.setattr(phase_c_shadow, "_fetch_ltp", lambda syms: {"ACME": 100.0})
    ledger_path = tmp_path / "ledger.json"
    monkeypatch.setattr(live_paper, "_LEDGER_PATH", ledger_path)

    original_record_opens = live_paper.record_opens

    def recording_record_opens(signals):
        call_order.append("record_opens")
        return original_record_opens(signals)

    def recording_open_pair(row):
        call_order.append("open_options_pair")
        return {"status": "OPEN"}

    with patch.object(live_paper, "record_opens", side_effect=recording_record_opens), \
         patch("pipeline.phase_c_options_shadow.open_options_pair",
               side_effect=recording_open_pair):
        phase_c_shadow.cmd_open()

    assert call_order[0] == "record_opens", (
        f"record_opens must fire before sidecar; got order: {call_order}"
    )
    assert "open_options_pair" in call_order


def test_cmd_open_skips_sidecar_when_signals_empty(tmp_path, monkeypatch):
    """When build_open_signals returns empty (no LTP match), neither ledger nor sidecar fires."""
    from unittest.mock import patch, MagicMock

    # OPPORTUNITY_LAG row but LTP is missing — signals will be empty
    breaks_path = _make_breaks_path(
        tmp_path,
        rows=[{"symbol": "GHOST", "classification": "OPPORTUNITY_LAG",
               "expected_return": 0.5, "z_score": 2.0}],
    )
    monkeypatch.setattr(phase_c_shadow, "_BREAKS_PATH", breaks_path)
    monkeypatch.setattr(phase_c_shadow, "_fetch_ltp", lambda syms: {})  # no prices

    mock_record_opens = MagicMock(return_value=0)
    mock_open_pair = MagicMock(return_value={"status": "OPEN"})

    with patch.object(live_paper, "record_opens", mock_record_opens), \
         patch("pipeline.phase_c_options_shadow.open_options_pair", mock_open_pair):
        rc = phase_c_shadow.cmd_open()

    assert rc == 0
    mock_record_opens.assert_not_called()
    mock_open_pair.assert_not_called()


# ---------------------------------------------------------------------------
# T7: sidecar CLOSE wiring tests
# ---------------------------------------------------------------------------

def _seed_futures_ledger(ledger_path, rows: list[dict]) -> None:
    """Write a list of raw ledger rows to the given path."""
    import json
    import os
    import tempfile
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", delete=False,
        dir=ledger_path.parent, prefix=ledger_path.name + ".", suffix=".tmp",
    ) as tmp:
        tmp.write(json.dumps(rows, indent=2))
        tmp_path = tmp.name
    os.replace(tmp_path, ledger_path)


def _futures_row(
    date="2026-04-29",
    symbol="RELIANCE",
    signal_time="2026-04-29 09:25:00",
    status="OPEN",
    entry_px=2398.0,
) -> dict:
    return {
        "tag": f"PHASE_C_VERIFY_{date}_1",
        "date": date,
        "signal_time": signal_time,
        "symbol": symbol,
        "side": "LONG",
        "z_score": 2.5,
        "entry_px": entry_px,
        "stop_pct": 0.02,
        "target_pct": 0.01,
        "notional_inr": 50000,
        "status": status,
        "exit_px": None if status == "OPEN" else entry_px * 1.01,
        "exit_time": None if status == "OPEN" else f"{date} 14:30:00",
        "exit_reason": None if status == "OPEN" else "TIME_STOP",
        "pnl_gross_inr": None if status == "OPEN" else 500.0,
        "pnl_net_inr": None if status == "OPEN" else 480.0,
    }


def test_cmd_close_calls_sidecar_for_each_closed_row(tmp_path, monkeypatch):
    """close_options_pair must be called once per CLOSED futures row after close_at_1430."""
    from unittest.mock import patch, MagicMock

    date_str = "2026-04-29"
    ledger_path = tmp_path / "ledger.json"
    monkeypatch.setattr(live_paper, "_LEDGER_PATH", ledger_path)

    # Pre-seed: one OPEN row (so cmd_close doesn't early-return) and two already-CLOSED rows
    # Simulates the state AFTER close_at_1430 ran (rows already transitioned).
    rows = [
        _futures_row(date=date_str, symbol="RELIANCE", signal_time="2026-04-29 09:35:00",
                     status="OPEN"),
        _futures_row(date=date_str, symbol="INFY", signal_time="2026-04-29 09:40:00",
                     status="CLOSED"),
        _futures_row(date=date_str, symbol="TCS", signal_time="2026-04-29 09:45:00",
                     status="CLOSED"),
    ]
    _seed_futures_ledger(ledger_path, rows)

    monkeypatch.setattr(phase_c_shadow, "_fetch_ltp",
                        lambda syms: {"RELIANCE": 2400.0})

    # close_at_1430 side_effect: mutate the OPEN row to CLOSED in-place on disk
    def fake_close_at_1430(date_str_arg, ltp):
        data = json.loads(ledger_path.read_text(encoding="utf-8"))
        n = 0
        for row in data:
            if row["date"] == date_str_arg and row["status"] == "OPEN":
                sym = row["symbol"]
                if sym in ltp:
                    row["status"] = "CLOSED"
                    row["exit_px"] = ltp[sym]
                    row["exit_time"] = f"{date_str_arg} 14:30:00"
                    row["exit_reason"] = "TIME_STOP"
                    n += 1
        _seed_futures_ledger(ledger_path, data)
        return n

    mock_close_pair = MagicMock(return_value={"status": "CLOSED"})
    with patch.object(live_paper, "close_at_1430", side_effect=fake_close_at_1430), \
         patch("pipeline.phase_c_options_shadow.close_options_pair", mock_close_pair):
        rc = phase_c_shadow.cmd_close(date_override=date_str)

    assert rc == 0
    # 3 CLOSED rows after fake_close_at_1430 (2 pre-existing + 1 just closed)
    assert mock_close_pair.call_count == 3
    called_ids = {c.args[0] for c in mock_close_pair.call_args_list}
    assert "2026-04-29_RELIANCE_0935" in called_ids
    assert "2026-04-29_INFY_0940" in called_ids
    assert "2026-04-29_TCS_0945" in called_ids


def test_cmd_close_continues_when_sidecar_raises(tmp_path, monkeypatch):
    """If sidecar raises, cmd_close still returns 0 and futures ledger is unaffected."""
    from unittest.mock import patch, MagicMock

    date_str = "2026-04-29"
    ledger_path = tmp_path / "ledger.json"
    monkeypatch.setattr(live_paper, "_LEDGER_PATH", ledger_path)

    rows = [_futures_row(date=date_str, symbol="RELIANCE", status="OPEN")]
    _seed_futures_ledger(ledger_path, rows)
    monkeypatch.setattr(phase_c_shadow, "_fetch_ltp",
                        lambda syms: {"RELIANCE": 2400.0})

    def fake_close_at_1430(date_str_arg, ltp):
        data = json.loads(ledger_path.read_text(encoding="utf-8"))
        for row in data:
            if row["date"] == date_str_arg and row["status"] == "OPEN":
                row["status"] = "CLOSED"
        _seed_futures_ledger(ledger_path, data)
        return 1

    mock_close_pair = MagicMock(side_effect=RuntimeError("boom"))
    with patch.object(live_paper, "close_at_1430", side_effect=fake_close_at_1430), \
         patch("pipeline.phase_c_options_shadow.close_options_pair", mock_close_pair):
        rc = phase_c_shadow.cmd_close(date_override=date_str)

    assert rc == 0


def test_cmd_close_skips_sidecar_when_no_opens(tmp_path, monkeypatch, caplog):
    """When ledger has no OPEN rows for date_str, cmd_close returns 0 and sidecar never fires."""
    from unittest.mock import patch, MagicMock

    date_str = "2026-04-29"
    ledger_path = tmp_path / "ledger.json"
    monkeypatch.setattr(live_paper, "_LEDGER_PATH", ledger_path)
    # Empty ledger — no OPEN rows
    _seed_futures_ledger(ledger_path, [])

    mock_close_pair = MagicMock(return_value={"status": "CLOSED"})
    with patch("pipeline.phase_c_options_shadow.close_options_pair", mock_close_pair), \
         caplog.at_level("INFO"):
        rc = phase_c_shadow.cmd_close(date_override=date_str)

    assert rc == 0
    mock_close_pair.assert_not_called()
    assert any("no OPEN entries" in r.message for r in caplog.records)


def test_cmd_close_handles_no_match_silently(tmp_path, monkeypatch):
    """When close_options_pair returns None (no paired row), cmd_close still returns 0."""
    from unittest.mock import patch, MagicMock

    date_str = "2026-04-29"
    ledger_path = tmp_path / "ledger.json"
    monkeypatch.setattr(live_paper, "_LEDGER_PATH", ledger_path)

    rows = [_futures_row(date=date_str, symbol="RELIANCE", status="OPEN")]
    _seed_futures_ledger(ledger_path, rows)
    monkeypatch.setattr(phase_c_shadow, "_fetch_ltp",
                        lambda syms: {"RELIANCE": 2400.0})

    def fake_close_at_1430(date_str_arg, ltp):
        data = json.loads(ledger_path.read_text(encoding="utf-8"))
        for row in data:
            if row["date"] == date_str_arg and row["status"] == "OPEN":
                row["status"] = "CLOSED"
        _seed_futures_ledger(ledger_path, data)
        return 1

    # close_options_pair returns None → no match in options ledger
    mock_close_pair = MagicMock(return_value=None)
    with patch.object(live_paper, "close_at_1430", side_effect=fake_close_at_1430), \
         patch("pipeline.phase_c_options_shadow.close_options_pair", mock_close_pair):
        rc = phase_c_shadow.cmd_close(date_override=date_str)

    assert rc == 0
    mock_close_pair.assert_called_once()


def test_cmd_close_signal_id_format(tmp_path, monkeypatch):
    """close_options_pair is called with signal_id in {date}_{symbol}_{HHMM} format."""
    from unittest.mock import patch, MagicMock

    date_str = "2026-04-29"
    ledger_path = tmp_path / "ledger.json"
    monkeypatch.setattr(live_paper, "_LEDGER_PATH", ledger_path)

    rows = [_futures_row(
        date=date_str, symbol="RELIANCE",
        signal_time="2026-04-29 09:35:00", status="OPEN",
    )]
    _seed_futures_ledger(ledger_path, rows)
    monkeypatch.setattr(phase_c_shadow, "_fetch_ltp",
                        lambda syms: {"RELIANCE": 2400.0})

    def fake_close_at_1430(date_str_arg, ltp):
        data = json.loads(ledger_path.read_text(encoding="utf-8"))
        for row in data:
            if row["date"] == date_str_arg and row["status"] == "OPEN":
                row["status"] = "CLOSED"
        _seed_futures_ledger(ledger_path, data)
        return 1

    mock_close_pair = MagicMock(return_value={"status": "CLOSED"})
    with patch.object(live_paper, "close_at_1430", side_effect=fake_close_at_1430), \
         patch("pipeline.phase_c_options_shadow.close_options_pair", mock_close_pair):
        rc = phase_c_shadow.cmd_close(date_override=date_str)

    assert rc == 0
    mock_close_pair.assert_called_once_with("2026-04-29_RELIANCE_0935")
