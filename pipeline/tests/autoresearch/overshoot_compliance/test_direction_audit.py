import pandas as pd
import pytest

from pipeline.autoresearch.overshoot_compliance import direction_audit as DA


def _survivor(ticker, direction, edge_net=0.5):
    return {"ticker": ticker, "direction": direction, "edge_net_pct": edge_net, "p_value": 1e-5}


def test_engine_long_matches_fade_down():
    survivors = [_survivor("A", "DOWN")]
    engine_calls = {"A": {"direction": "LONG"}}
    report = DA.audit(survivors, engine_calls)
    assert report["conflicts"] == 0
    assert report["rows"][0]["conflict"] is False


def test_engine_long_conflicts_with_fade_up():
    survivors = [_survivor("A", "UP")]
    engine_calls = {"A": {"direction": "LONG"}}
    report = DA.audit(survivors, engine_calls)
    assert report["conflicts"] == 1
    assert report["rows"][0]["conflict"] is True


def test_engine_call_missing_reports_unknown():
    survivors = [_survivor("A", "UP")]
    engine_calls = {}
    report = DA.audit(survivors, engine_calls)
    assert report["rows"][0]["engine_direction"] is None
    assert report["rows"][0]["conflict"] is None
