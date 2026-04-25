import datetime as dt
from unittest.mock import patch

from pipeline.earnings_calendar import runner


def _payload_for(_symbol):
    return {
        "board_meetings": {
            "data": [
                ["24-04-2026", "Quarterly Results"],
                ["29-08-2025", "Disclosure under Regulation 30"],
            ]
        }
    }


def test_run_for_universe_writes_day_and_history(tmp_path, monkeypatch):
    monkeypatch.setenv("INDIANAPI_KEY", "k")
    universe = ["RELIANCE", "HDFCBANK"]
    with patch(
        "pipeline.earnings_calendar.runner.fetch_corporate_actions",
        side_effect=lambda s: _payload_for(s),
    ):
        report = runner.run_for_universe(
            universe,
            data_dir=tmp_path,
            asof=dt.date(2026, 4, 25),
        )
    assert report["n_symbols_attempted"] == 2
    assert report["n_symbols_with_events"] == 2
    assert report["n_events_total"] == 2
    assert (tmp_path / "2026-04-25.json").exists()
    assert (tmp_path / "history.parquet").exists()


def test_run_logs_per_symbol_failures_without_aborting(tmp_path, monkeypatch):
    monkeypatch.setenv("INDIANAPI_KEY", "k")

    def flaky(symbol):
        if symbol == "BAD":
            raise RuntimeError("simulated 500")
        return _payload_for(symbol)

    with patch(
        "pipeline.earnings_calendar.runner.fetch_corporate_actions",
        side_effect=flaky,
    ):
        report = runner.run_for_universe(
            ["RELIANCE", "BAD", "HDFCBANK"],
            data_dir=tmp_path,
            asof=dt.date(2026, 4, 25),
        )
    assert report["n_symbols_attempted"] == 3
    assert report["n_symbols_with_events"] == 2
    assert report["failures"] == [{"symbol": "BAD", "reason": "simulated 500"}]


def test_run_for_empty_universe_writes_empty_day_json(tmp_path, monkeypatch):
    monkeypatch.setenv("INDIANAPI_KEY", "k")
    report = runner.run_for_universe(
        [], data_dir=tmp_path, asof=dt.date(2026, 4, 25)
    )
    assert report["n_symbols_attempted"] == 0
    assert (tmp_path / "2026-04-25.json").exists()
