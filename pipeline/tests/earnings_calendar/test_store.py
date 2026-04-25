import datetime as dt
import json

import pandas as pd

from pipeline.earnings_calendar import store
from pipeline.earnings_calendar.classifier import EventKind


def _make_event(symbol: str, event_date: dt.date, kind: EventKind = EventKind.QUARTERLY_EARNINGS):
    return {
        "symbol": symbol,
        "event_date": event_date,
        "kind": kind,
        "has_dividend": False,
        "has_fundraise": False,
        "agenda_raw": "Quarterly Results",
    }


def test_write_day_json_creates_file(tmp_path):
    events = [
        _make_event("RELIANCE", dt.date(2026, 4, 24)),
        _make_event("HDFCBANK", dt.date(2026, 4, 18)),
    ]
    out = store.write_day_json(events, tmp_path, asof=dt.date(2026, 4, 25))
    assert out.exists()
    assert out.name == "2026-04-25.json"
    data = json.loads(out.read_text())
    assert data["asof"] == "2026-04-25"
    assert len(data["events"]) == 2
    assert data["events"][0]["event_date"] == "2026-04-24"
    assert data["schema_version"] == "v1"


def test_write_day_json_creates_directories(tmp_path):
    sub = tmp_path / "deeper" / "tree"
    out = store.write_day_json([], sub, asof=dt.date(2026, 4, 25))
    assert out.exists()
    assert sub.exists()


def test_append_history_parquet_idempotent(tmp_path):
    events = [_make_event("RELIANCE", dt.date(2026, 4, 24))]
    p = tmp_path / "history.parquet"
    store.append_history(events, p, asof=dt.date(2026, 4, 25))
    n1 = len(pd.read_parquet(p))
    store.append_history(events, p, asof=dt.date(2026, 4, 25))
    n2 = len(pd.read_parquet(p))
    assert n1 == n2 == 1, "duplicate (symbol, event_date, asof) must not produce a second row"


def test_append_history_distinguishes_asof_versions(tmp_path):
    ev = _make_event("RELIANCE", dt.date(2026, 4, 24))
    p = tmp_path / "history.parquet"
    store.append_history([ev], p, asof=dt.date(2026, 4, 25))
    store.append_history([ev], p, asof=dt.date(2026, 4, 26))
    df = pd.read_parquet(p)
    assert len(df) == 2
    assert set(df["asof"].dt.strftime("%Y-%m-%d")) == {"2026-04-25", "2026-04-26"}


def test_append_history_creates_parent_dir(tmp_path):
    p = tmp_path / "nested" / "dir" / "history.parquet"
    store.append_history(
        [_make_event("X", dt.date(2026, 4, 24))], p, asof=dt.date(2026, 4, 25)
    )
    assert p.exists()


def test_append_history_empty_events_does_not_crash(tmp_path):
    p = tmp_path / "history.parquet"
    store.append_history([], p, asof=dt.date(2026, 4, 25))
    assert not p.exists() or len(pd.read_parquet(p)) == 0
