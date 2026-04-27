"""TDD tests for pipeline.phase_c_options_report — T8.

Each test writes synthetic JSON ledgers to tmp_path, patches module-level
path constants, and asserts on the returned Markdown string.

Spec: docs/superpowers/specs/2026-04-27-phase-c-options-paired-shadow-design.md §11
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import pipeline.phase_c_options_report as report_mod
from pipeline.phase_c_options_report import build_report


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_ledgers(
    tmp_path: Path,
    futures_rows: list[dict],
    options_rows: list[dict],
) -> tuple[Path, Path]:
    fp = tmp_path / "live_paper_ledger.json"
    op = tmp_path / "live_paper_options_ledger.json"
    fp.write_text(json.dumps(futures_rows), encoding="utf-8")
    op.write_text(json.dumps(options_rows), encoding="utf-8")
    return fp, op


def _base_futures_row(
    signal_id: str = "2026-04-30_RELIANCE_0935",
    pnl_net_inr: float = 200.0,
    notional_inr: float = 50000.0,
    is_expiry: bool = False,
) -> dict:
    return {
        "signal_id": signal_id,
        "date": signal_id.split("_")[0],
        "symbol": signal_id.split("_")[1],
        "signal_time": f"{signal_id.split('_')[0]} 09:35:00",
        "side": "LONG",
        "entry_px": 2400.0,
        "notional_inr": notional_inr,
        "status": "CLOSED",
        "pnl_net_inr": pnl_net_inr,
        "pnl_gross_inr": pnl_net_inr + 20.0,
    }


def _base_options_row(
    signal_id: str = "2026-04-30_RELIANCE_0935",
    pnl_net_pct: float = 0.05,
    is_expiry: bool = False,
    tier: str = "UNKNOWN",
    entry_iv: float | None = 0.25,
    dte: int = 15,
    status: str = "CLOSED",
    symbol: str | None = None,
) -> dict:
    sym = symbol or signal_id.split("_")[1]
    return {
        "signal_id": signal_id,
        "date": signal_id.split("_")[0],
        "symbol": sym,
        "side": "LONG",
        "option_type": "CE",
        "expiry_date": "2026-05-28",
        "days_to_expiry": dte,
        "is_expiry_day": is_expiry,
        "strike": 2400,
        "tradingsymbol": f"{sym}26MAY2400CE",
        "instrument_token": 12345678,
        "lot_size": 250,
        "lots": 1,
        "notional_at_entry": 30000.0,
        "entry_time": f"{signal_id.split('_')[0]}T09:35:12+05:30",
        "entry_bid": 119.5,
        "entry_ask": 122.0,
        "entry_mid": 120.75,
        "spread_pct_at_entry": 0.0207,
        "entry_iv": entry_iv,
        "entry_delta": 0.51,
        "entry_theta": -3.4,
        "entry_vega": 4.1,
        "drift_vs_rent_tier": tier,
        "drift_vs_rent_matrix": None,
        "status": status,
        "skip_reason": None,
        "exit_time": f"{signal_id.split('_')[0]}T14:30:00+05:30",
        "exit_bid": 130.0,
        "exit_ask": 132.0,
        "exit_mid": 131.0,
        "seconds_to_expiry_at_close": None,
        "pnl_gross_pct": pnl_net_pct + 0.005,
        "pnl_net_pct": pnl_net_pct,
        "pnl_gross_inr": (pnl_net_pct + 0.005) * 30000.0,
        "pnl_net_inr": pnl_net_pct * 30000.0,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestEmptyLedgers:
    def test_empty_ledgers(self, tmp_path, monkeypatch):
        fp, op = _write_ledgers(tmp_path, [], [])
        monkeypatch.setattr(report_mod, "FUTURES_LEDGER_PATH", fp)
        monkeypatch.setattr(report_mod, "OPTIONS_LEDGER_PATH", op)
        out_path = tmp_path / "report.md"
        monkeypatch.setattr(report_mod, "REPORT_PATH", out_path)

        md = build_report()

        assert "INSUFFICIENT_N" in md
        assert "N=0" in md
        # No crash — all 5 table headers still present
        assert "Table A" in md
        assert "Table B" in md
        assert "Table C" in md
        assert "Table D" in md
        assert "Table E" in md


class TestMissingLedgerFiles:
    def test_raises_file_not_found(self, tmp_path, monkeypatch):
        monkeypatch.setattr(report_mod, "FUTURES_LEDGER_PATH", tmp_path / "no.json")
        monkeypatch.setattr(report_mod, "OPTIONS_LEDGER_PATH", tmp_path / "nope.json")
        monkeypatch.setattr(report_mod, "REPORT_PATH", tmp_path / "out.md")

        with pytest.raises(FileNotFoundError):
            build_report()


class TestJoinContract:
    def test_inner_join_on_signal_id(self, tmp_path, monkeypatch):
        # 5 futures CLOSED, 3 matching options CLOSED
        ids = [f"2026-04-30_RELIANCE_093{i}" for i in range(5)]
        futures = [_base_futures_row(sid) for sid in ids]
        options = [_base_options_row(sid) for sid in ids[:3]]

        fp, op = _write_ledgers(tmp_path, futures, options)
        monkeypatch.setattr(report_mod, "FUTURES_LEDGER_PATH", fp)
        monkeypatch.setattr(report_mod, "OPTIONS_LEDGER_PATH", op)
        out_path = tmp_path / "report.md"
        monkeypatch.setattr(report_mod, "REPORT_PATH", out_path)

        md = build_report()

        assert "matched N=3" in md
        assert "unmatched-futures N=2" in md
        assert "unmatched-options N=0" in md


class TestTableAPairedDiff:
    def test_sign_correct_options_outperform(self, tmp_path, monkeypatch):
        """Options +4% vs futures +2% => mean paired_diff ~ +0.02."""
        ids = [f"2026-04-30_RELIANCE_093{i}" for i in range(6)]
        futures = [_base_futures_row(sid, pnl_net_inr=1000.0, notional_inr=50000.0) for sid in ids]
        # futures_pnl_pct = 1000/50000 = 0.02
        options = [_base_options_row(sid, pnl_net_pct=0.04) for sid in ids]

        fp, op = _write_ledgers(tmp_path, futures, options)
        monkeypatch.setattr(report_mod, "FUTURES_LEDGER_PATH", fp)
        monkeypatch.setattr(report_mod, "OPTIONS_LEDGER_PATH", op)
        out_path = tmp_path / "report.md"
        monkeypatch.setattr(report_mod, "REPORT_PATH", out_path)

        md = build_report()

        # mean paired diff should be +0.02 -> "+2.00%"
        assert "+2.00%" in md

    def test_bootstrap_skipped_when_n_below_5(self, tmp_path, monkeypatch):
        ids = [f"2026-04-30_RELIANCE_093{i}" for i in range(3)]
        futures = [_base_futures_row(sid) for sid in ids]
        options = [_base_options_row(sid) for sid in ids]

        fp, op = _write_ledgers(tmp_path, futures, options)
        monkeypatch.setattr(report_mod, "FUTURES_LEDGER_PATH", fp)
        monkeypatch.setattr(report_mod, "OPTIONS_LEDGER_PATH", op)
        out_path = tmp_path / "report.md"
        monkeypatch.setattr(report_mod, "REPORT_PATH", out_path)

        md = build_report()

        assert "insufficient n" in md.lower()

    def test_bootstrap_deterministic_with_seed(self, tmp_path, monkeypatch):
        ids = [f"2026-04-30_RELIANCE_093{i}" for i in range(8)]
        futures = [_base_futures_row(sid, pnl_net_inr=float(i * 100), notional_inr=50000.0) for i, sid in enumerate(ids)]
        options = [_base_options_row(sid, pnl_net_pct=float(i) * 0.01) for i, sid in enumerate(ids)]

        fp, op = _write_ledgers(tmp_path, futures, options)
        monkeypatch.setattr(report_mod, "FUTURES_LEDGER_PATH", fp)
        monkeypatch.setattr(report_mod, "OPTIONS_LEDGER_PATH", op)
        out_path = tmp_path / "report.md"
        monkeypatch.setattr(report_mod, "REPORT_PATH", out_path)

        md1 = build_report(seed=42)
        md2 = build_report(seed=42)
        assert md1 == md2


class TestTableBTierGroups:
    def test_groups_by_tier_and_expiry(self, tmp_path, monkeypatch):
        rows_futures = []
        rows_options = []
        # 2 HIGH-ALPHA non-expiry
        for i in range(2):
            sid = f"2026-04-30_RELIANCE_093{i}"
            rows_futures.append(_base_futures_row(sid))
            rows_options.append(_base_options_row(sid, tier="HIGH-ALPHA SYNTHETIC", is_expiry=False))
        # 2 EXPERIMENTAL non-expiry
        for i in range(2, 4):
            sid = f"2026-04-30_TATAMOTOR_093{i}"
            rows_futures.append(_base_futures_row(sid))
            rows_options.append(_base_options_row(sid, tier="EXPERIMENTAL", is_expiry=False))
        # 2 UNKNOWN expiry-day
        for i in range(4, 6):
            sid = f"2026-04-30_INFOSYS_093{i}"
            rows_futures.append(_base_futures_row(sid))
            rows_options.append(_base_options_row(sid, tier="UNKNOWN", is_expiry=True, dte=0))

        fp, op = _write_ledgers(tmp_path, rows_futures, rows_options)
        monkeypatch.setattr(report_mod, "FUTURES_LEDGER_PATH", fp)
        monkeypatch.setattr(report_mod, "OPTIONS_LEDGER_PATH", op)
        out_path = tmp_path / "report.md"
        monkeypatch.setattr(report_mod, "REPORT_PATH", out_path)

        md = build_report()

        assert "HIGH-ALPHA SYNTHETIC" in md
        assert "EXPERIMENTAL" in md
        assert "UNKNOWN" in md
        # expiry-day stratum exists
        assert "is_expiry_day=True" in md
        assert "is_expiry_day=False" in md


class TestTableCIVTerciles:
    def test_tercile_bucket_sizes(self, tmp_path, monkeypatch):
        ivs = [0.10, 0.15, 0.18, 0.20, 0.25, 0.28, 0.32, 0.40, 0.50]
        rows_futures = []
        rows_options = []
        for i, iv in enumerate(ivs):
            sid = f"2026-04-30_RELIANCE_093{i}"
            rows_futures.append(_base_futures_row(sid))
            rows_options.append(_base_options_row(sid, entry_iv=iv))

        fp, op = _write_ledgers(tmp_path, rows_futures, rows_options)
        monkeypatch.setattr(report_mod, "FUTURES_LEDGER_PATH", fp)
        monkeypatch.setattr(report_mod, "OPTIONS_LEDGER_PATH", op)
        out_path = tmp_path / "report.md"
        monkeypatch.setattr(report_mod, "REPORT_PATH", out_path)

        md = build_report()

        # 9 rows, each bucket gets 3
        assert "low" in md.lower()
        assert "mid" in md.lower()
        assert "high" in md.lower()
        # Each non-expiry bucket row has N=3
        assert "| 3 |" in md or "N=3" in md or "| 3|" in md

    def test_excludes_null_iv(self, tmp_path, monkeypatch):
        rows_futures = []
        rows_options = []
        for i in range(5):
            sid = f"2026-04-30_RELIANCE_093{i}"
            rows_futures.append(_base_futures_row(sid))
            rows_options.append(_base_options_row(sid, entry_iv=None))

        fp, op = _write_ledgers(tmp_path, rows_futures, rows_options)
        monkeypatch.setattr(report_mod, "FUTURES_LEDGER_PATH", fp)
        monkeypatch.setattr(report_mod, "OPTIONS_LEDGER_PATH", op)
        out_path = tmp_path / "report.md"
        monkeypatch.setattr(report_mod, "REPORT_PATH", out_path)

        md = build_report()

        # null-IV rows excluded from Table C, footnoted
        assert "iv_null_excluded" in md or "entry_iv=null" in md.lower() or "iv=null" in md.lower()
        # N=5 in footer for nulls
        assert "N=5" in md


class TestTableDDteBuckets:
    def test_dte_buckets_one_per_bucket(self, tmp_path, monkeypatch):
        dte_values = [0, 3, 10, 25, 45]
        rows_futures = []
        rows_options = []
        for i, dte in enumerate(dte_values):
            sid = f"2026-04-30_RELIANCE_093{i}"
            rows_futures.append(_base_futures_row(sid))
            rows_options.append(_base_options_row(sid, dte=dte, is_expiry=(dte == 0)))

        fp, op = _write_ledgers(tmp_path, rows_futures, rows_options)
        monkeypatch.setattr(report_mod, "FUTURES_LEDGER_PATH", fp)
        monkeypatch.setattr(report_mod, "OPTIONS_LEDGER_PATH", op)
        out_path = tmp_path / "report.md"
        monkeypatch.setattr(report_mod, "REPORT_PATH", out_path)

        md = build_report()

        assert "0d" in md
        assert "1-5d" in md
        assert "6-15d" in md
        assert "16-30d" in md
        assert "31+d" in md


class TestTableESkipRate:
    def test_skip_rate_per_ticker_order(self, tmp_path, monkeypatch):
        rows_options = []
        # 5 RELIANCE rows: 4 CLOSED + 1 SKIPPED_LIQUIDITY -> 20% skip
        for i in range(4):
            rows_options.append(_base_options_row(f"2026-04-30_RELIANCE_093{i}", status="CLOSED"))
        rows_options.append(_base_options_row("2026-04-30_RELIANCE_0940", status="SKIPPED_LIQUIDITY"))
        # 10 BHEL rows: 8 SKIPPED_LIQUIDITY + 2 CLOSED -> 80% skip
        for i in range(2):
            rows_options.append(_base_options_row(f"2026-04-30_BHEL_094{i}", status="CLOSED", symbol="BHEL"))
        for i in range(2, 10):
            rows_options.append(_base_options_row(f"2026-04-30_BHEL_094{i}", status="SKIPPED_LIQUIDITY", symbol="BHEL"))

        # Need matching futures rows for anything to render (but Table E uses full options ledger)
        futures = []
        fp, op = _write_ledgers(tmp_path, futures, rows_options)
        monkeypatch.setattr(report_mod, "FUTURES_LEDGER_PATH", fp)
        monkeypatch.setattr(report_mod, "OPTIONS_LEDGER_PATH", op)
        out_path = tmp_path / "report.md"
        monkeypatch.setattr(report_mod, "REPORT_PATH", out_path)

        md = build_report()

        # BHEL should appear before RELIANCE (80% > 20%)
        bhel_pos = md.find("BHEL")
        reliance_pos = md.find("RELIANCE")
        assert bhel_pos < reliance_pos, "BHEL (80% skip) should appear before RELIANCE (20%)"

    def test_top_10_only_when_many_tickers(self, tmp_path, monkeypatch):
        rows_options = []
        # 15 different tickers, each with 1 SKIPPED row
        tickers = [f"TICK{i:02d}" for i in range(15)]
        for i, tk in enumerate(tickers):
            rows_options.append(_base_options_row(
                f"2026-04-30_{tk}_0930", status="SKIPPED_LIQUIDITY", symbol=tk
            ))

        fp, op = _write_ledgers(tmp_path, [], rows_options)
        monkeypatch.setattr(report_mod, "FUTURES_LEDGER_PATH", fp)
        monkeypatch.setattr(report_mod, "OPTIONS_LEDGER_PATH", op)
        out_path = tmp_path / "report.md"
        monkeypatch.setattr(report_mod, "REPORT_PATH", out_path)

        md = build_report()

        assert "OTHERS (5 tickers)" in md


class TestVerdictThresholds:
    def _make_pairs(self, n: int, tmp_path, monkeypatch) -> str:
        rows_futures = [_base_futures_row(f"2026-04-30_RELIANCE_{i:04d}") for i in range(n)]
        rows_options = [_base_options_row(f"2026-04-30_RELIANCE_{i:04d}") for i in range(n)]
        fp, op = _write_ledgers(tmp_path, rows_futures, rows_options)
        monkeypatch.setattr(report_mod, "FUTURES_LEDGER_PATH", fp)
        monkeypatch.setattr(report_mod, "OPTIONS_LEDGER_PATH", op)
        out_path = tmp_path / "report.md"
        monkeypatch.setattr(report_mod, "REPORT_PATH", out_path)
        return build_report(seed=17)

    def test_verdict_n_30(self, tmp_path, monkeypatch):
        md = self._make_pairs(30, tmp_path, monkeypatch)
        assert "DESCRIPTIVE" in md
        # No bootstrap-inference verdict line
        assert "PAIRED_DIFF_ZERO_REJECTED" not in md
        assert "PAIRED_DIFF_ZERO_NOT_REJECTED" not in md

    def test_verdict_n_100(self, tmp_path, monkeypatch):
        md = self._make_pairs(100, tmp_path, monkeypatch)
        # One of the two inference verdicts must be present
        assert ("PAIRED_DIFF_ZERO_REJECTED" in md or "PAIRED_DIFF_ZERO_NOT_REJECTED" in md)


class TestOutputFile:
    def test_writes_to_output_path(self, tmp_path, monkeypatch):
        fp, op = _write_ledgers(tmp_path, [], [])
        monkeypatch.setattr(report_mod, "FUTURES_LEDGER_PATH", fp)
        monkeypatch.setattr(report_mod, "OPTIONS_LEDGER_PATH", op)
        out_path = tmp_path / "report.md"
        monkeypatch.setattr(report_mod, "REPORT_PATH", out_path)

        md = build_report()

        assert out_path.exists()
        assert out_path.read_text(encoding="utf-8") == md

    def test_subsequent_call_overwrites(self, tmp_path, monkeypatch):
        fp, op = _write_ledgers(tmp_path, [], [])
        monkeypatch.setattr(report_mod, "FUTURES_LEDGER_PATH", fp)
        monkeypatch.setattr(report_mod, "OPTIONS_LEDGER_PATH", op)
        out_path = tmp_path / "report.md"
        monkeypatch.setattr(report_mod, "REPORT_PATH", out_path)

        build_report()
        first_content = out_path.read_text(encoding="utf-8")
        build_report()
        second_content = out_path.read_text(encoding="utf-8")

        assert first_content == second_content


class TestUnmatchedCounts:
    def test_header_counts_correct(self, tmp_path, monkeypatch):
        # 5 futures CLOSED, 4 options CLOSED matching 4, 1 extra options CLOSED unmatched
        f_ids = [f"2026-04-30_RELIANCE_093{i}" for i in range(5)]
        o_ids = f_ids[:4] + ["2026-04-30_BHEL_0940"]  # 4 match + 1 extra

        futures = [_base_futures_row(sid) for sid in f_ids]
        options = [_base_options_row(sid, symbol=sid.split("_")[1]) for sid in o_ids]

        fp, op = _write_ledgers(tmp_path, futures, options)
        monkeypatch.setattr(report_mod, "FUTURES_LEDGER_PATH", fp)
        monkeypatch.setattr(report_mod, "OPTIONS_LEDGER_PATH", op)
        out_path = tmp_path / "report.md"
        monkeypatch.setattr(report_mod, "REPORT_PATH", out_path)

        md = build_report()

        assert "futures CLOSED N=5" in md
        assert "options CLOSED N=5" in md
        assert "matched N=4" in md
        assert "unmatched-futures N=1" in md
        assert "unmatched-options N=1" in md
