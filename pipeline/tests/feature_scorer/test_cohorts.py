import json
import pytest


@pytest.fixture
def sector_concentration(tmp_path, monkeypatch):
    data = {
        "NIFTYIT": {"constituents": [
            {"symbol": "TCS", "weight": 0.27}, {"symbol": "INFY", "weight": 0.25},
            {"symbol": "HCLTECH", "weight": 0.10}, {"symbol": "WIPRO", "weight": 0.06}
        ]},
        "BANKNIFTY": {"constituents": [
            {"symbol": "HDFCBANK", "weight": 0.28}, {"symbol": "ICICIBANK", "weight": 0.24},
            {"symbol": "SBIN", "weight": 0.10}
        ]},
    }
    f = tmp_path / "sector_concentration.json"
    f.write_text(json.dumps(data), encoding="utf-8")
    from pipeline.feature_scorer import cohorts
    monkeypatch.setattr(cohorts, "_SECTOR_CONCENTRATION_FILE", f, raising=False)
    return data


def test_ticker_to_cohort_hit(sector_concentration):
    from pipeline.feature_scorer.cohorts import ticker_to_cohort
    assert ticker_to_cohort("TCS") == "NIFTYIT"
    assert ticker_to_cohort("HDFCBANK") == "BANKNIFTY"


def test_ticker_to_cohort_miss_returns_midcap_fallback(sector_concentration):
    from pipeline.feature_scorer.cohorts import ticker_to_cohort
    assert ticker_to_cohort("KAYNES") == "MIDCAP_GENERIC"


def test_cohort_members_excludes_itself(sector_concentration):
    """When fitting a cohort model for TCS, don't include TCS in the cohort sample."""
    from pipeline.feature_scorer.cohorts import cohort_members
    members = cohort_members("NIFTYIT", exclude="TCS")
    assert "TCS" not in members
    assert {"INFY", "HCLTECH", "WIPRO"} <= set(members)


def test_cohort_members_returns_all_if_no_exclude(sector_concentration):
    from pipeline.feature_scorer.cohorts import cohort_members
    members = cohort_members("BANKNIFTY")
    assert set(members) == {"HDFCBANK", "ICICIBANK", "SBIN"}
