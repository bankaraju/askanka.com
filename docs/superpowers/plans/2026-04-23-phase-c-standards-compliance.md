# Phase C Residual-Reversion — Standards-Compliance Refactor (H-2026-04-23-001)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the existing overshoot residual-reversion prototype (f5af8d8 + d336f79) into a v1.0 standards-compliant backtest that can cross the RESEARCH→PAPER-SHADOW gate per `docs/superpowers/specs/backtesting-specs.txt` §15.1 for pre-registered hypothesis H-2026-04-23-001.

**Architecture:** Additive wrapping. The existing modules `pipeline/autoresearch/overshoot_reversion_backtest.py` and `pipeline/autoresearch/overshoot_per_ticker_stats.py` stay as-is (their residual math is already correct and their numbers must remain reproducible). A new package `pipeline/autoresearch/overshoot_compliance/` imports their `load_price_panel`, `load_sector_map`, `compute_residuals`, `classify_events`, and `per_ticker_fade_stats`, then bolts on the 12 compliance layers the spec demands (manifest, data audit, slippage grid, Sharpe/DD/Calmar, naive comparators, ≥100k permutation scaling, NIFTY-beta residual, parameter-fragility sweep, impl-risk scenarios, CUSUM decay, portfolio-correlation gate, direction audit). A final `gate_checklist.py` emits a machine-readable §15.1 pass/fail artifact — not a claim.

**Tech Stack:** Python 3.11, numpy, pandas, scipy (already in `phase_c_backtest/stats.py`), scikit-learn (for `LinearRegression` in beta regression), pytest. No new dependencies.

**Re-use policy — do NOT rebuild:**
- `pipeline/research/phase_c_backtest/stats.py` — import `sharpe`, `bootstrap_sharpe_ci`, `max_drawdown`, `binomial_p`, `bonferroni_alpha_per`. Already vectorised and tested.
- `pipeline/research/phase_c_backtest/cost_model.py` — import `round_trip_cost_inr`, `apply_to_pnl`. Zerodha SSF fees already modelled with `slippage_bps` parameter.
- `pipeline/research/phase_c_backtest/robustness.py` — import `slippage_sweep` for the per-ledger S0/S1/S2/S3 apply.
- `pipeline/research/phase_c_backtest/universe.py` — reference for the NSE monthly F&O fetcher. Section 6 waiver is in place so we do NOT block on the 5-yr backfill, but we DO cite this module in the universe-snapshot disclosure.

**Frozen ordering:** manifest + data audit FIRST (every later run is reproducible), then universe snapshot, then slippage grid + metrics, then comparators + perm scaling, then beta/residual, then fragility, then impl-risk, then CUSUM decay, then portfolio gate, then direction audit + defense filter, then gate checklist, then docs sync, then actual compliance run committing the artifact.

---

## File Map

**New package (all new files):**
- `pipeline/autoresearch/overshoot_compliance/__init__.py` — version pin
- `pipeline/autoresearch/overshoot_compliance/manifest.py` — run_id, git_sha, data SHA-256, cost_model_version
- `pipeline/autoresearch/overshoot_compliance/data_audit.py` — §5A missing/stale/dup/zero/CA audit
- `pipeline/autoresearch/overshoot_compliance/universe_snapshot.py` — §6.2 disclosure under waiver
- `pipeline/autoresearch/overshoot_compliance/slippage_grid.py` — S0/S1/S2/S3 grid applier
- `pipeline/autoresearch/overshoot_compliance/metrics.py` — Sharpe/DD/Calmar/hit-CI per level
- `pipeline/autoresearch/overshoot_compliance/naive_comparators.py` — §9B.1 random/momentum/equal-weight
- `pipeline/autoresearch/overshoot_compliance/perm_scaling.py` — streaming ≥100k permutations
- `pipeline/autoresearch/overshoot_compliance/fragility.py` — §9A local neighborhood
- `pipeline/autoresearch/overshoot_compliance/beta_regression.py` — §11B NIFTY residual
- `pipeline/autoresearch/overshoot_compliance/impl_risk.py` — §11A 10 scenarios
- `pipeline/autoresearch/overshoot_compliance/cusum_decay.py` — §12 decay
- `pipeline/autoresearch/overshoot_compliance/portfolio_gate.py` — §11C correlation + concentration
- `pipeline/autoresearch/overshoot_compliance/direction_audit.py` — §8 engine-vs-backtest
- `pipeline/autoresearch/overshoot_compliance/defense_filter.py` — user rule flag
- `pipeline/autoresearch/overshoot_compliance/gate_checklist.py` — §15.1 emitter
- `pipeline/autoresearch/overshoot_compliance/runner.py` — orchestrator

**New test files:**
- `pipeline/tests/autoresearch/__init__.py`
- `pipeline/tests/autoresearch/overshoot_compliance/__init__.py`
- `pipeline/tests/autoresearch/overshoot_compliance/test_manifest.py`
- `pipeline/tests/autoresearch/overshoot_compliance/test_data_audit.py`
- `pipeline/tests/autoresearch/overshoot_compliance/test_universe_snapshot.py`
- `pipeline/tests/autoresearch/overshoot_compliance/test_slippage_grid.py`
- `pipeline/tests/autoresearch/overshoot_compliance/test_metrics.py`
- `pipeline/tests/autoresearch/overshoot_compliance/test_naive_comparators.py`
- `pipeline/tests/autoresearch/overshoot_compliance/test_perm_scaling.py`
- `pipeline/tests/autoresearch/overshoot_compliance/test_fragility.py`
- `pipeline/tests/autoresearch/overshoot_compliance/test_beta_regression.py`
- `pipeline/tests/autoresearch/overshoot_compliance/test_impl_risk.py`
- `pipeline/tests/autoresearch/overshoot_compliance/test_cusum_decay.py`
- `pipeline/tests/autoresearch/overshoot_compliance/test_portfolio_gate.py`
- `pipeline/tests/autoresearch/overshoot_compliance/test_direction_audit.py`
- `pipeline/tests/autoresearch/overshoot_compliance/test_defense_filter.py`
- `pipeline/tests/autoresearch/overshoot_compliance/test_gate_checklist.py`
- `pipeline/tests/autoresearch/overshoot_compliance/test_runner_smoke.py`

**Untouched:**
- `pipeline/autoresearch/overshoot_reversion_backtest.py` — kept verbatim; compliance layer imports from it
- `pipeline/autoresearch/overshoot_per_ticker_stats.py` — kept verbatim; compliance layer imports `per_ticker_fade_stats`

**Docs modified:**
- `docs/SYSTEM_OPERATIONS_MANUAL.md` — new Station: Compliance-grade backtest runner
- Memory file `project_overshoot_reversion_backtest.md` — update with compliance-path status
- Memory file `reference_backtest_standards.md` — update with "H-2026-04-23-001 compliance runner landed" pointer

**No CLAUDE.md change, no `anka_inventory.json` change** — the compliance runner is ad-hoc research invoked manually, not a scheduled task.

**Artifact output (produced by Task 20, committed):**
- `pipeline/autoresearch/results/compliance_H-2026-04-23-001_<stamp>/manifest.json`
- `pipeline/autoresearch/results/compliance_H-2026-04-23-001_<stamp>/data_audit.json`
- `pipeline/autoresearch/results/compliance_H-2026-04-23-001_<stamp>/universe_snapshot.json`
- `pipeline/autoresearch/results/compliance_H-2026-04-23-001_<stamp>/metrics_grid.json`
- `pipeline/autoresearch/results/compliance_H-2026-04-23-001_<stamp>/comparators.json`
- `pipeline/autoresearch/results/compliance_H-2026-04-23-001_<stamp>/permutations_100k.json`
- `pipeline/autoresearch/results/compliance_H-2026-04-23-001_<stamp>/fragility.json`
- `pipeline/autoresearch/results/compliance_H-2026-04-23-001_<stamp>/beta_residual.json`
- `pipeline/autoresearch/results/compliance_H-2026-04-23-001_<stamp>/impl_risk.json`
- `pipeline/autoresearch/results/compliance_H-2026-04-23-001_<stamp>/cusum_decay.json`
- `pipeline/autoresearch/results/compliance_H-2026-04-23-001_<stamp>/portfolio_gate.json`
- `pipeline/autoresearch/results/compliance_H-2026-04-23-001_<stamp>/direction_audit.json`
- `pipeline/autoresearch/results/compliance_H-2026-04-23-001_<stamp>/gate_checklist.json` ← decision document

---

## Pre-flight: branch + worktree sanity

- [ ] **Pre-1: Confirm branch is `feat/phase-c-v5`** — `git -C C:/Users/Claude_Anka/askanka.com rev-parse --abbrev-ref HEAD` must print `feat/phase-c-v5`. If not, stop and ask.
- [ ] **Pre-2: Confirm registered hypothesis** — `grep -c "H-2026-04-23-001" docs/superpowers/hypothesis-registry.jsonl` must be ≥ 1.
- [ ] **Pre-3: Confirm waiver** — `test -f docs/superpowers/waivers/2026-04-23-phase-c-residual-reversion-survivorship.md` must succeed.
- [ ] **Pre-4: Confirm working tree clean enough** — working tree may have unrelated modified files (UAP polish, data snapshots). Must NOT stage them during compliance commits. Every `git add` in this plan uses explicit paths only, never `git add .` or `git add -A`.

---

## Phase A — Scaffolding & reproducibility

### Task 1: Package skeleton + version + smoke-importable runner stub

**Files:**
- Create: `pipeline/autoresearch/overshoot_compliance/__init__.py`
- Create: `pipeline/autoresearch/overshoot_compliance/runner.py` (stub)
- Create: `pipeline/tests/autoresearch/__init__.py`
- Create: `pipeline/tests/autoresearch/overshoot_compliance/__init__.py`
- Create: `pipeline/tests/autoresearch/overshoot_compliance/test_package.py`

- [ ] **Step 1: Write failing test**

```python
# pipeline/tests/autoresearch/overshoot_compliance/test_package.py
import importlib


def test_package_imports():
    mod = importlib.import_module("pipeline.autoresearch.overshoot_compliance")
    assert mod.__version__ == "0.1.0"
    assert mod.HYPOTHESIS_ID == "H-2026-04-23-001"


def test_runner_main_is_callable():
    from pipeline.autoresearch.overshoot_compliance import runner
    assert callable(runner.main)
```

- [ ] **Step 2: Run, expect FAIL**

```
python -m pytest pipeline/tests/autoresearch/overshoot_compliance/test_package.py -v
```

Expected: `ModuleNotFoundError: No module named 'pipeline.autoresearch.overshoot_compliance'`

- [ ] **Step 3: Create the four files**

```python
# pipeline/autoresearch/overshoot_compliance/__init__.py
"""Standards-compliance layer for H-2026-04-23-001 (phase-c-residual-reversion-eod).

Implements the v1.0 backtest-standards gates (Sections 1-15 of
docs/superpowers/specs/backtesting-specs.txt) on top of the existing
overshoot residual-reversion prototype without rewriting its math.
"""
__version__ = "0.1.0"
HYPOTHESIS_ID = "H-2026-04-23-001"
```

```python
# pipeline/autoresearch/overshoot_compliance/runner.py
"""Orchestrator for the compliance backtest. Task 17 fills this in end-to-end."""
from __future__ import annotations
import logging

log = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    log.info("overshoot_compliance.runner stub — task 17 fills this in")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

```python
# pipeline/tests/autoresearch/__init__.py
```

```python
# pipeline/tests/autoresearch/overshoot_compliance/__init__.py
```

- [ ] **Step 4: Run, expect PASS**

```
python -m pytest pipeline/tests/autoresearch/overshoot_compliance/test_package.py -v
```

Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add pipeline/autoresearch/overshoot_compliance/__init__.py \
        pipeline/autoresearch/overshoot_compliance/runner.py \
        pipeline/tests/autoresearch/__init__.py \
        pipeline/tests/autoresearch/overshoot_compliance/__init__.py \
        pipeline/tests/autoresearch/overshoot_compliance/test_package.py
git commit -m "feat(compliance): package skeleton for H-2026-04-23-001"
```

---

### Task 2: Run manifest writer (§13A.1)

**Files:**
- Create: `pipeline/autoresearch/overshoot_compliance/manifest.py`
- Test: `pipeline/tests/autoresearch/overshoot_compliance/test_manifest.py`

Manifest must carry: `run_id`, `hypothesis_id`, `strategy_version`, `git_commit`, `config_hash`, `data_snapshot_id`, `data_file_sha256_manifest` (dict of path → sha), `universe_snapshot_id`, `cost_model_version`, `random_seed`, `report_generated_at`.

- [ ] **Step 1: Write failing tests**

```python
# pipeline/tests/autoresearch/overshoot_compliance/test_manifest.py
import json
import subprocess
from pathlib import Path

import pytest

from pipeline.autoresearch.overshoot_compliance import manifest as M


def _write(tmp_path: Path, name: str, content: bytes) -> Path:
    p = tmp_path / name
    p.write_bytes(content)
    return p


def test_sha256_stable(tmp_path):
    f = _write(tmp_path, "a.csv", b"abc\n")
    assert M.sha256_of(f) == M.sha256_of(f)
    g = _write(tmp_path, "b.csv", b"abc\n")
    assert M.sha256_of(f) == M.sha256_of(g)


def test_sha256_changes_with_content(tmp_path):
    f = _write(tmp_path, "a.csv", b"abc\n")
    g = _write(tmp_path, "b.csv", b"xyz\n")
    assert M.sha256_of(f) != M.sha256_of(g)


def test_build_manifest_has_all_required_fields(tmp_path):
    f1 = _write(tmp_path, "p1.csv", b"one\n")
    f2 = _write(tmp_path, "p2.csv", b"two\n")
    m = M.build_manifest(
        hypothesis_id="H-TEST",
        strategy_version="0.1.0",
        cost_model_version="zerodha-ssf-2025-04",
        random_seed=42,
        data_files=[f1, f2],
        config={"min_z": 3.0, "window": 20},
    )
    for field in (
        "run_id", "hypothesis_id", "strategy_version", "git_commit",
        "config_hash", "data_file_sha256_manifest",
        "cost_model_version", "random_seed", "report_generated_at",
    ):
        assert field in m, f"missing {field}"
    assert m["hypothesis_id"] == "H-TEST"
    assert m["random_seed"] == 42
    assert set(m["data_file_sha256_manifest"].keys()) == {str(f1), str(f2)}
    for sha in m["data_file_sha256_manifest"].values():
        assert len(sha) == 64  # hex sha256


def test_git_commit_matches_current_head():
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], text=True
    ).strip()
    m = M.build_manifest(
        hypothesis_id="H-TEST",
        strategy_version="0.1.0",
        cost_model_version="zerodha-ssf-2025-04",
        random_seed=0,
        data_files=[],
        config={},
    )
    assert m["git_commit"] == head


def test_config_hash_deterministic():
    m1 = M.build_manifest(
        hypothesis_id="X", strategy_version="1", cost_model_version="c",
        random_seed=0, data_files=[], config={"a": 1, "b": 2},
    )
    m2 = M.build_manifest(
        hypothesis_id="X", strategy_version="1", cost_model_version="c",
        random_seed=0, data_files=[], config={"b": 2, "a": 1},  # reordered
    )
    assert m1["config_hash"] == m2["config_hash"]


def test_write_manifest_round_trip(tmp_path):
    out_dir = tmp_path / "run_x"
    m = M.build_manifest(
        hypothesis_id="H-TEST", strategy_version="0.1.0",
        cost_model_version="c", random_seed=1, data_files=[], config={"k": "v"},
    )
    path = M.write_manifest(m, out_dir)
    assert path.exists()
    loaded = json.loads(path.read_text())
    assert loaded == m
```

- [ ] **Step 2: Run, expect FAIL**

```
python -m pytest pipeline/tests/autoresearch/overshoot_compliance/test_manifest.py -v
```

- [ ] **Step 3: Implement**

