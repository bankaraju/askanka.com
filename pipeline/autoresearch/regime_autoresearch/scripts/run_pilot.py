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

from pipeline.autoresearch.regime_autoresearch.constants import (
    DATA_DIR, DELTA_IN_SAMPLE, PROPOSER_MODEL, REGIMES, REPO_ROOT,
    TRAIN_VAL_END, TRAIN_VAL_START,
)
from pipeline.autoresearch.regime_autoresearch.dsl import Proposal
from pipeline.autoresearch.regime_autoresearch.in_sample_runner import (
    append_proposal_log, run_in_sample,
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


def _compute_hurdle(regime: str) -> tuple[float, str]:
    """Delegate to incumbents.hurdle_sharpe_for_regime with a zero
    buy-and-hold fallback. Returns (hurdle_sharpe, source).
    """
    table = load_table(TABLE_PATH)
    return hurdle_sharpe_for_regime(table, regime, buy_hold_sharpe_fn=lambda r: 0.0)


def _build_neutral_panel(regime: str) -> pd.DataFrame:
    """Assemble the (date, ticker, close, volume, regime_zone) panel for the
    train+val window, filtered to `regime`-tagged dates. Uses the 67
    parquets in pipeline/data/research/phase_c/daily_bars.
    """
    if not REGIME_CSV.exists():
        raise FileNotFoundError(f"missing regime history: {REGIME_CSV}")
    regime_df = pd.read_csv(REGIME_CSV, parse_dates=["date"])
    mask = ((regime_df["date"] >= TRAIN_VAL_START)
            & (regime_df["date"] <= TRAIN_VAL_END)
            & (regime_df["regime_zone"] == regime))
    regime_window = regime_df.loc[mask, ["date", "regime_zone"]].copy()

    frames: list[pd.DataFrame] = []
    for parquet in sorted(DAILY_BARS_DIR.glob("*.parquet")):
        df = pd.read_parquet(parquet, columns=["date", "close", "volume"])
        df["ticker"] = parquet.stem
        frames.append(df)
    if not frames:
        raise RuntimeError(f"no parquets under {DAILY_BARS_DIR}")
    panel = pd.concat(frames, ignore_index=True)
    panel = panel.merge(regime_window, on="date", how="inner")
    return panel


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
        system = (
            "You are a quantitative researcher proposing ONE trading rule as a "
            "JSON object matching the DSL grammar. Respond with ONLY the JSON "
            "object — no markdown fences, no commentary. Fields: "
            "construction_type, feature, threshold_op, threshold_value, "
            "hold_horizon, regime, pair_id. threshold_value MUST be a grid "
            "member (see ABSOLUTE_THRESHOLD_GRID or K_GRID). pair_id must be "
            "null unless construction_type == 'pair'."
        )
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
        return text.strip()

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

    # APPROVED path: load panel, compute hurdle, run in-sample.
    hurdle_sharpe, hurdle_source = _compute_hurdle(regime)
    panel = _build_neutral_panel(regime)
    result = run_in_sample(proposal, panel, log_path=log_path,
                           incumbent_sharpe=hurdle_sharpe)
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
