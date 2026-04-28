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
    DATA_DIR, DELTA_IN_SAMPLE, MIN_EVENTS_FOR_PASS,
    MIN_EVENTS_PER_FOLD_FOR_PASS, MIN_NET_SHARPE, PROPOSER_MODEL, REGIMES,
    REPO_ROOT, TRAIN_VAL_END, TRAIN_VAL_START,
)
from pipeline.autoresearch.regime_autoresearch.dsl import (
    ABSOLUTE_THRESHOLD_GRID, CONSTRUCTION_TYPES, FEATURES, HOLD_HORIZONS,
    K_GRID, Proposal, THRESHOLD_OPS,
)
from pipeline.autoresearch.regime_autoresearch.in_sample_runner import (
    append_proposal_log, regime_buy_and_hold_sharpe, run_in_sample,  # noqa: F401 (regime_buy_and_hold_sharpe kept for rollback)
)
from pipeline.autoresearch.regime_autoresearch.incumbents import (
    TABLE_PATH, hurdle_sharpe_for_regime, load_table,
)
from pipeline.autoresearch.regime_autoresearch.null_basket_hurdle import (
    load_null_basket_hurdle,
)
from pipeline.autoresearch.regime_autoresearch.proposer import (
    ProposerView, generate_proposal, log_path_for_regime,
)

PILOT_TARGET = 20  # ~20 approved NEUTRAL proposals before autonomous mode
LOG_PATH = log_path_for_regime("NEUTRAL")  # v2: per-regime sharded log
HOLDOUT_LOG_PATH = DATA_DIR / "holdout_outcomes.jsonl"
# Proposer duplicate-suppression: how many retries on an exact-5-tuple
# match before we log DUPLICATE_GIVEUP and exit. The LLM is given the
# forbidden tuple on each retry so it has a chance to diverge.
DUPLICATE_MAX_RETRIES = 3


class DuplicateProposalError(Exception):
    """Raised when a validated proposal matches an existing log-row 5-tuple.

    The CLI catches this up to DUPLICATE_MAX_RETRIES times, each retry
    appending the duplicate tuple to the system prompt as a forbidden
    combination, before logging a DUPLICATE_GIVEUP row and exiting.
    """

    def __init__(self, tuple5: tuple) -> None:
        super().__init__(f"proposal repeats existing 5-tuple: {tuple5}")
        self.tuple5 = tuple5


def _proposal_tuple5(proposal_or_row) -> tuple:
    """Extract the (feature, construction_type, threshold_op, threshold_value,
    hold_horizon) 5-tuple used for duplicate detection.

    Accepts either a `Proposal` dataclass or a dict loaded from the
    proposal log (whose field names match). We intentionally OMIT regime
    and pair_id from the tuple: regime because the caller is always
    scanning within a single regime's log slice, pair_id because it's
    construction-specific.
    """
    if hasattr(proposal_or_row, "feature"):  # Proposal dataclass
        return (
            proposal_or_row.feature,
            proposal_or_row.construction_type,
            proposal_or_row.threshold_op,
            proposal_or_row.threshold_value,
            proposal_or_row.hold_horizon,
        )
    # dict path
    return (
        proposal_or_row.get("feature"),
        proposal_or_row.get("construction_type"),
        proposal_or_row.get("threshold_op"),
        proposal_or_row.get("threshold_value"),
        proposal_or_row.get("hold_horizon"),
    )


def _is_duplicate(proposal, log_path: Path, regime: str) -> bool:
    """True if `proposal`'s 5-tuple matches any prior row in `log_path`
    for the same regime (regardless of approval_status — we block repeats
    of REJECTED rules too, because re-proposing a known-rejected rule is
    exactly the failure mode this gate is meant to catch).
    """
    if not log_path.exists():
        return False
    target = _proposal_tuple5(proposal)
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("regime") != regime:
            continue
        if _proposal_tuple5(row) == target:
            return True
    return False
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


def _null_basket_construction(construction_type: str) -> str:
    """Map DSL construction_type to canonical null_basket_hurdle construction.

    DSL types: "single_long", "single_short", "long_short_basket", "pair".
    null_basket_hurdle CONSTRUCTIONS: "single_long", "single_short",
        "top_k", "bottom_k", "long_short_basket".

    "pair" maps to "long_short_basket" (closest analog — one long leg,
    one short leg). "top_k" and "bottom_k" are not DSL types: threshold_op
    encodes the direction, not the construction name.
    """
    _MAP = {
        "single_long": "single_long",
        "single_short": "single_short",
        "long_short_basket": "long_short_basket",
        "pair": "long_short_basket",  # closest analog
    }
    return _MAP.get(construction_type, "long_short_basket")


