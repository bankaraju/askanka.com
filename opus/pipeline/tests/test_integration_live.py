"""
Live integration test — runs against real APIs for 3 stocks.
Marked as slow; only run explicitly: pytest -m live
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.live


@pytest.mark.live
def test_screener_transcript_urls_for_hal():
    """Screener returns transcript URLs for HAL (large-cap defence)."""
    from opus.pipeline.retrieval.screener_client import ScreenerClient
    sc = ScreenerClient()
    urls = sc.get_transcript_urls("HAL")
    assert len(urls) >= 1, f"Expected at least 1 transcript URL for HAL, got {len(urls)}"
    assert all(u.get("type") == "transcript" for u in urls)


@pytest.mark.live
def test_bse_resolver_finds_reliance():
    """BSE Suggest API resolves RELIANCE — may return None if BSE blocks automated requests."""
    from opus.pipeline.retrieval.bse_resolver import resolve_bse_scrip
    result = resolve_bse_scrip("RELIANCE")
    if result is not None:
        assert result["bse_scrip"] == "500325"
    else:
        pytest.skip("BSE API blocked automated requests from this IP")


@pytest.mark.live
def test_screener_financials_for_tcs():
    """TCS: Screener financials + document links available."""
    from opus.pipeline.retrieval.screener_client import ScreenerClient
    sc = ScreenerClient()
    data = sc.get_financials("TCS")
    assert len(data.get("quarterly", [])) >= 1, "No quarterly data for TCS"
    assert len(data.get("documents", [])) >= 1, "No documents for TCS"
