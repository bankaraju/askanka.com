"""Task 9 — incumbent re-qualification audit (read-only).

For every (strategy_id, regime) cell in strategy_results_10.json this script
classifies the cell as one of four verdicts:

  BACKED_BY_ARTEFACT         — a current compliance artefact exists that
                               backs this cell (post-cutoff, correct regime or
                               explicit cross-regime manifest flag)
  CORRECTLY_INSUFFICIENT_POWER — row says INSUFFICIENT_POWER AND no artefact
                               exists; acceptable placeholder
  SHOULD_HAVE_BEEN_RUN       — row claims a Sharpe number but no backing
                               artefact OR row says INSUFFICIENT_POWER while a
                               current artefact exists that could refresh it
  STALE                      — backing artefact exists but predates the
                               cutoff date (CUTOFF_DATE constant below)

It WRITES two artefacts:
  pipeline/autoresearch/regime_autoresearch/data/incumbent_audit_2026-04-24.json
  pipeline/autoresearch/regime_autoresearch/data/incumbent_audit_2026-04-24.md

It DOES NOT mutate strategy_results_10.json. Issues surface as follow-up
tasks, not in-place mutations.
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pipeline.autoresearch.regime_autoresearch.constants import DATA_DIR, REGIMES, REPO_ROOT

TABLE_PATH = DATA_DIR / "strategy_results_10.json"
RESULTS_DIR = REPO_ROOT / "pipeline" / "autoresearch" / "results"

# Artefacts older than this date are considered STALE (framework moved on
# 2026-04-23 with the current slippage_grid / cost_model / regime_history).
CUTOFF_DATE_ISO = "2026-04-23"

OUT_JSON = DATA_DIR / "incumbent_audit_2026-04-24.json"
OUT_MD = DATA_DIR / "incumbent_audit_2026-04-24.md"


def _git_head_sha() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, stderr=subprocess.DEVNULL,
        )
        return out.decode().strip()
    except Exception:
        return "unknown"


def _cutoff_epoch() -> float:
    return datetime.fromisoformat(CUTOFF_DATE_ISO + "T00:00:00+00:00").timestamp()


def _find_artefact_for_strategy(strategy_id: str, results_dir: Path) -> Path | None:
    """Return the newest compliance dir whose name contains strategy_id.

    Also matches on known strategy-id-to-directory-slug aliases so that e.g.
    PHASE_C_LAG maps to compliance_phase_c_lag_*.
    """
    if not results_dir.exists():
        return None

    aliases: list[str] = [strategy_id.lower()]
    # Known aliases — compliance artefact dirs were named before the
    # strategy_results_10 registry existed, so they use slug form not
    # CAPS_WITH_UNDERSCORE.
    slug_aliases = {
        "PHASE_C_LAG": ["phase_c_lag"],
        "PHASE_C_OVERSHOOT": ["phase_c_overshoot"],
    }
    for alias in slug_aliases.get(strategy_id, []):
        aliases.append(alias)

    candidates: list[Path] = []
    for child in results_dir.iterdir():
        if not child.is_dir():
            continue
        name_lower = child.name.lower()
        if any(a in name_lower for a in aliases):
            candidates.append(child)

    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def _artefact_mtime_iso(path: Path) -> str:
    ts = path.stat().st_mtime
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _artefact_path_str(artefact: Path) -> str:
    """Return repo-relative path if artefact is under REPO_ROOT, else absolute."""
    try:
        return str(artefact.relative_to(REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return str(artefact).replace("\\", "/")


def _classify_cell(
    row_cell: dict,
    artefact_path: Path | None,
    cutoff_epoch: float,
) -> str:
    """Return the verdict for a single (strategy, regime) cell."""
    status_flag = row_cell.get("status_flag")
    claims_sharpe = row_cell.get("sharpe_point") is not None

    if artefact_path is None:
        if status_flag == "INSUFFICIENT_POWER" and not claims_sharpe:
            return "CORRECTLY_INSUFFICIENT_POWER"
        # Row claims a Sharpe but no artefact backs it.
        return "SHOULD_HAVE_BEEN_RUN"

    # Artefact exists.
    if artefact_path.stat().st_mtime < cutoff_epoch:
        return "STALE"

    if status_flag == "INSUFFICIENT_POWER":
        # We have a current artefact but the cell has not been refreshed.
        return "SHOULD_HAVE_BEEN_RUN"
    return "BACKED_BY_ARTEFACT"


def _priority(per_regime_verdict: dict[str, str]) -> str:
    verdicts = set(per_regime_verdict.values())
    if "SHOULD_HAVE_BEEN_RUN" in verdicts or "STALE" in verdicts:
        return "HIGH"
    if verdicts == {"BACKED_BY_ARTEFACT"}:
        return "NONE"
    if verdicts == {"CORRECTLY_INSUFFICIENT_POWER"}:
        return "NONE"
    return "MEDIUM"


def _notes(strategy_id: str, per_regime_verdict: dict[str, str],
           artefact_path: Path | None) -> str:
    bits: list[str] = []
    should_run = [r for r, v in per_regime_verdict.items() if v == "SHOULD_HAVE_BEEN_RUN"]
    stale = [r for r, v in per_regime_verdict.items() if v == "STALE"]
    if should_run:
        if artefact_path is None:
            bits.append(f"no compliance artefact on disk for {strategy_id}; "
                        f"regimes {sorted(should_run)} need first-time run")
        else:
            bits.append(f"artefact {artefact_path.name} exists but "
                        f"strategy_results_10 cells for {sorted(should_run)} "
                        f"were not refreshed")
    if stale:
        bits.append(f"artefact {artefact_path.name if artefact_path else '?'} "
                    f"predates {CUTOFF_DATE_ISO} framework cutoff "
                    f"(regimes {sorted(stale)})")
    if not bits:
        bits.append("placeholder accepted; retest when per-regime data available")
    return "; ".join(bits)


def audit(
    table_path: Path = TABLE_PATH,
    results_dir: Path = RESULTS_DIR,
    cutoff_date_iso: str = CUTOFF_DATE_ISO,
) -> dict[str, Any]:
    table = json.loads(table_path.read_text(encoding="utf-8"))
    cutoff_epoch = datetime.fromisoformat(
        cutoff_date_iso + "T00:00:00+00:00"
    ).timestamp()

    per_strategy: list[dict[str, Any]] = []
    counts = {"cells_backed": 0, "cells_correctly_insufficient": 0,
              "cells_should_have_been_run": 0, "cells_stale": 0}

    for inc in table.get("incumbents", []):
        sid = inc["strategy_id"]
        artefact = _find_artefact_for_strategy(sid, results_dir)
        per_regime_verdict: dict[str, str] = {}
        for regime in REGIMES:
            cell = inc.get("per_regime", {}).get(regime, {})
            verdict = _classify_cell(cell, artefact, cutoff_epoch)
            per_regime_verdict[regime] = verdict
            if verdict == "BACKED_BY_ARTEFACT":
                counts["cells_backed"] += 1
            elif verdict == "CORRECTLY_INSUFFICIENT_POWER":
                counts["cells_correctly_insufficient"] += 1
            elif verdict == "SHOULD_HAVE_BEEN_RUN":
                counts["cells_should_have_been_run"] += 1
            elif verdict == "STALE":
                counts["cells_stale"] += 1
        per_strategy.append({
            "strategy_id": sid,
            "strategy_name": inc.get("strategy_name"),
            "status": inc.get("status"),
            "per_regime_verdict": per_regime_verdict,
            "backing_artefact_path": (
                _artefact_path_str(artefact) if artefact is not None else None
            ),
            "artefact_mtime_iso": _artefact_mtime_iso(artefact) if artefact else None,
            "re_qualification_priority": _priority(per_regime_verdict),
            "notes": _notes(sid, per_regime_verdict, artefact),
        })

    report = {
        "audit_timestamp_iso": datetime.now(timezone.utc).isoformat(),
        "audit_commit_sha": _git_head_sha(),
        "cutoff_date_iso": cutoff_date_iso,
        "per_strategy": per_strategy,
        "summary": {
            "total_rows": len(per_strategy),
            "total_cells": len(per_strategy) * len(REGIMES),
            **counts,
        },
    }
    return report


def _write_md(report: dict[str, Any], out_md: Path) -> None:
    lines: list[str] = []
    summ = report["summary"]
    lines.append("# Incumbent re-qualification audit — 2026-04-24")
    lines.append("")
    lines.append(f"- Audit timestamp: `{report['audit_timestamp_iso']}`")
    lines.append(f"- Audit commit: `{report['audit_commit_sha']}`")
    lines.append(f"- Framework cutoff: `{report['cutoff_date_iso']}`")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Rows: {summ['total_rows']}")
    lines.append(f"- Cells: {summ['total_cells']} (rows x 5 regimes)")
    lines.append(f"- BACKED_BY_ARTEFACT: {summ['cells_backed']}")
    lines.append(f"- CORRECTLY_INSUFFICIENT_POWER: {summ['cells_correctly_insufficient']}")
    lines.append(f"- SHOULD_HAVE_BEEN_RUN: {summ['cells_should_have_been_run']}")
    lines.append(f"- STALE: {summ['cells_stale']}")
    lines.append("")
    lines.append("## Per-strategy verdicts")
    lines.append("")
    lines.append("| Strategy | Status | Priority | Backing artefact | Notes |")
    lines.append("|---|---|---|---|---|")
    for row in report["per_strategy"]:
        art = row["backing_artefact_path"] or "-"
        lines.append(
            f"| `{row['strategy_id']}` | {row['status']} "
            f"| {row['re_qualification_priority']} | `{art}` | {row['notes']} |"
        )
    lines.append("")
    lines.append("## HIGH-priority re-qualification queue")
    lines.append("")
    high = [r for r in report["per_strategy"]
            if r["re_qualification_priority"] == "HIGH"]
    if not high:
        lines.append("_No HIGH-priority items — all incumbents either backed or "
                     "correctly flagged INSUFFICIENT_POWER._")
    else:
        for r in high:
            lines.append(f"### `{r['strategy_id']}` — {r['strategy_name']}")
            lines.append("")
            needs = [rg for rg, v in r["per_regime_verdict"].items()
                     if v in ("SHOULD_HAVE_BEEN_RUN", "STALE")]
            lines.append(f"- Regimes needing re-run: {sorted(needs)}")
            lines.append(f"- Current backing artefact: "
                         f"`{r['backing_artefact_path'] or 'none'}`")
            lines.append(f"- Notes: {r['notes']}")
            lines.append("- Compute pointer: see `docs/superpowers/plans/"
                         "2026-04-24-regime-aware-autoresearch.md` §"
                         "\"Incumbent re-qualification runbook\" (follow-up task).")
            lines.append("")
    lines.append("## Recommended follow-up tasks")
    lines.append("")
    lines.append(
        "- Open one re-qualification task per HIGH-priority strategy. Each task runs the "
        "relevant compliance runner with regime stratification and then wires the cell update "
        "back into `strategy_results_10.json` via a separate, explicit step (not this audit)."
    )
    lines.append(
        "- If no HIGH items exist, the current scarcity fallback (buy-and-hold benchmark in "
        "`hurdle_sharpe_for_regime`) is load-bearing and should remain in force until incumbents "
        "are re-qualified."
    )
    out_md.write_text("\n".join(lines), encoding="utf-8")


def _print_summary(report: dict[str, Any]) -> None:
    s = report["summary"]
    print("Incumbent audit summary")
    print("-" * 72)
    print(f"total rows                      : {s['total_rows']}")
    print(f"total cells (rows * 5 regimes)  : {s['total_cells']}")
    print(f"BACKED_BY_ARTEFACT              : {s['cells_backed']}")
    print(f"CORRECTLY_INSUFFICIENT_POWER    : {s['cells_correctly_insufficient']}")
    print(f"SHOULD_HAVE_BEEN_RUN            : {s['cells_should_have_been_run']}")
    print(f"STALE                           : {s['cells_stale']}")
    print("-" * 72)
    print(f"{'strategy_id':<24} {'priority':<8} backing_artefact")
    for row in report["per_strategy"]:
        art = row["backing_artefact_path"] or "-"
        print(f"{row['strategy_id']:<24} {row['re_qualification_priority']:<8} {art}")


def main() -> int:
    report = audit()
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(
        json.dumps(report, indent=2, sort_keys=True), encoding="utf-8",
    )
    _write_md(report, OUT_MD)
    _print_summary(report)
    print(f"\nwrote {OUT_JSON.relative_to(REPO_ROOT)}")
    print(f"wrote {OUT_MD.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