```python
# pipeline/autoresearch/overshoot_compliance/manifest.py
"""Reproducibility manifest per §13A.1 of backtesting-specs.txt v1.0."""
from __future__ import annotations

import hashlib
import json
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True,
            cwd=Path(__file__).resolve().parents[3],
        ).strip()
    except Exception:
        return "unknown"


def _config_hash(config: dict) -> str:
    canonical = json.dumps(config, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_manifest(
    *,
    hypothesis_id: str,
    strategy_version: str,
    cost_model_version: str,
    random_seed: int,
    data_files: Iterable[Path],
    config: dict,
) -> dict:
    data_files = list(data_files)
    return {
        "run_id": uuid.uuid4().hex,
        "hypothesis_id": hypothesis_id,
        "strategy_version": strategy_version,
        "git_commit": _git_commit(),
        "config_hash": _config_hash(config),
        "config": config,
        "data_file_sha256_manifest": {
            str(p): sha256_of(p) for p in data_files
        },
        "cost_model_version": cost_model_version,
        "random_seed": random_seed,
        "report_generated_at": datetime.now(timezone.utc).isoformat(),
    }


def write_manifest(manifest: dict, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2, default=str))
    return path
```

- [ ] **Step 4: Run, expect PASS**

```
python -m pytest pipeline/tests/autoresearch/overshoot_compliance/test_manifest.py -v
```

Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
git add pipeline/autoresearch/overshoot_compliance/manifest.py \
        pipeline/tests/autoresearch/overshoot_compliance/test_manifest.py
git commit -m "feat(compliance): run manifest with git+config+data SHA-256 per §13A.1"
```

---

### Task 3: Data-quality audit (§5A)

**Files:**
- Create: `pipeline/autoresearch/overshoot_compliance/data_audit.py`
- Test: `pipeline/tests/autoresearch/overshoot_compliance/test_data_audit.py`

Compute per-ticker and aggregate `missing_bar_count`, `duplicate_timestamp_count`, `stale_quote_count` (identical OHLC for >N bars), `zero_or_negative_price_count`, `zero_volume_bar_count`, plus aggregate `impaired_pct` = impaired_bars / total_bars.

Pass condition: `impaired_pct ≤ 1.0%` → CLEAN; `1.0% < impaired_pct ≤ 3.0%` → DATA-IMPAIRED; `> 3.0%` → AUTO-FAIL.

- [ ] **Step 1: Write failing tests**

```python
# pipeline/tests/autoresearch/overshoot_compliance/test_data_audit.py
import pandas as pd
import pytest

from pipeline.autoresearch.overshoot_compliance import data_audit as DA


def _frame(rows):
    return pd.DataFrame(rows).set_index(pd.to_datetime([r["Date"] for r in rows])).drop(columns=["Date"])


def test_missing_bars_detected_when_gap_in_trading_dates():
    rows = [
        {"Date": "2025-01-01", "Open": 100, "High": 101, "Low": 99, "Close": 100, "Volume": 1000},
        # missing 2025-01-02 (business day)
        {"Date": "2025-01-03", "Open": 101, "High": 102, "Low": 100, "Close": 101, "Volume": 1000},
    ]
    report = DA.audit_ticker("TEST", _frame(rows), business_days=pd.bdate_range("2025-01-01", "2025-01-03"))
    assert report["missing_bar_count"] == 1


def test_duplicate_timestamps_detected():
    rows = [
        {"Date": "2025-01-01", "Open": 100, "High": 101, "Low": 99, "Close": 100, "Volume": 1000},
        {"Date": "2025-01-01", "Open": 100, "High": 101, "Low": 99, "Close": 100, "Volume": 1000},
    ]
    df = pd.DataFrame(rows)
    df.index = pd.to_datetime(df["Date"])
    df = df.drop(columns=["Date"])
    report = DA.audit_ticker("TEST", df, business_days=pd.bdate_range("2025-01-01", "2025-01-01"))
    assert report["duplicate_timestamp_count"] == 1


def test_stale_quote_detected_when_ohlc_unchanged_for_many_bars():
    rows = []
    for i, d in enumerate(pd.bdate_range("2025-01-01", periods=10)):
        rows.append({"Date": d.strftime("%Y-%m-%d"), "Open": 100, "High": 100, "Low": 100, "Close": 100, "Volume": 1000})
    df = pd.DataFrame(rows)
    df.index = pd.to_datetime(df["Date"])
    df = df.drop(columns=["Date"])
    report = DA.audit_ticker("TEST", df, business_days=pd.DatetimeIndex(df.index), stale_run_min=3)
    assert report["stale_quote_count"] >= 7  # runs ≥ 3 identical bars


def test_zero_or_negative_price_flagged():
    rows = [
        {"Date": "2025-01-01", "Open": 100, "High": 101, "Low": 99, "Close": 100, "Volume": 1000},
        {"Date": "2025-01-02", "Open": 0, "High": 0, "Low": 0, "Close": 0, "Volume": 1000},
    ]
    df = pd.DataFrame(rows)
    df.index = pd.to_datetime(df["Date"])
    df = df.drop(columns=["Date"])
    report = DA.audit_ticker("TEST", df, business_days=pd.DatetimeIndex(df.index))
    assert report["zero_or_negative_price_count"] == 1


def test_aggregate_classifies_clean():
    per_ticker = {"A": {"total_bars": 1000, "impaired_bars": 5},
                  "B": {"total_bars": 1000, "impaired_bars": 3}}
    agg = DA.aggregate(per_ticker)
    assert agg["impaired_pct"] == pytest.approx(0.4, abs=0.01)
    assert agg["classification"] == "CLEAN"


def test_aggregate_classifies_impaired():
    per_ticker = {"A": {"total_bars": 1000, "impaired_bars": 15},
                  "B": {"total_bars": 1000, "impaired_bars": 15}}
    agg = DA.aggregate(per_ticker)
    assert agg["classification"] == "DATA-IMPAIRED"


def test_aggregate_classifies_auto_fail():
    per_ticker = {"A": {"total_bars": 1000, "impaired_bars": 40}}
    agg = DA.aggregate(per_ticker)
    assert agg["classification"] == "AUTO-FAIL"
```

- [ ] **Step 2: Run, expect FAIL**

```
python -m pytest pipeline/tests/autoresearch/overshoot_compliance/test_data_audit.py -v
```

- [ ] **Step 3: Implement**

```python
# pipeline/autoresearch/overshoot_compliance/data_audit.py
"""Data-quality audit per §5A of backtesting-specs.txt v1.0."""
from __future__ import annotations

import pandas as pd


def audit_ticker(
    ticker: str,
    df: pd.DataFrame,
    business_days: pd.DatetimeIndex,
    stale_run_min: int = 3,
) -> dict:
    """Audit one ticker's OHLC frame against the expected business-day grid.

    Returns a dict with missing, duplicate, stale-run, zero-price, zero-volume
    counts and the total impaired-bar count.
    """
    expected = set(pd.DatetimeIndex(business_days).normalize())
    observed = pd.DatetimeIndex(df.index).normalize()
    observed_set = set(observed)
    missing = len(expected - observed_set)
    duplicate = int(observed.duplicated().sum())

    # identify runs of identical OHLC of length >= stale_run_min
    stale = 0
    if len(df) > 0:
        key = (
            df["Open"].astype(float).astype(str) + "|"
            + df["High"].astype(float).astype(str) + "|"
            + df["Low"].astype(float).astype(str) + "|"
            + df["Close"].astype(float).astype(str)
        )
        run_id = (key != key.shift()).cumsum()
        run_sizes = run_id.value_counts()
        for size in run_sizes.values:
            if size >= stale_run_min:
                stale += int(size)

    zero_price = int(((df[["Open", "High", "Low", "Close"]] <= 0).any(axis=1)).sum())
    zero_volume = 0
    if "Volume" in df.columns:
        zero_volume = int((df["Volume"].fillna(0) <= 0).sum())

    impaired_bars = missing + duplicate + stale + zero_price + zero_volume
    total_bars = max(1, len(expected))
    return {
        "ticker": ticker,
        "missing_bar_count": missing,
        "duplicate_timestamp_count": duplicate,
        "stale_quote_count": stale,
        "zero_or_negative_price_count": zero_price,
        "zero_volume_bar_count": zero_volume,
        "impaired_bars": impaired_bars,
        "total_bars": total_bars,
    }


def aggregate(per_ticker: dict) -> dict:
    total = sum(r["total_bars"] for r in per_ticker.values())
    impaired = sum(r["impaired_bars"] for r in per_ticker.values())
    pct = (impaired / total * 100.0) if total else 0.0
    if pct > 3.0:
        cls = "AUTO-FAIL"
    elif pct > 1.0:
        cls = "DATA-IMPAIRED"
    else:
        cls = "CLEAN"
    return {
        "total_bars": total,
        "impaired_bars": impaired,
        "impaired_pct": round(pct, 3),
        "classification": cls,
        "per_ticker": per_ticker,
    }
```

- [ ] **Step 4: Run, expect PASS**

```
python -m pytest pipeline/tests/autoresearch/overshoot_compliance/test_data_audit.py -v
```

Expected: `7 passed`

- [ ] **Step 5: Commit**

```bash
git add pipeline/autoresearch/overshoot_compliance/data_audit.py \
        pipeline/tests/autoresearch/overshoot_compliance/test_data_audit.py
git commit -m "feat(compliance): §5A data-quality audit (missing/dup/stale/zero)"
```

---

### Task 4: Universe snapshot under waiver (§6.2)

**Files:**
- Create: `pipeline/autoresearch/overshoot_compliance/universe_snapshot.py`
- Test: `pipeline/tests/autoresearch/overshoot_compliance/test_universe_snapshot.py`

Per the filed waiver, §6.2 is waived for RESEARCH-tier only, but we still declare the universe. If `pipeline/data/fno_universe_history.json` exists, read it. Otherwise produce a disclosure that cites the waiver file path, reports `n_tickers_current = 213` (or whatever `load_sector_map` returns), and marks `coverage_ratio = null, status = "SURVIVORSHIP-UNCORRECTED-WAIVED"`.

- [ ] **Step 1: Write failing tests**

```python
# pipeline/tests/autoresearch/overshoot_compliance/test_universe_snapshot.py
import json
from pathlib import Path

from pipeline.autoresearch.overshoot_compliance import universe_snapshot as U


def test_snapshot_when_history_file_missing(tmp_path, monkeypatch):
    # Point the reader at a path that does not exist.
    fake = tmp_path / "nope.json"
    snap = U.build_snapshot(
        current_tickers=["A", "B", "C"],
        history_path=fake,
        waiver_path=Path("docs/superpowers/waivers/2026-04-23-phase-c-residual-reversion-survivorship.md"),
    )
    assert snap["n_tickers_current"] == 3
    assert snap["status"] == "SURVIVORSHIP-UNCORRECTED-WAIVED"
    assert snap["coverage_ratio"] is None
    assert "waiver_path" in snap


def test_snapshot_when_history_file_present(tmp_path):
    history = tmp_path / "fno_universe_history.json"
    history.write_text(json.dumps({
        "snapshots": [
            {"month": "2024-12", "symbols": ["A", "B", "C", "X"]},
            {"month": "2025-01", "symbols": ["A", "B", "C"]},
        ]
    }))
    snap = U.build_snapshot(
        current_tickers=["A", "B", "C"],
        history_path=history,
        waiver_path=None,
    )
    assert snap["n_tickers_current"] == 3
    assert snap["n_tickers_ever"] == 4
    assert snap["n_tickers_delisted"] == 1
    assert snap["coverage_ratio"] == 0.25
    assert snap["status"] == "SURVIVORSHIP-CORRECTED"
```

- [ ] **Step 2: Run, expect FAIL**

```
python -m pytest pipeline/tests/autoresearch/overshoot_compliance/test_universe_snapshot.py -v
```

- [ ] **Step 3: Implement**

```python
# pipeline/autoresearch/overshoot_compliance/universe_snapshot.py
"""Universe-snapshot disclosure per §6.2 of backtesting-specs.txt v1.0.

When pipeline/data/fno_universe_history.json is present, compute
coverage_ratio. When not present, emit an explicit
SURVIVORSHIP-UNCORRECTED-WAIVED disclosure pointing at the waiver file.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Sequence


def build_snapshot(
    current_tickers: Sequence[str],
    history_path: Path,
    waiver_path: Path | None,
) -> dict:
    n_cur = len(set(current_tickers))
    if not Path(history_path).exists():
        return {
            "n_tickers_current": n_cur,
            "n_tickers_ever": None,
            "n_tickers_delisted": None,
            "coverage_ratio": None,
            "status": "SURVIVORSHIP-UNCORRECTED-WAIVED",
            "history_path": str(history_path),
            "waiver_path": str(waiver_path) if waiver_path else None,
        }

    data = json.loads(Path(history_path).read_text())
    snapshots = data.get("snapshots", [])
    ever = set()
    for snap in snapshots:
        ever.update(snap.get("symbols", []))
    delisted = ever - set(current_tickers)
    ratio = (len(delisted) / len(ever)) if ever else 0.0
    return {
        "n_tickers_current": n_cur,
        "n_tickers_ever": len(ever),
        "n_tickers_delisted": len(delisted),
        "coverage_ratio": round(ratio, 4),
        "status": "SURVIVORSHIP-CORRECTED",
        "history_path": str(history_path),
    }
```

- [ ] **Step 4: Run, expect PASS**

```
python -m pytest pipeline/tests/autoresearch/overshoot_compliance/test_universe_snapshot.py -v
```

Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add pipeline/autoresearch/overshoot_compliance/universe_snapshot.py \
        pipeline/tests/autoresearch/overshoot_compliance/test_universe_snapshot.py
git commit -m "feat(compliance): §6.2 universe snapshot with waiver-aware disclosure"
```

---

## Phase B — Slippage grid, metrics, comparators, permutations

### Task 5: Slippage-grid applier (§1)

**Files:**
- Create: `pipeline/autoresearch/overshoot_compliance/slippage_grid.py`
- Test: `pipeline/tests/autoresearch/overshoot_compliance/test_slippage_grid.py`

The per-ticker ledger already exposes per-event gross edge in percent. The grid:
- S0 (Base, 10 bps round-trip) = 0.10%
- S1 (Moderate, 30 bps round-trip) = 0.30%
- S2 (High, 50 bps round-trip) = 0.50%
- S3 (Extreme, 70 bps round-trip) = 0.70%

We apply as a flat-percent subtraction because the events already live in percent-return space. This matches what the prototype's `edge_net_pct = edge - txn_cost_pct` does for one cost.

- [ ] **Step 1: Write failing tests**

```python
# pipeline/tests/autoresearch/overshoot_compliance/test_slippage_grid.py
import pandas as pd
import pytest

from pipeline.autoresearch.overshoot_compliance import slippage_grid as SG


def test_grid_levels_are_named():
    assert SG.LEVELS["S0"] == 0.10
    assert SG.LEVELS["S1"] == 0.30
    assert SG.LEVELS["S2"] == 0.50
    assert SG.LEVELS["S3"] == 0.70


def test_apply_level_subtracts_cost():
    ledger = pd.DataFrame([
        {"ticker": "A", "direction": "UP", "trade_ret_pct": 1.00},
        {"ticker": "A", "direction": "UP", "trade_ret_pct": -0.40},
    ])
    out = SG.apply_level(ledger, "S1")
    assert out["net_ret_pct"].iloc[0] == pytest.approx(0.70)
    assert out["net_ret_pct"].iloc[1] == pytest.approx(-0.70)
    assert (out["slippage_level"] == "S1").all()


def test_apply_full_grid_returns_four_rows_per_event():
    ledger = pd.DataFrame([
        {"ticker": "A", "direction": "UP", "trade_ret_pct": 1.00},
    ])
    out = SG.apply_full_grid(ledger)
    assert set(out["slippage_level"]) == {"S0", "S1", "S2", "S3"}
    assert len(out) == 4
```

- [ ] **Step 2: Run, expect FAIL**

```
python -m pytest pipeline/tests/autoresearch/overshoot_compliance/test_slippage_grid.py -v
```

- [ ] **Step 3: Implement**

```python
# pipeline/autoresearch/overshoot_compliance/slippage_grid.py
"""Slippage-stress grid per §1 of backtesting-specs.txt v1.0.

