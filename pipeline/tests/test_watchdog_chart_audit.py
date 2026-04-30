"""Unit tests for pipeline/watchdog_chart_audit.py."""
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from pipeline import watchdog_chart_audit as wca
from pipeline.watchdog_chart_audit import audit_chart_universe


def _write_universe(p: Path, tickers: list[str]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"tickers": tickers}), encoding="utf-8")


def _write_csv(dir_: Path, ticker: str, last_date: str) -> None:
    dir_.mkdir(parents=True, exist_ok=True)
    (dir_ / f"{ticker}.csv").write_text(
        "Date,Open,High,Low,Close,Volume\n"
        "2026-01-01,100,101,99,100.5,1000\n"
        f"{last_date},105,106,104,105.5,2000\n",
        encoding="utf-8",
    )


def _setup(tmp_path: Path, tickers: list[str], last_dates: dict[str, str]):
    """Common fixture: universe + per-ticker fno csv with a chosen last_date.
    Returns (universe_path, fno_dir, state_path)."""
    universe_path = tmp_path / "canonical.json"
    fno_dir = tmp_path / "fno_historical"
    state_path = tmp_path / "audit_state.json"
    _write_universe(universe_path, tickers)
    for t, d in last_dates.items():
        _write_csv(fno_dir, t, d)
    return universe_path, fno_dir, state_path


def test_happy_path_returns_empty(tmp_path, monkeypatch):
    """Universe complete, csvs fresh, no state file -> no issues, state seeded."""
    tickers = ["AAA"] * 273  # exact size match
    tickers = [f"T{i:03d}" for i in range(273)]
    last_dates = {t: "2026-04-29" for t in tickers}
    universe_path, fno_dir, state_path = _setup(tmp_path, tickers, last_dates)

    # Stub compute_narrative — first run seeds state, no regression possible.
    monkeypatch.setattr(
        "pipeline.terminal.api.ticker_narrative.compute_narrative",
        lambda t: {"marker_count": 5},
    )

    issues = audit_chart_universe(
        universe_path=universe_path,
        fno_dir=fno_dir,
        state_path=state_path,
        tickers=("T000", "T001"),
        now=datetime(2026, 4, 30),
    )
    assert issues == []
    assert state_path.exists()
    persisted = json.loads(state_path.read_text())
    assert persisted["T000"]["marker_count"] == 5


def test_universe_size_drift_fires(tmp_path, monkeypatch):
    tickers = [f"T{i:03d}" for i in range(270)]  # 3 short
    last_dates = {t: "2026-04-29" for t in tickers}
    universe_path, fno_dir, state_path = _setup(tmp_path, tickers, last_dates)
    monkeypatch.setattr(
        "pipeline.terminal.api.ticker_narrative.compute_narrative",
        lambda t: {"marker_count": 1},
    )
    issues = audit_chart_universe(
        universe_path=universe_path, fno_dir=fno_dir, state_path=state_path,
        tickers=(), now=datetime(2026, 4, 30),
    )
    kinds = [i["kind"] for i in issues]
    assert "universe_size" in kinds
    assert any("270" in i["detail"] and "273" in i["detail"]
               for i in issues if i["kind"] == "universe_size")


def test_missing_universe_file_fires_universe_missing(tmp_path):
    fno_dir = tmp_path / "fno_historical"
    state_path = tmp_path / "audit_state.json"
    issues = audit_chart_universe(
        universe_path=tmp_path / "nope.json", fno_dir=fno_dir,
        state_path=state_path, tickers=(),
    )
    assert any(i["kind"] == "universe_missing" for i in issues)


def test_missing_csvs_fires_with_sample(tmp_path, monkeypatch):
    tickers = [f"T{i:03d}" for i in range(273)]
    # Skip 7 csvs to trigger the sample-with-+more rendering.
    last_dates = {t: "2026-04-29" for t in tickers if not t.endswith("7")}
    universe_path, fno_dir, state_path = _setup(tmp_path, tickers, last_dates)
    monkeypatch.setattr(
        "pipeline.terminal.api.ticker_narrative.compute_narrative",
        lambda t: {"marker_count": 1},
    )
    issues = audit_chart_universe(
        universe_path=universe_path, fno_dir=fno_dir, state_path=state_path,
        tickers=(), now=datetime(2026, 4, 30),
    )
    miss = [i for i in issues if i["kind"] == "missing_csvs"]
    assert len(miss) == 1
    # 27 of 273 tickers end in '7' (T007, T017, ..., T267) — verify count.
    assert "27 of 273" in miss[0]["detail"]
    assert "more" in miss[0]["detail"]


