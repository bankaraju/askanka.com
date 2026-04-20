"""Tests for the NSE F&O bhavcopy PCR fetcher."""
from __future__ import annotations

import io
import zipfile

import pandas as pd
import pytest

from pipeline.research.phase_c_backtest import bhavcopy


_SAMPLE_HEADER = (
    "TradDt,BizDt,Sgmt,Src,FinInstrmTp,FinInstrmId,ISIN,TckrSymb,SctySrs,XpryDt,"
    "FininstrmActlXpryDt,StrkPric,OptnTp,FinInstrmNm,OpnPric,HghPric,LwPric,"
    "ClsPric,LastPric,PrvsClsgPric,UndrlygPric,SttlmPric,OpnIntrst,ChngInOpnIntrst,"
    "TtlTradgVol,TtlTrfVal,TtlNbOfTxsExctd,SsnId,NewBrdLotQty,Rmks,Rsvd1,Rsvd2,"
    "Rsvd3,Rsvd4"
)


def _row(*, fin_tp: str, sym: str, opt: str, oi: float, strike: float = 100.0) -> str:
    """Build one CSV row matching the live NSE schema."""
    return (
        f"2024-10-15,2024-10-15,FO,NSE,{fin_tp},1,,{sym},,2024-10-31,2024-10-31,"
        f"{strike:.2f},{opt},STUB,0,0,0,0,0,0,100,0,{oi},0,0,0,0,F1,500,,,,,"
    )


def test_parse_aggregates_oi_and_computes_pcr():
    csv_text = "\n".join([
        _SAMPLE_HEADER,
        _row(fin_tp="STO", sym="ABC", opt="CE", oi=1000, strike=100),
        _row(fin_tp="STO", sym="ABC", opt="CE", oi=500, strike=110),  # second strike
        _row(fin_tp="STO", sym="ABC", opt="PE", oi=750, strike=100),
    ])
    df = bhavcopy._parse_stock_options(csv_text)
    assert len(df) == 1
    row = df.iloc[0]
    assert row["symbol"] == "ABC"
    assert row["call_oi"] == 1500.0
    assert row["put_oi"] == 750.0
    assert row["pcr"] == pytest.approx(0.5, abs=1e-9)


def test_parse_skips_index_options_and_futures():
    csv_text = "\n".join([
        _SAMPLE_HEADER,
        _row(fin_tp="IDO", sym="NIFTY", opt="CE", oi=99999),  # Index Option — must skip
        _row(fin_tp="STF", sym="ABC", opt="XX", oi=42),       # Stock Future — must skip
        _row(fin_tp="STO", sym="ABC", opt="CE", oi=100),      # Stock Option — keep
        _row(fin_tp="STO", sym="ABC", opt="PE", oi=50),
    ])
    df = bhavcopy._parse_stock_options(csv_text)
    assert set(df["symbol"]) == {"ABC"}
    assert df.iloc[0]["call_oi"] == 100.0
    assert df.iloc[0]["put_oi"] == 50.0


def test_parse_handles_zero_call_oi_as_nan_pcr():
    csv_text = "\n".join([
        _SAMPLE_HEADER,
        _row(fin_tp="STO", sym="XYZ", opt="PE", oi=200),
    ])
    df = bhavcopy._parse_stock_options(csv_text)
    row = df.iloc[0]
    assert row["call_oi"] == 0.0
    assert row["put_oi"] == 200.0
    assert pd.isna(row["pcr"])


def test_parse_empty_csv_returns_empty_frame():
    csv_text = _SAMPLE_HEADER + "\n"
    df = bhavcopy._parse_stock_options(csv_text)
    assert df.empty
    assert list(df.columns) == ["symbol", "call_oi", "put_oi", "pcr"]


def test_pcr_by_symbol_skips_nan(tmp_path, monkeypatch):
    # Stub fetch_pcr to return a frame with one NaN PCR row
    df = pd.DataFrame([
        {"symbol": "GOOD", "call_oi": 1000.0, "put_oi": 500.0, "pcr": 0.5},
        {"symbol": "ZERO_CALL", "call_oi": 0.0, "put_oi": 200.0, "pcr": float("nan")},
    ])
    monkeypatch.setattr(bhavcopy, "fetch_pcr", lambda d: df)
    result = bhavcopy.pcr_by_symbol("2024-10-15")
    assert result == {"GOOD": 0.5}


def test_pcr_by_symbol_returns_empty_dict_on_unavailable(monkeypatch):
    def _raise(_d):
        raise bhavcopy.BhavcopyUnavailable("test")
    monkeypatch.setattr(bhavcopy, "fetch_pcr", _raise)
    assert bhavcopy.pcr_by_symbol("2024-10-15") == {}


def test_fetch_pcr_returns_cached_parquet(tmp_path, monkeypatch):
    cache_dir = tmp_path / "pcr_history"
    cache_dir.mkdir()
    monkeypatch.setattr(bhavcopy, "_PCR_DIR", cache_dir)
    expected = pd.DataFrame([{"symbol": "X", "call_oi": 1.0, "put_oi": 1.0, "pcr": 1.0}])
    expected.to_parquet(cache_dir / "2024-10-15.parquet", index=False)

    def _should_not_be_called(*a, **kw):
        raise AssertionError("download attempted on cache hit")
    monkeypatch.setattr(bhavcopy, "_download_zip", _should_not_be_called)
    out = bhavcopy.fetch_pcr("2024-10-15")
    assert list(out["symbol"]) == ["X"]


def test_fetch_pcr_writes_cache_on_miss(tmp_path, monkeypatch):
    cache_dir = tmp_path / "pcr_history"
    cache_dir.mkdir()
    monkeypatch.setattr(bhavcopy, "_PCR_DIR", cache_dir)

    csv_text = "\n".join([
        _SAMPLE_HEADER,
        _row(fin_tp="STO", sym="ABC", opt="CE", oi=1000),
        _row(fin_tp="STO", sym="ABC", opt="PE", oi=500),
    ])
    blob = io.BytesIO()
    with zipfile.ZipFile(blob, "w") as z:
        z.writestr("BhavCopy_NSE_FO_0_0_0_20241015_F_0000.csv", csv_text)
    monkeypatch.setattr(bhavcopy, "_download_zip", lambda url: blob.getvalue())

    out = bhavcopy.fetch_pcr("2024-10-15")
    assert (cache_dir / "2024-10-15.parquet").is_file()
    assert out.iloc[0]["symbol"] == "ABC"
    assert out.iloc[0]["pcr"] == pytest.approx(0.5)