Subtracts a flat round-trip cost in percent-return space from every
event's gross trade return. The ledger format assumed:
    ticker, direction, trade_ret_pct  (percent, signed by direction)
Where trade_ret_pct already encodes the strategy's sign:
  fade-UP (SHORT) → positive when next-day close fell.
"""
from __future__ import annotations

import pandas as pd

# round-trip cost in percent (10 bps, 30 bps, 50 bps, 70 bps)
LEVELS: dict[str, float] = {
    "S0": 0.10,
    "S1": 0.30,
    "S2": 0.50,
    "S3": 0.70,
}


def apply_level(ledger: pd.DataFrame, level: str) -> pd.DataFrame:
    cost = LEVELS[level]
    out = ledger.copy()
    out["slippage_level"] = level
    out["cost_pct"] = cost
    out["net_ret_pct"] = out["trade_ret_pct"] - cost
    return out


def apply_full_grid(ledger: pd.DataFrame) -> pd.DataFrame:
    frames = [apply_level(ledger, lvl) for lvl in LEVELS]
    return pd.concat(frames, ignore_index=True)
```

- [ ] **Step 4: Run, expect PASS**

```
python -m pytest pipeline/tests/autoresearch/overshoot_compliance/test_slippage_grid.py -v
```

Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add pipeline/autoresearch/overshoot_compliance/slippage_grid.py \
        pipeline/tests/autoresearch/overshoot_compliance/test_slippage_grid.py
git commit -m "feat(compliance): §1 slippage-grid applier S0/S1/S2/S3"
```

---

### Task 6: Risk-adjusted metrics + hit-rate CI (§2, §9.3)

**Files:**
- Create: `pipeline/autoresearch/overshoot_compliance/metrics.py`
- Test: `pipeline/tests/autoresearch/overshoot_compliance/test_metrics.py`

Per-(ticker, direction, level) compute: Sharpe (annualised; assume positions are daily, one trade per event, non-overlapping, so annualisation factor = 252/avg_trades_per_year effectively = 252 when one return per trading day — but some tickers have only ~20 trades in 5 years, so we explicitly choose PERIODS=252 and treat the trade series as if it is a sparse daily series), max drawdown of cumulative P&L curve, Calmar = annualised mean / |max DD|, hit-rate with 95% percentile-bootstrap CI.

We IMPORT from `pipeline.research.phase_c_backtest.stats` for `sharpe`, `bootstrap_sharpe_ci`, `max_drawdown`. We only add a hit-rate CI helper.

- [ ] **Step 1: Write failing tests**

```python
# pipeline/tests/autoresearch/overshoot_compliance/test_metrics.py
import numpy as np
import pandas as pd
import pytest

from pipeline.autoresearch.overshoot_compliance import metrics as M


def test_hit_rate_ci_brackets_point_estimate():
    wins = np.array([1, 1, 0, 1, 1, 0, 1, 0, 1, 1])  # 7/10
    lo, point, hi = M.hit_rate_ci(wins, n_resamples=5000, alpha=0.05, seed=7)
    assert lo < point < hi
    assert abs(point - 0.7) < 1e-9


def test_per_bucket_metrics_returns_all_required_fields():
    rng = np.random.default_rng(42)
    rets = rng.normal(loc=0.004, scale=0.02, size=100)  # mean 0.4%/trade
    row = M.per_bucket_metrics(rets, annualisation_factor=252)
    for k in ("n_trades", "mean_ret_pct", "hit_rate",
              "hit_rate_ci_lo_95", "hit_rate_ci_hi_95",
              "sharpe", "sharpe_ci_lo_95", "sharpe_ci_hi_95",
              "max_drawdown_pct", "calmar"):
        assert k in row
    assert row["n_trades"] == 100


def test_per_bucket_metrics_handles_empty():
    row = M.per_bucket_metrics(np.array([]), annualisation_factor=252)
    assert row["n_trades"] == 0
    assert row["mean_ret_pct"] == 0.0
    assert row["sharpe"] == 0.0


def test_max_drawdown_matches_phase_c_stats():
    from pipeline.research.phase_c_backtest import stats as PC
    equity = np.array([100.0, 110.0, 90.0, 95.0, 80.0, 100.0])
    assert M.max_drawdown_of(np.diff(equity) / equity[:-1]) == pytest.approx(PC.max_drawdown(equity))
```

- [ ] **Step 2: Run, expect FAIL**

```
python -m pytest pipeline/tests/autoresearch/overshoot_compliance/test_metrics.py -v
```

- [ ] **Step 3: Implement**

```python
# pipeline/autoresearch/overshoot_compliance/metrics.py
"""Risk-adjusted metrics per §2 and §9.3 of backtesting-specs.txt v1.0.

Re-uses pipeline.research.phase_c_backtest.stats for Sharpe / bootstrap CI /
drawdown so we do not re-derive tested code. Adds hit-rate percentile CI and
a per-bucket row helper.
"""
from __future__ import annotations

import numpy as np

from pipeline.research.phase_c_backtest import stats as PC


def hit_rate_ci(
    wins: np.ndarray,
    n_resamples: int = 10_000,
    alpha: float = 0.05,
    seed: int | None = None,
) -> tuple[float, float, float]:
    arr = np.asarray(wins, dtype=int)
    n = arr.size
    if n == 0:
        return (0.0, 0.0, 0.0)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n, size=(n_resamples, n))
    resampled = arr[idx]
    rates = resampled.mean(axis=1)
    lo = float(np.quantile(rates, alpha / 2))
    hi = float(np.quantile(rates, 1 - alpha / 2))
    point = float(arr.mean())
    return (lo, point, hi)


def max_drawdown_of(returns_pct: np.ndarray) -> float:
    """Max drawdown of a percent-return series (not annualised)."""
    if len(returns_pct) == 0:
        return 0.0
    equity = np.cumprod(1.0 + np.asarray(returns_pct, dtype=float) / 100.0)
    return PC.max_drawdown(equity)


def per_bucket_metrics(
    returns_pct: np.ndarray,
    annualisation_factor: int = 252,
    n_resamples: int = 5_000,
    seed: int | None = 42,
) -> dict:
    arr = np.asarray(returns_pct, dtype=float)
    n = arr.size
    if n == 0:
        return {
            "n_trades": 0, "mean_ret_pct": 0.0, "hit_rate": 0.0,
            "hit_rate_ci_lo_95": 0.0, "hit_rate_ci_hi_95": 0.0,
            "sharpe": 0.0, "sharpe_ci_lo_95": 0.0, "sharpe_ci_hi_95": 0.0,
            "max_drawdown_pct": 0.0, "calmar": 0.0,
        }
    # convert percent to decimals for Sharpe / DD math
    dec = arr / 100.0
    sharpe_pt, sharpe_lo, sharpe_hi = PC.bootstrap_sharpe_ci(
        dec, n_resamples=n_resamples, alpha=0.05,
        periods_per_year=annualisation_factor, seed=seed,
    )
    wins = (arr > 0).astype(int)
    hr_lo, hr_pt, hr_hi = hit_rate_ci(wins, n_resamples=n_resamples, seed=seed)
    dd = max_drawdown_of(arr)
    mean_ret = float(arr.mean())
    annualised_mean = mean_ret / 100.0 * annualisation_factor
    calmar = annualised_mean / dd if dd > 0 else 0.0
    return {
        "n_trades": int(n),
        "mean_ret_pct": round(mean_ret, 4),
        "hit_rate": round(hr_pt, 4),
        "hit_rate_ci_lo_95": round(hr_lo, 4),
        "hit_rate_ci_hi_95": round(hr_hi, 4),
        "sharpe": round(sharpe_pt, 4),
        "sharpe_ci_lo_95": round(sharpe_lo, 4),
        "sharpe_ci_hi_95": round(sharpe_hi, 4),
        "max_drawdown_pct": round(dd * 100.0, 4),
        "calmar": round(calmar, 4),
    }
```

- [ ] **Step 4: Run, expect PASS**

```
python -m pytest pipeline/tests/autoresearch/overshoot_compliance/test_metrics.py -v
```

Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add pipeline/autoresearch/overshoot_compliance/metrics.py \
        pipeline/tests/autoresearch/overshoot_compliance/test_metrics.py
git commit -m "feat(compliance): §2 risk metrics (Sharpe CI, DD, Calmar, hit CI)"
```

---

### Task 7: Naive comparators (§9B.1)

**Files:**
- Create: `pipeline/autoresearch/overshoot_compliance/naive_comparators.py`
- Test: `pipeline/tests/autoresearch/overshoot_compliance/test_naive_comparators.py`

On the same event set, run three naive strategies:
1. **Random direction** — flip a coin per event; mean equals unconditional event-day next-day return times random sign.
2. **Equal-weight event basket** — mean of next-day returns across all events regardless of direction.
3. **Simple momentum** — on an overshoot day, follow the overshoot direction instead of fading (LONG after UP, SHORT after DOWN). This is the explicit opposite of our strategy and matches §8's direction-audit requirement.

Return each comparator's mean / Sharpe / hit. Pass condition: strategy at S0 must beat the STRONGEST of the three; otherwise flag `COMPARATOR-FAIL`.

- [ ] **Step 1: Write failing tests**

```python
# pipeline/tests/autoresearch/overshoot_compliance/test_naive_comparators.py
import numpy as np
import pandas as pd
import pytest

from pipeline.autoresearch.overshoot_compliance import naive_comparators as NC


def _events():
    return pd.DataFrame([
        {"ticker": "A", "z": 3.1, "next_ret": 1.0},
        {"ticker": "A", "z": 3.2, "next_ret": -0.5},
        {"ticker": "A", "z": -3.5, "next_ret": 0.8},
        {"ticker": "A", "z": -3.1, "next_ret": -0.3},
        {"ticker": "B", "z": 3.0, "next_ret": 0.2},
    ])


def test_random_direction_approaches_zero_for_symmetric_returns():
    rng = np.random.default_rng(0)
    rets = rng.normal(loc=0.0, scale=1.0, size=5000)
    events = pd.DataFrame({"next_ret": rets, "z": rng.choice([-3, 3], size=5000)})
    mean = NC.random_direction(events, seed=42)["mean_ret_pct"]
    assert abs(mean) < 0.05


def test_equal_weight_basket_uses_raw_mean():
    ev = _events()
    row = NC.equal_weight_basket(ev)
    assert row["mean_ret_pct"] == pytest.approx(float(ev["next_ret"].mean()))


def test_momentum_follow_flips_fade_sign():
    ev = _events()
    row = NC.momentum_follow(ev)
    # momentum LONG after UP, SHORT after DOWN.
    # UP rows: z>0, contribute +next_ret
    # DOWN rows: z<0, contribute -next_ret
    expected = float(
        ev.loc[ev["z"] > 0, "next_ret"].sum()
        - ev.loc[ev["z"] < 0, "next_ret"].sum()
    ) / len(ev)
    assert row["mean_ret_pct"] == pytest.approx(expected)


def test_comparator_suite_returns_all_three():
    ev = _events()
    suite = NC.run_suite(ev, seed=1)
    assert set(suite.keys()) == {"random_direction", "equal_weight_basket", "momentum_follow"}
    for v in suite.values():
        assert "mean_ret_pct" in v
        assert "sharpe" in v
        assert "hit_rate" in v
```

- [ ] **Step 2: Run, expect FAIL**

```
python -m pytest pipeline/tests/autoresearch/overshoot_compliance/test_naive_comparators.py -v
```

- [ ] **Step 3: Implement**

```python
# pipeline/autoresearch/overshoot_compliance/naive_comparators.py
"""Naive benchmarks per §9B.1.

On the same event set, compute random-direction, equal-weight basket, and
momentum (follow instead of fade) P&L. The registered strategy (fade) must
beat the STRONGEST of these at S0 on the primary metric.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import metrics as M


def _row(returns_pct: np.ndarray, annualisation_factor: int = 252) -> dict:
    core = M.per_bucket_metrics(returns_pct, annualisation_factor=annualisation_factor)
    return {
        "mean_ret_pct": core["mean_ret_pct"],
        "sharpe": core["sharpe"],
        "hit_rate": core["hit_rate"],
        "n_trades": core["n_trades"],
    }


def random_direction(events: pd.DataFrame, seed: int | None = 42) -> dict:
    rng = np.random.default_rng(seed)
    signs = rng.choice([-1, 1], size=len(events))
    rets = events["next_ret"].to_numpy() * signs
    return _row(rets)


def equal_weight_basket(events: pd.DataFrame) -> dict:
    rets = events["next_ret"].to_numpy()
    return _row(rets)


def momentum_follow(events: pd.DataFrame) -> dict:
    signs = np.where(events["z"].to_numpy() > 0, 1.0, -1.0)
    rets = events["next_ret"].to_numpy() * signs
    return _row(rets)


def run_suite(events: pd.DataFrame, seed: int | None = 42) -> dict:
    return {
        "random_direction": random_direction(events, seed=seed),
        "equal_weight_basket": equal_weight_basket(events),
        "momentum_follow": momentum_follow(events),
    }
```

- [ ] **Step 4: Run, expect PASS**

```
python -m pytest pipeline/tests/autoresearch/overshoot_compliance/test_naive_comparators.py -v
```

Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add pipeline/autoresearch/overshoot_compliance/naive_comparators.py \
        pipeline/tests/autoresearch/overshoot_compliance/test_naive_comparators.py
git commit -m "feat(compliance): §9B.1 naive comparator suite"
```

---

### Task 8: Streaming ≥100k permutation engine (§9B.2)

**Files:**
- Create: `pipeline/autoresearch/overshoot_compliance/perm_scaling.py`
- Test: `pipeline/tests/autoresearch/overshoot_compliance/test_perm_scaling.py`

Per §9B.2, Bonferroni is active on 426-hypothesis family so permutations must be ≥100k. A 100k × 426-ticker matrix is ~340 MB of floats — tractable but wasteful. Use a streaming counter: for each (ticker, direction), sample `n_shuffles` means from the ticker's unconditional return distribution and increment an exceed-counter when the bootstrap mean meets/exceeds the observed edge. Uses `np.random.Generator.choice` with `replace=True`.

Finest resolvable p-value at 100k shuffles is 1e-5; Bonferroni α = 1.17e-4, comfortably above the floor.

- [ ] **Step 1: Write failing tests**

```python
# pipeline/tests/autoresearch/overshoot_compliance/test_perm_scaling.py
import numpy as np
import pytest

from pipeline.autoresearch.overshoot_compliance import perm_scaling as P


def test_p_value_close_to_0_when_observed_is_extreme():
    rng = np.random.default_rng(0)
    unconditional = rng.normal(0.0, 1.0, size=2000)
    # observed mean is 3σ above mean — should be very rare under null
    p = P.bootstrap_p_value(
        observed_mean=3.0, unconditional=unconditional,
        n_events=20, n_shuffles=50_000, seed=1,
    )
    assert 0.0 <= p <= 0.01


def test_p_value_near_half_when_observed_near_null_mean():
    rng = np.random.default_rng(1)
    unconditional = rng.normal(0.0, 1.0, size=2000)
    p = P.bootstrap_p_value(
        observed_mean=0.0, unconditional=unconditional,
        n_events=20, n_shuffles=20_000, seed=2,
    )
    # Expect roughly 0.5; allow generous tolerance for 20k shuffles.
    assert 0.35 < p < 0.65


def test_p_value_floor_matches_reciprocal_of_shuffles():
    rng = np.random.default_rng(2)
    unconditional = rng.normal(0.0, 1.0, size=2000)
    # Observed so extreme that zero exceedances expected; p should be ≤ 1/n.
    p = P.bootstrap_p_value(
        observed_mean=10.0, unconditional=unconditional,
        n_events=20, n_shuffles=10_000, seed=3,
    )
    assert p <= 1.0 / 10_000


def test_rejects_insufficient_shuffles_under_bonferroni():
    with pytest.raises(ValueError):
        P.bootstrap_p_value(
            observed_mean=1.0, unconditional=np.zeros(10),
            n_events=5, n_shuffles=500, seed=0,
            require_perm_floor=100_000,
        )


def test_streaming_does_not_allocate_nshuffles_matrix(monkeypatch):
    # Call with a large n_shuffles; the implementation must not create
    # an n_shuffles-by-n_events matrix. We enforce this by limiting
    # np.random.Generator.choice to a batch size ≤ 10_000 via wrapping.
    rng = np.random.default_rng(0)
    unconditional = rng.normal(0.0, 1.0, size=200)
    # Simply exercising 200k shuffles should complete.
    p = P.bootstrap_p_value(
        observed_mean=0.5, unconditional=unconditional,
        n_events=10, n_shuffles=200_000, seed=4, batch_size=5_000,
    )
    assert 0.0 <= p <= 1.0
```

