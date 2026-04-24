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
from pipeline.autoresearch.regime_autoresearch.dsl import (
    ABSOLUTE_THRESHOLD_GRID, CONSTRUCTION_TYPES, FEATURES, HOLD_HORIZONS,
    K_GRID, Proposal, THRESHOLD_OPS,
)
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

    def fake_run_in_sample(p, panel, log_path, incumbent_sharpe,
                            event_dates=None, tickers=None):
        calls["in_sample"] += 1
        calls["event_dates"] = event_dates
        calls["tickers"] = tickers
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

    # Stub panel + event_dates helpers so tests never touch the real data
    # dirs. The unfiltered panel and regime-filtered event_dates are now
    # two separate helpers (see run_pilot._build_panel /
    # _get_event_dates); stub both.
    monkeypatch.setattr(run_pilot, "_build_panel",
                         lambda: _stub_panel(), raising=False)
    monkeypatch.setattr(
        run_pilot, "_get_event_dates",
        lambda panel, regime: pd.DatetimeIndex(
            sorted(panel.loc[panel["regime_zone"] == regime, "date"].unique())
        ),
        raising=False,
    )
    # Stub hurdle so the CLI has a deterministic incumbent.
    # Accept any extra kwargs (panel, event_dates, hold_horizon) introduced
    # by the Task 8 step 2 switch to the real regime-conditional buy-and-hold
    # and the subsequent decoupling of panel from event_dates.
    monkeypatch.setattr(run_pilot, "_compute_hurdle",
                         lambda regime, **kw: (0.10, "scarcity_fallback:buy_and_hold"),
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


def test_strip_fences_to_json_handles_common_haiku_wrappers():
    """The fence-stripper must isolate ``{...}`` from four common Haiku shapes:
    clean JSON, ```json-fenced, plain ```-fenced, and leading prose.
    """
    body = '{"feature": "ret_5d", "hold_horizon": 5}'

    # 1. Clean JSON — must round-trip verbatim (modulo whitespace).
    assert run_pilot._strip_fences_to_json(body) == body

    # 2. ```json ... ``` fenced
    fenced_json = f"```json\n{body}\n```"
    assert run_pilot._strip_fences_to_json(fenced_json) == body

    # 3. ``` ... ``` fenced (no language tag)
    fenced_plain = f"```\n{body}\n```"
    assert run_pilot._strip_fences_to_json(fenced_plain) == body

    # 4. Leading prose then JSON
    prosed = f"Here is the proposal:\n{body}\nThis is based on recent data."
    assert run_pilot._strip_fences_to_json(prosed) == body

    # Also assert the loud-failure branch for a response with no JSON at all.
    with pytest.raises(ValueError, match="no JSON object"):
        run_pilot._strip_fences_to_json("sorry, I cannot comply.")


def test_system_prompt_inlines_all_dsl_enums():
    """The Haiku system prompt must enumerate every DSL enum literally.

    Prior versions described the grammar abstractly ("must be a grid member"),
    which let Haiku confabulate values (construction_type="absolute",
    feature="rsi_14"). Guarding against future regressions where someone
    shortens the prompt and loses an enum.
    """
    regime = "NEUTRAL"
    prompt = run_pilot._build_system_prompt(regime)

    # Every FEATURE must appear verbatim.
    for feat in FEATURES:
        assert feat in prompt, f"feature {feat!r} missing from system prompt"

    # Every CONSTRUCTION_TYPE must appear verbatim.
    for ctype in CONSTRUCTION_TYPES:
        assert ctype in prompt, f"construction_type {ctype!r} missing from system prompt"

    # Every THRESHOLD_OP must appear verbatim.
    for op in THRESHOLD_OPS:
        assert op in prompt, f"threshold_op {op!r} missing from system prompt"

    # Every HOLD_HORIZON value must appear verbatim.
    for h in HOLD_HORIZONS:
        assert str(h) in prompt, f"hold_horizon {h!r} missing from system prompt"

    # Every ABSOLUTE_THRESHOLD_GRID value must appear verbatim.
    for v in ABSOLUTE_THRESHOLD_GRID:
        assert str(v) in prompt, (
            f"ABSOLUTE_THRESHOLD_GRID value {v!r} missing from system prompt"
        )

    # Every K_GRID value must appear verbatim.
    for k in K_GRID:
        assert str(k) in prompt, f"K_GRID value {k!r} missing from system prompt"

    # Regime must be interpolated so the LLM can't drift to another label.
    assert regime in prompt, "regime not interpolated into system prompt"


def _write_pilot_data_stubs(tmp_path, regime_rows, bar_rows):
    """Write minimal regime_history + NIFTY + VIX + daily_bars stubs under
    tmp_path, returning paths so callers can monkeypatch the run_pilot
    module-level constants. `regime_rows` is a list of
    (iso_date, zone, score) tuples; `bar_rows` is a list of
    (iso_date, close, volume) tuples for the single stub ticker XYZ.
    """
    regime_csv = tmp_path / "regime_history.csv"
    regime_csv.write_text(
        "date,regime_zone,signal_score\n"
        + "\n".join(f"{d},{z},{s}" for d, z, s in regime_rows)
        + "\n"
    )

    nifty_csv = tmp_path / "NIFTY_daily.csv"
    nifty_csv.write_text(
        "date,open,high,low,close,volume\n"
        + "\n".join(
            f"{d},{c - 50},{c + 50},{c - 100},{c},{v}"
            for d, c, v in bar_rows
        )
        + "\n"
    )

    vix_csv = tmp_path / "vix_history.csv"
    vix_csv.write_text(
        "date,vix_close\n"
        + "\n".join(f"{d},{15.0 + i}" for i, (d, *_rest) in enumerate(bar_rows))
        + "\n"
    )

    bars_dir = tmp_path / "daily_bars"
    bars_dir.mkdir()
    real = pd.DataFrame({
        "date": pd.to_datetime([d for d, *_ in bar_rows]),
        "open": [c - 2 for _d, c, _v in bar_rows],
        "high": [c + 3 for _d, c, _v in bar_rows],
        "low": [c - 3 for _d, c, _v in bar_rows],
        "close": [c for _d, c, _v in bar_rows],
        "volume": [v for _d, _c, v in bar_rows],
    })
    real.to_parquet(bars_dir / "XYZ.parquet", index=False)
    return {
        "regime_csv": regime_csv, "nifty_csv": nifty_csv,
        "vix_csv": vix_csv, "bars_dir": bars_dir,
    }


def test_pilot_panel_has_pseudo_tickers(monkeypatch, tmp_path):
    """_build_panel must union NIFTY/VIX/REGIME pseudo-ticker series into
    the per-ticker panel. Without these, 5 of 20 DSL features
    (beta_nifty_60d, beta_vix_60d, macro_composite_60d_corr, and any
    features composing them) return NaN for every ticker and the compiler
    reports n_events=0. This test pins the union behaviour in place.
    """
    neutral_dates = ["2022-06-01", "2022-06-02", "2022-06-03"]
    regime_rows = [
        (d, "NEUTRAL", s) for d, s in zip(neutral_dates, [1.0, 2.0, 3.0])
    ]
    bar_rows = [
        ("2022-06-01", 17050, 1000),
        ("2022-06-02", 17150, 1100),
        ("2022-06-03", 17200, 1200),
    ]
    stubs = _write_pilot_data_stubs(tmp_path, regime_rows, bar_rows)

    # Point module-level constants at the stubs. The NIFTY parquet path is
    # deliberately inside bars_dir but absent so _load_nifty_bars() falls
    # through to the NIFTY_CSV branch.
    monkeypatch.setattr(run_pilot, "REGIME_CSV", stubs["regime_csv"])
    monkeypatch.setattr(run_pilot, "NIFTY_PARQUET",
                         stubs["bars_dir"] / "NIFTY.parquet")
    monkeypatch.setattr(run_pilot, "NIFTY_CSV", stubs["nifty_csv"])
    monkeypatch.setattr(run_pilot, "VIX_CSV", stubs["vix_csv"])
    monkeypatch.setattr(run_pilot, "DAILY_BARS_DIR", stubs["bars_dir"])

    panel = run_pilot._build_panel()

    tickers = set(panel["ticker"].unique())
    assert "NIFTY" in tickers, "NIFTY pseudo-ticker missing from panel"
    assert "VIX" in tickers, "VIX pseudo-ticker missing from panel"
    assert "REGIME" in tickers, "REGIME pseudo-ticker missing from panel"
    assert "XYZ" in tickers, "real ticker XYZ missing from panel"

    assert len(panel[panel["ticker"] == "NIFTY"]) == 3
    assert len(panel[panel["ticker"] == "VIX"]) == 3
    assert len(panel[panel["ticker"] == "REGIME"]) == 3
    # REGIME close must be signal_score, not signal_score column name left over.
    regime_bars = panel[panel["ticker"] == "REGIME"].sort_values("date")
    assert list(regime_bars["close"]) == [1.0, 2.0, 3.0]


def test_panel_unfiltered_event_dates_regime_filtered(monkeypatch, tmp_path):
    """_build_panel must return rows from ALL regime zones within
    [PANEL_START, TRAIN_VAL_END], while _get_event_dates(panel, regime)
    must return EXACTLY the regime-tagged dates in [TRAIN_VAL_START,
    TRAIN_VAL_END], sorted ascending.

    Pins the panel/event_dates decoupling that the Mode-1 pilot depends on:
    a regime-filtered panel caps every ticker's trailing window at ~165
    rows (the NEUTRAL event count) which starves 252d features. Keeping
    the panel unfiltered and the event set regime-filtered lets those
    features compute correctly.
    """
    # Mixed regime_zones across six dates inside train+val plus one date
    # BEFORE TRAIN_VAL_START to verify the panel retains pre-train rows
    # (they feed trailing-window features) but event_dates does NOT leak
    # them in.
    regime_rows = [
        ("2019-03-01", "NEUTRAL", 0.5),   # pre-train — panel-yes, events-no
        ("2022-05-02", "NEUTRAL", 1.0),   # event: NEUTRAL
        ("2022-05-03", "RISK-ON", 2.0),   # event: not NEUTRAL
        ("2022-05-04", "NEUTRAL", 3.0),   # event: NEUTRAL
        ("2022-05-05", "CAUTION", 4.0),   # event: not NEUTRAL
        ("2022-05-06", "NEUTRAL", 5.0),   # event: NEUTRAL
        ("2025-01-02", "NEUTRAL", 6.0),   # post-train — panel-no, events-no
    ]
    bar_rows = [
        ("2019-03-01", 10000, 500),
        ("2022-05-02", 17000, 1000),
        ("2022-05-03", 17100, 1100),
        ("2022-05-04", 17200, 1200),
        ("2022-05-05", 17300, 1300),
        ("2022-05-06", 17400, 1400),
        ("2025-01-02", 21000, 2000),
    ]
    stubs = _write_pilot_data_stubs(tmp_path, regime_rows, bar_rows)

    monkeypatch.setattr(run_pilot, "REGIME_CSV", stubs["regime_csv"])
    monkeypatch.setattr(run_pilot, "NIFTY_PARQUET",
                         stubs["bars_dir"] / "NIFTY.parquet")
    monkeypatch.setattr(run_pilot, "NIFTY_CSV", stubs["nifty_csv"])
    monkeypatch.setattr(run_pilot, "VIX_CSV", stubs["vix_csv"])
    monkeypatch.setattr(run_pilot, "DAILY_BARS_DIR", stubs["bars_dir"])

    panel = run_pilot._build_panel()

    # Panel contains rows from ALL regimes present inside the panel
    # window (PANEL_START..TRAIN_VAL_END). The 2025-01-02 row is past
    # TRAIN_VAL_END (2024-04-22), so it must NOT be in the panel.
    zones_in_panel = set(
        panel.loc[panel["regime_zone"].notna(), "regime_zone"].unique()
    )
    assert zones_in_panel == {"NEUTRAL", "RISK-ON", "CAUTION"}, (
        f"panel must retain all regime zones seen in-window; got {zones_in_panel}"
    )
    # The pre-train NEUTRAL row (2019-03-01) MUST be in the panel
    # (it's what lets 252d features look back beyond TRAIN_VAL_START).
    assert (panel["date"] == pd.Timestamp("2019-03-01")).any(), (
        "pre-train panel rows missing — trailing-window features will starve"
    )
    # The post-train row (2025-01-02) MUST be clipped.
    assert not (panel["date"] == pd.Timestamp("2025-01-02")).any(), (
        "post-TRAIN_VAL_END rows must not leak into the in-sample panel"
    )

    event_dates = run_pilot._get_event_dates(panel, "NEUTRAL")

    # Event dates MUST be exactly the three NEUTRAL dates inside train+val.
    expected = pd.DatetimeIndex([
        pd.Timestamp("2022-05-02"),
        pd.Timestamp("2022-05-04"),
        pd.Timestamp("2022-05-06"),
    ])
    assert list(event_dates) == list(expected), (
        f"event_dates mismatch: got {list(event_dates)}, expected {list(expected)}"
    )
    # Sorted ascending.
    assert list(event_dates) == sorted(event_dates)
    # All within [TRAIN_VAL_START, TRAIN_VAL_END].
    tv_start = pd.Timestamp(run_pilot.TRAIN_VAL_START)
    tv_end = pd.Timestamp(run_pilot.TRAIN_VAL_END)
    assert (event_dates >= tv_start).all()
    assert (event_dates <= tv_end).all()
    # Pre-train NEUTRAL row must NOT be an event date even though it's
    # in the panel.
    assert pd.Timestamp("2019-03-01") not in event_dates


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
