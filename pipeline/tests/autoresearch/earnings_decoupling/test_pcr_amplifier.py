import pandas as pd

from pipeline.autoresearch.earnings_decoupling.pcr_amplifier import apply_pcr_filter


def test_apply_pcr_filter_passthrough_when_disabled():
    ledger = pd.DataFrame([{"ticker": "RELIANCE", "trade_ret_pct": 0.5}])
    out, manifest = apply_pcr_filter(ledger, enabled=False)
    assert len(out) == len(ledger)
    assert manifest == {"pcr_track": "deferred", "n_passed": 1, "n_failed": 0}


def test_apply_pcr_filter_raises_when_enabled_without_data():
    ledger = pd.DataFrame([{"ticker": "RELIANCE", "trade_ret_pct": 0.5}])
    try:
        apply_pcr_filter(ledger, enabled=True)
    except NotImplementedError:
        return
    raise AssertionError("expected NotImplementedError when enabled=True before backfill")