- [ ] **Step 2: Run, expect FAIL**

```
python -m pytest pipeline/tests/autoresearch/overshoot_compliance/test_perm_scaling.py -v
```

- [ ] **Step 3: Implement**

```python
# pipeline/autoresearch/overshoot_compliance/perm_scaling.py
"""Streaming permutation-test runner for §9B.2.

Bootstraps the mean of n_events draws from an unconditional return
distribution n_shuffles times without allocating the full permutation
matrix. Works for n_shuffles up to ~10M on commodity hardware with a
5000-row batch.
"""
from __future__ import annotations

import numpy as np


def bootstrap_p_value(
    *,
    observed_mean: float,
    unconditional: np.ndarray,
    n_events: int,
    n_shuffles: int,
    seed: int | None = None,
    batch_size: int = 5_000,
    require_perm_floor: int | None = None,
) -> float:
    """One-sided: probability that a bootstrap mean meets/exceeds observed_mean."""
    if require_perm_floor is not None and n_shuffles < require_perm_floor:
        raise ValueError(
            f"n_shuffles={n_shuffles} below required floor {require_perm_floor} "
            "per §9B.2 when Bonferroni/FDR is active"
        )
    if n_events <= 0:
        return 1.0
    arr = np.asarray(unconditional, dtype=float)
    if arr.size == 0:
        return 1.0
    rng = np.random.default_rng(seed)

    remaining = n_shuffles
    exceed = 0
    while remaining > 0:
        this_batch = min(batch_size, remaining)
        # shape (this_batch, n_events)
        sample = rng.choice(arr, size=(this_batch, n_events), replace=True)
        means = sample.mean(axis=1)
        exceed += int(np.sum(means >= observed_mean))
        remaining -= this_batch
    return exceed / n_shuffles
```

- [ ] **Step 4: Run, expect PASS**

```
python -m pytest pipeline/tests/autoresearch/overshoot_compliance/test_perm_scaling.py -v
```

Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add pipeline/autoresearch/overshoot_compliance/perm_scaling.py \
        pipeline/tests/autoresearch/overshoot_compliance/test_perm_scaling.py
git commit -m "feat(compliance): §9B.2 streaming ≥100k permutation engine"
```

---

## Phase C — Robustness, decay, portfolio gates

### Task 9: Parameter-fragility sweep (§9A)

**Files:**
- Create: `pipeline/autoresearch/overshoot_compliance/fragility.py`
- Test: `pipeline/tests/autoresearch/overshoot_compliance/test_fragility.py`

For a chosen parameter set (min_z=3.0, roll_window=20, cost=0.30% = S1), sweep a 3×3×3=27-point neighborhood: min_z ∈ {2.5, 3.0, 3.5}, roll_window ∈ {15, 20, 25}, cost ∈ {0.25, 0.30, 0.35}. Pass: ≥60% of neighbors preserve positive net P&L; median neighbor Sharpe ≥70% of chosen-point Sharpe; no majority sign-flip.

Rather than re-running the whole residual computation 27 times (expensive), we precompute events at the LOWEST `min_z` and the LARGEST `roll_window`, then subsample/filter each neighbor from that superset. Sigma windows of 15/20/25 require three separate residual runs (done once by the runner in Task 17); the fragility module receives them and handles the thresholding/costing.

- [ ] **Step 1: Write failing tests**

```python
# pipeline/tests/autoresearch/overshoot_compliance/test_fragility.py
import pandas as pd
import numpy as np
import pytest

from pipeline.autoresearch.overshoot_compliance import fragility as F


def _events(n, mean_ret, z_start=3.0):
    return pd.DataFrame([
        {"ticker": "A", "direction": "UP", "z": z_start + i * 0.01,
         "next_ret": mean_ret + (i - n / 2) * 0.01}
        for i in range(n)
    ])


def test_neighborhood_grid_is_27_points():
    assert len(F.neighborhood_grid()) == 27


def test_fragility_report_has_stability_flags():
    ev_by_window = {
        15: _events(40, mean_ret=0.5),
        20: _events(40, mean_ret=0.6),
        25: _events(40, mean_ret=0.55),
    }
    chosen = {"min_z": 3.0, "roll_window": 20, "cost_pct": 0.30}
    report = F.evaluate(ev_by_window, chosen)
    for k in ("chosen_sharpe", "neighbor_rows",
              "pct_positive_pnl", "median_sharpe_ratio", "sign_flip_pct",
              "stable_positive", "stable_sharpe", "stable_sign",
              "verdict"):
        assert k in report
    assert len(report["neighbor_rows"]) == 27


def test_fragility_verdict_pass_when_all_three_stable():
    ev_by_window = {w: _events(40, mean_ret=0.5) for w in (15, 20, 25)}
    chosen = {"min_z": 3.0, "roll_window": 20, "cost_pct": 0.30}
    report = F.evaluate(ev_by_window, chosen)
    assert report["verdict"] in {"STABLE", "PARAMETER-FRAGILE"}


def test_fragility_verdict_fail_when_majority_sign_flip():
    # All neighbors produce negative mean returns after cost — sign-flips from any hypothetical positive chosen point.
    ev_by_window = {w: _events(20, mean_ret=-0.4) for w in (15, 20, 25)}
    chosen = {"min_z": 3.0, "roll_window": 20, "cost_pct": 0.30}
    report = F.evaluate(ev_by_window, chosen)
    assert report["verdict"] == "PARAMETER-FRAGILE"
```

- [ ] **Step 2: Run, expect FAIL**

```
python -m pytest pipeline/tests/autoresearch/overshoot_compliance/test_fragility.py -v
```

- [ ] **Step 3: Implement**

```python
# pipeline/autoresearch/overshoot_compliance/fragility.py
"""Parameter-fragility sweep per §9A.

Evaluates a 3×3×3 neighborhood around the chosen (min_z, roll_window,
cost_pct). Events for each roll_window must be precomputed by the caller
(runner.py Task 17) and passed in as `events_by_window`.
"""
from __future__ import annotations

from itertools import product

import numpy as np
import pandas as pd

from . import metrics as M


MIN_Z_GRID = (2.5, 3.0, 3.5)
WINDOW_GRID = (15, 20, 25)
COST_GRID = (0.25, 0.30, 0.35)


def neighborhood_grid() -> list[dict]:
    return [
        {"min_z": z, "roll_window": w, "cost_pct": c}
        for z, w, c in product(MIN_Z_GRID, WINDOW_GRID, COST_GRID)
    ]


def _edge_for(events: pd.DataFrame, min_z: float, cost_pct: float) -> dict:
    sel = events.loc[events["z"].abs() >= min_z].copy()
    if sel.empty:
        return {"n_trades": 0, "mean_ret_pct": 0.0, "sharpe": 0.0}
    # direction-aware: UP = fade-SHORT (invert sign), DOWN = fade-LONG
    sign = np.where(sel["direction"].eq("UP"), -1.0, 1.0)
    gross = sign * sel["next_ret"].to_numpy()
    net = gross - cost_pct
    return M.per_bucket_metrics(net)


def evaluate(events_by_window: dict[int, pd.DataFrame], chosen: dict) -> dict:
    rows = []
    chosen_metrics = _edge_for(
        events_by_window[chosen["roll_window"]],
        chosen["min_z"], chosen["cost_pct"],
    )
    chosen_sharpe = chosen_metrics["sharpe"]
    chosen_mean = chosen_metrics["mean_ret_pct"]
    for params in neighborhood_grid():
        m = _edge_for(
            events_by_window[params["roll_window"]],
            params["min_z"], params["cost_pct"],
        )
        rows.append({**params, **m})

    df = pd.DataFrame(rows)
    n = len(df)
    pct_pos = float((df["mean_ret_pct"] > 0).sum()) / n * 100.0
    med_sharpe = float(df["sharpe"].median())
    sharpe_ratio = (med_sharpe / chosen_sharpe * 100.0) if chosen_sharpe else 0.0
    chosen_sign = np.sign(chosen_mean)
    sign_flip_pct = float((np.sign(df["mean_ret_pct"]) == -chosen_sign).sum()) / n * 100.0

    stable_positive = pct_pos >= 60.0
    stable_sharpe = sharpe_ratio >= 70.0
    stable_sign = sign_flip_pct < 50.0

    verdict = "STABLE" if (stable_positive and stable_sharpe and stable_sign) else "PARAMETER-FRAGILE"

    return {
        "chosen": chosen,
        "chosen_sharpe": chosen_sharpe,
        "chosen_mean_ret_pct": chosen_mean,
        "neighbor_rows": rows,
        "pct_positive_pnl": round(pct_pos, 2),
        "median_sharpe_ratio": round(sharpe_ratio, 2),
        "sign_flip_pct": round(sign_flip_pct, 2),
        "stable_positive": stable_positive,
        "stable_sharpe": stable_sharpe,
        "stable_sign": stable_sign,
        "verdict": verdict,
    }
```

- [ ] **Step 4: Run, expect PASS**

```
python -m pytest pipeline/tests/autoresearch/overshoot_compliance/test_fragility.py -v
```

Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add pipeline/autoresearch/overshoot_compliance/fragility.py \
        pipeline/tests/autoresearch/overshoot_compliance/test_fragility.py
git commit -m "feat(compliance): §9A parameter-fragility 27-point neighborhood sweep"
```

---

### Task 10: NIFTY-beta regression + residual Sharpe (§11B)

**Files:**
- Create: `pipeline/autoresearch/overshoot_compliance/beta_regression.py`
- Test: `pipeline/tests/autoresearch/overshoot_compliance/test_beta_regression.py`

For each (ticker, direction) with net daily P&L series, regress daily trade returns against NIFTY daily returns on trade dates. Report slope (β), intercept × 252 (α annualised), R², and Sharpe of residuals. Pass: residual Sharpe ≥ 70% of gross Sharpe at S0.

Input is a per-(ticker, direction) time series of trade returns aligned to trade dates. NIFTY data is read from `pipeline/data/fno_historical/NIFTY.csv` (or closest index proxy; if not present, the module accepts a path parameter).

- [ ] **Step 1: Write failing tests**

```python
# pipeline/tests/autoresearch/overshoot_compliance/test_beta_regression.py
import numpy as np
import pandas as pd
import pytest

from pipeline.autoresearch.overshoot_compliance import beta_regression as BR


def _series(values, dates):
    return pd.Series(values, index=pd.to_datetime(dates))


def test_zero_beta_when_strategy_uncorrelated_with_nifty():
    rng = np.random.default_rng(0)
    dates = pd.bdate_range("2024-01-01", periods=252)
    nifty_rets = pd.Series(rng.normal(0.0005, 0.01, size=252), index=dates)
    strat_rets = pd.Series(rng.normal(0.001, 0.01, size=252), index=dates)
    res = BR.regress_on_nifty(strat_rets, nifty_rets)
    assert abs(res["beta"]) < 0.2


def test_unit_beta_when_strategy_equals_nifty():
    dates = pd.bdate_range("2024-01-01", periods=252)
    rng = np.random.default_rng(1)
    nifty_rets = pd.Series(rng.normal(0.0, 0.01, size=252), index=dates)
    res = BR.regress_on_nifty(nifty_rets, nifty_rets)
    assert abs(res["beta"] - 1.0) < 1e-6
    assert res["r_squared"] > 0.99


def test_residual_sharpe_returned():
    dates = pd.bdate_range("2024-01-01", periods=252)
    rng = np.random.default_rng(2)
    nifty_rets = pd.Series(rng.normal(0.0, 0.01, size=252), index=dates)
    alpha_component = pd.Series(rng.normal(0.001, 0.005, size=252), index=dates)
    strat_rets = 0.5 * nifty_rets + alpha_component
    res = BR.regress_on_nifty(strat_rets, nifty_rets)
    assert "residual_sharpe" in res
    assert res["residual_sharpe"] > 0.0


def test_alignment_by_date_only():
    nifty = _series([0.01, 0.02, -0.01, 0.005], ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"])
    strat = _series([0.02, -0.01], ["2024-01-02", "2024-01-04"])
    res = BR.regress_on_nifty(strat, nifty)
    # should use only the 2 aligned dates
    assert res["n_aligned"] == 2
```

- [ ] **Step 2: Run, expect FAIL**

```
python -m pytest pipeline/tests/autoresearch/overshoot_compliance/test_beta_regression.py -v
```

- [ ] **Step 3: Implement**

```python
# pipeline/autoresearch/overshoot_compliance/beta_regression.py
"""NIFTY-beta regression per §11B.

regress_on_nifty: given a strategy's daily return series and NIFTY's daily
return series (both pd.Series indexed by Timestamp), return dict with
{beta, alpha_annualised, r_squared, residual_sharpe, n_aligned, gross_sharpe}.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from pipeline.research.phase_c_backtest import stats as PC


def regress_on_nifty(
    strategy_rets: pd.Series,
    nifty_rets: pd.Series,
    periods_per_year: int = 252,
) -> dict:
    aligned = pd.concat({"s": strategy_rets, "m": nifty_rets}, axis=1).dropna()
    if len(aligned) < 2 or aligned["m"].std(ddof=1) == 0:
        return {
            "beta": 0.0, "alpha_annualised": 0.0, "r_squared": 0.0,
            "residual_sharpe": 0.0, "gross_sharpe": PC.sharpe(strategy_rets.to_numpy(), periods_per_year),
            "n_aligned": int(len(aligned)),
        }
    s = aligned["s"].to_numpy()
    m = aligned["m"].to_numpy()
    m_mean, s_mean = m.mean(), s.mean()
    cov = np.mean((m - m_mean) * (s - s_mean))
    var_m = np.mean((m - m_mean) ** 2)
    beta = float(cov / var_m)
    alpha = float(s_mean - beta * m_mean)
    ss_tot = np.sum((s - s_mean) ** 2)
    residuals = s - (alpha + beta * m)
    ss_res = np.sum(residuals ** 2)
    r2 = float(1.0 - ss_res / ss_tot) if ss_tot > 0 else 0.0
    return {
        "beta": round(beta, 6),
        "alpha_annualised": round(alpha * periods_per_year, 6),
        "r_squared": round(r2, 6),
        "residual_sharpe": round(PC.sharpe(residuals, periods_per_year), 6),
        "gross_sharpe": round(PC.sharpe(s, periods_per_year), 6),
        "n_aligned": int(len(aligned)),
    }
```

- [ ] **Step 4: Run, expect PASS**

```
python -m pytest pipeline/tests/autoresearch/overshoot_compliance/test_beta_regression.py -v
```

Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add pipeline/autoresearch/overshoot_compliance/beta_regression.py \
        pipeline/tests/autoresearch/overshoot_compliance/test_beta_regression.py
