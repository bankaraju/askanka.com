import json

from pipeline.earnings_calendar.peers import (
    build_peer_cohorts,
    freeze_peers,
    load_frozen_peers,
)


def _meta_fixture():
    # symbol -> (broad_sector, market_cap_cr)
    return {
        "RELIANCE":  ("ENERGY",     1827086.0),
        "ONGC":      ("ENERGY",      330000.0),
        "BPCL":      ("ENERGY",      120000.0),
        "IOC":       ("ENERGY",      180000.0),
        "HDFCBANK":  ("FINANCIALS", 1200000.0),
        "ICICIBANK": ("FINANCIALS", 1000000.0),
        "AXISBANK":  ("FINANCIALS",  450000.0),
        "TCS":       ("IT",         1500000.0),
        "INFY":      ("IT",         1100000.0),
        "WIPRO":     ("IT",          250000.0),
    }


def test_peers_share_sector():
    meta = _meta_fixture()
    cohorts = build_peer_cohorts(meta, n_size_bucket_neighbours=2)
    for sym, peers in cohorts.items():
        sector = meta[sym][0]
        for p in peers:
            assert meta[p][0] == sector, f"{p} not in same sector as {sym}"


def test_peers_exclude_self():
    cohorts = build_peer_cohorts(_meta_fixture())
    for sym, peers in cohorts.items():
        assert sym not in peers


def test_peers_size_bucket_proximity():
    # ICICIBANK (1.0M) is closest to HDFCBANK (1.2M); AXISBANK (450k) further
    cohorts = build_peer_cohorts(_meta_fixture(), n_size_bucket_neighbours=1)
    assert cohorts["HDFCBANK"] == ["ICICIBANK"]


def test_peers_truncate_to_available_universe():
    # WIPRO sector has only 2 other tickers
    cohorts = build_peer_cohorts(_meta_fixture(), n_size_bucket_neighbours=5)
    assert len(cohorts["WIPRO"]) == 2


def test_peers_default_n_is_three():
    cohorts = build_peer_cohorts(_meta_fixture())
    # ENERGY has 4 names, so RELIANCE should get 3 peers
    assert len(cohorts["RELIANCE"]) == 3


def test_peers_skip_unscoreable_meta():
    """Symbols with missing/null market_cap must be excluded from both sides
    (cannot be peer, cannot have peers) — silent fallback would corrupt the
    cohort. Per data validation policy §9.3 quarantine pattern."""
    meta = {
        "TCS":   ("IT", 1500000.0),
        "INFY":  ("IT", 1100000.0),
        "WIPRO": ("IT", None),
    }
    cohorts = build_peer_cohorts(meta)
    assert "WIPRO" not in cohorts
    for peers in cohorts.values():
        assert "WIPRO" not in peers


def test_peers_min_cohort_marks_unavailable():
    """If a symbol's sector has < min_peers other symbols, the symbol is
    omitted from the cohort map (caller can decide PARTIAL/exploratory or
    drop). Per spec — peers must be real, not padded."""
    meta = {
        "ALONE": ("DEFENCE", 100.0),
        "TCS":   ("IT",      1500000.0),
        "INFY":  ("IT",      1100000.0),
        "WIPRO": ("IT",      250000.0),
    }
    cohorts = build_peer_cohorts(meta, min_peers=2)
    assert "ALONE" not in cohorts


def test_load_frozen_peers_round_trip(tmp_path):
    cohorts = {"RELIANCE": ["ONGC", "BPCL"]}
    p = tmp_path / "peers_frozen.json"
    p.write_text(json.dumps({"frozen_at": "2026-04-25", "cohorts": cohorts}))
    out = load_frozen_peers(p)
    assert out["frozen_at"] == "2026-04-25"
    assert out["cohorts"] == cohorts


def test_freeze_peers_writes_file(tmp_path):
    p = tmp_path / "peers_frozen.json"
    out_path = freeze_peers(_meta_fixture(), p, asof="2026-04-25")
    assert out_path == p
    payload = json.loads(p.read_text())
    assert payload["frozen_at"] == "2026-04-25"
    assert "RELIANCE" in payload["cohorts"]


def test_freeze_peers_creates_parent_dir(tmp_path):
    p = tmp_path / "nested" / "deeper" / "peers_frozen.json"
    freeze_peers(_meta_fixture(), p, asof="2026-04-25")
    assert p.exists()
