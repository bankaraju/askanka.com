from __future__ import annotations

from datetime import date, timedelta

from pipeline.autoresearch.regime_autoresearch.forward_shadow import ready_for_promotion


def test_not_ready_too_few_days():
    assert ready_for_promotion(days_since_start=40, n_events=80, forward_sharpe=0.5,
                                 incumbent_sharpe=0.3) is False


def test_not_ready_too_few_events():
    assert ready_for_promotion(days_since_start=90, n_events=40, forward_sharpe=0.5,
                                 incumbent_sharpe=0.3) is False


def test_not_ready_below_incumbent():
    assert ready_for_promotion(days_since_start=90, n_events=60, forward_sharpe=0.2,
                                 incumbent_sharpe=0.3) is False


def test_ready_when_all_gates_met():
    assert ready_for_promotion(days_since_start=90, n_events=60, forward_sharpe=0.5,
                                 incumbent_sharpe=0.3) is True