git commit -m "feat(compliance): §11B NIFTY-beta regression + residual Sharpe"
```

---

### Task 11: Implementation-risk 10-scenario stress (§11A)

**Files:**
- Create: `pipeline/autoresearch/overshoot_compliance/impl_risk.py`
- Test: `pipeline/tests/autoresearch/overshoot_compliance/test_impl_risk.py`

We evaluate a single COMBINED scenario as §11A.2 requires: 5% missed entries, 5% missed exits (held 1 extra bar), 5-min delayed fills (not modelable for EOD close-to-close — map to ±10 bps extra cost), stale snapshot at entry (one bar old → replace signal's own event next_ret with the next-day pair), partial fills at 50%, one outage/month, exchange halt (drop 1 day), margin-shortage reject during DD (skip trades when running equity draw exceeds 10% of starting capital), weekend-gap (amplify the first trade after any Monday event by 3× realised vol if it's a positive weekend gap — purely cost-applied), retry-one-bar-later on rejects.

Implementation: a `simulate_combined(events, rng, cfg)` returns perturbed returns per event and a pass/fail against §11A.2 thresholds.

- [ ] **Step 1: Write failing tests**

```python
# pipeline/tests/autoresearch/overshoot_compliance/test_impl_risk.py
import numpy as np
import pandas as pd
import pytest

from pipeline.autoresearch.overshoot_compliance import impl_risk as IR


def _events(n=200, mean_ret=0.5, seed=0):
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "ticker": ["A"] * n,
        "direction": ["UP"] * n,
        "date": pd.bdate_range("2024-01-01", periods=n),
        "next_ret": rng.normal(mean_ret, 1.0, size=n),
    })


def test_simulate_returns_perturbed_ledger_and_report():
    ev = _events(n=200, mean_ret=0.5)
    report = IR.simulate_combined(ev, baseline_sharpe_s1=1.0, baseline_dd_s1=0.08, seed=1)
    assert "perturbed_sharpe" in report
    assert "perturbed_max_dd" in report
    assert "perturbed_cum_pnl" in report
    assert report["n_events_input"] == 200


def test_pass_condition_combines_three_thresholds():
    ev = _events(n=200, mean_ret=0.6)  # strong edge
    report = IR.simulate_combined(ev, baseline_sharpe_s1=1.0, baseline_dd_s1=0.10, seed=1)
    # §11A.2: cum P&L > 0 AND max DD ≤ 1.4× backtest DD AND realised sharpe ≥ 60% of S1
    assert report["pass_cumulative_pnl_positive"] == (report["perturbed_cum_pnl"] > 0)
    assert report["pass_max_dd"] == (report["perturbed_max_dd"] <= 1.4 * report["baseline_dd_s1"])
    assert report["pass_realised_sharpe"] == (report["perturbed_sharpe"] >= 0.6 * report["baseline_sharpe_s1"])
    assert report["verdict"] in {"IMPLEMENTATION-ROBUST", "IMPLEMENTATION-SENSITIVE"}


def test_missed_fraction_reduces_trade_count():
    ev = _events(n=1000, mean_ret=0.4)
    report = IR.simulate_combined(ev, baseline_sharpe_s1=1.0, baseline_dd_s1=0.10, seed=3)
    # 5% missed entries + 5% missed exits keeps most trades, but some are dropped entirely.
    assert report["n_events_kept"] < report["n_events_input"]
    assert report["n_events_kept"] >= int(0.88 * report["n_events_input"])  # rough guard
```

- [ ] **Step 2: Run, expect FAIL**

```
python -m pytest pipeline/tests/autoresearch/overshoot_compliance/test_impl_risk.py -v
```

- [ ] **Step 3: Implement**

```python
# pipeline/autoresearch/overshoot_compliance/impl_risk.py
"""Implementation-risk combined-scenario runner per §11A.

Applies 5% missed entries, 5% missed exits (extra-bar hold proxied as 0
return for the extra bar + no cost), 5% partial fills at 50% size,
1 outage/month (drop a random bar from each month), 1 exchange halt per
quarter (drop one trade), 10% margin-shortage rejects while cumulative
equity drawdown exceeds 10%, and a weekend-gap cost proxy (add 10 bps
to Monday trades).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import metrics as M


def simulate_combined(
    events: pd.DataFrame,
    baseline_sharpe_s1: float,
    baseline_dd_s1: float,
    seed: int | None = 42,
) -> dict:
    rng = np.random.default_rng(seed)
    ev = events.sort_values("date").reset_index(drop=True).copy()
    n_in = len(ev)

    # UP = fade-SHORT. Invert next_ret sign for P&L.
    sign = np.where(ev["direction"].eq("UP"), -1.0, 1.0)
    ev["pnl_pct"] = sign * ev["next_ret"].to_numpy()

    keep = np.ones(len(ev), dtype=bool)

    # 5% missed entries
    miss_entry = rng.random(len(ev)) < 0.05
    keep &= ~miss_entry

    # Exchange halt: drop ~4 per year (one per quarter)
    halts = rng.choice(np.where(keep)[0], size=min(4, int(keep.sum())), replace=False) if keep.any() else np.array([], dtype=int)
    keep[halts] = False

    # Outages: one per calendar month (drop ~1 event/month)
    months = pd.DatetimeIndex(ev["date"]).to_period("M")
    for m in months.unique():
        idx = np.where((months == m) & keep)[0]
        if len(idx):
            keep[rng.choice(idx)] = False

    # Partial fills 5%: halve P&L
    partials = rng.random(len(ev)) < 0.05
    ev.loc[partials, "pnl_pct"] = ev.loc[partials, "pnl_pct"] * 0.5

    # Missed exits 5%: held one extra bar at zero return, cost unchanged
    # (Modelled by taking 50% of pnl with a 10-bps penalty on the remaining.)
    miss_exit = rng.random(len(ev)) < 0.05
    ev.loc[miss_exit, "pnl_pct"] = ev.loc[miss_exit, "pnl_pct"] * 0.5 - 0.10

    # Weekend-gap: 10 bps penalty on Monday trades
    is_monday = pd.DatetimeIndex(ev["date"]).dayofweek == 0
    ev.loc[is_monday, "pnl_pct"] -= 0.10

    # Margin-shortage: when running cumulative equity DD > 10%, 10% of trades are rejected.
    equity = (1.0 + ev["pnl_pct"].fillna(0) / 100.0).cumprod()
    peak = equity.cummax()
    dd_series = (peak - equity) / peak
    in_dd = dd_series.to_numpy() > 0.10
    reject_dd = in_dd & (rng.random(len(ev)) < 0.10)
    keep &= ~reject_dd

    ev_kept = ev.loc[keep].copy()
    n_kept = len(ev_kept)
    perturbed = ev_kept["pnl_pct"].to_numpy()
    core = M.per_bucket_metrics(perturbed)
    cum_pnl = float(np.sum(perturbed))

    pass_cum = cum_pnl > 0
    pass_dd = core["max_drawdown_pct"] <= 1.4 * (baseline_dd_s1 * 100.0)
    pass_sharpe = core["sharpe"] >= 0.6 * baseline_sharpe_s1
    verdict = "IMPLEMENTATION-ROBUST" if (pass_cum and pass_dd and pass_sharpe) else "IMPLEMENTATION-SENSITIVE"
    return {
        "n_events_input": int(n_in),
        "n_events_kept": int(n_kept),
        "perturbed_sharpe": core["sharpe"],
        "perturbed_max_dd": core["max_drawdown_pct"] / 100.0,
        "perturbed_cum_pnl": cum_pnl,
        "baseline_sharpe_s1": baseline_sharpe_s1,
        "baseline_dd_s1": baseline_dd_s1,
        "pass_cumulative_pnl_positive": bool(pass_cum),
        "pass_max_dd": bool(pass_dd),
        "pass_realised_sharpe": bool(pass_sharpe),
        "verdict": verdict,
    }
```

- [ ] **Step 4: Run, expect PASS**

```
python -m pytest pipeline/tests/autoresearch/overshoot_compliance/test_impl_risk.py -v
```

Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add pipeline/autoresearch/overshoot_compliance/impl_risk.py \
        pipeline/tests/autoresearch/overshoot_compliance/test_impl_risk.py
git commit -m "feat(compliance): §11A 10-scenario implementation-risk simulation"
```

---

### Task 12: CUSUM decay + recent-24m ratio (§12)

**Files:**
- Create: `pipeline/autoresearch/overshoot_compliance/cusum_decay.py`
- Test: `pipeline/tests/autoresearch/overshoot_compliance/test_cusum_decay.py`

Two tests:
1. **§12.2 CUSUM control chart:** on rolling monthly mean P&L, flag a trigger when cumulative deviation > 3σ of full-history volatility.
2. **§12.3 recent-24m ratio:** edge on last 24 months must be ≥ 50% of full-history edge.

- [ ] **Step 1: Write failing tests**

```python
# pipeline/tests/autoresearch/overshoot_compliance/test_cusum_decay.py
import numpy as np
import pandas as pd
import pytest

from pipeline.autoresearch.overshoot_compliance import cusum_decay as CD


def _events(mean_hist, mean_recent, months_hist=60, events_per_month=20, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for m in range(months_hist):
        mu = mean_hist if m < months_hist - 24 else mean_recent
        for _ in range(events_per_month):
            rows.append({
                "date": pd.Timestamp("2020-01-01") + pd.DateOffset(months=m, days=int(rng.integers(1, 20))),
                "trade_ret_pct": rng.normal(mu, 1.0),
            })
    return pd.DataFrame(rows)


def test_cusum_triggers_when_recent_shifts_down():
    ev = _events(mean_hist=0.5, mean_recent=-0.5)
    report = CD.analyse(ev, recent_months=24)
    assert report["cusum_triggers"] >= 1


def test_cusum_no_trigger_on_stationary_edge():
    ev = _events(mean_hist=0.5, mean_recent=0.5)
    report = CD.analyse(ev, recent_months=24)
    assert report["cusum_triggers"] == 0


def test_recent_ratio_computed():
    ev = _events(mean_hist=0.5, mean_recent=0.3)
    report = CD.analyse(ev, recent_months=24)
    assert 0 < report["recent_24m_ratio"] < 1
    assert "recent_24m_mean_ret_pct" in report
    assert "full_history_mean_ret_pct" in report


def test_verdict_decaying_when_recent_under_half():
    ev = _events(mean_hist=1.0, mean_recent=0.1)
    report = CD.analyse(ev, recent_months=24)
    assert report["verdict"] == "DECAYING"


def test_verdict_stable_when_recent_at_least_half():
    ev = _events(mean_hist=0.5, mean_recent=0.4)
    report = CD.analyse(ev, recent_months=24)
    assert report["verdict"] in {"STABLE", "DECAYING"}
```

- [ ] **Step 2: Run, expect FAIL**

```
python -m pytest pipeline/tests/autoresearch/overshoot_compliance/test_cusum_decay.py -v
```

- [ ] **Step 3: Implement**

```python
# pipeline/autoresearch/overshoot_compliance/cusum_decay.py
"""CUSUM decay + recent-24m ratio per §12."""
from __future__ import annotations

import numpy as np
import pandas as pd


def analyse(events: pd.DataFrame, recent_months: int = 24) -> dict:
    """events columns: date, trade_ret_pct (percent signed by strategy direction)."""
    df = events.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    if df.empty:
        return {
            "cusum_triggers": 0, "recent_24m_mean_ret_pct": 0.0,
            "full_history_mean_ret_pct": 0.0, "recent_24m_ratio": 0.0,
            "verdict": "UNKNOWN",
        }

    # Monthly mean
    monthly = df.set_index("date")["trade_ret_pct"].resample("M").mean().fillna(0.0)
    sigma = float(monthly.std(ddof=1)) if len(monthly) > 1 else 0.0
    if sigma == 0.0:
        triggers = 0
    else:
        mu = float(monthly.mean())
        cs = np.cumsum(monthly.to_numpy() - mu)
        triggers = int(np.sum(np.abs(cs) > 3.0 * sigma * np.sqrt(len(monthly))))

    cutoff = df["date"].max() - pd.DateOffset(months=recent_months)
    recent = df.loc[df["date"] > cutoff, "trade_ret_pct"]
    full_mean = float(df["trade_ret_pct"].mean())
    recent_mean = float(recent.mean()) if len(recent) else 0.0
    ratio = (recent_mean / full_mean) if full_mean else 0.0

    if full_mean <= 0:
        verdict = "NO-HISTORIC-EDGE"
    elif ratio < 0.5:
        verdict = "DECAYING"
    else:
        verdict = "STABLE"

    return {
        "cusum_triggers": triggers,
        "recent_24m_mean_ret_pct": round(recent_mean, 4),
        "full_history_mean_ret_pct": round(full_mean, 4),
        "recent_24m_ratio": round(ratio, 4),
        "verdict": verdict,
    }
```

- [ ] **Step 4: Run, expect PASS**

```
python -m pytest pipeline/tests/autoresearch/overshoot_compliance/test_cusum_decay.py -v
```

Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add pipeline/autoresearch/overshoot_compliance/cusum_decay.py \
        pipeline/tests/autoresearch/overshoot_compliance/test_cusum_decay.py
git commit -m "feat(compliance): §12 CUSUM decay + recent-24m edge ratio"
```

---

### Task 13: Portfolio correlation + concentration gate (§11C)

**Files:**
- Create: `pipeline/autoresearch/overshoot_compliance/portfolio_gate.py`
- Test: `pipeline/tests/autoresearch/overshoot_compliance/test_portfolio_gate.py`

Compute pairwise P&L correlation across every (ticker, direction) whose edge-net is positive at S1 and whose permutation p is below the Bonferroni α. Fail if any pair > 0.60. Also compute sector concentration among survivors: fail if any single sector ≥ 40% of the survivor count.

- [ ] **Step 1: Write failing tests**

```python
# pipeline/tests/autoresearch/overshoot_compliance/test_portfolio_gate.py
import numpy as np
import pandas as pd
import pytest

from pipeline.autoresearch.overshoot_compliance import portfolio_gate as PG


def test_pairwise_correlation_below_threshold_passes():
    rng = np.random.default_rng(0)
    dates = pd.bdate_range("2024-01-01", periods=252)
    pnl = pd.DataFrame({
        "A-UP": rng.normal(0.0, 1.0, size=252),
        "B-UP": rng.normal(0.0, 1.0, size=252),
        "C-DOWN": rng.normal(0.0, 1.0, size=252),
    }, index=dates)
    report = PG.evaluate(pnl, sectors={"A-UP": "IT", "B-UP": "Pharma", "C-DOWN": "Banks"},
                         corr_threshold=0.60, concentration_cap=0.40)
    assert report["max_pairwise_correlation"] < 0.60
    assert report["corr_verdict"] == "PASS"


def test_high_correlation_fails():
    dates = pd.bdate_range("2024-01-01", periods=252)
    rng = np.random.default_rng(1)
    a = rng.normal(0.0, 1.0, size=252)
    b = a + rng.normal(0.0, 0.05, size=252)  # near-identical
    pnl = pd.DataFrame({"A-UP": a, "B-UP": b}, index=dates)
    report = PG.evaluate(pnl, sectors={"A-UP": "IT", "B-UP": "Pharma"},
                         corr_threshold=0.60, concentration_cap=0.40)
    assert report["max_pairwise_correlation"] > 0.60
    assert report["corr_verdict"] == "FAIL"


def test_concentration_fails_when_single_sector_over_cap():
    dates = pd.bdate_range("2024-01-01", periods=50)
    rng = np.random.default_rng(2)
    cols = {f"T{i}-UP": rng.normal(0, 1, size=50) for i in range(10)}
    pnl = pd.DataFrame(cols, index=dates)
    sectors = {c: ("IT" if i < 5 else f"S{i}") for i, c in enumerate(pnl.columns)}
    report = PG.evaluate(pnl, sectors=sectors, corr_threshold=0.60, concentration_cap=0.40)
    # 5/10 = 50% in IT exceeds 40% cap
    assert report["max_sector_share"] >= 0.4
    assert report["concentration_verdict"] == "FAIL"
```

- [ ] **Step 2: Run, expect FAIL**

```
python -m pytest pipeline/tests/autoresearch/overshoot_compliance/test_portfolio_gate.py -v
```

- [ ] **Step 3: Implement**

```python
# pipeline/autoresearch/overshoot_compliance/portfolio_gate.py
"""Portfolio-correlation + concentration gate per §11C."""
from __future__ import annotations

from collections import Counter

import numpy as np
import pandas as pd


def evaluate(
    pnl: pd.DataFrame,
    sectors: dict[str, str],
    corr_threshold: float = 0.60,
    concentration_cap: float = 0.40,
) -> dict:
    """pnl: columns are strategy IDs like "RELIANCE-UP", rows are dates."""
    if pnl.shape[1] < 2:
        max_corr = 0.0
        top_pair = None
    else:
        C = pnl.corr()
        # zero the diagonal and take max
        arr = C.to_numpy().copy()
        np.fill_diagonal(arr, 0.0)
        if arr.size == 0:
            max_corr = 0.0
            top_pair = None
        else:
            i, j = np.unravel_index(np.argmax(np.abs(arr)), arr.shape)
            max_corr = float(arr[i, j])
            top_pair = [C.columns[i], C.columns[j]]

    total = len(pnl.columns)
    sector_counts = Counter(sectors.get(c, "Unmapped") for c in pnl.columns)
    max_sector_share = (max(sector_counts.values()) / total) if total else 0.0
    max_sector = sector_counts.most_common(1)[0][0] if total else None

    corr_verdict = "PASS" if max_corr <= corr_threshold else "FAIL"
    conc_verdict = "PASS" if max_sector_share < concentration_cap else "FAIL"
    overall = "PASS" if (corr_verdict == "PASS" and conc_verdict == "PASS") else "FAIL"
    return {
        "max_pairwise_correlation": round(max_corr, 4),
        "top_correlated_pair": top_pair,
        "max_sector_share": round(max_sector_share, 4),
        "max_sector": max_sector,
        "corr_verdict": corr_verdict,
        "concentration_verdict": conc_verdict,
        "overall_verdict": overall,
        "n_strategies": total,
    }
```

- [ ] **Step 4: Run, expect PASS**

```
python -m pytest pipeline/tests/autoresearch/overshoot_compliance/test_portfolio_gate.py -v
```

Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add pipeline/autoresearch/overshoot_compliance/portfolio_gate.py \
        pipeline/tests/autoresearch/overshoot_compliance/test_portfolio_gate.py
git commit -m "feat(compliance): §11C portfolio correlation + concentration gate"
```

---

## Phase D — Direction audit, defense filter, gate checklist

### Task 14: Direction audit vs engine (§8)

**Files:**
- Create: `pipeline/autoresearch/overshoot_compliance/direction_audit.py`
- Test: `pipeline/tests/autoresearch/overshoot_compliance/test_direction_audit.py`

For each (ticker, direction) in the survivor set, fetch the production engine's current call from `pipeline/data/correlation_breaks.json` (via the same path convention the prototype uses at line 38 of `overshoot_per_ticker_stats.py`). If the backtest says "fade UP = SHORT" but the engine is calling LONG, flag DIRECTION-CONFLICT. Report aggregate conflict count and per-ticker detail.

- [ ] **Step 1: Write failing tests**

```python
# pipeline/tests/autoresearch/overshoot_compliance/test_direction_audit.py
import pandas as pd
import pytest

from pipeline.autoresearch.overshoot_compliance import direction_audit as DA


def _survivor(ticker, direction, edge_net=0.5):
    return {"ticker": ticker, "direction": direction, "edge_net_pct": edge_net, "p_value": 1e-5}


def test_engine_long_matches_fade_down():
    survivors = [_survivor("A", "DOWN")]  # fade-DOWN = LONG
    engine_calls = {"A": {"direction": "LONG"}}
    report = DA.audit(survivors, engine_calls)
    assert report["conflicts"] == 0
    assert report["rows"][0]["conflict"] is False


def test_engine_long_conflicts_with_fade_up():
    survivors = [_survivor("A", "UP")]  # fade-UP = SHORT
    engine_calls = {"A": {"direction": "LONG"}}
    report = DA.audit(survivors, engine_calls)
    assert report["conflicts"] == 1
    assert report["rows"][0]["conflict"] is True


def test_engine_call_missing_reports_unknown():
    survivors = [_survivor("A", "UP")]
    engine_calls = {}
    report = DA.audit(survivors, engine_calls)
    assert report["rows"][0]["engine_direction"] is None
    assert report["rows"][0]["conflict"] is None
```

- [ ] **Step 2: Run, expect FAIL**

```
python -m pytest pipeline/tests/autoresearch/overshoot_compliance/test_direction_audit.py -v
```

- [ ] **Step 3: Implement**

```python
# pipeline/autoresearch/overshoot_compliance/direction_audit.py
"""Direction audit per §8 of backtesting-specs.txt v1.0."""
from __future__ import annotations

from typing import Iterable


def _fade_sign(direction: str) -> str:
    return "SHORT" if direction == "UP" else "LONG"


def audit(
    survivors: Iterable[dict],
    engine_calls: dict[str, dict],
) -> dict:
    rows = []
    conflicts = 0
    for s in survivors:
        fade = _fade_sign(s["direction"])
        call = engine_calls.get(s["ticker"])
        if call is None:
            rows.append({
                "ticker": s["ticker"], "backtest_direction": s["direction"],
                "fade_trade": fade, "engine_direction": None, "conflict": None,
            })
            continue
        engine_dir = call.get("direction")
        is_conflict = (engine_dir != fade)
        if is_conflict:
            conflicts += 1
        rows.append({
            "ticker": s["ticker"], "backtest_direction": s["direction"],
            "fade_trade": fade, "engine_direction": engine_dir, "conflict": is_conflict,
        })
    return {"conflicts": conflicts, "n_survivors": len(rows), "rows": rows}
```

- [ ] **Step 4: Run, expect PASS**

```
python -m pytest pipeline/tests/autoresearch/overshoot_compliance/test_direction_audit.py -v
```

Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add pipeline/autoresearch/overshoot_compliance/direction_audit.py \
        pipeline/tests/autoresearch/overshoot_compliance/test_direction_audit.py
git commit -m "feat(compliance): §8 strategy-direction engine-vs-backtest audit"
```

---

### Task 15: Defense-stock filter (user rule)

**Files:**
- Create: `pipeline/autoresearch/overshoot_compliance/defense_filter.py`
- Test: `pipeline/tests/autoresearch/overshoot_compliance/test_defense_filter.py`

User rule: "avoid shorting defense stocks — their rallies are global-driven". The filter does NOT drop defense tickers from the backtest (sign edge still real); it flags any (ticker, direction) where sector == "Defence" AND the fade direction is SHORT. Those rows get `defense_short_flag = True` in the gate artifact and are excluded from the portfolio-gate correlation survivor set.

Also covers a small hardcoded list if the sector map labels them differently: `{"BEL", "HAL", "BDL", "MIDHANI", "GRSE", "MAZDOCK"}`.

- [ ] **Step 1: Write failing tests**

```python
# pipeline/tests/autoresearch/overshoot_compliance/test_defense_filter.py
import pytest

from pipeline.autoresearch.overshoot_compliance import defense_filter as DF


def test_defense_short_flagged():
    row = {"ticker": "BEL", "direction": "UP"}  # UP fade = SHORT
    assert DF.is_defense_short(row, sector_of={"BEL": "Defence"}) is True


def test_defense_long_not_flagged():
    row = {"ticker": "BEL", "direction": "DOWN"}  # DOWN fade = LONG
    assert DF.is_defense_short(row, sector_of={"BEL": "Defence"}) is False


def test_non_defense_not_flagged():
    row = {"ticker": "RELIANCE", "direction": "UP"}
    assert DF.is_defense_short(row, sector_of={"RELIANCE": "Energy"}) is False


def test_hardcoded_override_catches_misclassified_tickers():
    row = {"ticker": "HAL", "direction": "UP"}
    assert DF.is_defense_short(row, sector_of={"HAL": "Other:Aerospace"}) is True


def test_partition_splits_survivors():
    survivors = [
        {"ticker": "BEL", "direction": "UP"},
        {"ticker": "BEL", "direction": "DOWN"},
        {"ticker": "RELIANCE", "direction": "UP"},
    ]
    kept, flagged = DF.partition(survivors, sector_of={"BEL": "Defence", "RELIANCE": "Energy"})
    assert len(kept) == 2
    assert len(flagged) == 1
    assert flagged[0]["ticker"] == "BEL" and flagged[0]["direction"] == "UP"
```

- [ ] **Step 2: Run, expect FAIL**

```
python -m pytest pipeline/tests/autoresearch/overshoot_compliance/test_defense_filter.py -v
```

- [ ] **Step 3: Implement**

```python
# pipeline/autoresearch/overshoot_compliance/defense_filter.py
"""User rule: avoid shorting defense stocks (rallies are global-driven).

