"""Chart-v2 health audit — F&O universe coverage + freshness + narrative
marker regression.

Called from pipeline.watchdog step 4c (alongside audit_track_record) on
every gate run. Output is a list of audit-failure dicts; the watchdog
wraps each into an Issue(IssueKind.CONTENT_DRIFT) so the dedup state and
fan-out collapse already in place handle "alert once, suppress until
resolved."

Why this lives outside the watchdog module: the marker-regression check
imports the running narrative compute, which pulls pandas + the route's
private helpers. Keeping it in a sibling module lets `pipeline.watchdog`
import lazily and makes the unit test surface small.

The check is a defense layer for the "silent staleness reaches a paying
customer" failure mode (the original April-15 freeze, the prior
trust_score schema drift). A laptop-side audit catches everything except
the laptop-itself-down case; the planned cloud-side companion (after
/web-setup) covers that final mile.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

REPO = Path(__file__).resolve().parent.parent
UNIVERSE_PATH = REPO / "pipeline" / "data" / "canonical_fno_research_v3.json"
FNO_HIST_DIR = REPO / "pipeline" / "data" / "fno_historical"
STATE_PATH = REPO / "pipeline" / "data" / "chart_audit_state.json"

EXPECTED_UNIVERSE_SIZE = 273
SPOT_CHECK_TICKERS = ("ONGC", "COALINDIA", "RELIANCE", "HDFCBANK", "LAURUSLABS", "INFY")
TAIL_STALE_DAYS = 4  # mirror pipeline/terminal/api/charts.py _TAIL_STALE_DAYS


def audit_chart_universe(
    *,
    universe_path: Path = UNIVERSE_PATH,
    fno_dir: Path = FNO_HIST_DIR,
    state_path: Path = STATE_PATH,
    tickers: tuple = SPOT_CHECK_TICKERS,
    now: datetime | None = None,
) -> list[dict]:
    """Return a list of {kind, detail} dicts. Empty = healthy.

    Kinds (kept short for the watchdog detail line):
      universe_missing / universe_unreadable / universe_size
      missing_csvs / stale_tail
      marker_regression
    """
    now = now or datetime.now()
    issues: list[dict] = []
    issues.extend(_check_universe_coverage(universe_path, fno_dir))
    issues.extend(_check_universe_freshness(universe_path, fno_dir, now))
    issues.extend(_check_marker_regressions(tickers, state_path, now))
    return issues


def _read_universe(universe_path: Path) -> tuple[list[str], dict | None]:
    """Returns (tickers, error_issue). On any read failure, tickers is empty
    and error_issue is the issue dict to surface."""
    if not universe_path.exists():
        return [], {
            "kind": "universe_missing",
            "detail": f"{universe_path.name} not found at {universe_path}",
        }
    try:
        data = json.loads(universe_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        return [], {"kind": "universe_unreadable", "detail": str(e)}
    if isinstance(data, dict):
        tickers = data.get("tickers", [])
    elif isinstance(data, list):
        tickers = data
    else:
        return [], {
            "kind": "universe_unreadable",
            "detail": f"unexpected JSON root type {type(data).__name__}",
        }
    return list(tickers), None


def _check_universe_coverage(universe_path: Path, fno_dir: Path) -> list[dict]:
    tickers, err = _read_universe(universe_path)
    if err:
        return [err]

    n = len(tickers)
    out: list[dict] = []
    if n != EXPECTED_UNIVERSE_SIZE:
        out.append({
            "kind": "universe_size",
            "detail": (
                f"canonical_fno_research_v3.json has {n} tickers, "
                f"expected {EXPECTED_UNIVERSE_SIZE}"
            ),
        })

    missing = [t for t in tickers if not (fno_dir / f"{t}.csv").exists()]
    if missing:
        sample = ", ".join(missing[:5])
        more = f" (+{len(missing) - 5} more)" if len(missing) > 5 else ""
        out.append({
            "kind": "missing_csvs",
            "detail": (
                f"{len(missing)} of {n} tickers have no fno_historical csv: "
                f"{sample}{more}"
            ),
        })
    return out


def _check_universe_freshness(
    universe_path: Path, fno_dir: Path, now: datetime
) -> list[dict]:
    tickers, err = _read_universe(universe_path)
    if err:
        return []  # already surfaced by _check_universe_coverage

    stale: list[tuple[str, int]] = []
    for t in tickers:
        p = fno_dir / f"{t}.csv"
        if not p.exists():
            continue
        last_dt = _last_bar_date(p)
        if last_dt is None:
            continue
        age = (now.date() - last_dt.date()).days
        if age > TAIL_STALE_DAYS:
            stale.append((t, age))

    if not stale:
        return []
    stale.sort(key=lambda x: -x[1])
    sample = ", ".join(f"{t}({a}d)" for t, a in stale[:5])
    more = f" (+{len(stale) - 5} more)" if len(stale) > 5 else ""
    return [{
        "kind": "stale_tail",
        "detail": (
            f"{len(stale)} F&O csvs have last-bar age > {TAIL_STALE_DAYS}d: "
            f"{sample}{more}"
        ),
    }]


def _last_bar_date(csv_path: Path) -> datetime | None:
    """Read the last non-empty line of a Date,Open,High,Low,Close,Volume csv
    and parse the date column. Streaming-tail to avoid loading the whole
    file (cheap for ~250 daily bars but principled for the universe sweep)."""
    try:
        last_line = ""
        with csv_path.open(encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    last_line = line
        if not last_line:
            return None
        first_col = last_line.split(",", 1)[0].strip()
        return datetime.strptime(first_col, "%Y-%m-%d")
    except (OSError, ValueError):
        return None


def _check_marker_regressions(
    tickers: tuple, state_path: Path, now: datetime
) -> list[dict]:
    """Call narrative compute_narrative() directly, compare marker_count to
    the prior run's count from state_path. Regression = previously >0,
    now 0. First run for a ticker only seeds state, no alert."""
    try:
        from pipeline.terminal.api.ticker_narrative import compute_narrative
    except ImportError as e:
        return [{
            "kind": "marker_regression",
            "detail": f"narrative module import failed: {e}",
        }]

    state = _load_state(state_path)
    issues: list[dict] = []
    new_state: dict[str, Any] = dict(state)

    for ticker in tickers:
        try:
            doc = compute_narrative(ticker)
            count = int(doc.get("marker_count", 0))
        except Exception as e:
            logger.warning("compute_narrative failed for %s: %s", ticker, e)
            count = -1  # sentinel: callable error, not legitimate-zero

        prev = state.get(ticker, {}).get("marker_count")

        if count == -1:
            issues.append({
                "kind": "marker_regression",
                "detail": f"{ticker}: narrative compute raised an exception",
            })
        elif prev is not None and prev > 0 and count == 0:
            issues.append({
                "kind": "marker_regression",
                "detail": (
                    f"{ticker}: marker count {prev} -> 0 "
                    f"(narrative endpoint may be broken or data files removed)"
                ),
            })

        if count >= 0:  # only persist legitimate observations
            new_state[ticker] = {
                "marker_count": count,
                "last_check": now.isoformat(),
            }

    _save_state(new_state, state_path)
    return issues


def _load_state(state_path: Path) -> dict:
    if not state_path.exists():
        return {}
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_state(state: dict, state_path: Path) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = state_path.with_suffix(state_path.suffix + ".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    tmp.replace(state_path)


def _main(argv: list[str] | None = None) -> int:
    """CLI entry — `python -m pipeline.watchdog_chart_audit`.

    Used by the cloud-side companion routine (independent witness for the
    laptop-down case) so the audit can run from a stateless git checkout
    with one command. Local laptop runs go through pipeline.watchdog
    instead — this entry is the non-laptop path. Exit code 0 = healthy,
    1 = at least one issue, 2 = invocation error.
    """
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        prog="python -m pipeline.watchdog_chart_audit",
        description="Chart-v2 health audit (universe + freshness + markers).",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Emit findings as JSON to stdout instead of human-readable lines.",
    )
    args = parser.parse_args(argv)

    issues = audit_chart_universe()
    if args.json:
        print(json.dumps({
            "ok": not issues,
            "issue_count": len(issues),
            "issues": issues,
            "checked_at": datetime.now().isoformat(),
        }, indent=2))
    else:
        if not issues:
            print(f"[OK] chart audit clean — universe + freshness + markers all green "
                  f"({datetime.now():%Y-%m-%d %H:%M})")
        else:
            print(f"[FAIL] {len(issues)} issue(s) found:")
            for i in issues:
                print(f"  - {i['kind']}: {i['detail']}")
    return 0 if not issues else 1


if __name__ == "__main__":
    import sys
    sys.exit(_main())