def test_stale_tail_detection(tmp_path, monkeypatch):
    """A csv whose last bar is older than TAIL_STALE_DAYS fires stale_tail."""
    tickers = [f"T{i:03d}" for i in range(273)]
    last_dates = {t: "2026-04-29" for t in tickers}
    last_dates["T000"] = "2026-04-20"  # 10 days stale at now=2026-04-30
    last_dates["T001"] = "2026-04-21"  # 9 days stale
    universe_path, fno_dir, state_path = _setup(tmp_path, tickers, last_dates)
    monkeypatch.setattr(
        "pipeline.terminal.api.ticker_narrative.compute_narrative",
        lambda t: {"marker_count": 1},
    )
    issues = audit_chart_universe(
        universe_path=universe_path, fno_dir=fno_dir, state_path=state_path,
        tickers=(), now=datetime(2026, 4, 30),
    )
    stale = [i for i in issues if i["kind"] == "stale_tail"]
    assert len(stale) == 1
    # T000 should appear first (sorted by descending age).
    assert "T000(10d)" in stale[0]["detail"]
    assert "T001(9d)" in stale[0]["detail"]


def test_marker_regression_fires_only_on_zero_after_nonzero(tmp_path, monkeypatch):
    tickers = [f"T{i:03d}" for i in range(273)]
    last_dates = {t: "2026-04-29" for t in tickers}
    universe_path, fno_dir, state_path = _setup(tmp_path, tickers, last_dates)

    # Seed state from a prior run: T000 had 12 markers, T001 had 0 (legitimate).
    state_path.write_text(json.dumps({
        "T000": {"marker_count": 12, "last_check": "2026-04-29T06:00:00"},
        "T001": {"marker_count": 0, "last_check": "2026-04-29T06:00:00"},
    }))

    # This run: T000 collapses to 0 (regression), T001 stays at 0 (no alert).
    counts = {"T000": 0, "T001": 0}
    monkeypatch.setattr(
        "pipeline.terminal.api.ticker_narrative.compute_narrative",
        lambda t: {"marker_count": counts.get(t, 5)},
    )

    issues = audit_chart_universe(
        universe_path=universe_path, fno_dir=fno_dir, state_path=state_path,
        tickers=("T000", "T001"), now=datetime(2026, 4, 30),
    )
    regress = [i for i in issues if i["kind"] == "marker_regression"]
    assert len(regress) == 1
    assert "T000" in regress[0]["detail"]
    assert "12" in regress[0]["detail"] and "0" in regress[0]["detail"]
    # T001 had prev=0 so no regression alert fires.
    assert all("T001" not in i["detail"] for i in regress)


def test_marker_compute_exception_fires_regression(tmp_path, monkeypatch):
    """If compute_narrative raises, that's a fail-loud regression even with
    no prior state — a broken endpoint is worse than a legitimate-zero."""
    tickers = [f"T{i:03d}" for i in range(273)]
    last_dates = {t: "2026-04-29" for t in tickers}
    universe_path, fno_dir, state_path = _setup(tmp_path, tickers, last_dates)

    def _boom(t):
        raise RuntimeError("simulated narrative failure")
    monkeypatch.setattr(
        "pipeline.terminal.api.ticker_narrative.compute_narrative", _boom
    )

    issues = audit_chart_universe(
        universe_path=universe_path, fno_dir=fno_dir, state_path=state_path,
        tickers=("T000",), now=datetime(2026, 4, 30),
    )
    regress = [i for i in issues if i["kind"] == "marker_regression"]
    assert len(regress) == 1
    assert "exception" in regress[0]["detail"]
    # Exception path must NOT overwrite the state file (sentinel -1 skipped).
    if state_path.exists():
        persisted = json.loads(state_path.read_text())
        assert "T000" not in persisted


def test_dedup_keeps_state_after_normal_run(tmp_path, monkeypatch):
    """State should accumulate across runs so future regressions are catchable."""
    tickers = [f"T{i:03d}" for i in range(273)]
    last_dates = {t: "2026-04-29" for t in tickers}
    universe_path, fno_dir, state_path = _setup(tmp_path, tickers, last_dates)

    monkeypatch.setattr(
        "pipeline.terminal.api.ticker_narrative.compute_narrative",
        lambda t: {"marker_count": 7},
    )
    audit_chart_universe(
        universe_path=universe_path, fno_dir=fno_dir, state_path=state_path,
        tickers=("T000",), now=datetime(2026, 4, 30),
    )
    audit_chart_universe(
        universe_path=universe_path, fno_dir=fno_dir, state_path=state_path,
        tickers=("T000",), now=datetime(2026, 5, 1),
    )
    persisted = json.loads(state_path.read_text())
    assert persisted["T000"]["marker_count"] == 7
    # last_check should be the LATER timestamp, proving the second run wrote.
    assert persisted["T000"]["last_check"].startswith("2026-05-01")