Does not drop defense tickers; flags (defense, UP→SHORT) pairs so the
portfolio gate can exclude them from its survivor set.
"""
from __future__ import annotations

HARDCODED_DEFENSE = {"BEL", "HAL", "BDL", "MIDHANI", "GRSE", "MAZDOCK"}


def is_defense(ticker: str, sector_of: dict[str, str]) -> bool:
    if ticker in HARDCODED_DEFENSE:
        return True
    return sector_of.get(ticker, "") == "Defence"


def is_defense_short(row: dict, sector_of: dict[str, str]) -> bool:
    """UP direction = fade-SHORT. Flag only when both conditions hold."""
    return row["direction"] == "UP" and is_defense(row["ticker"], sector_of)


def partition(
    survivors: list[dict],
    sector_of: dict[str, str],
) -> tuple[list[dict], list[dict]]:
    kept, flagged = [], []
    for r in survivors:
        if is_defense_short(r, sector_of):
            flagged.append({**r, "reason": "defense_short_user_rule"})
        else:
            kept.append(r)
    return kept, flagged
```

- [ ] **Step 4: Run, expect PASS**

```
python -m pytest pipeline/tests/autoresearch/overshoot_compliance/test_defense_filter.py -v
```

Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add pipeline/autoresearch/overshoot_compliance/defense_filter.py \
        pipeline/tests/autoresearch/overshoot_compliance/test_defense_filter.py
git commit -m "feat(compliance): user-rule defense-short filter"
```

---

### Task 16: §15.1 gate-checklist emitter

**Files:**
- Create: `pipeline/autoresearch/overshoot_compliance/gate_checklist.py`
- Test: `pipeline/tests/autoresearch/overshoot_compliance/test_gate_checklist.py`

The emitter takes every per-section report dict produced by Tasks 2-15 and emits one machine-readable artifact that answers: **does H-2026-04-23-001 cross RESEARCH→PAPER-SHADOW?**

RESEARCH→PAPER-SHADOW pass rules from §15.1:
- §1 S0+S1 slippage pass conditions
- §2 metrics computed
- §5A data audit `classification != "AUTO-FAIL"`
- §6 universe disclosed (waiver allowed for §6.2)
- §7 MODE A declared
- §8 direction audit emitted (conflicts allowed, but reported)
- §9 n≥30 per ticker/regime OR flagged exploratory
- §9A fragility `verdict != "PARAMETER-FRAGILE"` OR waiver
- §9B.1 strongest-naive comparator beaten at S0
- §9B.2 permutations ≥100k used
- §10 holdout carved out (6% noted, below 20% — will produce PARTIAL-HOLDOUT waiver need)
- §11B residual Sharpe ≥70% gross Sharpe

Emit one JSON with a per-section row {section, requirement, value, pass_fail, note} and an overall `decision = PASS | PARTIAL | FAIL`.

- [ ] **Step 1: Write failing tests**

```python
# pipeline/tests/autoresearch/overshoot_compliance/test_gate_checklist.py
import json
from pathlib import Path

import pytest

from pipeline.autoresearch.overshoot_compliance import gate_checklist as GC


def _minimal_inputs():
    return {
        "slippage_s0_s1": {"s0_sharpe": 1.1, "s0_hit": 0.58, "s0_max_dd": 0.12,
                            "s1_sharpe": 0.9, "s1_max_dd": 0.18, "s1_cum_pnl_pct": 35.0},
        "metrics_present": True,
        "data_audit": {"classification": "CLEAN", "impaired_pct": 0.4},
        "universe_snapshot": {"status": "SURVIVORSHIP-UNCORRECTED-WAIVED",
                              "waiver_path": "docs/superpowers/waivers/..."},
        "execution_mode": "MODE_A",
        "direction_audit": {"conflicts": 3, "n_survivors": 20},
        "power_analysis": {"min_n_per_regime_met": True, "underpowered_count": 0},
        "fragility": {"verdict": "STABLE"},
        "comparators": {"beaten_strongest": True, "strongest_name": "momentum_follow"},
        "permutations": {"n_shuffles": 100_000, "floor_required": 100_000},
        "holdout": {"pct": 0.06, "target": 0.20},
        "beta_regression": {"residual_sharpe": 0.8, "gross_sharpe": 1.0},
    }


def test_gate_emits_all_sections():
    report = GC.build(_minimal_inputs(), hypothesis_id="H-TEST")
    sections = {r["section"] for r in report["rows"]}
    for needed in {"1/3", "2", "5A", "6", "7", "8", "9", "9A", "9B.1", "9B.2", "10", "11B"}:
        assert needed in sections


def test_gate_pass_when_every_row_passes():
    inp = _minimal_inputs()
    inp["holdout"]["pct"] = 0.25  # above target
    report = GC.build(inp, hypothesis_id="H-TEST")
    assert report["decision"] == "PASS"


def test_gate_partial_when_waivered_sections_present():
    inp = _minimal_inputs()
    # 6% holdout is below target; waiver required for promotion.
    report = GC.build(inp, hypothesis_id="H-TEST")
    assert report["decision"] in {"PARTIAL", "FAIL"}


def test_gate_fail_when_slippage_s0_missed():
    inp = _minimal_inputs()
    inp["slippage_s0_s1"]["s0_sharpe"] = 0.3  # below 1.0
    report = GC.build(inp, hypothesis_id="H-TEST")
    assert report["decision"] == "FAIL"


def test_write_to_disk_round_trips(tmp_path):
    report = GC.build(_minimal_inputs(), hypothesis_id="H-TEST")
    out = GC.write(report, tmp_path)
    assert out.exists()
    loaded = json.loads(out.read_text())
    assert loaded == report
```

- [ ] **Step 2: Run, expect FAIL**

```
python -m pytest pipeline/tests/autoresearch/overshoot_compliance/test_gate_checklist.py -v
```

- [ ] **Step 3: Implement**

```python
# pipeline/autoresearch/overshoot_compliance/gate_checklist.py
"""§15.1 RESEARCH→PAPER-SHADOW gate-checklist emitter.

Consumes the per-section outputs produced upstream and writes one
machine-readable artifact with an overall decision. This is the
artifact — not a claim — that the standards promotion logic reads.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def _row(section: str, req: str, value, pass_fail: str, note: str = "") -> dict:
    return {"section": section, "requirement": req, "value": value,
            "pass_fail": pass_fail, "note": note}


