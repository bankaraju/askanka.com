"""Mode-1 pilot CLI — human-in-loop, ONE iteration per invocation.

One iteration = propose -> human gate -> (optionally) in-sample evaluate
-> append to proposal_log.jsonl -> exit. The human re-invokes this CLI
to drive the NEUTRAL pilot proposal-by-proposal.

View isolation (§0.3 invariant): this script builds a `ProposerView`
exposing only the in-sample log + strategy_results_10.json. The
`read_holdout_tail` method on that view raises PermissionError, so the
LLM proposer can never see holdout outcomes.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


def _load_env_file() -> None:
    """Load pipeline/.env into os.environ if present. Stdlib-only, no dotenv dep.
    Quietly no-ops if the file is missing; never overwrites existing env vars."""
    env_file = Path(__file__).resolve().parents[3] / ".env"  # pipeline/.env
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        if "=" not in line or line.strip().startswith("#"):
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env_file()


from pipeline.autoresearch.regime_autoresearch.constants import (
    DATA_DIR, DELTA_IN_SAMPLE, PROPOSER_MODEL, REGIMES, REPO_ROOT,
    TRAIN_VAL_END, TRAIN_VAL_START,
)
from pipeline.autoresearch.regime_autoresearch.dsl import (
    ABSOLUTE_THRESHOLD_GRID, CONSTRUCTION_TYPES, FEATURES, HOLD_HORIZONS,
    K_GRID, Proposal, THRESHOLD_OPS,
)
from pipeline.autoresearch.regime_autoresearch.in_sample_runner import (
    append_proposal_log, regime_buy_and_hold_sharpe, run_in_sample,
)
from pipeline.autoresearch.regime_autoresearch.incumbents import (
    TABLE_PATH, hurdle_sharpe_for_regime, load_table,
)
from pipeline.autoresearch.regime_autoresearch.proposer import (
    ProposerView, generate_proposal,
)

PILOT_TARGET = 20  # ~20 approved NEUTRAL proposals before autonomous mode
LOG_PATH = DATA_DIR / "proposal_log.jsonl"
HOLDOUT_LOG_PATH = DATA_DIR / "holdout_outcomes.jsonl"
REGIME_CSV = REPO_ROOT / "pipeline/data/regime_history.csv"
DAILY_BARS_DIR = REPO_ROOT / "pipeline/data/research/phase_c/daily_bars"
# Panel goes back 3+ years before TRAIN_VAL_START (2021-04-23) so that the
# longest-window feature (vol_percentile_252d, 253 trailing bars) has valid
# values from day 1 of train+val. 2018-01-02 is the earliest date cached by
# the quantile rework in 2b1aba4 (yfinance earliest available for the ETF
# aliases). Stock parquets start at TRAIN_VAL_START-1; even so, the full
# train+val window gives ~750 rows per ticker before TRAIN_VAL_END — more
# than enough runway for the 252d features once event_dates are separated
# from panel rows.
PANEL_START = "2018-01-02"
# Pseudo-ticker data sources. 5 of 20 DSL features
# (beta_nifty_60d, beta_vix_60d, macro_composite_60d_corr, plus features
# that compose them) need NIFTY/VIX/REGIME series keyed by ticker name
# inside the panel. Without these, those features return NaN for every
# ticker and the compiler reports n_events=0 whenever Haiku picks one.
NIFTY_PARQUET = DAILY_BARS_DIR / "NIFTY.parquet"  # canonical cache, may be absent
NIFTY_CSV = REPO_ROOT / "pipeline/data/india_historical/indices/NIFTY_daily.csv"
VIX_CSV = REPO_ROOT / "pipeline/data/vix_history.csv"


def _count_approved(log_path: Path, regime: str) -> int:
    if not log_path.exists():
        return 0
    n = 0
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("regime") == regime and row.get("approval_status") == "APPROVED":
            n += 1
    return n


def _compute_hurdle(regime: str, panel: pd.DataFrame | None = None,
                    event_dates: pd.DatetimeIndex | None = None,
                    hold_horizon: int = 1) -> tuple[float, str]:
    """Delegate to incumbents.hurdle_sharpe_for_regime with the real
    regime-conditional buy-and-hold Sharpe as the scarcity fallback.

    When incumbents are plentiful (>= INCUMBENT_SCARCITY_MIN clean), the
    fallback is never consulted and can be anything — we still supply
    the real function so the signature is consistent and a future table
    change that drops incumbents below the scarcity threshold doesn't
    silently revert to 0.0.

    `panel` is the full unfiltered history; `event_dates` is the
    regime-filtered date list to benchmark against. The caller is
    responsible for building both (via `_build_panel` +
    `_get_event_dates`) so the benchmark sees the same trade-day set as
    the proposal.

    Returns (hurdle_sharpe, source).
    """
    table = load_table(TABLE_PATH)
    if panel is None or event_dates is None:
        # Plumbing path (tests) — can't compute a real buy-and-hold; defer
        # to the zero lambda so behaviour is identical to the Task 2 stub
        # when no panel is available.
        return hurdle_sharpe_for_regime(
            table, regime, buy_hold_sharpe_fn=lambda r: 0.0,
        )
    buy_hold_fn = lambda r: regime_buy_and_hold_sharpe(  # noqa: E731
        panel, event_dates, benchmark_ticker="NIFTY",
        hold_horizon=hold_horizon,
    )
    return hurdle_sharpe_for_regime(table, regime, buy_hold_sharpe_fn=buy_hold_fn)


def _load_nifty_bars() -> pd.DataFrame:
    """Load NIFTY 50 daily close bars. Tries the canonical parquet cache
    first, then falls back to the authoritative india_historical CSV, then
    finally to a yfinance fetch of ^NSEI written to the canonical cache.

    Returns a DataFrame with columns [date, ticker="NIFTY", close, volume].
    Volume is zero-filled — no feature consumes NIFTY volume/turnover and
    the pseudo-ticker has no exchange-traded volume concept anyway.
    """
    if NIFTY_PARQUET.exists():
        df = pd.read_parquet(NIFTY_PARQUET, columns=["date", "close"])
    elif NIFTY_CSV.exists():
        df = pd.read_csv(NIFTY_CSV, parse_dates=["date"], usecols=["date", "close"])
    else:
        from pipeline.autoresearch.regime_autoresearch._yfinance_util import (
            download_ohlcv,
        )
        raw = download_ohlcv("^NSEI", TRAIN_VAL_START, "2026-04-23")
        if raw.empty:
            raise RuntimeError(
                "NIFTY bars unavailable: no parquet cache, no india_historical "
                "CSV, and yfinance fetch of ^NSEI failed"
            )
        df = raw[["date", "close"]].copy()
        # Write to canonical cache for subsequent invocations.
        NIFTY_PARQUET.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(NIFTY_PARQUET, index=False)

    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df["ticker"] = "NIFTY"
    df["volume"] = 0
    return df[["date", "close", "volume", "ticker"]]


def _load_vix_bars() -> pd.DataFrame:
    """Load VIX daily close series from pipeline/data/vix_history.csv.

    CSV columns: date, vix_close. Reshape to (date, ticker="VIX", close, volume).
    """
    if not VIX_CSV.exists():
        raise FileNotFoundError(f"missing VIX history: {VIX_CSV}")
    df = pd.read_csv(VIX_CSV, parse_dates=["date"])
    df = df.rename(columns={"vix_close": "close"})
    df["ticker"] = "VIX"
    df["volume"] = 0
    return df[["date", "close", "volume", "ticker"]]


def _load_regime_bars(regime_df: pd.DataFrame) -> pd.DataFrame:
    """Reshape regime_history.csv's signal_score column as a REGIME
    pseudo-ticker series so macro_composite_60d_corr can correlate tickers
    against the ETF regime score.
    """
    df = regime_df[["date", "signal_score"]].copy()
    df = df.rename(columns={"signal_score": "close"})
    df["ticker"] = "REGIME"
    df["volume"] = 0
    return df[["date", "close", "volume", "ticker"]]


def _build_panel() -> pd.DataFrame:
    """Assemble the full (date, ticker, close, volume, regime_zone) panel
    spanning [PANEL_START, TRAIN_VAL_END] for all tickers and all dates.

    The panel is NOT filtered by regime — that filtering belongs to
    event_dates, which is what the compiler actually uses to decide which
    days to evaluate the rule on. Panel rows exist so trailing-window
    features (e.g. vol_percentile_252d, needs 253 prior bars) have enough
    history to return non-NaN values on every event date.

    Includes the three pseudo-ticker series (NIFTY/VIX/REGIME) required
    by 5 of 20 DSL features (beta_nifty_60d, beta_vix_60d,
    macro_composite_60d_corr, and anything composing them). Without the
    pseudo-tickers, those features return NaN for every ticker and the
    compiler reports n_events=0 regardless of threshold.

    The `regime_zone` column is left-joined from regime_history.csv; it
    will be NaN for panel dates before regime history began
    (regime_history currently starts at TRAIN_VAL_START). That's fine —
    pre-train rows are never event dates, so their zone tag is unused.
    """
    if not REGIME_CSV.exists():
        raise FileNotFoundError(f"missing regime history: {REGIME_CSV}")
    regime_df = pd.read_csv(REGIME_CSV, parse_dates=["date"])
    regime_zones = regime_df[["date", "regime_zone"]].copy()

    panel_start_ts = pd.Timestamp(PANEL_START)
    panel_end_ts = pd.Timestamp(TRAIN_VAL_END)

    frames: list[pd.DataFrame] = []
    for parquet in sorted(DAILY_BARS_DIR.glob("*.parquet")):
        # Skip the (potentially-cached) NIFTY parquet — it's loaded
        # separately by _load_nifty_bars so we don't double-count.
        if parquet.name == "NIFTY.parquet":
            continue
        df = pd.read_parquet(parquet, columns=["date", "close", "volume"])
        # Some auxiliary parquets under daily_bars/ (e.g. dii_net_daily,
        # fii_net_daily, india_vix_daily) are empty placeholders from
        # earlier Task 0a work. Skipping them avoids a pandas
        # FutureWarning about concatenating all-NA entries and prevents
        # spurious "tickers" from leaking into the panel.
        if df.empty:
            continue
        df["ticker"] = parquet.stem
        frames.append(df)
    if not frames:
        raise RuntimeError(f"no parquets under {DAILY_BARS_DIR}")

    # Load the three pseudo-ticker frames from their canonical sources and
    # union them into the per-ticker panel. Consistent columns are
    # enforced (date, ticker, close, volume).
    nifty_df = _load_nifty_bars()
    vix_df = _load_vix_bars()
    regime_bars = _load_regime_bars(regime_df)

    panel = pd.concat(
        frames + [nifty_df, vix_df, regime_bars], ignore_index=True,
    )
    panel["date"] = pd.to_datetime(panel["date"])
    # Apply the panel window. Upper bound is TRAIN_VAL_END so no holdout
    # data bleeds into in-sample evaluation.
    panel = panel[(panel["date"] >= panel_start_ts)
                  & (panel["date"] <= panel_end_ts)].copy()
    # Left-join regime_zone so every row has the column; dates before
    # regime_history begins get NaN, which is fine because those rows are
    # never picked as event dates.
    panel = panel.merge(regime_zones, on="date", how="left")
    return panel


def _get_event_dates(panel: pd.DataFrame, regime: str) -> pd.DatetimeIndex:
    """Return the unique dates in [TRAIN_VAL_START, TRAIN_VAL_END] tagged
    with the given regime, sorted ascending.

    These are the days on which the compiler will evaluate the rule. The
    panel itself spans a wider window so trailing-window features have
    sufficient history; the two concepts are intentionally decoupled.
    """
    start = pd.Timestamp(TRAIN_VAL_START)
    end = pd.Timestamp(TRAIN_VAL_END)
    mask = ((panel["date"] >= start)
            & (panel["date"] <= end)
            & (panel["regime_zone"] == regime))
    dates = pd.DatetimeIndex(
        sorted(panel.loc[mask, "date"].unique())
    )
    return dates


def _strip_fences_to_json(raw: str) -> str:
    """Extract the first balanced ``{...}`` JSON object from a Haiku response.

    Handles all of:
      * clean ``{...}`` with no wrapper
      * triple-backtick fenced with or without a ``json`` tag
      * leading or trailing prose around the JSON object

    The caller (proposer) is responsible for ``json.loads``; this helper only
    isolates the candidate substring via position-based slicing so we don't
    accidentally swallow parse errors here.

    Raises ``ValueError`` if no balanced-looking JSON object is found, so a
    genuinely-broken LLM response is loud rather than silent.
    """
    stripped = raw.strip()
    try:
        start = stripped.index("{")
        end = stripped.rindex("}")
    except ValueError:
        raise ValueError(
            "LLM response contained no JSON object: " + raw[:200]
        ) from None
    if end < start:
        raise ValueError(
            "LLM response contained no JSON object: " + raw[:200]
        )
    return stripped[start:end + 1]


def _build_system_prompt(regime: str) -> str:
    """Build the Haiku system prompt with every DSL enum inlined verbatim.

    Prior versions described the grammar abstractly ("must be a grid member"),
    which let Haiku confabulate field values (e.g. construction_type="absolute",
    feature="rsi_14"). We now enumerate every allowed value imported from dsl.py
    so the prompt stays in sync if the grammar grows.
    """
    features = ", ".join(FEATURES)
    constructions = ", ".join(CONSTRUCTION_TYPES)
    ops = ", ".join(f'"{op}"' for op in THRESHOLD_OPS)
    abs_grid = ", ".join(str(v) for v in ABSOLUTE_THRESHOLD_GRID)
    k_grid = ", ".join(str(v) for v in K_GRID)
    horizons = ", ".join(str(h) for h in HOLD_HORIZONS)
    return (
        "You generate a single DSL proposal as strict JSON (no markdown "
        "fences, no prose).\n\n"
        "Required keys: construction_type, feature, threshold_op, "
        "threshold_value, hold_horizon, regime, pair_id.\n\n"
        "ALLOWED VALUES — pick EXACTLY one of the listed items for each "
        "field:\n"
        f"- construction_type: one of: {constructions}\n"
        f"- feature: one of: {features}\n"
        f"- threshold_op: one of: {ops}\n"
        "- threshold_value: when threshold_op is \">\" or \"<\", must be a "
        f"number from ABSOLUTE_THRESHOLD_GRID [{abs_grid}]; when "
        "threshold_op is \"top_k\" or \"bottom_k\" (construction_type must be "
        f"long_short_basket), must be an integer from K_GRID [{k_grid}]\n"
        f"- hold_horizon: one of: {horizons}\n"
        f"- regime: must be \"{regime}\"\n"
        "- pair_id: must be null unless construction_type is \"pair\"\n\n"
        "Respond with the JSON object only. No code fences. No preamble. "
        "Start with { and end with }."
    )


def _build_llm_call():
    """Factory for an anthropic messages.create wrapper that returns raw JSON.

    The wrapper signature is `llm_call(model, context) -> str|dict`, consumed
    by `proposer.generate_proposal`. Kept in a factory so tests can monkeypatch
    this symbol without importing anthropic at all.
    """
    try:
        import anthropic  # noqa: F401 — imported lazily
    except ImportError as exc:
        raise RuntimeError(
            "anthropic SDK not installed; cannot run real iteration"
        ) from exc
    import anthropic as _anthropic
    client = _anthropic.Anthropic()

    def _call(model: str, context: dict) -> str:
        system = _build_system_prompt(context["regime"])
        user = (
            f"Regime: {context['regime']}\n"
            f"Recent in-sample proposals (last 200): "
            f"{json.dumps(context['recent_in_sample'][-10:], default=str)}\n"
            f"Incumbent table (strategy_results_10): "
            f"{json.dumps(context.get('incumbents', {}), default=str)[:2000]}"
        )
        resp = client.messages.create(
            model=model,
            max_tokens=512,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        # Anthropic returns a content list of blocks; concatenate text blocks.
        text = "".join(
            b.text for b in resp.content if getattr(b, "type", "") == "text"
        )
        # Persist the raw pre-strip response so BLOCKED iterations leave a
        # forensic artefact without needing another paid API call.
        try:
            (DATA_DIR / "last_llm_response.txt").write_text(text, encoding="utf-8")
        except Exception:  # pragma: no cover — best-effort logging only
            pass
        # Haiku sometimes ignores the "no markdown fences" instruction; strip
        # fences / leading prose here so the proposer gets clean JSON.
        return _strip_fences_to_json(text)

    return _call


def _print_proposal(p: Proposal) -> None:
    print("\n--- PROPOSAL ---")
    print(f"  construction_type : {p.construction_type}")
    print(f"  feature           : {p.feature}")
    print(f"  threshold_op      : {p.threshold_op}")
    print(f"  threshold_value   : {p.threshold_value}")
    print(f"  hold_horizon      : {p.hold_horizon}")
    print(f"  regime            : {p.regime}")
    if p.pair_id:
        print(f"  pair_id           : {p.pair_id}")


def _make_row(proposal: Proposal, approval_status: str,
              result: dict | None, hurdle_sharpe: float | None,
              hurdle_source: str | None) -> dict:
    row = {
        "proposal_id": f"P-{uuid.uuid4().hex[:12]}",
        "regime": proposal.regime,
        "construction_type": proposal.construction_type,
        "feature": proposal.feature,
        "threshold_op": proposal.threshold_op,
        "threshold_value": proposal.threshold_value,
        "hold_horizon": proposal.hold_horizon,
        "pair_id": proposal.pair_id,
        "approval_status": approval_status,
        "timestamp_iso": datetime.now(timezone.utc).isoformat(),
    }
    if result is not None:
        row["net_sharpe_mean"] = result.get("net_sharpe_in_sample")
        row["n_events"] = result.get("n_events_in_sample")
        row["hurdle_sharpe"] = hurdle_sharpe
        row["hurdle_source"] = hurdle_source
        row["passes_delta_in"] = (
            row["net_sharpe_mean"] is not None
            and hurdle_sharpe is not None
            and (row["net_sharpe_mean"] - hurdle_sharpe) >= DELTA_IN_SAMPLE
        )
    return row


def run_one_iteration(regime: str, log_path: Path,
                      auto_approve: bool = False) -> int:
    if regime not in REGIMES:
        print(f"error: unknown regime {regime!r}; must be one of {REGIMES}",
              file=sys.stderr)
        return 2

    n_approved = _count_approved(log_path, regime)
    print(f"[pilot {regime}] approved so far: {n_approved + 1} of ~{PILOT_TARGET}")

    view = ProposerView(
        in_sample_log=log_path,
        holdout_log=HOLDOUT_LOG_PATH,
        strategy_results=TABLE_PATH,
    )
    llm_call = _build_llm_call() if not auto_approve or os.environ.get("ANTHROPIC_API_KEY") else None
    proposal = generate_proposal(view, regime, llm_call)
    _print_proposal(proposal)

    if auto_approve:
        answer = "y"
        print("Approve this proposal? [y/n/s] (auto-approve): y")
    else:
        answer = input("Approve this proposal? [y/n/s] (s=skip, don't log): ").strip().lower()

    if answer == "s":
        print("[pilot] skipped — no row written.")
        return 0

    if answer == "n":
        row = _make_row(proposal, "REJECTED", None, None, None)
        append_proposal_log(log_path, row)
        print(f"[pilot] REJECTED — logged to {log_path}")
        return 0

    if answer != "y":
        print(f"[pilot] unrecognised answer {answer!r}; treating as skip.")
        return 0

    # APPROVED path: build the unfiltered panel, compute regime-filtered
    # event_dates separately, exclude pseudo-tickers from the trade
    # universe, then run the compiler with all three passed explicitly.
    panel = _build_panel()
    event_dates = _get_event_dates(panel, regime)
    pseudo = {"NIFTY", "VIX", "REGIME"}
    tickers = sorted(
        t for t in panel["ticker"].unique() if t not in pseudo
    )
    hurdle_sharpe, hurdle_source = _compute_hurdle(
        regime, panel=panel, event_dates=event_dates,
        hold_horizon=proposal.hold_horizon,
    )
    result = run_in_sample(proposal, panel, log_path=log_path,
                           incumbent_sharpe=hurdle_sharpe,
                           event_dates=event_dates, tickers=tickers)
    row = _make_row(proposal, "APPROVED", result, hurdle_sharpe, hurdle_source)
    append_proposal_log(log_path, row)

    print("\n--- IN-SAMPLE RESULT ---")
    print(f"  proposal_id     : {row['proposal_id']}")
    print(f"  n_events        : {row['n_events']}")
    print(f"  net_sharpe_mean : {row['net_sharpe_mean']:.4f}")
    print(f"  hurdle_sharpe   : {hurdle_sharpe:.4f}  ({hurdle_source})")
    print(f"  delta_in target : {DELTA_IN_SAMPLE:.2f}")
    verdict = "PASS" if row["passes_delta_in"] else "FAIL"
    print(f"  verdict         : {verdict}")
    print(f"\n[pilot] APPROVED — logged to {log_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="run_pilot",
        description="Run ONE iteration of the Mode-1 human-in-loop pilot.",
    )
    parser.add_argument("--regime", default="NEUTRAL", choices=list(REGIMES))
    parser.add_argument("--log", type=Path, default=LOG_PATH,
                        help="proposal_log.jsonl path (default: package data dir)")
    parser.add_argument("--auto-approve", action="store_true",
                        help="skip the input() prompt and force APPROVE "
                             "(used only for end-to-end verification)")
    args = parser.parse_args(argv)

    return run_one_iteration(
        regime=args.regime,
        log_path=args.log,
        auto_approve=args.auto_approve,
    )


if __name__ == "__main__":
    raise SystemExit(main())
