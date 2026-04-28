"""Tests for ``pipeline.research.intraday_v1.bhavcopy_backfill``.

Covers the no-hallucination contract: real bhavcopy bytes in, real OI out.
Missing date (404, parse failure, holiday) means no file emitted — no
interpolation, no carry-forward, no synthetic defaults. Pre-existing files
are preserved (live oi_scanner snapshots are richer than what bhavcopy gives).
"""
from __future__ import annotations

import io
import json
import zipfile
from datetime import date
from pathlib import Path
from typing import Optional

import pandas as pd
import pytest

from pipeline.research.intraday_v1 import bhavcopy_backfill


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Modern UDiFF column order — matches NSE's
# BhavCopy_NSE_FO_0_0_0_<YYYYMMDD>_F_0000.csv.zip schema (verified 2026-04-28).
UDIFF_COLS = [
    "TradDt", "BizDt", "Sgmt", "Src", "FinInstrmTp", "FinInstrmId", "ISIN",
    "TckrSymb", "SctySrs", "XpryDt", "FininstrmActlXpryDt", "StrkPric",
    "OptnTp", "FinInstrmNm", "OpnPric", "HghPric", "LwPric", "ClsPric",
    "LastPric", "PrvsClsgPric", "UndrlygPric", "SttlmPric", "OpnIntrst",
    "ChngInOpnIntrst", "TtlTradgVol", "TtlTrfVal", "TtlNbOfTxsExctd",
    "SsnId", "NewBrdLotQty", "Rmks", "Rsvd1", "Rsvd2", "Rsvd3", "Rsvd4",
]


def _make_row(*, instr_tp: str, ticker: str, expiry: str, strike: float,
              opt_tp: str, oi: int, trade_dt: str = "2026-04-28") -> dict:
    """Build a minimal bhavcopy row — only fields the parser/aggregator reads
    are populated; the rest are filled with bhavcopy-realistic defaults."""
    return {
        "TradDt": trade_dt, "BizDt": trade_dt, "Sgmt": "FO", "Src": "NSE",
        "FinInstrmTp": instr_tp, "FinInstrmId": 0, "ISIN": "",
        "TckrSymb": ticker, "SctySrs": "", "XpryDt": expiry,
        "FininstrmActlXpryDt": expiry, "StrkPric": strike, "OptnTp": opt_tp,
        "FinInstrmNm": "", "OpnPric": 0.0, "HghPric": 0.0, "LwPric": 0.0,
        "ClsPric": 0.0, "LastPric": 0.0, "PrvsClsgPric": 0.0,
        "UndrlygPric": 0.0, "SttlmPric": 0.0, "OpnIntrst": oi,
        "ChngInOpnIntrst": 0, "TtlTradgVol": 0, "TtlTrfVal": 0.0,
        "TtlNbOfTxsExctd": 0, "SsnId": "F1", "NewBrdLotQty": 0,
        "Rmks": "", "Rsvd1": "", "Rsvd2": "", "Rsvd3": "", "Rsvd4": "",
    }


def _zip_bytes_from_rows(rows: list, member_name: str = "fo.csv") -> bytes:
    """Produce a ZIP whose only member is a UDiFF-shaped CSV of ``rows``."""
    df = pd.DataFrame(rows, columns=UDIFF_COLS)
    csv_text = df.to_csv(index=False)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(member_name, csv_text)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_parse_bhavcopy_extracts_csv_from_zip() -> None:
    rows = [
        _make_row(instr_tp="STO", ticker="RELIANCE", expiry="2026-04-28",
                  strike=2800.0, opt_tp="CE", oi=12345),
        _make_row(instr_tp="STO", ticker="RELIANCE", expiry="2026-04-28",
                  strike=2800.0, opt_tp="PE", oi=23456),
    ]
    zb = _zip_bytes_from_rows(rows)
    df = bhavcopy_backfill.parse_bhavcopy(zb)
    assert len(df) == 2
    assert set(["FinInstrmTp", "TckrSymb", "XpryDt", "OptnTp", "OpnIntrst"]).issubset(df.columns)
    assert df.iloc[0]["TckrSymb"] == "RELIANCE"
    assert int(df.iloc[1]["OpnIntrst"]) == 23456