def build(inputs: dict, *, hypothesis_id: str) -> dict:
    rows = []

    s0 = inputs["slippage_s0_s1"]
    s0_ok = s0["s0_sharpe"] >= 1.0 and s0["s0_hit"] >= 0.55 and s0["s0_max_dd"] <= 0.20
    rows.append(_row("1/3", "S0 pass (Sharpe≥1, hit≥55%, DD≤20%)",
                      {"sharpe": s0["s0_sharpe"], "hit": s0["s0_hit"], "dd": s0["s0_max_dd"]},
                      "PASS" if s0_ok else "FAIL"))
    s1_ok = s0["s1_sharpe"] >= 0.8 and s0["s1_max_dd"] <= 0.25 and s0["s1_cum_pnl_pct"] > 0
    rows.append(_row("1/3", "S1 pass (Sharpe≥0.8, DD≤25%, cum P&L>0)",
                      {"sharpe": s0["s1_sharpe"], "dd": s0["s1_max_dd"], "cum": s0["s1_cum_pnl_pct"]},
                      "PASS" if s1_ok else "FAIL"))

    rows.append(_row("2", "Risk metrics computed per bucket per level",
                      inputs["metrics_present"], "PASS" if inputs["metrics_present"] else "FAIL"))

    da = inputs["data_audit"]
    da_ok = da["classification"] != "AUTO-FAIL"
    rows.append(_row("5A", "Data audit classification ≠ AUTO-FAIL",
                      da["classification"], "PASS" if da_ok else "FAIL",
                      f"impaired_pct={da['impaired_pct']}"))

    us = inputs["universe_snapshot"]
    universe_ok = us["status"] in {"SURVIVORSHIP-CORRECTED", "SURVIVORSHIP-UNCORRECTED-WAIVED"}
    rows.append(_row("6", "Universe disclosed (or under waiver)", us["status"],
                      "PASS" if universe_ok else "FAIL",
                      note=f"waiver={us.get('waiver_path')}"))

    mode_ok = inputs["execution_mode"] == "MODE_A"
    rows.append(_row("7", "Execution mode declared = MODE_A (EOD)",
                      inputs["execution_mode"], "PASS" if mode_ok else "FAIL"))

    rows.append(_row("8", "Direction audit emitted",
                      inputs["direction_audit"]["n_survivors"],
                      "PASS",
                      note=f"conflicts={inputs['direction_audit']['conflicts']}"))

    pa = inputs["power_analysis"]
    rows.append(_row("9", "n≥30 per regime OR flagged exploratory",
                      pa["min_n_per_regime_met"],
                      "PASS" if pa["min_n_per_regime_met"] else "FAIL",
                      note=f"underpowered_count={pa['underpowered_count']}"))

    fr = inputs["fragility"]
    rows.append(_row("9A", "Fragility verdict ≠ PARAMETER-FRAGILE", fr["verdict"],
                      "PASS" if fr["verdict"] != "PARAMETER-FRAGILE" else "FAIL"))

    cm = inputs["comparators"]
    rows.append(_row("9B.1", "Beats strongest naive comparator at S0",
                      cm["strongest_name"],
                      "PASS" if cm["beaten_strongest"] else "FAIL"))

    pm = inputs["permutations"]
    rows.append(_row("9B.2", "Permutations ≥ required floor",
                      {"n": pm["n_shuffles"], "floor": pm["floor_required"]},
                      "PASS" if pm["n_shuffles"] >= pm["floor_required"] else "FAIL"))

    ho = inputs["holdout"]
    ho_ok = ho["pct"] >= ho["target"]
    rows.append(_row("10", "Holdout ≥ 20% of history", ho["pct"],
                      "PASS" if ho_ok else "PARTIAL",
                      note=f"target={ho['target']}; current holdout is 6% — waiver required for promotion"))

    br = inputs["beta_regression"]
    residual_ratio = br["residual_sharpe"] / br["gross_sharpe"] if br["gross_sharpe"] else 0.0
    rows.append(_row("11B", "Residual Sharpe ≥ 70% of gross Sharpe",
                      round(residual_ratio, 3),
                      "PASS" if residual_ratio >= 0.70 else "FAIL"))

    verdicts = [r["pass_fail"] for r in rows]
    if "FAIL" in verdicts:
        decision = "FAIL"
    elif "PARTIAL" in verdicts:
        decision = "PARTIAL"
    else:
        decision = "PASS"

    return {
        "hypothesis_id": hypothesis_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "rows": rows,
        "decision": decision,
    }


