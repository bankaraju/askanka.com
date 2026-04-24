"""Mode-1 pilot CLI exercises proposer -> in_sample -> log with human gating.

The CLI runs ONE iteration per invocation; the human re-invokes to drive
the pilot proposal-by-proposal. These tests stub the proposer, in_sample
runner, and input() so no real Haiku call, no real panel load, and no
real sleep happen during the test suite.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from pipeline.autoresearch.regime_autoresearch import proposer as proposer_mod
from pipeline.autoresearch.regime_autoresearch import in_sample_runner as isr_mod
from pipeline.autoresearch.regime_autoresearch.dsl import Proposal
from pipeline.autoresearch.regime_autoresearch.scripts import run_pilot


def _fixed_proposal() -> Proposal:
    return Proposal(
        construction_type="single_long",
        feature="ret_5d",
        threshold_op=">",
        threshold_value=0.5,
        hold_horizon=5,
        regime="NEUTRAL",
        pair_id=None,
    )


def _stub_panel() -> pd.DataFrame:
    # Minimal shape: regime_zone column only matters for the stub runner.
    return pd.DataFrame([
        {"date": pd.Timestamp("2022-01-03"), "ticker": "X",
         "close": 100.0, "volume": 1_000_000, "regime_zone": "NEUTRAL"},
    ])


@pytest.fixture
def patched_env(monkeypatch, tmp_path):
    """Stub proposer.generate_proposal, in_sample_runner.run_in_sample,
    input, and point the CLI at a tmp log + tmp panel builder.
    """
    log_path = tmp_path / "proposal_log.jsonl"

    calls = {"proposer": 0, "in_sample": 0, "inputs": []}

    def fake_generate(view, regime, llm_call):
        calls["proposer"] += 1
        return _fixed_proposal()

    def fake_run_in_sample(p, panel, log_path, incumbent_sharpe):
        calls["in_sample"] += 1
        return {
            "net_sharpe_in_sample": 0.42,
            "n_events_in_sample": 48,
            "gap_vs_incumbent": 0.42 - incumbent_sharpe,
            "incumbent_sharpe": incumbent_sharpe,
        }

    monkeypatch.setattr(proposer_mod, "generate_proposal", fake_generate)
    monkeypatch.setattr(isr_mod, "run_in_sample", fake_run_in_sample)
    # Also patch the same symbols as bound inside run_pilot, in case of from-imports.
    monkeypatch.setattr(run_pilot, "generate_proposal", fake_generate, raising=False)
    monkeypatch.setattr(run_pilot, "run_in_sample", fake_run_in_sample, raising=False)

    # Stub panel builder so tests never touch the real data dirs.
    monkeypatch.setattr(run_pilot, "_build_neutral_panel",
                         lambda regime: _stub_panel(), raising=False)
    # Stub hurdle so the CLI has a deterministic incumbent.
    monkeypatch.setattr(run_pilot, "_compute_hurdle",
                         lambda regime: (0.10, "scarcity_fallback:buy_and_hold"),
                         raising=False)
    # Stub the Haiku llm_call factory — MUST NOT be invoked during tests.
    def _blow_up(*a, **kw):
        raise AssertionError("real llm_call must not be invoked in tests")
    monkeypatch.setattr(run_pilot, "_build_llm_call", lambda: _blow_up, raising=False)

    return {"log_path": log_path, "calls": calls, "monkeypatch": monkeypatch}


def _inputs(monkeypatch, answers: list[str]):
    q = list(answers)

    def fake_input(prompt=""):
        return q.pop(0)
    monkeypatch.setattr("builtins.input", fake_input)


def test_pilot_reject_path(patched_env, monkeypatch):
    """n -> REJECTED row appended, no in-sample run."""
    _inputs(monkeypatch, ["n"])
    rc = run_pilot.run_one_iteration(regime="NEUTRAL",
                                     log_path=patched_env["log_path"])
    assert rc == 0
    assert patched_env["calls"]["proposer"] == 1
    assert patched_env["calls"]["in_sample"] == 0
    lines = patched_env["log_path"].read_text().strip().splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["approval_status"] == "REJECTED"
    assert row["regime"] == "NEUTRAL"
    # No in-sample fields since we short-circuited.
    assert "net_sharpe_mean" not in row or row.get("net_sharpe_mean") is None


def test_pilot_skip_path(patched_env, monkeypatch):
    """s -> nothing logged, no in-sample run."""
    _inputs(monkeypatch, ["s"])
    rc = run_pilot.run_one_iteration(regime="NEUTRAL",
                                     log_path=patched_env["log_path"])
    assert rc == 0
    assert patched_env["calls"]["proposer"] == 1
    assert patched_env["calls"]["in_sample"] == 0
    assert not patched_env["log_path"].exists() or \
        patched_env["log_path"].read_text().strip() == ""


def test_pilot_approve_path(patched_env, monkeypatch):
    """y -> in-sample runs, APPROVED row with net_sharpe_mean, hurdle, passes_delta_in."""
    _inputs(monkeypatch, ["y"])
    rc = run_pilot.run_one_iteration(regime="NEUTRAL",
                                     log_path=patched_env["log_path"])
    assert rc == 0
    assert patched_env["calls"]["in_sample"] == 1
    lines = patched_env["log_path"].read_text().strip().splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["approval_status"] == "APPROVED"
    assert row["regime"] == "NEUTRAL"
    assert row["net_sharpe_mean"] == pytest.approx(0.42)
    assert row["n_events"] == 48
    assert row["hurdle_sharpe"] == pytest.approx(0.10)
    assert row["hurdle_source"] == "scarcity_fallback:buy_and_hold"
    # passes_delta_in: 0.42 - 0.10 = 0.32 >= DELTA_IN_SAMPLE (0.15) -> True
    assert row["passes_delta_in"] is True
    # DSL fields present
    assert row["feature"] == "ret_5d"
    assert row["construction_type"] == "single_long"
    assert row["threshold_op"] == ">"
    assert row["threshold_value"] == 0.5
    assert row["hold_horizon"] == 5


def test_pilot_counter_reads_existing_log(patched_env, monkeypatch, capsys):
    """Counter reads how many APPROVED NEUTRAL rows exist and prints N+1-of-target."""
    log = patched_env["log_path"]
    log.parent.mkdir(parents=True, exist_ok=True)
    # Pre-populate 3 APPROVED NEUTRAL entries + 1 REJECTED + 1 APPROVED EUPHORIA
    # (the counter should only count APPROVED NEUTRAL).
    rows = [
        {"proposal_id": "P-001", "regime": "NEUTRAL", "approval_status": "APPROVED"},
        {"proposal_id": "P-002", "regime": "NEUTRAL", "approval_status": "APPROVED"},
        {"proposal_id": "P-003", "regime": "NEUTRAL", "approval_status": "APPROVED"},
        {"proposal_id": "P-004", "regime": "NEUTRAL", "approval_status": "REJECTED"},
        {"proposal_id": "P-005", "regime": "EUPHORIA", "approval_status": "APPROVED"},
    ]
    log.write_text("\n".join(json.dumps(r) for r in rows) + "\n")

    _inputs(monkeypatch, ["s"])  # skip so we don't alter the log
    run_pilot.run_one_iteration(regime="NEUTRAL", log_path=log)
    out = capsys.readouterr().out
    # Counter: 4th proposal out of ~20 target
    assert "4" in out and "20" in out, \
        f"expected counter '4 of ~20' in stdout, got: {out!r}"


def test_pilot_view_isolation_preserved(patched_env, monkeypatch):
    """The proposer context built by the CLI must NOT call read_holdout_tail."""
    captured_view: dict = {}

    def capture_generate(view, regime, llm_call):
        captured_view["view"] = view
        return _fixed_proposal()

    monkeypatch.setattr(run_pilot, "generate_proposal", capture_generate, raising=False)
    _inputs(monkeypatch, ["s"])
    run_pilot.run_one_iteration(regime="NEUTRAL",
                                log_path=patched_env["log_path"])
    view = captured_view["view"]
    # The CLI MUST build a ProposerView whose read_holdout_tail raises.
    from pipeline.autoresearch.regime_autoresearch.proposer import ProposerView
    assert isinstance(view, ProposerView)
    with pytest.raises(PermissionError, match="holdout"):
        view.read_holdout_tail(5)
