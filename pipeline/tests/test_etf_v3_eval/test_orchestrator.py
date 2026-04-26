# pipeline/tests/test_etf_v3_eval/test_orchestrator.py
import pytest
from pipeline.autoresearch.etf_v3_eval.phase_2.orchestrator import (
    Phase2Inputs,
    iter_run_configs,
)


def test_iter_run_configs_emits_lookback_x_universe_grid():
    inputs = Phase2Inputs(
        replay_parquets={
            "126": "pipeline/autoresearch/data/intraday_break_replay_60d_v0.1_ungated.parquet",
            "273": "pipeline/autoresearch/data/intraday_break_replay_60d_v0.2_minute_bars.parquet",
        },
        lookbacks=(756, 1200, 1236),
        feature_set="curated",
        seed=0,
    )
    configs = list(iter_run_configs(inputs))
    # 3 lookbacks × 2 universes = 6 base runs
    assert len(configs) == 6
    assert {(c.lookback_days, c.universe) for c in configs} == {
        (756, "126"), (1200, "126"), (1236, "126"),
        (756, "273"), (1200, "273"), (1236, "273"),
    }


# ── Polish guard tests ────────────────────────────────────────────────────────


def test_phase2_inputs_rejects_empty_lookbacks():
    with pytest.raises(ValueError, match="lookbacks"):
        Phase2Inputs(replay_parquets={"126": "p"}, lookbacks=())


def test_phase2_inputs_rejects_negative_seed():
    with pytest.raises(ValueError, match="seed"):
        Phase2Inputs(replay_parquets={"126": "p"}, seed=-1)


def test_phase2_inputs_rejects_zero_n_iterations():
    with pytest.raises(ValueError, match="n_iterations"):
        Phase2Inputs(replay_parquets={"126": "p"}, n_iterations=0)
