"""Earnings-calendar storage layer.

Writes one JSON snapshot per as-of date and appends to a cumulative parquet
keyed by (symbol, event_date, asof) so vendor-side restatements (data
validation policy §11.2) remain visible without overwriting prior
snapshots.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Iterable

import pandas as pd

SCHEMA_VERSION = "v1"


def _serialise_event(ev: dict) -> dict:
    out = dict(ev)
    out["event_date"] = ev["event_date"].isoformat()
    out["kind"] = str(ev["kind"])
    return out


def write_day_json(
    events: Iterable[dict], out_dir: Path | str, asof: dt.date
) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{asof.isoformat()}.json"
    body = {
        "asof": asof.isoformat(),
        "schema_version": SCHEMA_VERSION,
        "events": [_serialise_event(e) for e in events],
    }
    out.write_text(json.dumps(body, indent=2))
    return out


def _events_to_df(events: Iterable[dict], asof: dt.date) -> pd.DataFrame:
    rows = []
    for ev in events:
        rows.append(
            {
                "symbol": ev["symbol"],
                "event_date": pd.Timestamp(ev["event_date"]),
                "kind": str(ev["kind"]),
                "has_dividend": bool(ev["has_dividend"]),
                "has_fundraise": bool(ev["has_fundraise"]),
                "agenda_raw": ev.get("agenda_raw", ""),
                "asof": pd.Timestamp(asof),
            }
        )
    if not rows:
        return pd.DataFrame(
            columns=["symbol", "event_date", "kind", "has_dividend", "has_fundraise", "agenda_raw", "asof"]
        )
    return pd.DataFrame(rows)


def append_history(
    events: Iterable[dict], parquet_path: Path | str, asof: dt.date
) -> None:
    parquet_path = Path(parquet_path)
    new_df = _events_to_df(events, asof)
    if new_df.empty and not parquet_path.exists():
        return
    if parquet_path.exists():
        old_df = pd.read_parquet(parquet_path)
        combined = pd.concat([old_df, new_df], ignore_index=True)
    else:
        combined = new_df
    combined = combined.drop_duplicates(
        subset=["symbol", "event_date", "asof"]
    ).reset_index(drop=True)
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    combined.to_parquet(parquet_path, index=False)
