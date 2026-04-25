"""Peer-cohort builder for the H-2026-04-25-001 earnings-decoupling
hypothesis.

User-locked rule: peers = same broad sector + similar size bucket, frozen
ex-ante for the duration of the backtest. The freeze prevents in-sample
peer reselection (a common look-ahead bug) and is therefore committed to
the repo as a snapshot under
`pipeline/data/earnings_calendar/peers_frozen.json`.

This module is the builder; the frozen file is the canonical input the
backtest will consume. The builder is NOT re-run during backtest
evaluation."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping, Optional


def build_peer_cohorts(
    meta: Mapping[str, tuple[str, Optional[float]]],
    *,
    n_size_bucket_neighbours: int = 3,
    min_peers: int = 1,
) -> dict[str, list[str]]:
    """For each ticker, return the n nearest-by-market-cap peers within the
    same broad sector. Excludes self. Truncates if sector is small.

    Symbols whose market_cap is None are excluded from both sides — they
    cannot be peers (no comparable size) and cannot have peers (size
    bucket undefined). Per data validation policy §9.3 quarantine pattern.

    If a symbol's sector has fewer than ``min_peers`` other valid symbols,
    the symbol is omitted from the cohort map. Caller (freeze script /
    backtest) decides whether to label PARTIAL or drop.

    Inputs:
        meta: {symbol: (broad_sector, market_cap_in_consistent_unit_or_None)}
    """
    valid = {sym: (sec, cap) for sym, (sec, cap) in meta.items() if cap is not None}
    by_sector: dict[str, list[str]] = {}
    for sym, (sector, _cap) in valid.items():
        by_sector.setdefault(sector, []).append(sym)

    out: dict[str, list[str]] = {}
    for sym, (sector, cap) in valid.items():
        candidates = [s for s in by_sector[sector] if s != sym]
        if len(candidates) < min_peers:
            continue
        candidates.sort(key=lambda s: abs(valid[s][1] - cap))
        out[sym] = candidates[:n_size_bucket_neighbours]
    return out


def freeze_peers(
    meta: Mapping[str, tuple[str, Optional[float]]],
    path: Path | str,
    asof: str,
    *,
    n_size_bucket_neighbours: int = 3,
    min_peers: int = 1,
    lineage: Optional[dict] = None,
) -> Path:
    """Build cohorts and write them to disk as a frozen-as-of snapshot.

    The output is a JSON object with three keys: ``frozen_at`` (ISO date
    string), ``cohorts`` ({symbol: [peer1, peer2, peer3]}) and
    ``lineage`` (data sources + known caveats per data validation policy
    §7). This file is the canonical input for the backtest and is
    committed to the repository — re-freezing requires a new hypothesis
    version (data validation policy §11.3 point-in-time correctness)."""
    cohorts = build_peer_cohorts(
        meta,
        n_size_bucket_neighbours=n_size_bucket_neighbours,
        min_peers=min_peers,
    )
    payload = {"frozen_at": asof, "cohorts": cohorts}
    if lineage is not None:
        payload["lineage"] = lineage
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2))
    return p


def load_frozen_peers(path: Path | str) -> dict:
    return json.loads(Path(path).read_text())