def _null_basket_k(proposal) -> int:
    """Extract cardinality k for the null basket lookup.

    For top_k / bottom_k threshold_ops, threshold_value IS k (an integer
    from K_GRID).  For everything else, the basket has a single ticker
    so k=1.
    """
    if proposal.threshold_op in ("top_k", "bottom_k"):
        return int(proposal.threshold_value)
    return 1


def _compute_hurdle(regime: str, panel: pd.DataFrame | None = None,
                    event_dates: pd.DatetimeIndex | None = None,
                    hold_horizon: int = 1,
                    proposal=None) -> tuple[float, str]:
    """v2: look up the construction-matched null-basket hurdle.

    Uses load_null_basket_hurdle(construction, k, hold_horizon, regime,
    window='train_val') instead of the v1 NIFTY buy-and-hold / scarcity
    fallback pair. Falls back gracefully when the parquet table is absent
    (test or pre-build environments) or when the proposal is not provided.

    Returns (hurdle_sharpe, source).
    """
    if proposal is not None:
        construction = _null_basket_construction(proposal.construction_type)
        k = _null_basket_k(proposal)
        try:
            hurdle = load_null_basket_hurdle(
                construction=construction,
                k=k,
                hold_horizon=hold_horizon,
                regime=regime,
                window="train_val",
            )
            return hurdle, f"null_basket:{construction}:k={k}:h={hold_horizon}"
        except (FileNotFoundError, KeyError):
            # Parquet not built yet — fall through to incumbent table
            pass
    # Legacy path: used when proposal is None (tests / pre-build)
    table = load_table(TABLE_PATH)
    return hurdle_sharpe_for_regime(table, regime)


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


