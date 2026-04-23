import pytest

from pipeline.autoresearch.overshoot_compliance import defense_filter as DF


def test_defense_short_flagged():
    row = {"ticker": "BEL", "direction": "UP"}
    assert DF.is_defense_short(row, sector_of={"BEL": "Defence"}) is True


def test_defense_long_not_flagged():
    row = {"ticker": "BEL", "direction": "DOWN"}
    assert DF.is_defense_short(row, sector_of={"BEL": "Defence"}) is False


def test_non_defense_not_flagged():
    row = {"ticker": "RELIANCE", "direction": "UP"}
    assert DF.is_defense_short(row, sector_of={"RELIANCE": "Energy"}) is False


def test_hardcoded_override_catches_misclassified_tickers():
    row = {"ticker": "HAL", "direction": "UP"}
    assert DF.is_defense_short(row, sector_of={"HAL": "Other:Aerospace"}) is True


def test_partition_splits_survivors():
    survivors = [
        {"ticker": "BEL", "direction": "UP"},
        {"ticker": "BEL", "direction": "DOWN"},
        {"ticker": "RELIANCE", "direction": "UP"},
    ]
    kept, flagged = DF.partition(survivors, sector_of={"BEL": "Defence", "RELIANCE": "Energy"})
    assert len(kept) == 2
    assert len(flagged) == 1
    assert flagged[0]["ticker"] == "BEL" and flagged[0]["direction"] == "UP"
