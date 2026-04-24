"""Per-regime BH-FDR batch trigger — runs daily at 05:00 IST.

Fires a BH-FDR batch for a regime whenever the v1 whichever-first rule
is satisfied: >=10 new pre-registered proposals since last batch OR
>=30 calendar days since last batch (whichever comes first).

Writes surviving rules to holdout_queue_{regime}.jsonl and marks their
hypothesis-registry state as HOLDOUT_QUEUED.

Called by AnkaAutoresearchBHFDR.bat.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from pipeline.autoresearch.regime_autoresearch.constants import (
    BH_FDR_BATCH_ACCUMULATED_COUNT, BH_FDR_BATCH_CALENDAR_DAYS,
    BH_FDR_Q, DATA_DIR, REGIMES,
)


BATCH_STATE_PATH = DATA_DIR / "bh_fdr_batch_state.json"


def _preg_path(regime: str) -> Path:
    slug = regime.lower().replace("-", "_")
    return DATA_DIR / f"pre_registered_{slug}.jsonl"


def _holdout_queue_path(regime: str) -> Path:
    slug = regime.lower().replace("-", "_")
    return DATA_DIR / f"holdout_queue_{slug}.jsonl"


def _load_batch_state() -> dict:
    if not BATCH_STATE_PATH.exists():
        return {r: {"last_batch_date": "1970-01-01T00:00:00+00:00",
                    "last_batch_count": 0}
                for r in REGIMES}
    return json.loads(BATCH_STATE_PATH.read_text())


def _save_batch_state(state: dict) -> None:
    BATCH_STATE_PATH.write_text(json.dumps(state, indent=2))


def _load_pre_registered_since(path: Path, since_iso: str) -> list[dict]:
    if not path.exists():
        return []
    since = datetime.fromisoformat(since_iso)
    rows = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        when = datetime.fromisoformat(
            row.get("pre_registered_at", "1970-01-01T00:00:00+00:00")
        )
        if when > since:
            rows.append(row)
    return rows


def should_fire_batch_for_regime(preg_path: Path, state: dict,
                                   now_iso: str) -> bool:
    """v1 whichever-first: >=10 new pre-reg OR >=30 days since last batch."""
    rows = _load_pre_registered_since(
        preg_path, state["last_batch_date"],
    )
    last = datetime.fromisoformat(state["last_batch_date"])
    now = datetime.fromisoformat(now_iso)
    days = (now - last).days
    return (
        len(rows) >= BH_FDR_BATCH_ACCUMULATED_COUNT
        or days >= BH_FDR_BATCH_CALENDAR_DAYS
    )


def _bh_fdr_survivors(rows: list[dict], q: float = BH_FDR_Q) -> list[dict]:
    if not rows:
        return []
    p = np.array([r["p_value"] for r in rows])
    m = len(p)
    order = np.argsort(p)
    sorted_p = p[order]
    thresh = q * (np.arange(1, m + 1) / m)
    passes = sorted_p <= thresh
    if not passes.any():
        return []
    k_star = int(np.where(passes)[0].max()) + 1
    surviving = order[:k_star].tolist()
    return [rows[i] for i in surviving]


def run_batch_for_regime(regime: str, state: dict,
                           now_iso: str) -> list[dict]:
    path = _preg_path(regime)
    rows = _load_pre_registered_since(path, state["last_batch_date"])
    survivors = _bh_fdr_survivors(rows)
    if survivors:
        qpath = _holdout_queue_path(regime)
        qpath.parent.mkdir(parents=True, exist_ok=True)
        with qpath.open("a") as f:
            for s in survivors:
                f.write(json.dumps(
                    {**s, "queued_at": now_iso,
                     "state": "HOLDOUT_QUEUED"}
                ) + "\n")
    state["last_batch_date"] = now_iso
    state["last_batch_count"] = len(rows)
    return survivors


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--now", default=None,
                    help="ISO datetime to use as 'now' (default: utcnow)")
    ap.add_argument("--regime", choices=REGIMES, default=None)
    args = ap.parse_args(argv)

    now_iso = args.now or datetime.now(timezone.utc).isoformat()
    state = _load_batch_state()
    regimes = [args.regime] if args.regime else list(REGIMES)
    summary: dict[str, dict] = {}
    for r in regimes:
        if should_fire_batch_for_regime(
            _preg_path(r), state[r], now_iso,
        ):
            survivors = run_batch_for_regime(r, state[r], now_iso)
            summary[r] = {"fired": True, "n_survivors": len(survivors)}
            print(f"[bh_fdr] {r}: fired batch, {len(survivors)} survivors")
        else:
            summary[r] = {"fired": False, "n_survivors": 0}
            print(f"[bh_fdr] {r}: not ready")
    _save_batch_state(state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