def _build_system_prompt(regime: str,
                          forbidden_tuples: list[tuple] | None = None) -> str:
    """Build the Haiku system prompt with every DSL enum inlined verbatim.

    Prior versions described the grammar abstractly ("must be a grid member"),
    which let Haiku confabulate field values (e.g. construction_type="absolute",
    feature="rsi_14"). We now enumerate every allowed value imported from dsl.py
    so the prompt stays in sync if the grammar grows.

    `forbidden_tuples` (when non-empty) is appended as an explicit
    anti-duplication directive listing exact (feature,
    construction_type, threshold_op, threshold_value, hold_horizon)
    tuples the LLM MUST NOT re-emit. This is a belt-and-braces companion
    to the post-validate dedup gate in `run_one_iteration`: during the
    20-iter NEUTRAL pilot (2026-04-24) Haiku re-rolled 3 identical rules
    despite seeing prior proposals, so we now shout the constraint into
    the system prompt itself.
    """
    features = ", ".join(FEATURES)
    constructions = ", ".join(CONSTRUCTION_TYPES)
    ops = ", ".join(f'"{op}"' for op in THRESHOLD_OPS)
    abs_grid = ", ".join(str(v) for v in ABSOLUTE_THRESHOLD_GRID)
    k_grid = ", ".join(str(v) for v in K_GRID)
    horizons = ", ".join(str(h) for h in HOLD_HORIZONS)
    base = (
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
        "AVOID PROPOSING ANY RULE WITH THE SAME (feature, construction_type, "
        "threshold_op, threshold_value, hold_horizon) TUPLE as any prior "
        "proposal in the user-message context list. Generate a rule that is "
        "structurally different from every one above.\n\n"
    )
    if forbidden_tuples:
        lines = "\n".join(f"  - {t}" for t in forbidden_tuples)
        base += (
            "DO NOT REPEAT ANY OF THESE EXACT TUPLES — each was just "
            "proposed and rejected as a duplicate:\n"
            f"{lines}\n\n"
        )
    base += (
        "Respond with the JSON object only. No code fences. No preamble. "
        "Start with { and end with }."
    )
    return base


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
        forbidden = context.get("forbidden_tuples") or []
        system = _build_system_prompt(context["regime"],
                                      forbidden_tuples=forbidden)
        user = (
            f"Regime: {context['regime']}\n"
            f"Recent in-sample proposals (last 200): "
            f"{json.dumps(context['recent_in_sample'][-10:], default=str)}\n"
            f"Incumbent table (strategy_results_10): "
            f"{json.dumps(context.get('incumbents', {}), default=str)[:2000]}"
        )
        # temperature=0.7 set explicitly for proposal diversity. Default
        # of 1.0 hasn't prevented Haiku re-rolling identical rules, but
        # dropping the temperature slightly does at least bias the
        # sampler away from low-entropy repeats — combined with the
        # forbidden-tuple directive and the post-validate dedup gate,
        # this is defense-in-depth.
        resp = client.messages.create(
            model=model,
            max_tokens=512,
            temperature=0.7,
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


def _compute_verdict(n_events: int | None, net_sharpe: float | None,
                     hurdle_sharpe: float | None,
                     fold_n_events: list[int] | None = None,
                     insufficient_for_folds: bool = False) -> dict:
    """Compute the in-sample verdict booleans.

    Returns a dict with:
      - passes_delta_in: net_sharpe - hurdle >= DELTA_IN_SAMPLE
        AND net_sharpe >= MIN_NET_SHARPE (absolute floor, Backlog #195)
      - passes_min_events: n_events >= MIN_EVENTS_FOR_PASS
      - passes_all_folds_populated: every fold had at least
        MIN_EVENTS_PER_FOLD_FOR_PASS events AND the runner did not fall
        back to a single-pass evaluation
      - verdict_pass: all three of the above True
      - verdict_reason: human-readable string on FAIL (empty on PASS)

    Any None input propagates to a safe False. The `n_events=0` failure
    mode motivating the min_events gate (observed 2026-04-24 pilot on
    `trust_score top_20` which passed delta_in with 0 trades) cannot
    produce verdict_pass=True because min_events=0 < 20.

    The all_folds_populated gate (Task #198) catches a separate failure
    mode: features with a 252-bar trailing requirement silently empty
    fold 0 when the panel only goes back 3 years before TRAIN_VAL_START.
    The empty fold averages in as 0.0, but the non-empty folds can still
    pull the mean above hurdle+delta_in — falsely passing. We now
    require every fold to carry at least MIN_EVENTS_PER_FOLD_FOR_PASS
    events. insufficient_for_folds (single-pass fallback rows) auto-fail
    because the rule's in-sample window is too short for a trustworthy
    cross-time Sharpe.

    The MIN_NET_SHARPE absolute floor (Backlog #195, 2026-04-28) is
    folded into passes_delta_in: even if the gap clears, a net-negative
    proposal is not deployable. v2's null-basket hurdle in NEUTRAL h=1
    runs deeply negative (-1.6 to -3.5 Sharpe), so without the floor
    proposals with net_sharpe ≈ 0 cleared delta_in by ~9× the threshold.
    """
    passes_delta_in_gap = (
        net_sharpe is not None
        and hurdle_sharpe is not None
        and (net_sharpe - hurdle_sharpe) >= DELTA_IN_SAMPLE
    )
    passes_min_net_sharpe = (
        net_sharpe is not None and net_sharpe >= MIN_NET_SHARPE
    )
    passes_delta_in = bool(passes_delta_in_gap and passes_min_net_sharpe)
    passes_min_events = (
        n_events is not None and n_events >= MIN_EVENTS_FOR_PASS
    )
    passes_all_folds_populated = (
        not insufficient_for_folds
        and fold_n_events is not None
        and len(fold_n_events) > 0
        and all(n >= MIN_EVENTS_PER_FOLD_FOR_PASS for n in fold_n_events)
    )
    verdict_pass = bool(
        passes_delta_in and passes_min_events and passes_all_folds_populated
    )
    reason = ""
    if not verdict_pass:
        reasons = []
        if not passes_min_events:
            reasons.append(
                f"insufficient events (n={n_events} < {MIN_EVENTS_FOR_PASS})"
            )
        if not passes_delta_in:
            if not passes_delta_in_gap:
                reasons.append("delta_in gap below hurdle")
            if not passes_min_net_sharpe:
                reasons.append(
                    f"net_sharpe below floor (need >= {MIN_NET_SHARPE})"
                )
        if not passes_all_folds_populated:
            if insufficient_for_folds:
                reasons.append(
                    "single-pass fallback (insufficient events for K folds)"
                )
            elif fold_n_events is None or len(fold_n_events) == 0:
                reasons.append("no fold breakdown available")
            else:
                sparse = [
                    (i, n) for i, n in enumerate(fold_n_events)
                    if n < MIN_EVENTS_PER_FOLD_FOR_PASS
                ]
                parts = ", ".join(
                    f"fold {i} has {n} events" for i, n in sparse
                )
                reasons.append(
                    f"{parts} (min required: {MIN_EVENTS_PER_FOLD_FOR_PASS})"
                )
        reason = "; ".join(reasons)
    return {
        "passes_delta_in": passes_delta_in,
        "passes_min_events": passes_min_events,
        "passes_all_folds_populated": passes_all_folds_populated,
        "verdict_pass": verdict_pass,
        "verdict_reason": reason,
    }


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
        "schema_version": "v2",
    }
    if result is not None:
        row["net_sharpe_mean"] = result.get("net_sharpe_in_sample")
        row["n_events"] = result.get("n_events_in_sample")
        row["hurdle_sharpe"] = hurdle_sharpe
        row["hurdle_source"] = hurdle_source
        # Task #191 — fold breakdown from K-fold time-series CV; carried
        # into the row so the downstream reader can see cross-time
        # Sharpe robustness, not just the aggregate.
        row["fold_sharpes"] = result.get("fold_sharpes")
        row["fold_n_events"] = result.get("fold_n_events")
        row["sharpe_oos_std"] = result.get("sharpe_oos_std")
        row["insufficient_for_folds"] = result.get("insufficient_for_folds")
        verdict = _compute_verdict(
            row["n_events"], row["net_sharpe_mean"], hurdle_sharpe,
            fold_n_events=row.get("fold_n_events"),
            insufficient_for_folds=bool(row.get("insufficient_for_folds")),
        )
        # passes_delta_in preserved for backward compat; the
        # passes_min_events gate enforces MIN_EVENTS_FOR_PASS so
        # `n_events=0` cannot produce a spurious PASS verdict. The
        # passes_all_folds_populated gate (Task #198) blocks the
        # fold-0-empty failure mode on 252-bar features.
        row["passes_delta_in"] = verdict["passes_delta_in"]
        row["passes_min_events"] = verdict["passes_min_events"]
        row["passes_all_folds_populated"] = verdict["passes_all_folds_populated"]
    return row


