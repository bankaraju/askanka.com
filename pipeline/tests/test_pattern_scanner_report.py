import json
from pathlib import Path
from pipeline.pattern_scanner_report import build_report


def test_build_report_writes_markdown(tmp_path):
    ledger = tmp_path / "ledger.json"
    rows = [
        {"signal_id": "2026-04-28_RELIANCE_BULLISH_HAMMER",
         "date": "2026-04-28", "symbol": "RELIANCE", "side": "LONG",
         "pattern_id": "BULLISH_HAMMER", "is_expiry_day": False,
         "status": "CLOSED", "pnl_net_pct": 0.012,
         "futures_pnl_net_pct": 0.008,
         "scanner_z_score_at_entry": 3.0},
        {"signal_id": "2026-04-28_TATAMOTORS_BEARISH_ENGULFING",
         "date": "2026-04-28", "symbol": "TATAMOTORS", "side": "SHORT",
         "pattern_id": "BEARISH_ENGULFING", "is_expiry_day": False,
         "status": "CLOSED", "pnl_net_pct": -0.005,
         "futures_pnl_net_pct": -0.002,
         "scanner_z_score_at_entry": 2.1},
    ]
    ledger.write_text(json.dumps(rows))
    out = tmp_path / "report.md"
    build_report(ledger_path=ledger, out_path=out)
    text = out.read_text()
    assert "Headline paired diff" in text
    assert "Win rate by pattern_id" in text
    assert "BULLISH_HAMMER" in text
    assert "BEARISH_ENGULFING" in text