def test_aggregate_picks_next_month_expiry_correctly() -> None:
    """Three expiries for one symbol — aggregator must pick the
    second-earliest expiry > eval_date as 'next' and sum its OI."""
    eval_d = date(2026, 4, 28)
    rows = [
        # Near (2026-04-28, expires today)
        _make_row(instr_tp="STO", ticker="ACME", expiry="2026-04-28",
                  strike=100.0, opt_tp="CE", oi=11),
        _make_row(instr_tp="STO", ticker="ACME", expiry="2026-04-28",
                  strike=100.0, opt_tp="PE", oi=22),
        # Next (2026-05-26)
        _make_row(instr_tp="STO", ticker="ACME", expiry="2026-05-26",
                  strike=100.0, opt_tp="CE", oi=100),
        _make_row(instr_tp="STO", ticker="ACME", expiry="2026-05-26",
                  strike=110.0, opt_tp="CE", oi=200),
        _make_row(instr_tp="STO", ticker="ACME", expiry="2026-05-26",
                  strike=100.0, opt_tp="PE", oi=300),
        # Far (2026-06-30, must NOT be the 'next' chain)
        _make_row(instr_tp="STO", ticker="ACME", expiry="2026-06-30",
                  strike=100.0, opt_tp="CE", oi=99_999),
        _make_row(instr_tp="STO", ticker="ACME", expiry="2026-06-30",
                  strike=100.0, opt_tp="PE", oi=88_888),
    ]
    df = pd.DataFrame(rows, columns=UDIFF_COLS)
    out = bhavcopy_backfill.aggregate_oi_for_date(df, eval_d)
    assert "ACME" in out
    blob = out["ACME"]
    assert blob["near"]["expiry"] == "2026-04-28"
    assert blob["near"]["call_oi"] == 11
    assert blob["near"]["put_oi"] == 22
    assert blob["next"]["expiry"] == "2026-05-26"
    assert blob["next"]["call_oi"] == 300  # 100 + 200, summed across strikes
    assert blob["next"]["put_oi"] == 300


def test_aggregate_skips_symbol_with_only_one_expiry() -> None:
    """A symbol with only a near expiry has no 'next' chain — must be omitted."""
    eval_d = date(2026, 4, 28)
    rows = [
        _make_row(instr_tp="STO", ticker="ACME", expiry="2026-04-28",
                  strike=100.0, opt_tp="CE", oi=11),
        _make_row(instr_tp="STO", ticker="ACME", expiry="2026-04-28",
                  strike=100.0, opt_tp="PE", oi=22),
        # Multi-expiry control symbol so the output dict isn't empty
        _make_row(instr_tp="STO", ticker="OK", expiry="2026-04-28",
                  strike=50.0, opt_tp="CE", oi=1),
        _make_row(instr_tp="STO", ticker="OK", expiry="2026-04-28",
                  strike=50.0, opt_tp="PE", oi=2),
        _make_row(instr_tp="STO", ticker="OK", expiry="2026-05-26",
                  strike=50.0, opt_tp="CE", oi=3),
        _make_row(instr_tp="STO", ticker="OK", expiry="2026-05-26",
                  strike=50.0, opt_tp="PE", oi=4),
    ]
    df = pd.DataFrame(rows, columns=UDIFF_COLS)
    out = bhavcopy_backfill.aggregate_oi_for_date(df, eval_d)
    assert "ACME" not in out
    assert "OK" in out


def test_aggregate_includes_only_optstk_and_optidx_not_futures() -> None:
    """Stock futures (STF) and index futures (IDF) must be filtered out;
    options only (STO/IDO) are retained."""
    eval_d = date(2026, 4, 28)
    rows = [
        # Futures rows (must be ignored)
        _make_row(instr_tp="STF", ticker="ACME", expiry="2026-04-28",
                  strike=0.0, opt_tp="", oi=99_999),
        _make_row(instr_tp="STF", ticker="ACME", expiry="2026-05-26",
                  strike=0.0, opt_tp="", oi=88_888),
        _make_row(instr_tp="IDF", ticker="NIFTY", expiry="2026-04-28",
                  strike=0.0, opt_tp="", oi=77_777),
        _make_row(instr_tp="IDF", ticker="NIFTY", expiry="2026-05-26",
                  strike=0.0, opt_tp="", oi=66_666),
        # Options rows for same symbols (legitimate)
        _make_row(instr_tp="STO", ticker="ACME", expiry="2026-04-28",
                  strike=100.0, opt_tp="CE", oi=11),
        _make_row(instr_tp="STO", ticker="ACME", expiry="2026-04-28",
                  strike=100.0, opt_tp="PE", oi=22),
        _make_row(instr_tp="STO", ticker="ACME", expiry="2026-05-26",
                  strike=100.0, opt_tp="CE", oi=300),
        _make_row(instr_tp="STO", ticker="ACME", expiry="2026-05-26",
                  strike=100.0, opt_tp="PE", oi=400),
        _make_row(instr_tp="IDO", ticker="NIFTY", expiry="2026-04-28",
                  strike=24000.0, opt_tp="CE", oi=10),
        _make_row(instr_tp="IDO", ticker="NIFTY", expiry="2026-04-28",
                  strike=24000.0, opt_tp="PE", oi=20),
        _make_row(instr_tp="IDO", ticker="NIFTY", expiry="2026-05-26",
                  strike=24000.0, opt_tp="CE", oi=500),
        _make_row(instr_tp="IDO", ticker="NIFTY", expiry="2026-05-26",
                  strike=24000.0, opt_tp="PE", oi=600),
    ]
    df = pd.DataFrame(rows, columns=UDIFF_COLS)
    out = bhavcopy_backfill.aggregate_oi_for_date(df, eval_d)
    # Futures OI (99_999/88_888/77_777/66_666) must NOT leak into the output.
    assert out["ACME"]["next"]["call_oi"] == 300
    assert out["ACME"]["next"]["put_oi"] == 400
    assert out["NIFTY"]["next"]["call_oi"] == 500
    assert out["NIFTY"]["next"]["put_oi"] == 600


