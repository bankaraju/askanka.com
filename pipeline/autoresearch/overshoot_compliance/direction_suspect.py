"""DIRECTION-SUSPECT classifier (spec §5).

Reads LAG and OVERSHOOT slice compliance artifacts (permutations_100k.json)
and emits per-(ticker, direction) verdicts:

  CLEAN                     — LAG FOLLOW clears Bonferroni, OR neither slice clears.
  DIRECTION_SUSPECT         — OVERSHOOT FADE clears Bonferroni but LAG FOLLOW does not.
                              Live engine is trading the wrong side.
  PARAMETER_FRAGILE_DIRECTION — Both slices clear Bonferroni. Edge under multiple theses.
  INSUFFICIENT_POWER        — Either slice had n_events < 10.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

_MIN_EVENTS = 10


@dataclass
class CellResult:
    ticker: str
    direction: str
    slice_name: str
    n_events: int
    bonferroni_pass: bool
    edge_net_pct: float | None
    p_value: float | None


def load_cells(
    permutations_path: Path,
    slice_name: str,
    bonferroni_alpha: float,
) -> Iterator[CellResult]:
    """Yield CellResult objects from a permutations_100k.json artifact."""
    blob = json.loads(Path(permutations_path).read_text(encoding="utf-8"))
    for row in blob.get("rows", []):
        edge = row.get("edge_net_pct")
        p = row.get("p_value")
        passes = (
            edge is not None
            and p is not None
            and edge > 0
            and p <= bonferroni_alpha
        )
        yield CellResult(
            ticker=row["ticker"],
            direction=row["direction"],
            slice_name=slice_name,
            n_events=row.get("n_events", 0),
            bonferroni_pass=bool(passes),
            edge_net_pct=edge,
            p_value=p,
        )


def _bonferroni_alpha_from_manifest(manifest_path: Path) -> float:
    """Derive Bonferroni-corrected alpha from manifest.json config."""
    m = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    family_size = int(m.get("config", {}).get("family_size", 1))
    return 0.05 / max(1, family_size)


def classify_direction_verdict(lag: CellResult, overshoot: CellResult) -> str:
    """Classify a paired (lag, overshoot) result into one of four verdicts.

    Decision priority:
      1. INSUFFICIENT_POWER  if either slice n_events < 10
      2. PARAMETER_FRAGILE_DIRECTION  if both pass Bonferroni
      3. DIRECTION_SUSPECT   if overshoot passes but lag does not
      4. CLEAN               otherwise (lag passes alone, or neither passes)
    """
    if lag.ticker != overshoot.ticker or lag.direction != overshoot.direction:
        raise ValueError(
            f"Paired results must share (ticker, direction); got "
            f"{(lag.ticker, lag.direction)} vs {(overshoot.ticker, overshoot.direction)}"
        )
    if lag.n_events < _MIN_EVENTS or overshoot.n_events < _MIN_EVENTS:
        return "INSUFFICIENT_POWER"
    if lag.bonferroni_pass and overshoot.bonferroni_pass:
        return "PARAMETER_FRAGILE_DIRECTION"
    if overshoot.bonferroni_pass and not lag.bonferroni_pass:
        return "DIRECTION_SUSPECT"
    return "CLEAN"


def classify_all_cells(
    lag_artifact_path: Path,
    lag_manifest_path: Path,
    overshoot_artifact_path: Path,
    overshoot_manifest_path: Path,
    output_path: Path,
) -> dict:
    """Run the classifier over all (ticker, direction) pairs and write verdicts.json."""
    lag_alpha = _bonferroni_alpha_from_manifest(lag_manifest_path)
    ovs_alpha = _bonferroni_alpha_from_manifest(overshoot_manifest_path)

    lag_cells = list(load_cells(lag_artifact_path, "LAG", lag_alpha))
    ovs_cells = list(load_cells(overshoot_artifact_path, "OVERSHOOT", ovs_alpha))

    lag_by_key = {(c.ticker, c.direction): c for c in lag_cells}
    ovs_by_key = {(c.ticker, c.direction): c for c in ovs_cells}
    all_keys = sorted(set(lag_by_key) | set(ovs_by_key))

    verdicts = []
    for key in all_keys:
        lag = lag_by_key.get(key) or _empty_cell(key, "LAG")
        ovs = ovs_by_key.get(key) or _empty_cell(key, "OVERSHOOT")
        verdicts.append({
            "ticker": key[0],
            "direction": key[1],
            "verdict": classify_direction_verdict(lag, ovs),
            "lag": _cell_as_dict(lag),
            "overshoot": _cell_as_dict(ovs),
        })

    output = {
        "verdicts": verdicts,
        "summary": _summarize(verdicts),
        "meta": {
            "lag_bonferroni_alpha": lag_alpha,
            "overshoot_bonferroni_alpha": ovs_alpha,
        },
    }
    Path(output_path).write_text(json.dumps(output, indent=2), encoding="utf-8")
    return output


def _empty_cell(key: tuple[str, str], slice_name: str) -> CellResult:
    return CellResult(
        ticker=key[0],
        direction=key[1],
        slice_name=slice_name,
        n_events=0,
        bonferroni_pass=False,
        edge_net_pct=None,
        p_value=None,
    )


def _cell_as_dict(c: CellResult) -> dict:
    return {
        "n_events": c.n_events,
        "bonferroni_pass": c.bonferroni_pass,
        "edge_net_pct": c.edge_net_pct,
        "p_value": c.p_value,
    }


def _summarize(verdicts: list[dict]) -> dict:
    counts: dict[str, int] = {}
    for v in verdicts:
        counts[v["verdict"]] = counts.get(v["verdict"], 0) + 1
    return {"verdict_counts": counts, "n_cells": len(verdicts)}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="DIRECTION-SUSPECT classifier (spec §5). "
                    "Reads LAG + OVERSHOOT compliance artifacts and emits verdicts.json."
    )
    p.add_argument("--lag-artifact", required=True, type=Path,
                   help="Path to LAG slice permutations_100k.json")
    p.add_argument("--lag-manifest", required=True, type=Path,
                   help="Path to LAG slice manifest.json")
    p.add_argument("--overshoot-artifact", required=True, type=Path,
                   help="Path to OVERSHOOT slice permutations_100k.json")
    p.add_argument("--overshoot-manifest", required=True, type=Path,
                   help="Path to OVERSHOOT slice manifest.json")
    p.add_argument("--output", required=True, type=Path,
                   help="Output path for verdicts.json")
    args = p.parse_args(argv)

    out = classify_all_cells(
        lag_artifact_path=args.lag_artifact,
        lag_manifest_path=args.lag_manifest,
        overshoot_artifact_path=args.overshoot_artifact,
        overshoot_manifest_path=args.overshoot_manifest,
        output_path=args.output,
    )
    print(json.dumps(out["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
