"""Tests for macro_stress.compute_msi.

Covers the cached_fii kwarg added for the intraday MSI refresh (plan
2026-04-22-msi-intraday). NSE publishes FII/DII flows EOD only, so the
intraday refresh must reuse the value cached by the morning scan rather
than refetching.
"""

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from macro_stress import compute_msi


def test_compute_msi_uses_cached_fii_when_provided():
    """When cached_fii is provided, _fetch_institutional_flow must NOT be called
    and the cached values flow through to the inst_flow component."""
    cached = {"fii_net": -2000.0, "dii_net": 1500.0, "combined_flow": -500.0}
    with patch("macro_stress._fetch_institutional_flow") as mock_fetch, \
         patch("macro_stress._fetch_india_vix", return_value=14.5), \
         patch("macro_stress._fetch_india_vix_90d_avg", return_value=13.0), \
         patch("macro_stress._fetch_usdinr_change_5d", return_value=0.3), \
         patch("macro_stress._fetch_nifty_30d_return", return_value=-1.5), \
         patch("macro_stress._fetch_crude_change_5d", return_value=1.0):
        result = compute_msi(cached_fii=cached)

    mock_fetch.assert_not_called()
    assert result["fii_net"] == -2000.0
    assert result["dii_net"] == 1500.0
    assert result["combined_flow"] == -500.0


def test_compute_msi_without_cached_fii_calls_fetch():
    """Baseline: without cached_fii, the existing HTTP fetch path runs."""
    fake_inst = {"fii_net": -100.0, "dii_net": 50.0, "combined_flow": -50.0}
    with patch("macro_stress._fetch_institutional_flow", return_value=fake_inst) as mock_fetch, \
         patch("macro_stress._fetch_india_vix", return_value=14.5), \
         patch("macro_stress._fetch_india_vix_90d_avg", return_value=13.0), \
         patch("macro_stress._fetch_usdinr_change_5d", return_value=0.3), \
         patch("macro_stress._fetch_nifty_30d_return", return_value=-1.5), \
         patch("macro_stress._fetch_crude_change_5d", return_value=1.0):
        result = compute_msi()

    mock_fetch.assert_called_once()
    assert result["fii_net"] == -100.0