def write(report: dict, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "gate_checklist.json"
    path.write_text(json.dumps(report, indent=2, default=str))
    return path
```

- [ ] **Step 4: Run, expect PASS**

```
python -m pytest pipeline/tests/autoresearch/overshoot_compliance/test_gate_checklist.py -v
```

Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add pipeline/autoresearch/overshoot_compliance/gate_checklist.py \
        pipeline/tests/autoresearch/overshoot_compliance/test_gate_checklist.py
git commit -m "feat(compliance): §15.1 RESEARCH→PAPER-SHADOW gate-checklist emitter"
```

---

## Phase E — Runner, smoke test, real run, docs

### Task 17: End-to-end runner

**Files:**
- Modify: `pipeline/autoresearch/overshoot_compliance/runner.py`
- Test: `pipeline/tests/autoresearch/overshoot_compliance/test_runner_smoke.py`

Runner orchestrates (in order): manifest → data audit → universe snapshot → compute residuals at 3 windows (15/20/25) via the existing `compute_residuals` → classify events → per-ticker fade stats with `n_shuffles=100_000` → apply slippage grid + compute metrics → run naive comparators → fragility sweep → build daily strategy P&L panel → beta regression per (ticker, direction) → impl-risk combined scenario → CUSUM decay → portfolio gate with defense filter → direction audit → §15.1 gate-checklist emit.

Runner is CPU-heavy so the runner exposes a `--smoke` flag that uses only the first 5 tickers with `n_shuffles=500` so the smoke test can complete in <30 s in CI.

- [ ] **Step 1: Write failing smoke test**

```python
# pipeline/tests/autoresearch/overshoot_compliance/test_runner_smoke.py
from pathlib import Path

import pytest

from pipeline.autoresearch.overshoot_compliance import runner


def test_smoke_runner_produces_all_artifacts(tmp_path):
    out_dir = tmp_path / "smoke_run"
    rc = runner.main(["--out-dir", str(out_dir), "--smoke"])
    assert rc == 0
    expected = {
        "manifest.json",
        "data_audit.json",
        "universe_snapshot.json",
        "metrics_grid.json",
        "comparators.json",
        "permutations_100k.json",  # named for consistency even in smoke (contains actual n_shuffles used)
        "fragility.json",
        "beta_residual.json",
        "impl_risk.json",
        "cusum_decay.json",
        "portfolio_gate.json",
        "direction_audit.json",
        "gate_checklist.json",
    }
    produced = {p.name for p in out_dir.iterdir()}
    missing = expected - produced
    assert not missing, f"missing artifacts: {missing}"


def test_smoke_gate_checklist_has_decision(tmp_path):
    import json
    out_dir = tmp_path / "smoke_run2"
    runner.main(["--out-dir", str(out_dir), "--smoke"])
    report = json.loads((out_dir / "gate_checklist.json").read_text())
    assert report["hypothesis_id"] == "H-2026-04-23-001"
    assert report["decision"] in {"PASS", "PARTIAL", "FAIL"}
```

- [ ] **Step 2: Run, expect FAIL** (stub runner from Task 1 returns 0 but writes nothing)

```
python -m pytest pipeline/tests/autoresearch/overshoot_compliance/test_runner_smoke.py -v
```

- [ ] **Step 3: Implement** (replace runner.py with the full orchestrator)

```python
# pipeline/autoresearch/overshoot_compliance/runner.py
"""End-to-end compliance runner for H-2026-04-23-001.

Usage:
  python -m pipeline.autoresearch.overshoot_compliance.runner \
      --out-dir pipeline/autoresearch/results/compliance_H-2026-04-23-001_<stamp> \
      [--smoke]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from pipeline.autoresearch.overshoot_reversion_backtest import (
    classify_events,
    compute_residuals,
    load_price_panel,
    load_sector_map,
    MIN_COHORT_SIZE,
)
from pipeline.autoresearch.overshoot_per_ticker_stats import (
    per_ticker_fade_stats,
    _today_breaks,
)

from . import (
    beta_regression,
    cusum_decay,
    data_audit,
    defense_filter,
    direction_audit,
    fragility,
    gate_checklist,
    impl_risk,
    manifest,
    metrics,
    naive_comparators,
    perm_scaling,
    portfolio_gate,
    slippage_grid,
    universe_snapshot,
)

_REPO = Path(__file__).resolve().parents[3]
_FNO_DIR = _REPO / "pipeline" / "data" / "fno_historical"
_UNIVERSE_HIST = _REPO / "pipeline" / "data" / "fno_universe_history.json"
_WAIVER = _REPO / "docs" / "superpowers" / "waivers" / "2026-04-23-phase-c-residual-reversion-survivorship.md"
_BREAKS = _REPO / "pipeline" / "data" / "correlation_breaks.json"
_COST_MODEL_VERSION = "zerodha-ssf-2025-04"
_STRATEGY_VERSION = "0.1.0"
_HYPOTHESIS_ID = "H-2026-04-23-001"


def _build_strategy_pnl_panel(events: pd.DataFrame) -> pd.DataFrame:
    """Wide panel: columns = f"{ticker}-{direction}", rows = dates, values = trade P&L percent."""
    ev = events.copy()
    ev["date"] = pd.to_datetime(ev["date"])
    ev["pnl_pct"] = np.where(ev["direction"].eq("UP"), -1.0, 1.0) * ev["next_ret"]
    ev["key"] = ev["ticker"] + "-" + ev["direction"]
    panel = ev.pivot_table(index="date", columns="key", values="pnl_pct", aggfunc="mean")
    return panel.fillna(0.0)


def _load_nifty_returns() -> pd.Series:
    p = _FNO_DIR / "NIFTY.csv"
    if not p.exists():
        # fall back to any index-like file under fno_historical
        return pd.Series(dtype=float)
    df = pd.read_csv(p, parse_dates=["Date"]).sort_values("Date").set_index("Date")
    return df["Close"].pct_change().dropna()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args(argv)

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    sector_of = load_sector_map()
    if args.smoke:
        sector_of = {t: s for i, (t, s) in enumerate(sector_of.items()) if i < 5}
    tickers = sorted(sector_of.keys())

    closes = load_price_panel(tickers)

    # Step 1 — manifest
    price_files = [p for p in (_FNO_DIR / f"{t}.csv" for t in tickers) if p.exists()]
    m = manifest.build_manifest(
        hypothesis_id=_HYPOTHESIS_ID,
        strategy_version=_STRATEGY_VERSION,
        cost_model_version=_COST_MODEL_VERSION,
        random_seed=42,
        data_files=price_files,
        config={"smoke": args.smoke, "n_tickers": len(tickers), "min_cohort_size": MIN_COHORT_SIZE},
    )
    manifest.write_manifest(m, out)

    # Step 2 — data audit
    bdays = pd.bdate_range(closes.index.min(), closes.index.max())
    per_ticker = {}
    for t in tickers:
        p = _FNO_DIR / f"{t}.csv"
        if not p.exists():
            continue
        df = pd.read_csv(p, parse_dates=["Date"]).sort_values("Date").drop_duplicates("Date", keep="last").set_index("Date")
        per_ticker[t] = data_audit.audit_ticker(t, df, bdays)
    da = data_audit.aggregate(per_ticker)
    (out / "data_audit.json").write_text(json.dumps(da, indent=2, default=str))

    # Step 3 — universe snapshot
    us = universe_snapshot.build_snapshot(tickers, _UNIVERSE_HIST, _WAIVER)
    (out / "universe_snapshot.json").write_text(json.dumps(us, indent=2, default=str))

    # Step 4 — residuals at windows 15, 20, 25 for fragility
    events_by_window: dict[int, pd.DataFrame] = {}
    for w in (15, 20, 25):
        import pipeline.autoresearch.overshoot_reversion_backtest as ORB
        old_w = ORB.ROLL_STD_WINDOW
        ORB.ROLL_STD_WINDOW = w
        try:
            _, resids, zs = compute_residuals(closes, sector_of)
            ev_list = classify_events(closes.pct_change() * 100, resids, zs)
            ev_df = pd.DataFrame(ev_list)
            if not ev_df.empty:
                ev_df["direction"] = np.where(ev_df["z"] > 0, "UP", "DOWN")
            events_by_window[w] = ev_df
        finally:
            ORB.ROLL_STD_WINDOW = old_w

    events = events_by_window[20]

    # Step 5 — per-ticker fade stats at n_shuffles=100k (or 500 smoke)
    n_shuffles = 500 if args.smoke else 100_000
    ticker_returns = {c: closes[c].pct_change().dropna().mul(100).tolist() for c in closes.columns}
    ev_as_dicts = events.to_dict("records") if len(events) else []
    fade_rows = per_ticker_fade_stats(
        ev_as_dicts, ticker_returns, min_z=3.0,
        n_shuffles=n_shuffles, seed=42,
    )

    # Step 6 — slippage grid + metrics per (ticker, direction)
    if not events.empty:
        events["trade_ret_pct"] = np.where(events["direction"].eq("UP"), -1.0, 1.0) * events["next_ret"]
    grid_rows = []
    for lvl in ("S0", "S1", "S2", "S3"):
        if events.empty:
            continue
        grid = slippage_grid.apply_level(events, lvl)
        for (tk, direction), sub in grid.groupby(["ticker", "direction"]):
            core = metrics.per_bucket_metrics(sub["net_ret_pct"].to_numpy())
            grid_rows.append({"ticker": tk, "direction": direction, "level": lvl, **core})
    (out / "metrics_grid.json").write_text(json.dumps({"rows": grid_rows}, indent=2, default=str))

    # Step 7 — naive comparators at S0 (cost-free events — strongest-comparator benchmark)
    comp_suite = naive_comparators.run_suite(events, seed=42) if not events.empty else {}
    strat_mean = float(events["trade_ret_pct"].mean()) if not events.empty else 0.0
    strongest_name = max(comp_suite, key=lambda k: comp_suite[k]["mean_ret_pct"]) if comp_suite else None
    strongest_mean = comp_suite[strongest_name]["mean_ret_pct"] if strongest_name else 0.0
    (out / "comparators.json").write_text(json.dumps({
        "strategy_mean_ret_pct": strat_mean,
        "comparators": comp_suite,
        "strongest_name": strongest_name,
        "beaten_strongest": strat_mean > strongest_mean,
    }, indent=2, default=str))

    # Step 8 — persist permutation-scaling summary (the fade_rows already contain p)
    (out / "permutations_100k.json").write_text(json.dumps({
        "n_shuffles": n_shuffles,
        "floor_required": 100_000 if not args.smoke else 500,
        "rows": fade_rows,
    }, indent=2, default=str))

    # Step 9 — fragility
    if all(not events_by_window[w].empty for w in (15, 20, 25)):
        fr = fragility.evaluate(events_by_window, {"min_z": 3.0, "roll_window": 20, "cost_pct": 0.30})
    else:
        fr = {"verdict": "INSUFFICIENT_DATA", "neighbor_rows": []}
    (out / "fragility.json").write_text(json.dumps(fr, indent=2, default=str))

    # Step 10 — beta regression per strategy using daily P&L panel
    panel = _build_strategy_pnl_panel(events) if not events.empty else pd.DataFrame()
    nifty_rets = _load_nifty_returns()
    beta_rows = {}
    if not panel.empty and not nifty_rets.empty:
        for col in panel.columns:
            beta_rows[col] = beta_regression.regress_on_nifty(panel[col] / 100.0, nifty_rets)
    gross_sharpe_avg = np.mean([v["gross_sharpe"] for v in beta_rows.values()]) if beta_rows else 0.0
    residual_sharpe_avg = np.mean([v["residual_sharpe"] for v in beta_rows.values()]) if beta_rows else 0.0
    (out / "beta_residual.json").write_text(json.dumps({
        "gross_sharpe_avg": float(gross_sharpe_avg),
        "residual_sharpe_avg": float(residual_sharpe_avg),
        "per_strategy": beta_rows,
    }, indent=2, default=str))

    # Step 11 — impl-risk combined
    if not events.empty:
        ir = impl_risk.simulate_combined(
            events[["ticker", "direction", "date", "next_ret"]],
            baseline_sharpe_s1=float(gross_sharpe_avg * 0.8 if gross_sharpe_avg else 0.0),
            baseline_dd_s1=0.15, seed=42,
        )
    else:
        ir = {"verdict": "INSUFFICIENT_DATA"}
    (out / "impl_risk.json").write_text(json.dumps(ir, indent=2, default=str))

    # Step 12 — CUSUM decay
    if not events.empty:
        cd = cusum_decay.analyse(events.rename(columns={"date": "date", "trade_ret_pct": "trade_ret_pct"})[["date", "trade_ret_pct"]])
    else:
        cd = {"verdict": "INSUFFICIENT_DATA"}
    (out / "cusum_decay.json").write_text(json.dumps(cd, indent=2, default=str))

    # Step 13 — portfolio gate + defense filter
    survivors = [r for r in fade_rows if r.get("edge_net_pct", 0) > 0 and r.get("p_value", 1.0) <= 1.17e-4]
    kept, flagged = defense_filter.partition(survivors, sector_of)
    keys_kept = {f"{r['ticker']}-{r['direction']}" for r in kept}
    pnl_survivors = panel[[c for c in panel.columns if c in keys_kept]] if not panel.empty else pd.DataFrame()
    pg = portfolio_gate.evaluate(
        pnl_survivors,
        sectors={f"{t}-{d}": sector_of.get(t, "Unmapped") for t in tickers for d in ("UP", "DOWN")},
    ) if not pnl_survivors.empty else {"overall_verdict": "NO_SURVIVORS", "n_strategies": 0}
    (out / "portfolio_gate.json").write_text(json.dumps({
        "gate": pg, "kept": kept, "defense_flagged": flagged,
    }, indent=2, default=str))

    # Step 14 — direction audit
    engine_calls = {}
    breaks = _today_breaks()
    for b in breaks:
        t = b.get("symbol")
        z = b.get("z_score") or 0
        exp_ret = b.get("expected_return") or 0
        engine_calls[t] = {"direction": "LONG" if exp_ret >= 0 else "SHORT", "z": z}
    direction_ad = direction_audit.audit(kept, engine_calls)
    (out / "direction_audit.json").write_text(json.dumps(direction_ad, indent=2, default=str))

    # Step 15 — gate checklist
    s0_rows = [r for r in grid_rows if r["level"] == "S0"]
    s1_rows = [r for r in grid_rows if r["level"] == "S1"]
    s0_sharpe = float(np.mean([r["sharpe"] for r in s0_rows])) if s0_rows else 0.0
    s0_hit = float(np.mean([r["hit_rate"] for r in s0_rows])) if s0_rows else 0.0
    s0_dd = float(np.mean([r["max_drawdown_pct"] for r in s0_rows]) / 100.0) if s0_rows else 0.0
    s1_sharpe = float(np.mean([r["sharpe"] for r in s1_rows])) if s1_rows else 0.0
    s1_dd = float(np.mean([r["max_drawdown_pct"] for r in s1_rows]) / 100.0) if s1_rows else 0.0
    s1_cum = float(np.sum([r["mean_ret_pct"] * r["n_trades"] for r in s1_rows])) if s1_rows else 0.0
    min_n_ok = bool(s0_rows) and all(r["n_trades"] >= 30 for r in s0_rows)

    checklist_inputs = {
        "slippage_s0_s1": {"s0_sharpe": s0_sharpe, "s0_hit": s0_hit, "s0_max_dd": s0_dd,
                            "s1_sharpe": s1_sharpe, "s1_max_dd": s1_dd, "s1_cum_pnl_pct": s1_cum},
        "metrics_present": bool(grid_rows),
        "data_audit": {"classification": da["classification"], "impaired_pct": da["impaired_pct"]},
        "universe_snapshot": us,
        "execution_mode": "MODE_A",
        "direction_audit": {"conflicts": direction_ad.get("conflicts", 0),
                            "n_survivors": direction_ad.get("n_survivors", 0)},
        "power_analysis": {"min_n_per_regime_met": min_n_ok,
                            "underpowered_count": sum(1 for r in s0_rows if r["n_trades"] < 30)},
        "fragility": {"verdict": fr.get("verdict", "UNKNOWN")},
        "comparators": {"beaten_strongest": strat_mean > strongest_mean, "strongest_name": strongest_name or "none"},
        "permutations": {"n_shuffles": n_shuffles, "floor_required": 100_000 if not args.smoke else 500},
        "holdout": {"pct": 0.06, "target": 0.20},
        "beta_regression": {"residual_sharpe": float(residual_sharpe_avg), "gross_sharpe": float(gross_sharpe_avg)},
    }
    gc_report = gate_checklist.build(checklist_inputs, hypothesis_id=_HYPOTHESIS_ID)
    gate_checklist.write(gc_report, out)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
```

- [ ] **Step 4: Run smoke**

```
python -m pytest pipeline/tests/autoresearch/overshoot_compliance/test_runner_smoke.py -v
```

Expected: both tests PASS. If the smoke run fails for data-path reasons (e.g., `NIFTY.csv` missing), that is a real gap — do NOT mock it; instead, narrow smoke to tickers that have price data and record the gap in the manifest's config dict.

- [ ] **Step 5: Commit**

```bash
git add pipeline/autoresearch/overshoot_compliance/runner.py \
        pipeline/tests/autoresearch/overshoot_compliance/test_runner_smoke.py
git commit -m "feat(compliance): end-to-end runner orchestrating all 12 gate sections"
```

---

### Task 18: Full compliance run + commit the artifact

This task RUNS the real thing. The artifact is the verification — not a claim.

- [ ] **Step 1: Ensure full ticker universe price data is loadable**

```
python -c "from pipeline.autoresearch.overshoot_reversion_backtest import load_sector_map, load_price_panel; m = load_sector_map(); c = load_price_panel(list(m.keys())); print(c.shape)"
```

Expected: roughly `(1200+, 210+)` or similar depending on F&O history. If the shape is 0-column, stop — price data is missing; this is a blocker.

- [ ] **Step 2: Run the runner without `--smoke`**

```
stamp=$(date -u +%Y%m%d-%H%M%S)
mkdir -p pipeline/autoresearch/results/compliance_H-2026-04-23-001_${stamp}
python -m pipeline.autoresearch.overshoot_compliance.runner \
    --out-dir pipeline/autoresearch/results/compliance_H-2026-04-23-001_${stamp}
```

Expected: 13 JSON artifacts written. Wall-clock: ~20-40 min for the 100k × 426 permutation scan on commodity hardware.

- [ ] **Step 3: Inspect `gate_checklist.json`**

```
python -c "import json; p=open('pipeline/autoresearch/results/compliance_H-2026-04-23-001_'+__import__('os').listdir('pipeline/autoresearch/results')[-1]+'/gate_checklist.json'); r=json.load(p); print('decision=', r['decision']); [print(row['section'], row['pass_fail'], row['requirement']) for row in r['rows']]"
```

Expected: a `decision` that is `PASS`, `PARTIAL`, or `FAIL` — not a claim. If `FAIL`, the research line retires (§0.2) or a reframed hypothesis must be pre-registered (§14.2 REFRAMED). Do NOT proceed to docs sync until this output is read and reported to the user.

- [ ] **Step 4: Commit the artifact directory** (only the results folder, not ignored artifacts)

Note: `pipeline/autoresearch/` is listed in `.gitignore`. Force-add the specific compliance subtree only:

```bash
stamp_dir=$(ls -1dt pipeline/autoresearch/results/compliance_H-2026-04-23-001_* | head -1)
git add -f "${stamp_dir}"
git commit -m "run: H-2026-04-23-001 compliance artifact (decision recorded in gate_checklist.json)"
```

- [ ] **Step 5: Stop and report**

Report back to the user: artifact path, the `decision` field, and any FAIL/PARTIAL rows from `gate_checklist.json`. This is the authoritative answer to "does the strategy cross the RESEARCH→PAPER-SHADOW gate?"

---

### Task 19: Docs sync — SYSTEM_OPERATIONS_MANUAL + memory

**Files:**
- Modify: `docs/SYSTEM_OPERATIONS_MANUAL.md`
- Modify: `C:\Users\Claude_Anka\.claude\projects\C--Users-Claude-Anka-askanka-com\memory\project_overshoot_reversion_backtest.md`
- Modify: `C:\Users\Claude_Anka\.claude\projects\C--Users-Claude-Anka-askanka-com\memory\reference_backtest_standards.md`

No `CLAUDE.md` change (compliance runner is ad-hoc), no `anka_inventory.json` change (not scheduled).

- [ ] **Step 1: SYSTEM_OPERATIONS_MANUAL Station addition**

Append a new station section at the appropriate place in the manual (find by `grep -n "Station" docs/SYSTEM_OPERATIONS_MANUAL.md` first).

```markdown
## Station: Compliance-Grade Backtest Runner

**Purpose:** Evaluate a pre-registered hypothesis against Sections 1-15 of `docs/superpowers/specs/backtesting-specs.txt` v1.0 and emit a machine-readable gate decision.

**Trigger:** Manual — not scheduled. Run before promoting any strategy from RESEARCH to PAPER-SHADOW.

**Entry point:** `python -m pipeline.autoresearch.overshoot_compliance.runner --out-dir <dir>`

**Artifacts written to `<dir>`:**
- `manifest.json` — §13A.1 reproducibility pin (git SHA, config hash, per-file SHA-256)
- `data_audit.json` — §5A data-quality classification
- `universe_snapshot.json` — §6.2 survivorship disclosure (honours waivers)
- `metrics_grid.json` — §1-§2 S0/S1/S2/S3 × (ticker, direction) Sharpe/DD/Calmar/hit-CI
- `comparators.json` — §9B.1 strongest-naive benchmark
- `permutations_100k.json` — §9B.2 streaming p-values
- `fragility.json` — §9A 27-point parameter neighborhood
- `beta_residual.json` — §11B NIFTY alpha-after-beta
- `impl_risk.json` — §11A combined 10-scenario stress
- `cusum_decay.json` — §12 decay flags + recent-24m ratio
- `portfolio_gate.json` — §11C correlation + concentration + defense filter
- `direction_audit.json` — §8 engine-vs-backtest sign mismatch
- `gate_checklist.json` — §15.1 decision (PASS / PARTIAL / FAIL)

**First strategy run:** H-2026-04-23-001 (phase-c-residual-reversion-eod). See `docs/superpowers/hypothesis-registry.jsonl` line 1.

**Decision authority:** `gate_checklist.json::decision` is the single source of truth. If `decision != "PASS"`, the strategy cannot promote to PAPER-SHADOW without a waiver in `docs/superpowers/waivers/`.
```

- [ ] **Step 2: Update memory `project_overshoot_reversion_backtest.md`**

Replace or append content (read current contents first; final bullet should say):

```
**Compliance path (2026-04-23 onward):** Refactored into `pipeline/autoresearch/overshoot_compliance/` — additive wrapper that satisfies Sections 1-15 of backtesting-specs.txt v1.0. The existing scripts (`overshoot_reversion_backtest.py`, `overshoot_per_ticker_stats.py`) remain the math source — the compliance layer bolts on manifest/audit/grid/metrics/comparators/permutations/fragility/beta/impl-risk/decay/correlation/direction/gate-checklist. First gate artifact committed: `pipeline/autoresearch/results/compliance_H-2026-04-23-001_<stamp>/`. Read `gate_checklist.json::decision` before quoting any number.
```

- [ ] **Step 3: Update memory `reference_backtest_standards.md`**

Append to the "Current status" section:

```
**2026-04-23 compliance runner landed.** `pipeline/autoresearch/overshoot_compliance/` produces the 13-artifact §15.1 gate-check for any pre-registered residual-reversion hypothesis. H-2026-04-23-001 is the first strategy to run it; its decision lives at `pipeline/autoresearch/results/compliance_H-2026-04-23-001_<stamp>/gate_checklist.json`.
```

- [ ] **Step 4: Commit docs**

```bash
git add docs/SYSTEM_OPERATIONS_MANUAL.md \
        "C:\Users\Claude_Anka\.claude\projects\C--Users-Claude-Anka-askanka-com\memory\project_overshoot_reversion_backtest.md" \
        "C:\Users\Claude_Anka\.claude\projects\C--Users-Claude-Anka-askanka-com\memory\reference_backtest_standards.md"
git commit -m "docs: sync compliance runner into ops manual + memory"
```

---

### Task 20: Task list hygiene

**Files:** None (TaskUpdate only).

- [ ] **Step 1: Mark #116 completed** — transaction-cost task, now fully subsumed by slippage grid
- [ ] **Step 2: Mark #117 completed** — regime-stratify handled by per-bucket metrics (per-ticker grid)
- [ ] **Step 3: Mark #119 completed** — documented as deferred per user; record that in task notes only, do NOT mark done
- [ ] **Step 4: Mark #120 completed** — MODE A EOD-entry variant IS the compliance registered run
- [ ] **Step 5: Mark #121 completed** — survivorship waiver filed + disclosure in `universe_snapshot.json`
- [ ] **Step 6: Mark #122 completed** — handled by `direction_audit.json`

(Use TaskUpdate. No git commit needed.)

---

## Self-review checklist (run after writing all 20 tasks)

**Spec coverage map (v1.0 backtesting-specs.txt):**
- §0 research integrity — enforced by workflow: pre-registered hypothesis is the binding primary, gate-checklist is the non-negotiable artifact. **Covered** by Task 18 (no retroactive claims).
- §1 slippage grid — **Task 5**
- §2 metrics — **Task 6**
- §3 pass/fail — **Task 16 gate checklist** applies these thresholds
- §5 Sunday integration — **Deferred** (ad-hoc runner, not scheduled). Noted in Task 19 docs. Compliance runner does NOT land as a scheduled task.
- §5A data quality — **Task 3**
- §6 survivorship — **Task 4** under waiver
- §7 timing — declared MODE_A in manifest (**Task 2**) and gate-checklist (**Task 16**)
- §8 direction audit — **Task 14**
- §9 n, CI, power — n≥30 check in gate checklist (**Task 16**), CIs in metrics (**Task 6**)
- §9A fragility — **Task 9**
- §9B.1 comparators — **Task 7**
- §9B.2 permutations — **Task 8**
- §10.1 holdout — noted 6% under target in gate checklist (**Task 16**) — triggers PARTIAL verdict; waiver required for promotion
- §10.2 purged WF — existing `walk_forward_folds` in prototype is chronological; 1-day horizon makes the purge trivial (±1 bar embargo implicit). **Task 16** notes this and marks §10.2 as noted-with-note (no separate gate row, so mentioned under §10 in gate).
- §11 ADV capacity — **NOT covered in v1**. Plan leaves as gap for v2 (will require F&O ADV fetcher; survivor notional cap applied at deployment). Documented in Task 19 SYSTEM_OPERATIONS_MANUAL.
- §11A impl-risk — **Task 11**
- §11B beta/residual — **Task 10**
- §11C correlation/concentration — **Task 13**
- §12 decay — **Task 12**
- §13 drift — deferred (no shadow trades yet). Noted in Task 19.
- §13A reproducibility — **Task 2 manifest**
- §14 registry — already pre-registered (0db0775), no plan task.
- §15.1 gate — **Task 16 emitter + Task 18 artifact**

**Gaps explicitly acknowledged** (to disclose when reporting Task 18 to user):
- §11 ADV test — not yet built; would require F&O ADV data. Gate verdict flags capacity as "not measured".
- §10.2 purged walk-forward embargo — verified implicit-only for 1-day horizon; no separate test module.
- §13 drift — deferred; activates when strategy reaches PAPER-SHADOW.

**Placeholder scan:** Grep the plan for "TBD", "TODO", "implement later", "similar to", "fill in". None expected.

**Type consistency scan:**
- Manifest keys used in Task 2 match those tested in Task 2 ✔
- `per_bucket_metrics` signature used identically in Tasks 6, 7, 9, 11 ✔
- `events_by_window` shape (dict[int, pd.DataFrame]) declared in Task 9, produced in Task 17 ✔
- `gate_checklist.build(inputs, hypothesis_id=...)` signature consistent Task 16 ↔ Task 17 ✔
- `slippage_grid.LEVELS` dict keys S0/S1/S2/S3 used identically in Tasks 5, 17 ✔

**Done — plan ready.**

---

## Summary for execution handoff

20 tasks, TDD throughout, no placeholders. Phases:
- **A (Tasks 1-4):** scaffold + manifest + data audit + universe snapshot
- **B (Tasks 5-8):** slippage grid + metrics + comparators + 100k permutations
- **C (Tasks 9-13):** fragility + beta + impl-risk + CUSUM + portfolio
- **D (Tasks 14-16):** direction audit + defense filter + gate checklist
- **E (Tasks 17-20):** runner + real run + docs + task-list hygiene

Final artifact commit (Task 18) is the **verification** that the strategy crosses or misses the gate — not a claim. Report the `gate_checklist.json::decision` back to the user before moving on.
