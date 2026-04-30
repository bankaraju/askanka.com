"""Tests for pipeline.autoresearch.auto_spread_discovery.proposer."""
from __future__ import annotations

from datetime import date

import pytest

from pipeline.research.auto_spread_discovery.proposer import (
    Candidate, enumerate_candidates, REGIMES, HOLDS, PER_SIDE_TOP_K,
)


def _mock_ticker_map() -> dict[str, str]:
    """Two sectors with enough legs, two sectors below threshold."""
    return {
        # Banks: 5 tickers (above threshold)
        "HDFCBANK": "Banks", "ICICIBANK": "Banks", "KOTAKBANK": "Banks",
        "AXISBANK": "Banks", "SBIN": "Banks",
        # IT_Services: 4 tickers (above threshold)
        "TCS": "IT_Services", "INFY": "IT_Services",
        "WIPRO": "IT_Services", "HCLTECH": "IT_Services",
        # Defence: 2 tickers (BELOW threshold of 3)
        "HAL": "Defence", "BEL": "Defence",
        # FMCG: 1 ticker (BELOW threshold)
        "ITC": "FMCG",
    }


def test_family_size_lock():
    # Lock at design time: 4 sectors * 3 (= 4*3 ordered pairs) * 5 regimes * 3 holds
    out = enumerate_candidates(
        sectors=["Banks", "IT_Services", "Defence", "FMCG"],
        ticker_map=_mock_ticker_map(),
    )
    expected = 4 * 3 * len(REGIMES) * len(HOLDS)
    assert len(out) == expected


def test_excludes_self_pair():
    out = enumerate_candidates(
        sectors=["Banks", "IT_Services"],
        ticker_map=_mock_ticker_map(),
    )
    for c in out:
        assert c.sector_a != c.sector_b


def test_directional_pairs_both_directions_present():
    out = enumerate_candidates(
        sectors=["Banks", "IT_Services"],
        ticker_map=_mock_ticker_map(),
    )
    pairs = {(c.sector_a, c.sector_b) for c in out}
    assert ("Banks", "IT_Services") in pairs
    assert ("IT_Services", "Banks") in pairs  # opposite direction is a separate hypothesis


def test_dropped_liquidity_when_legs_below_top_k():
    out = enumerate_candidates(
        sectors=["Banks", "Defence"],
        ticker_map=_mock_ticker_map(),
    )
    # Defence has only 2 tickers; any pair touching Defence is DROPPED
    defence_cells = [c for c in out if c.sector_a == "Defence" or c.sector_b == "Defence"]
    assert len(defence_cells) > 0
    for c in defence_cells:
        assert c.status == "DROPPED_LIQUIDITY"
    # Banks-Banks doesn't exist (self-pair); Banks alone has none
    # Banks-vs-FMCG would also drop because FMCG has 1 ticker. We only test Banks/Defence here.


def test_legs_a_legs_b_top_k_ordering():
    out = enumerate_candidates(
        sectors=["Banks", "IT_Services"],
        ticker_map=_mock_ticker_map(),
    )
    bk_to_it = next(c for c in out if c.sector_a == "Banks"
                    and c.sector_b == "IT_Services" and c.regime == "NEUTRAL"
                    and c.hold == 1)
    # Alphabetical fallback (v0): top-3 of Banks alphabetically
    assert bk_to_it.legs_a == ("AXISBANK", "HDFCBANK", "ICICIBANK")
    assert bk_to_it.legs_b == ("HCLTECH", "INFY", "TCS")
    assert bk_to_it.n_legs_a == PER_SIDE_TOP_K
    assert bk_to_it.n_legs_b == PER_SIDE_TOP_K


def test_pair_id_uniqueness():
    out = enumerate_candidates(
        sectors=["Banks", "IT_Services", "Defence"],
        ticker_map=_mock_ticker_map(),
    )
    ids = [c.pair_id for c in out]
    assert len(ids) == len(set(ids))


def test_all_regimes_and_holds_present_per_pair():
    out = enumerate_candidates(
        sectors=["Banks", "IT_Services"],
        ticker_map=_mock_ticker_map(),
    )
    bk_to_it = [c for c in out if c.sector_a == "Banks"
                and c.sector_b == "IT_Services"]
    assert len(bk_to_it) == len(REGIMES) * len(HOLDS)
    by_regime = {c.regime for c in bk_to_it}
    assert by_regime == set(REGIMES)
    by_hold = {c.hold for c in bk_to_it}
    assert by_hold == set(HOLDS)


def test_candidate_immutable():
    c = Candidate(
        pair_id="X__VS__Y__NEUTRAL__1d",
        sector_a="X", sector_b="Y",
        regime="NEUTRAL", hold=1,
        status="ENUMERATED",
        n_legs_a=3, n_legs_b=3,
        legs_a=("a", "b", "c"), legs_b=("d", "e", "f"),
        frozen_at="2026-04-30T00:00:00Z",
    )
    with pytest.raises((AttributeError, TypeError)):
        c.status = "DROPPED_LIQUIDITY"


def test_empty_ticker_map_yields_all_dropped():
    out = enumerate_candidates(
        sectors=["Banks", "IT_Services"],
        ticker_map={},
    )
    assert all(c.status == "DROPPED_LIQUIDITY" for c in out)


def test_excludes_unmapped_sector_via_default_loader_skips_when_excluded():
    # When 'Unmapped' is in the sector list, the default loader filters it.
    # Here we just verify our function honours an explicit sectors list that
    # already has Unmapped removed.
    out = enumerate_candidates(
        sectors=["Banks", "IT_Services"],
        ticker_map=_mock_ticker_map(),
    )
    assert all(c.sector_a in {"Banks", "IT_Services"} for c in out)
    assert all(c.sector_b in {"Banks", "IT_Services"} for c in out)