def test_backfill_range_skips_existing_files(monkeypatch, tmp_path: Path) -> None:
    """Pre-existing JSON file (e.g., a richer live oi_scanner snapshot) must
    not be overwritten by the bhavcopy backfill."""
    out_dir = tmp_path / "oi"
    out_dir.mkdir()
    pre_existing_d = date(2026, 4, 27)
    pre_existing_path = out_dir / f"{pre_existing_d.isoformat()}.json"
    sentinel = {"_marker": "pre-existing-live-snapshot"}
    pre_existing_path.write_text(json.dumps(sentinel), encoding="utf-8")

    # Build a mock zip we'd hand to backfill if the file weren't already there.
    rows = [
        _make_row(instr_tp="STO", ticker="ACME", expiry="2026-04-27",
                  strike=100.0, opt_tp="CE", oi=11, trade_dt="2026-04-27"),
        _make_row(instr_tp="STO", ticker="ACME", expiry="2026-04-27",
                  strike=100.0, opt_tp="PE", oi=22, trade_dt="2026-04-27"),
        _make_row(instr_tp="STO", ticker="ACME", expiry="2026-05-26",
                  strike=100.0, opt_tp="CE", oi=300, trade_dt="2026-04-27"),
        _make_row(instr_tp="STO", ticker="ACME", expiry="2026-05-26",
                  strike=100.0, opt_tp="PE", oi=400, trade_dt="2026-04-27"),
    ]
    zb = _zip_bytes_from_rows(rows)
    monkeypatch.setattr(bhavcopy_backfill, "download_bhavcopy", lambda d: zb)

    summary = bhavcopy_backfill.backfill_range(pre_existing_d, pre_existing_d, out_dir)

    # File preserved (not overwritten)
    assert json.loads(pre_existing_path.read_text(encoding="utf-8")) == sentinel
    assert summary["days_attempted"] == 1
    assert summary["days_skipped_existing"] == 1
    assert summary["days_written"] == 0


def test_backfill_range_skips_holidays(monkeypatch, tmp_path: Path) -> None:
    """A 404 (or any None return from download_bhavcopy) must produce no file
    and tally cleanly under days_skipped_404_or_holiday."""
    out_dir = tmp_path / "oi"
    out_dir.mkdir()

    holiday_d = date(2026, 4, 14)
    rows_for_other_day = [
        _make_row(instr_tp="STO", ticker="ACME", expiry="2026-04-15",
                  strike=100.0, opt_tp="CE", oi=11, trade_dt="2026-04-15"),
        _make_row(instr_tp="STO", ticker="ACME", expiry="2026-04-15",
                  strike=100.0, opt_tp="PE", oi=22, trade_dt="2026-04-15"),
        _make_row(instr_tp="STO", ticker="ACME", expiry="2026-05-26",
                  strike=100.0, opt_tp="CE", oi=300, trade_dt="2026-04-15"),
        _make_row(instr_tp="STO", ticker="ACME", expiry="2026-05-26",
                  strike=100.0, opt_tp="PE", oi=400, trade_dt="2026-04-15"),
    ]
    zb_other = _zip_bytes_from_rows(rows_for_other_day)

    def fake_download(d: date) -> Optional[bytes]:
        if d == holiday_d:
            return None
        return zb_other

    monkeypatch.setattr(bhavcopy_backfill, "download_bhavcopy", fake_download)

    summary = bhavcopy_backfill.backfill_range(holiday_d, date(2026, 4, 15), out_dir)

    assert summary["days_attempted"] == 2
    assert summary["days_skipped_404_or_holiday"] == 1
    assert summary["days_written"] == 1
    # Holiday produced no file
    assert not (out_dir / f"{holiday_d.isoformat()}.json").exists()
    # Non-holiday produced exactly one file
    written = out_dir / "2026-04-15.json"
    assert written.exists()
    blob = json.loads(written.read_text(encoding="utf-8"))
    assert blob["ACME"]["next"]["call_oi"] == 300
    assert blob["ACME"]["next"]["put_oi"] == 400