def _propose_with_dedup(view: ProposerView, regime: str, llm_call,
                         log_path: Path) -> tuple[Proposal | None, list[tuple]]:
    """Generate a proposal, retrying on exact-5-tuple duplicates up to
    DUPLICATE_MAX_RETRIES times.

    On each retry, the failed tuple is added to `forbidden_tuples` which
    `_build_llm_call` threads into the system prompt as an explicit
    "DO NOT REPEAT" list. Returns (proposal, forbidden_tuples) on success;
    (None, forbidden_tuples) if all retries produced duplicates, in which
    case the CLI is expected to log a DUPLICATE_GIVEUP row and exit.

    `llm_call` may be None for test paths that stub `generate_proposal`
    directly — those stubs never hit the real Haiku client and so the
    forbidden_tuples threading is a no-op.
    """
    forbidden: list[tuple] = []
    last_proposal: Proposal | None = None
    for attempt in range(DUPLICATE_MAX_RETRIES + 1):
        # Wrap llm_call so the forbidden-tuples list reaches _build_llm_call's
        # inner `_call(model, context)` via the shared context dict.
        if llm_call is not None and forbidden:
            inner = llm_call

            def _wrapped(model, context, _inner=inner, _forbidden=list(forbidden)):
                ctx = dict(context)
                ctx["forbidden_tuples"] = _forbidden
                return _inner(model=model, context=ctx)

            current_call = _wrapped
        else:
            current_call = llm_call
        candidate = generate_proposal(view, regime, current_call)
        last_proposal = candidate
        if _is_duplicate(candidate, log_path, regime):
            forbidden.append(_proposal_tuple5(candidate))
            print(
                f"[pilot] duplicate 5-tuple detected "
                f"({_proposal_tuple5(candidate)}); "
                f"retry {attempt + 1}/{DUPLICATE_MAX_RETRIES}"
            )
            if attempt >= DUPLICATE_MAX_RETRIES:
                return None, forbidden
            continue
        return candidate, forbidden
    # Defensive — loop above always returns.
    return None, forbidden


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
    proposal, forbidden_tuples = _propose_with_dedup(view, regime, llm_call, log_path)
    if proposal is None:
        # 3 consecutive duplicates — log forensic row and exit cleanly.
        placeholder = Proposal(
            construction_type="single_long",
            feature="ret_1d",
            threshold_op=">",
            threshold_value=0.0,
            hold_horizon=1,
            regime=regime,
            pair_id=None,
        )
        row = _make_row(placeholder, "DUPLICATE_GIVEUP", None, None, None)
        row["duplicate_tuples"] = [list(t) for t in forbidden_tuples]
        append_proposal_log(log_path, row)
        print(
            f"[pilot] DUPLICATE_GIVEUP — Haiku produced "
            f"{DUPLICATE_MAX_RETRIES} consecutive duplicates of existing "
            f"log 5-tuples; logged to {log_path} and exiting."
        )
        return 0
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
        hold_horizon=proposal.hold_horizon, proposal=proposal,
    )
    result = run_in_sample(proposal, panel, log_path=log_path,
                           incumbent_sharpe=hurdle_sharpe,
                           event_dates=event_dates, tickers=tickers)
    row = _make_row(proposal, "APPROVED", result, hurdle_sharpe, hurdle_source)
    append_proposal_log(log_path, row)

    gap = (
        (row["net_sharpe_mean"] - hurdle_sharpe)
        if row["net_sharpe_mean"] is not None and hurdle_sharpe is not None
        else None
    )
    passes_delta_in = row["passes_delta_in"]
    passes_min_events = row["passes_min_events"]
    passes_all_folds_populated = row.get("passes_all_folds_populated", False)
    verdict_pass = bool(
        passes_delta_in and passes_min_events and passes_all_folds_populated
    )
    delta_mark = "OK" if passes_delta_in else "FAIL"
    events_mark = "OK" if passes_min_events else "FAIL"
    folds_mark = "OK" if passes_all_folds_populated else "FAIL"
    print("\n--- IN-SAMPLE RESULT ---")
    print(f"  proposal_id     : {row['proposal_id']}")
    fold_n = row.get("fold_n_events")
    if fold_n:
        fold_n_str = ", ".join(str(n) for n in fold_n)
        print(
            f"  n_events        : {row['n_events']} "
            f"(folds: {fold_n_str})"
        )
    else:
        print(f"  n_events        : {row['n_events']}")
    fold_s = row.get("fold_sharpes")
    if fold_s:
        fold_s_str = ", ".join(f"{s:+.2f}" for s in fold_s)
        print(f"  fold_sharpes    : [{fold_s_str}]")
    oos_std = row.get("sharpe_oos_std")
    if oos_std is not None:
        print(
            f"  net_sharpe_mean : {row['net_sharpe_mean']:+.4f}   "
            f"(OOS sigma: {oos_std:.4f})"
        )
    else:
        print(f"  net_sharpe_mean : {row['net_sharpe_mean']:.4f}")
    if row.get("insufficient_for_folds"):
        print(
            "  WARNING         : insufficient events for K-fold CV; "
            "single-pass fallback used"
        )
    print(f"  hurdle_sharpe   : {hurdle_sharpe:.4f}  ({hurdle_source})")
    gap_str = f"{gap:+.4f}" if gap is not None else "n/a"
    print(
        f"  delta_in gap    : {gap_str}  (target: {DELTA_IN_SAMPLE:.2f}) {delta_mark}"
    )
    print(
        f"  min_events gate : {row['n_events']} (target: {MIN_EVENTS_FOR_PASS}) {events_mark}"
    )
    # all_folds_populated gate (Task #198) — require every fold to have
    # at least MIN_EVENTS_PER_FOLD_FOR_PASS events. Prints a specific
    # diagnostic when the gate fails so the reader can tell which fold
    # was starved.
    if passes_all_folds_populated:
        print(
            f"  all_folds gate  : OK (min required per fold: "
            f"{MIN_EVENTS_PER_FOLD_FOR_PASS})"
        )
    else:
        if row.get("insufficient_for_folds"):
            detail = (
                "single-pass fallback (insufficient events for K folds)"
            )
        elif not fold_n:
            detail = "no fold breakdown available"
        else:
            sparse = [
                (i, n) for i, n in enumerate(fold_n)
                if n < MIN_EVENTS_PER_FOLD_FOR_PASS
            ]
            detail = ", ".join(
                f"fold {i} has {n} events" for i, n in sparse
            )
        print(
            f"  all_folds gate  : FAIL — {detail} "
            f"(min required: {MIN_EVENTS_PER_FOLD_FOR_PASS})"
        )
    verdict = "PASS" if verdict_pass else "FAIL"
    print(f"  verdict         : {verdict}")
    print(f"\n[pilot] APPROVED — logged to {log_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="run_pilot",
        description="Run ONE iteration of the Mode-1 human-in-loop pilot.",
    )
    parser.add_argument("--regime", default="NEUTRAL", choices=list(REGIMES))
    parser.add_argument("--log", type=Path, default=None,
                        help="proposal log path override (default: per-regime sharded log)")
    parser.add_argument("--auto-approve", action="store_true",
                        help="skip the input() prompt and force APPROVE "
                             "(used only for end-to-end verification)")
    args = parser.parse_args(argv)

    log_path = args.log if args.log is not None else log_path_for_regime(args.regime)
    return run_one_iteration(
        regime=args.regime,
        log_path=log_path,
        auto_approve=args.auto_approve,
    )


if __name__ == "__main__":
    raise SystemExit(main())
