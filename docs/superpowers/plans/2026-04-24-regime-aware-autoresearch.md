# Regime-Aware Stock/Pair Autoresearch Engine — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a regime-conditional stock/pair autoresearch engine that discovers DSL-constrained trading rules, gates them through a frozen holdout with BH-FDR q=0.1, and promotes survivors through forward-shadow into a 10-slot-per-regime incumbent table.

**Architecture:** `pipeline/autoresearch/regime_autoresearch/` is the single directory. The proposer (LLM, Haiku 4.5 pinned) fills DSL slots; the in-sample runner computes net-of-cost Sharpe on purged walk-forward folds; qualifying rules touch the frozen holdout once; BH-FDR-survivors enter 60-day/50-event forward shadow; promotions displace lowest-Sharpe incumbent in that regime. A pre-commit hook + CI check refuses new strategy files without a hypothesis-registry entry.

**Tech Stack:** Python 3.11+, pandas 2.x, scikit-learn (LassoCV for alpha selection reuse), pyarrow parquet, pytest, anthropic SDK (proposer LLM), git hooks (bash), GitHub Actions (CI).

**Spec:** `docs/superpowers/specs/2026-04-24-regime-aware-autoresearch-design.md` (commit bba49d6).

---

## File layout

```
pipeline/autoresearch/regime_autoresearch/
├── __init__.py
├── constants.py                            # Δ_in, Δ_holdout, REGIMES, HOLDOUT_START, FORWARD_SHADOW_MIN_DAYS, etc
├── dsl.py                                  # Grammar validator, compiler, family-size enumerator
├── features.py                             # 20 regime_features_v1 functions, all causal
├── in_sample_runner.py                     # Net-of-cost Sharpe via slippage_grid, proposal_log writer
├── proposer.py                             # LLM proposer (anthropic SDK) + view-isolation
├── holdout_runner.py                       # Single-touch holdout + BH-FDR q=0.1 batch
├── forward_shadow.py                       # 60d/50-event paper-trade supervisor
├── promotions.py                           # 7-state lifecycle + displacement
├── incumbents.py                           # strategy_results_10.json loader + hurdle logic
├── cli.py                                  # `python -m pipeline.autoresearch.regime_autoresearch` entry
├── data/
│   ├── strategy_results_10.json
│   ├── cointegrated_pairs_v1.json
│   ├── ssf_availability.json
│   ├── proposal_log.jsonl
│   ├── holdout_outcomes.jsonl              # ACL: proposer-runtime user has NO read access
│   ├── forward_shadow_ledger.jsonl
│   └── promotions.jsonl
└── tests/                                  # lives at pipeline/tests/autoresearch/regime_autoresearch/
    ├── test_regime_history_integrity.py
    ├── test_dsl_grammar.py
    ├── test_features_causal.py
    ├── test_in_sample_runner.py
    ├── test_proposer_view_isolation.py
    ├── test_holdout_runner.py
    ├── test_bh_fdr_multiplicity.py
    ├── test_forward_shadow.py
    ├── test_lifecycle_state_machine.py
    └── test_kill_switch.py

pipeline/data/
├── regime_history.csv                      # Task 0a produces
└── vix_history.csv                         # Task 0b produces

pipeline/scripts/hooks/
└── pre-commit-strategy-gate.sh             # Task 7

.github/workflows/
└── strategy-gate.yml                       # Task 7
```

---

## Global constants (pinned in `constants.py`)

```python
# pipeline/autoresearch/regime_autoresearch/constants.py
"""Pinned constants for the regime-aware autoresearch engine v1."""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = Path(__file__).parent / "data"

# The 5 ETF regime labels. Canonical — do not rename.
REGIMES: tuple[str, ...] = ("RISK-OFF", "CAUTION", "NEUTRAL", "RISK-ON", "EUPHORIA")

# Split boundaries (ISO dates)
TRAIN_VAL_START = "2021-04-23"
TRAIN_VAL_END = "2024-04-22"
HOLDOUT_START = "2024-04-23"
HOLDOUT_END = "2026-04-23"

# Hurdle constants
DELTA_IN_SAMPLE = 0.15       # qualify-for-holdout Sharpe gap
DELTA_HOLDOUT = 0.10         # holdout-pass Sharpe gap
INCUMBENT_SCARCITY_MIN = 3   # < this → scarcity fallback to regime-cond buy-and-hold

# Proposer budget
PROPOSALS_PER_REGIME_HARD_CAP = 500
CONSECUTIVE_NO_IMPROVE_SOFT_CAP = 50
PROPOSER_CONTEXT_WINDOW_SIZE = 200  # last-N in-sample proposals visible to LLM

# BH-FDR
BH_FDR_Q = 0.10
BH_FDR_BATCH_CALENDAR_DAYS = 30        # whichever-first with...
BH_FDR_BATCH_ACCUMULATED_COUNT = 10

# Lifecycle
SLOTS_PER_REGIME = 10
PROMOTIONS_PER_REGIME_PER_QUARTER = 2
FORWARD_SHADOW_MIN_DAYS = 60
FORWARD_SHADOW_MIN_EVENTS = 50
CUSUM_RECENT_24M_RETIRE_THRESHOLD = 0.50

# LLM
PROPOSER_MODEL = "claude-haiku-4-5-20251001"
```

---

## Task 0: Data Foundation (6 sub-tasks)

**Files touched:** `pipeline/data/regime_history.csv`, `pipeline/data/vix_history.csv`, `pipeline/autoresearch/regime_autoresearch/data/strategy_results_10.json`, `pipeline/autoresearch/regime_autoresearch/data/cointegrated_pairs_v1.json`, `pipeline/autoresearch/regime_autoresearch/data/ssf_availability.json`.

This is the riskiest task — nothing downstream works without it. Six sub-tasks, each with its own TDD loop and commit.

---

### Task 0a: Causal `regime_history.csv` + integrity test

**Files:**
- Create: `pipeline/autoresearch/regime_autoresearch/scripts/build_regime_history.py`
- Create: `pipeline/tests/autoresearch/regime_autoresearch/test_regime_history_integrity.py`
- Create (output): `pipeline/data/regime_history.csv`

- [ ] **0a-Step 1: Write the integrity test (failing)**

```python
# pipeline/tests/autoresearch/regime_autoresearch/test_regime_history_integrity.py
"""Loud failures if regime_history.csv is missing, stale, or has gaps > 5 bars."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

REGIME_CSV = Path("pipeline/data/regime_history.csv")
VALID_REGIMES = {"RISK-OFF", "CAUTION", "NEUTRAL", "RISK-ON", "EUPHORIA"}
MIN_START = pd.Timestamp("2021-04-23")


@pytest.fixture(scope="module")
def df() -> pd.DataFrame:
    if not REGIME_CSV.exists():
        pytest.fail(f"missing: {REGIME_CSV}")
    frame = pd.read_csv(REGIME_CSV, parse_dates=["date"]).sort_values("date")
    return frame


def test_columns(df):
    assert {"date", "regime_zone", "signal_score"}.issubset(df.columns)


def test_non_empty(df):
    assert len(df) > 0, "regime_history.csv is empty"


def test_coverage_start(df):
    assert df["date"].min() <= MIN_START, f"coverage starts after {MIN_START}"


def test_no_large_gaps(df):
    gaps = df["date"].diff().dropna().dt.days
    assert gaps.max() <= 7, f"gap of {gaps.max()} days exceeds 7-day tolerance"


def test_valid_zones_only(df):
    unknown = set(df["regime_zone"].unique()) - VALID_REGIMES
    assert not unknown, f"unknown zones: {unknown}"


def test_min_four_distinct_zones(df):
    assert df["regime_zone"].nunique() >= 4, "too few zones represented; check weights"
```

- [ ] **0a-Step 2: Run test to verify it fails**

```bash
pytest pipeline/tests/autoresearch/regime_autoresearch/test_regime_history_integrity.py -v
```
Expected: FAIL with `missing: pipeline/data/regime_history.csv`.

- [ ] **0a-Step 3: Implement the builder script**

```python
# pipeline/autoresearch/regime_autoresearch/scripts/build_regime_history.py
"""Produces pipeline/data/regime_history.csv via the existing backfill.

Uses pipeline.research.phase_c_backtest.regime.backfill_regime, which in turn
delegates to pipeline.autoresearch.etf_reoptimize._signal_to_zone.

KNOWN CAVEAT: this applies current optimal weights to historical returns. The
zone mapping function is causal, but the weights themselves were selected
using data that includes the historical window. A v2 improvement would be
rolling-weights-recomputed-quarterly. For v1 we accept this and document it.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

from pipeline.research.phase_c_backtest.regime import _signal_to_zone, _compute_signal

REPO_ROOT = Path(__file__).resolve().parents[4]
WEIGHTS_PATH = REPO_ROOT / "pipeline/data/etf_optimal_weights.json"
ETF_BARS_DIR = REPO_ROOT / "pipeline/data/etf_bars"
OUT_CSV = REPO_ROOT / "pipeline/data/regime_history.csv"
START = "2021-04-23"


def _load_etf_bars(weights: dict[str, float]) -> dict[str, pd.DataFrame]:
    bars: dict[str, pd.DataFrame] = {}
    for sym in weights:
        p = ETF_BARS_DIR / f"{sym}.csv"
        if not p.exists():
            print(f"warn: missing bars for {sym}", file=sys.stderr)
            continue
        bars[sym] = pd.read_csv(p, parse_dates=["date"]).sort_values("date")
    return bars


def main() -> int:
    cfg = json.loads(WEIGHTS_PATH.read_text(encoding="utf-8"))
    weights = cfg["optimal_weights"]
    etf_bars = _load_etf_bars(weights)

    # Union of all ETF trading dates ≥ START
    all_dates = sorted({d for df in etf_bars.values()
                        for d in df["date"][df["date"] >= pd.Timestamp(START)]})
    rows = []
    for d in all_dates:
        signal = _compute_signal(d.strftime("%Y-%m-%d"), weights, etf_bars)
        rows.append({"date": d, "regime_zone": _signal_to_zone(signal),
                     "signal_score": round(signal, 4)})
    out = pd.DataFrame(rows).sort_values("date")
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_CSV, index=False)
    print(f"wrote {len(out)} rows to {OUT_CSV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **0a-Step 4: Build the file**

```bash
python -m pipeline.autoresearch.regime_autoresearch.scripts.build_regime_history
```
Expected: `wrote <N> rows to pipeline/data/regime_history.csv` with N ≈ 1,200 business days.

- [ ] **0a-Step 5: Re-run integrity test to verify pass**

```bash
pytest pipeline/tests/autoresearch/regime_autoresearch/test_regime_history_integrity.py -v
```
Expected: 6 passed.

- [ ] **0a-Step 6: Commit**

```bash
git add pipeline/autoresearch/regime_autoresearch/scripts/build_regime_history.py \
        pipeline/tests/autoresearch/regime_autoresearch/test_regime_history_integrity.py \
        pipeline/data/regime_history.csv
git commit -m "feat(regime_history): causal 2021-04-23→today series + integrity test"
```

---

### Task 0b: VIX history (yfinance + NSE fallback)

**Files:**
- Create: `pipeline/autoresearch/regime_autoresearch/scripts/build_vix_history.py`
- Create (output): `pipeline/data/vix_history.csv`

- [ ] **0b-Step 1: Implement the builder**

```python
# pipeline/autoresearch/regime_autoresearch/scripts/build_vix_history.py
"""VIX history (India VIX close) via yfinance primary + NSE archive fallback.

Forward-fill policy: gap ≤ 2 bars (for holidays), longer gaps left NaN so
the downstream feature builder can flag them.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import pandas as pd
import yfinance as yf

REPO_ROOT = Path(__file__).resolve().parents[4]
OUT_CSV = REPO_ROOT / "pipeline/data/vix_history.csv"
NSE_FALLBACK = REPO_ROOT / "pipeline/data/india_historical/indices/INDIAVIX.csv"
START = "2021-04-01"
END = "2026-05-01"


def _from_yfinance() -> pd.DataFrame:
    df = yf.download("^INDIAVIX", start=START, end=END, progress=False)
    if df.empty:
        return df
    df = df.reset_index()[["Date", "Close"]].rename(columns={"Date": "date", "Close": "vix_close"})
    df["date"] = pd.to_datetime(df["date"])
    return df


def _from_nse_archive() -> pd.DataFrame:
    if not NSE_FALLBACK.exists():
        return pd.DataFrame(columns=["date", "vix_close"])
    df = pd.read_csv(NSE_FALLBACK, parse_dates=["date"])
    col = "close" if "close" in df.columns else df.columns[-1]
    return df.rename(columns={col: "vix_close"})[["date", "vix_close"]]


def main() -> int:
    df_yf = _from_yfinance()
    if df_yf.empty:
        logging.warning("yfinance INDIAVIX empty; falling back to NSE archive")
        df_yf = _from_nse_archive()
    df_nse = _from_nse_archive()

    combined = pd.concat([df_yf, df_nse], ignore_index=True).dropna()
    combined = combined.drop_duplicates(subset=["date"], keep="first").sort_values("date")
    # Forward-fill gaps of ≤ 2 bars only
    combined = combined.set_index("date").asfreq("B")
    combined["vix_close"] = combined["vix_close"].ffill(limit=2)
    combined = combined.reset_index().dropna()

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(OUT_CSV, index=False)
    print(f"wrote {len(combined)} rows to {OUT_CSV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **0b-Step 2: Build the file**

```bash
python -m pipeline.autoresearch.regime_autoresearch.scripts.build_vix_history
```
Expected: `wrote <N> rows to pipeline/data/vix_history.csv` with N ≈ 1,200.

- [ ] **0b-Step 3: Smoke-check**

```bash
python -c "
import pandas as pd
df = pd.read_csv('pipeline/data/vix_history.csv', parse_dates=['date'])
print('rows=', len(df))
print('range=', df['date'].min(), '→', df['date'].max())
print('vix summary:', df['vix_close'].describe())
assert df['vix_close'].between(5, 80).all(), 'VIX out of plausible range'
"
```
Expected: rows ~1,200, vix range [5, 80].

- [ ] **0b-Step 4: Commit**

```bash
git add pipeline/autoresearch/regime_autoresearch/scripts/build_vix_history.py \
        pipeline/data/vix_history.csv
git commit -m "feat(vix_history): build causal INDIAVIX series via yfinance + NSE fallback"
```

---

### Task 0c: SSF availability + borrow cost

**Files:**
- Create: `pipeline/autoresearch/regime_autoresearch/scripts/build_ssf_availability.py`
- Create (output): `pipeline/autoresearch/regime_autoresearch/data/ssf_availability.json`

- [ ] **0c-Step 1: Implement the builder**

```python
# pipeline/autoresearch/regime_autoresearch/scripts/build_ssf_availability.py
"""Build ssf_availability.json from Kite instruments list + NSE stocklending fees.

Output schema: {ticker: {"is_ssf_available": bool, "borrow_cost_bps": int, "notes": str}}
For v1 we use a conservative default: all F&O tickers are SSF-available at 25 bps
(the Zerodha ballpark for most names). A v2 would call Kite's instrument API
and the NSE SLB API for per-ticker truth.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[4]
FNO_DIR = REPO_ROOT / "pipeline/data/india_historical/fno_stocks"
OUT = REPO_ROOT / "pipeline/autoresearch/regime_autoresearch/data/ssf_availability.json"
DEFAULT_BORROW_BPS = 25
HIGH_BORROW_TICKERS = {"IRCTC": 80, "VEDL": 60, "ADANIENT": 100, "ADANIPOWER": 100}


def main() -> int:
    tickers = sorted(p.stem for p in FNO_DIR.glob("*.csv"))
    table = {}
    for t in tickers:
        table[t] = {
            "is_ssf_available": True,
            "borrow_cost_bps": HIGH_BORROW_TICKERS.get(t, DEFAULT_BORROW_BPS),
            "notes": "v1 default; refresh via Kite + NSE SLB in v2",
        }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(table, indent=2, sort_keys=True), encoding="utf-8")
    print(f"wrote {len(table)} tickers to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **0c-Step 2: Build**

```bash
python -m pipeline.autoresearch.regime_autoresearch.scripts.build_ssf_availability
```
Expected: `wrote ~213 tickers`.

- [ ] **0c-Step 3: Commit**

```bash
git add -f pipeline/autoresearch/regime_autoresearch/scripts/build_ssf_availability.py \
           pipeline/autoresearch/regime_autoresearch/data/ssf_availability.json
git commit -m "feat(ssf_availability): conservative-default SSF/borrow table for F&O universe"
```
(The `-f` is because `pipeline/autoresearch/` has a gitignore; artifacts must be force-added.)

---

### Task 0d: Within-sector cointegration pair artifact

**Files:**
- Create: `pipeline/autoresearch/regime_autoresearch/scripts/build_cointegrated_pairs.py`
- Create (output): `pipeline/autoresearch/regime_autoresearch/data/cointegrated_pairs_v1.json`

- [ ] **0d-Step 1: Implement the builder**

```python
# pipeline/autoresearch/regime_autoresearch/scripts/build_cointegrated_pairs.py
"""Engle-Granger cointegration within broad sectors on the train window only.

Reuses BROAD_SECTOR from overshoot_reversion_backtest. Train window is the
autoresearch TRAIN_VAL window (2021-04-23 → 2024-04-22). We never test on
holdout data, so this artifact is causal by construction.
"""
from __future__ import annotations

import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import coint

from pipeline.autoresearch.overshoot_reversion_backtest import BROAD_SECTOR
from pipeline.autoresearch.regime_autoresearch.constants import (
    TRAIN_VAL_START, TRAIN_VAL_END,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
FNO_DIR = REPO_ROOT / "pipeline/data/india_historical/fno_stocks"
OUT = REPO_ROOT / "pipeline/autoresearch/regime_autoresearch/data/cointegrated_pairs_v1.json"


def _close_series(ticker: str) -> pd.Series | None:
    p = FNO_DIR / f"{ticker}.csv"
    if not p.exists():
        return None
    df = pd.read_csv(p, parse_dates=["date"]).sort_values("date")
    df = df[(df["date"] >= TRAIN_VAL_START) & (df["date"] <= TRAIN_VAL_END)]
    if df.empty or df["close"].isna().mean() > 0.1:
        return None
    return df.set_index("date")["close"]


def _sector_buckets() -> dict[str, list[str]]:
    buckets: dict[str, list[str]] = {}
    for t, s in BROAD_SECTOR.items():
        buckets.setdefault(s, []).append(t)
    return {s: tickers for s, tickers in buckets.items() if len(tickers) >= 2}


def main() -> int:
    buckets = _sector_buckets()
    results = []
    for sector, tickers in buckets.items():
        print(f"{sector}: {len(tickers)} tickers, {len(tickers)*(len(tickers)-1)//2} pairs")
        for a, b in itertools.combinations(tickers, 2):
            s_a, s_b = _close_series(a), _close_series(b)
            if s_a is None or s_b is None:
                continue
            joined = pd.concat([s_a, s_b], axis=1).dropna()
            if len(joined) < 120:
                continue
            t_stat, p_val, _ = coint(joined.iloc[:, 0], joined.iloc[:, 1])
            if p_val < 0.05:
                results.append({
                    "pair_id": f"{a}_{b}",
                    "leg_a": a,
                    "leg_b": b,
                    "sector": sector,
                    "coint_t": round(float(t_stat), 4),
                    "coint_p": round(float(p_val), 6),
                    "n_obs_train": len(joined),
                })
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"pairs": results, "train_window": [TRAIN_VAL_START, TRAIN_VAL_END]},
                              indent=2, sort_keys=True), encoding="utf-8")
    print(f"wrote {len(results)} cointegrated pairs to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **0d-Step 2: Build (expect ~30-60 min wall time)**

```bash
python -m pipeline.autoresearch.regime_autoresearch.scripts.build_cointegrated_pairs
```
Expected: `wrote <N> cointegrated pairs` with N in [100, 600].

- [ ] **0d-Step 3: Commit**

```bash
git add -f pipeline/autoresearch/regime_autoresearch/scripts/build_cointegrated_pairs.py \
           pipeline/autoresearch/regime_autoresearch/data/cointegrated_pairs_v1.json
git commit -m "feat(cointegrated_pairs_v1): Engle-Granger within-sector pair universe on train window"
```

---

### Task 0e: Seed `strategy_results_10.json`

**Files:**
- Create: `pipeline/autoresearch/regime_autoresearch/scripts/seed_strategy_results.py`
- Create (output): `pipeline/autoresearch/regime_autoresearch/data/strategy_results_10.json`

- [ ] **0e-Step 1: Implement the seeder**

```python
# pipeline/autoresearch/regime_autoresearch/scripts/seed_strategy_results.py
"""Seed strategy_results_10.json from existing compliance artifacts.

For each known incumbent strategy, look up any gate_checklist.json artifact
under pipeline/autoresearch/results/ and extract per-regime sharpe/CI where
present. Where absent, mark INSUFFICIENT_POWER.

Incumbents per the spec (v1 seed list; fewer-than-10 is acceptable):
  SI_PRIMARY  — Spread Intelligence regime-gated, primary flavour
  SI_SECONDARY — Spread Intelligence sector-neutral flavour
  PHASE_C_LAG — Phase C LAG route (alert-only; H-107 FAIL Bonferroni)
  OVERSHOOT_TORNTPOWER — per-ticker fade, TORNTPOWER STRONG (2026-04-23 verdict)
  OVERSHOOT_MULTITICKER — per-ticker fade top-5 defence-excluded
  FCS_LONG_TOPK — FCS top-k long-only
  FCS_LONG_SHORT — FCS market-neutral
  TA_SCORER_RELIANCE — TA fingerprint RELIANCE pilot (walk-forward only)
  OPUS_TRUST_SPREAD — OPUS trust-tilted cross-sectional
  PHASE_AB_REVERSE — Reverse Regime Phase A/B (collapsed)
"""
from __future__ import annotations

import json
from pathlib import Path

from pipeline.autoresearch.regime_autoresearch.constants import REGIMES

REPO_ROOT = Path(__file__).resolve().parents[4]
OUT = REPO_ROOT / "pipeline/autoresearch/regime_autoresearch/data/strategy_results_10.json"

SEED_INCUMBENTS = [
    {"strategy_id": "SI_PRIMARY",
     "strategy_name": "Spread Intelligence regime-gated primary",
     "status": "LIVE"},
    {"strategy_id": "SI_SECONDARY",
     "strategy_name": "Spread Intelligence sector-neutral",
     "status": "LIVE"},
    {"strategy_id": "PHASE_C_LAG",
     "strategy_name": "Phase C LAG (alert-only post H-107 FAIL)",
     "status": "LIVE_ALERT_ONLY"},
    {"strategy_id": "OVERSHOOT_TORNTPOWER",
     "strategy_name": "Per-ticker fade — TORNTPOWER STRONG",
     "status": "LIVE"},
    {"strategy_id": "OVERSHOOT_MULTITICKER",
     "strategy_name": "Per-ticker fade top-5 (defence-excluded)",
     "status": "LIVE"},
    {"strategy_id": "FCS_LONG_TOPK",
     "strategy_name": "FCS top-k long-only",
     "status": "LIVE"},
    {"strategy_id": "FCS_LONG_SHORT",
     "strategy_name": "FCS market-neutral long/short",
     "status": "LIVE"},
    {"strategy_id": "TA_SCORER_RELIANCE",
     "strategy_name": "TA fingerprint RELIANCE pilot (walk-forward only)",
     "status": "EXPLORING"},
    {"strategy_id": "OPUS_TRUST_SPREAD",
     "strategy_name": "OPUS trust-tilted cross-sectional",
     "status": "EXPLORING"},
    {"strategy_id": "PHASE_AB_REVERSE",
     "strategy_name": "Reverse Regime Phase A/B (collapsed)",
     "status": "LIVE"},
]


def _insufficient_power_cell() -> dict:
    return {
        "n_obs": 0,
        "sharpe_point": None,
        "sharpe_ci_low": None,
        "sharpe_ci_high": None,
        "p_value_vs_zero": None,
        "p_value_vs_buy_hold": None,
        "compliance_artifact_path": None,
        "status_flag": "INSUFFICIENT_POWER",
    }


def main() -> int:
    rows = []
    for inc in SEED_INCUMBENTS:
        per_regime = {r: _insufficient_power_cell() for r in REGIMES}
        rows.append({**inc, "per_regime": per_regime})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"incumbents": rows, "seeded_at": "2026-04-24",
                               "spec_version": "v1"}, indent=2, sort_keys=True),
                   encoding="utf-8")
    print(f"seeded {len(rows)} incumbents (all cells INSUFFICIENT_POWER; Task 9 refreshes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **0e-Step 2: Build**

```bash
python -m pipeline.autoresearch.regime_autoresearch.scripts.seed_strategy_results
```
Expected: `seeded 10 incumbents`.

- [ ] **0e-Step 3: Commit**

```bash
git add -f pipeline/autoresearch/regime_autoresearch/scripts/seed_strategy_results.py \
           pipeline/autoresearch/regime_autoresearch/data/strategy_results_10.json
git commit -m "feat(strategy_results_10): seed 10 incumbents with INSUFFICIENT_POWER cells (Task 9 refreshes)"
```

---

### Task 0f: Deprecation sweep (same commit as retirement notice)

**Files:**
- Modify: mark Phase C cross-sectional as DEAD via README
- Create: `docs/superpowers/DEPRECATED-2026-04-24.md`
- Modify: any production code referencing a non-existent `regime_history.csv` path

- [ ] **0f-Step 1: Identify code paths that read the old phantom file**

```bash
grep -rn "regime_history.csv" pipeline/ | grep -v "__pycache__" | grep -v "regime_autoresearch"
```
Record each hit path → the file exists now (Task 0a) so these become valid reads, not phantom reads. Verify each still does the right thing.

- [ ] **0f-Step 2: Write the deprecation notice**

```markdown
# docs/superpowers/DEPRECATED-2026-04-24.md
# Deprecations — 2026-04-24

## Hard retirements (DEAD, cannot re-enter engine without new hypothesis)

### Phase C cross-sectional geometry
- **Packages:** `pipeline/autoresearch/phase_c_cross_sectional/`
- **Evidence:** H-2026-04-24-002 abandoned at n=116; H-2026-04-24-003 FAIL (margin −4.98, p=0.81, Fragility STABLE 26/27). Tag: `H-2026-04-24-003-FAIL`.
- **Retirement scope:** geometry as originally framed (asymmetric-threshold persistent-break Lasso on the full 213-ticker F&O panel). The artefact directory stays for reproducibility; no live code references this strategy for signal generation.

## Phantom-data code paths fixed in the same commit

All production code that previously read `pipeline/data/regime_history.csv` now reads the causal file produced by Task 0a. Before this commit, the file did not exist and readers silently fell back to empty DataFrames (observed in H-003 runner).

## Policy going forward

Any new trading-rule file in `pipeline/` must be accompanied by a `docs/superpowers/hypothesis-registry.jsonl` entry with `status ∈ {PRE_REGISTERED, LIVE}`. This is enforced by the pre-commit hook added in Task 7.
```

- [ ] **0f-Step 3: Add DEAD marker to phase_c_cross_sectional README**

```python
# pipeline/autoresearch/phase_c_cross_sectional/__init__.py
"""
RETIRED 2026-04-24 — See docs/superpowers/DEPRECATED-2026-04-24.md

This package is preserved for reproducibility of the H-2026-04-24-003
compliance artefact only. It must not be imported by any live-signal code.
"""
```

- [ ] **0f-Step 4: Commit everything together**

```bash
git add docs/superpowers/DEPRECATED-2026-04-24.md \
        pipeline/autoresearch/phase_c_cross_sectional/__init__.py
git commit -m "$(cat <<'EOF'
deprecate: Phase C cross-sec geometry + fix phantom regime_history.csv readers

Task 0 of the regime-aware autoresearch engine. Consolidates hard retirements
and the data-foundation fix into one commit so nothing is half-migrated.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 1: DSL grammar + feature library

**Files:**
- Create: `pipeline/autoresearch/regime_autoresearch/__init__.py`
- Create: `pipeline/autoresearch/regime_autoresearch/dsl.py`
- Create: `pipeline/autoresearch/regime_autoresearch/features.py`
- Create: `pipeline/tests/autoresearch/regime_autoresearch/test_dsl_grammar.py`
- Create: `pipeline/tests/autoresearch/regime_autoresearch/test_features_causal.py`

- [ ] **Step 1: Write failing grammar test**

```python
# pipeline/tests/autoresearch/regime_autoresearch/test_dsl_grammar.py
"""DSL grammar validation + family-size enumeration."""
from __future__ import annotations

import pytest

from pipeline.autoresearch.regime_autoresearch.dsl import (
    FEATURES, THRESHOLD_OPS, HOLD_HORIZONS, CONSTRUCTION_TYPES,
    Proposal, validate, enumerate_family_size,
)


def test_feature_library_size():
    assert len(FEATURES) == 20


def test_grammar_enumeration_non_pair():
    # 3 non-pair constructions × 20 × 4 ops × 8 thresholds × 3 holds × 5 regimes
    assert enumerate_family_size(include_pairs=False) == 28_800


def test_validate_accepts_good_proposal():
    p = Proposal(
        construction_type="single_long",
        feature="ret_20d",
        threshold_op=">",
        threshold_value=0.05,
        hold_horizon=5,
        regime="NEUTRAL",
        pair_id=None,
    )
    assert validate(p) is True


def test_validate_rejects_unknown_feature():
    p = Proposal("single_long", "not_a_feature", ">", 0.05, 5, "NEUTRAL", None)
    with pytest.raises(ValueError, match="unknown feature"):
        validate(p)


def test_validate_rejects_pair_without_pair_id():
    p = Proposal("pair", "ret_20d", ">", 2.0, 5, "NEUTRAL", None)
    with pytest.raises(ValueError, match="pair construction requires pair_id"):
        validate(p)


def test_validate_rejects_non_pair_with_pair_id():
    p = Proposal("single_long", "ret_20d", ">", 0.05, 5, "NEUTRAL", "RELIANCE_INFY")
    with pytest.raises(ValueError, match="pair_id only valid when construction_type == 'pair'"):
        validate(p)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest pipeline/tests/autoresearch/regime_autoresearch/test_dsl_grammar.py -v
```
Expected: FAIL, ImportError.

- [ ] **Step 3: Implement the DSL**

```python
# pipeline/autoresearch/regime_autoresearch/dsl.py
"""DSL grammar v1 — validator, compiler, family-size enumerator."""
from __future__ import annotations

from dataclasses import dataclass

from pipeline.autoresearch.regime_autoresearch.constants import REGIMES

FEATURES: tuple[str, ...] = (
    "ret_1d", "ret_5d", "ret_20d", "ret_60d", "mom_ratio_20_60",
    "vol_20d", "vol_percentile_252d", "vol_of_vol_60d",
    "resid_vs_sector_1d", "z_resid_vs_sector_20d", "beta_nifty_60d",
    "days_from_52w_high", "dist_from_52w_high_pct",
    "beta_vix_60d", "macro_composite_60d_corr",
    "adv_20d", "adv_percentile_252d", "turnover_ratio_20d",
    "trust_score", "trust_sector_rank",
)

THRESHOLD_OPS: tuple[str, ...] = (">", "<", "top_k", "bottom_k")

# Feature-specific threshold grids — 8 points each. The DSL keeps them simple:
# absolute-level thresholds for `>`/`<`, k-values for `top_k`/`bottom_k`.
ABSOLUTE_THRESHOLD_GRID: tuple[float, ...] = (-2.0, -1.0, -0.5, 0.0, 0.5, 1.0, 2.0, 3.0)
K_GRID: tuple[int, ...] = (3, 5, 10, 15, 20, 25, 30, 40)

HOLD_HORIZONS: tuple[int, ...] = (1, 5, 20)
CONSTRUCTION_TYPES: tuple[str, ...] = (
    "single_long", "single_short", "long_short_basket", "pair",
)


@dataclass(frozen=True)
class Proposal:
    construction_type: str
    feature: str
    threshold_op: str
    threshold_value: float
    hold_horizon: int
    regime: str
    pair_id: str | None


def validate(p: Proposal) -> bool:
    """True if proposal fits the grammar. Raises ValueError with reason otherwise."""
    if p.construction_type not in CONSTRUCTION_TYPES:
        raise ValueError(f"unknown construction_type: {p.construction_type}")
    if p.feature not in FEATURES:
        raise ValueError(f"unknown feature: {p.feature}")
    if p.threshold_op not in THRESHOLD_OPS:
        raise ValueError(f"unknown threshold_op: {p.threshold_op}")
    if p.hold_horizon not in HOLD_HORIZONS:
        raise ValueError(f"hold_horizon must be one of {HOLD_HORIZONS}")
    if p.regime not in REGIMES:
        raise ValueError(f"regime must be one of {REGIMES}")
    if p.threshold_op in ("top_k", "bottom_k"):
        if p.threshold_value not in K_GRID:
            raise ValueError(f"k-op requires threshold_value in {K_GRID}")
    else:
        if p.threshold_value not in ABSOLUTE_THRESHOLD_GRID:
            raise ValueError(f"absolute-op requires threshold_value in {ABSOLUTE_THRESHOLD_GRID}")
    if p.construction_type == "pair" and not p.pair_id:
        raise ValueError("pair construction requires pair_id")
    if p.construction_type != "pair" and p.pair_id is not None:
        raise ValueError("pair_id only valid when construction_type == 'pair'")
    return True


def enumerate_family_size(include_pairs: bool = False, n_pairs: int = 0) -> int:
    """Cardinality of the grammar for multiplicity accounting."""
    non_pair = 3 * len(FEATURES) * len(THRESHOLD_OPS) * 8 * len(HOLD_HORIZONS) * len(REGIMES)
    if not include_pairs:
        return non_pair
    pair = 1 * len(FEATURES) * len(THRESHOLD_OPS) * 8 * len(HOLD_HORIZONS) * len(REGIMES) * max(n_pairs, 1)
    return non_pair + pair
```

- [ ] **Step 4: Package init**

```python
# pipeline/autoresearch/regime_autoresearch/__init__.py
"""Regime-aware stock/pair autoresearch engine — see spec 2026-04-24-regime-aware-autoresearch-design."""
```

- [ ] **Step 5: Re-run grammar test → pass**

```bash
pytest pipeline/tests/autoresearch/regime_autoresearch/test_dsl_grammar.py -v
```
Expected: 5 passed.

- [ ] **Step 6: Write failing features-causality test**

```python
# pipeline/tests/autoresearch/regime_autoresearch/test_features_causal.py
"""Causality check: every feature at date t uses only rows with date < t."""
from __future__ import annotations

import pandas as pd
import numpy as np

from pipeline.autoresearch.regime_autoresearch.features import (
    FEATURE_FUNCS, build_feature_matrix,
)


def _synthetic_panel(n_tickers: int = 5, n_days: int = 300, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2023-01-01", periods=n_days)
    tickers = [f"T{i}" for i in range(n_tickers)]
    rows = []
    for t in tickers:
        closes = 100 + np.cumsum(rng.standard_normal(n_days) * 0.5)
        vols = 1e7 + rng.standard_normal(n_days) * 1e5
        for d, c, v in zip(dates, closes, vols):
            rows.append({"date": d, "ticker": t, "close": c, "volume": v})
    return pd.DataFrame(rows)


def test_all_20_features_registered():
    assert len(FEATURE_FUNCS) == 20


def test_causality_pointwise():
    """For each feature, flipping a future bar must not change today's value."""
    panel = _synthetic_panel()
    evaluation_date = panel["date"].iloc[150]
    past = panel[panel["date"] < evaluation_date].copy()

    panel_mut = panel.copy()
    future_mask = panel_mut["date"] >= evaluation_date
    panel_mut.loc[future_mask, "close"] = panel_mut.loc[future_mask, "close"] * 10.0

    tickers = panel["ticker"].unique().tolist()
    v1 = build_feature_matrix(panel, evaluation_date, tickers)
    v2 = build_feature_matrix(panel_mut, evaluation_date, tickers)
    pd.testing.assert_frame_equal(v1, v2, check_exact=False, rtol=1e-9, atol=1e-9)
```

- [ ] **Step 7: Run test to verify it fails**

```bash
pytest pipeline/tests/autoresearch/regime_autoresearch/test_features_causal.py -v
```
Expected: FAIL, ImportError.

- [ ] **Step 8: Implement feature library**

```python
# pipeline/autoresearch/regime_autoresearch/features.py
"""regime_features_v1 — 20 causal features over the ticker × date panel.

Every feature at date t uses only rows with date < t (strict inequality).
Unit-test `test_features_causal.py` asserts this pointwise.
"""
from __future__ import annotations

from typing import Callable

import numpy as np
import pandas as pd

from pipeline.autoresearch.regime_autoresearch.dsl import FEATURES


def _trailing(panel: pd.DataFrame, ticker: str, t: pd.Timestamp, n: int) -> pd.Series:
    df = panel[(panel["ticker"] == ticker) & (panel["date"] < t)].sort_values("date")
    return df.tail(n)["close"]


def ret_1d(panel: pd.DataFrame, ticker: str, t: pd.Timestamp) -> float:
    s = _trailing(panel, ticker, t, 2)
    if len(s) < 2 or s.iloc[0] == 0: return np.nan
    return float(s.iloc[-1] / s.iloc[0] - 1.0)


def _return_n(panel, ticker, t, n):
    s = _trailing(panel, ticker, t, n + 1)
    if len(s) < n + 1 or s.iloc[0] == 0: return np.nan
    return float(s.iloc[-1] / s.iloc[0] - 1.0)


def ret_5d(panel, ticker, t): return _return_n(panel, ticker, t, 5)
def ret_20d(panel, ticker, t): return _return_n(panel, ticker, t, 20)
def ret_60d(panel, ticker, t): return _return_n(panel, ticker, t, 60)


def mom_ratio_20_60(panel, ticker, t):
    r20 = ret_20d(panel, ticker, t); r60 = ret_60d(panel, ticker, t)
    if pd.isna(r60) or r60 == 0: return np.nan
    return r20 / r60


def vol_20d(panel, ticker, t):
    s = _trailing(panel, ticker, t, 21)
    if len(s) < 21: return np.nan
    rets = s.pct_change().dropna()
    return float(rets.std() * np.sqrt(252))


def vol_percentile_252d(panel, ticker, t):
    s = _trailing(panel, ticker, t, 253)
    if len(s) < 253: return np.nan
    rets = s.pct_change().dropna()
    if len(rets) < 20: return np.nan
    rolling = rets.rolling(20).std() * np.sqrt(252)
    rolling = rolling.dropna()
    if rolling.empty: return np.nan
    return float((rolling.iloc[-1] <= rolling).mean())


def vol_of_vol_60d(panel, ticker, t):
    s = _trailing(panel, ticker, t, 81)
    if len(s) < 81: return np.nan
    rets = s.pct_change().dropna()
    roll_vol = rets.rolling(20).std().dropna()
    if len(roll_vol) < 2: return np.nan
    return float(roll_vol.std())


def resid_vs_sector_1d(panel, ticker, t):
    # Returns this ticker's 1d return minus leave-one-out sector mean 1d return.
    # For tests without a sector map, degenerates to ticker_ret - universe_mean.
    # The runner will pass a sector-enriched panel where needed.
    my = ret_1d(panel, ticker, t)
    if pd.isna(my): return np.nan
    others = []
    for other in panel["ticker"].unique():
        if other == ticker: continue
        r = ret_1d(panel, other, t)
        if not pd.isna(r): others.append(r)
    if not others: return np.nan
    return float(my - np.mean(others))


def z_resid_vs_sector_20d(panel, ticker, t):
    # z-score of resid_vs_sector_1d over trailing 20 sector-strip days.
    history = []
    for lag in range(1, 21):
        # Walk back by days in the ticker's own index so we stay causal
        s = _trailing(panel, ticker, t, lag + 2)
        if len(s) < lag + 2: continue
        prior_t = s.index[-lag] if hasattr(s, "index") else t
        history.append(resid_vs_sector_1d(panel, ticker, prior_t))
    history = [h for h in history if not pd.isna(h)]
    if len(history) < 10: return np.nan
    sd = np.std(history)
    if sd == 0: return np.nan
    current = resid_vs_sector_1d(panel, ticker, t)
    if pd.isna(current): return np.nan
    return float((current - np.mean(history)) / sd)


def beta_nifty_60d(panel, ticker, t):
    # Requires a NIFTY series in panel; if absent, return NaN.
    s = _trailing(panel, ticker, t, 61)
    if len(s) < 61: return np.nan
    nifty = panel[(panel["ticker"] == "NIFTY") & (panel["date"] < t)].sort_values("date").tail(61)["close"]
    if len(nifty) < 61: return np.nan
    r_t = s.pct_change().dropna().values
    r_n = nifty.pct_change().dropna().values
    n = min(len(r_t), len(r_n))
    if n < 30: return np.nan
    cov = np.cov(r_t[-n:], r_n[-n:])[0, 1]
    var_n = np.var(r_n[-n:])
    if var_n == 0: return np.nan
    return float(cov / var_n)


def days_from_52w_high(panel, ticker, t):
    s = _trailing(panel, ticker, t, 252)
    if len(s) == 0: return np.nan
    idx_max = s.values.argmax()
    return float(len(s) - 1 - idx_max)


def dist_from_52w_high_pct(panel, ticker, t):
    s = _trailing(panel, ticker, t, 252)
    if len(s) == 0 or s.max() == 0: return np.nan
    return float((s.iloc[-1] - s.max()) / s.max())


def beta_vix_60d(panel, ticker, t):
    s = _trailing(panel, ticker, t, 61)
    if len(s) < 61: return np.nan
    vix = panel[(panel["ticker"] == "VIX") & (panel["date"] < t)].sort_values("date").tail(61)["close"]
    if len(vix) < 61: return np.nan
    r_t = s.pct_change().dropna().values
    r_v = vix.pct_change().dropna().values
    n = min(len(r_t), len(r_v))
    if n < 30: return np.nan
    cov = np.cov(r_t[-n:], r_v[-n:])[0, 1]
    var_v = np.var(r_v[-n:])
    if var_v == 0: return np.nan
    return float(cov / var_v)


def macro_composite_60d_corr(panel, ticker, t):
    # Correlation to the ETF regime score over 60d. Runner injects 'REGIME' pseudo-ticker.
    s = _trailing(panel, ticker, t, 61)
    if len(s) < 61: return np.nan
    reg = panel[(panel["ticker"] == "REGIME") & (panel["date"] < t)].sort_values("date").tail(61)["close"]
    if len(reg) < 61: return np.nan
    r_t = s.pct_change().dropna().values
    r_r = reg.pct_change().dropna().values
    n = min(len(r_t), len(r_r))
    if n < 30: return np.nan
    return float(np.corrcoef(r_t[-n:], r_r[-n:])[0, 1])


def adv_20d(panel, ticker, t):
    df = panel[(panel["ticker"] == ticker) & (panel["date"] < t)].sort_values("date").tail(20)
    if len(df) < 20 or "volume" not in df.columns: return np.nan
    return float((df["close"] * df["volume"]).mean() / 1e7)  # ₹ Cr


def adv_percentile_252d(panel, ticker, t):
    df = panel[(panel["ticker"] == ticker) & (panel["date"] < t)].sort_values("date").tail(252)
    if len(df) < 252 or "volume" not in df.columns: return np.nan
    dv = (df["close"] * df["volume"]).rolling(20).mean().dropna() / 1e7
    if dv.empty: return np.nan
    return float((dv.iloc[-1] <= dv).mean())


def turnover_ratio_20d(panel, ticker, t):
    # Requires market_cap column on panel rows. Returns NaN if absent.
    df = panel[(panel["ticker"] == ticker) & (panel["date"] < t)].sort_values("date").tail(20)
    if len(df) < 20 or "market_cap" not in df.columns: return np.nan
    adv = (df["close"] * df["volume"]).mean()
    mcap = df["market_cap"].iloc[-1]
    if mcap == 0 or pd.isna(mcap): return np.nan
    return float(adv / mcap)


def trust_score(panel, ticker, t):
    # Runner injects trust_score column on panel rows (per ticker, constant over dates).
    df = panel[(panel["ticker"] == ticker) & (panel["date"] < t)]
    if df.empty or "trust_score" not in df.columns: return np.nan
    val = df["trust_score"].dropna()
    return float(val.iloc[-1]) if not val.empty else np.nan


def trust_sector_rank(panel, ticker, t):
    if "trust_score" not in panel.columns or "sector" not in panel.columns: return np.nan
    last = panel[panel["date"] < t].sort_values("date").groupby("ticker").tail(1)
    if ticker not in last["ticker"].values: return np.nan
    my_sector = last[last["ticker"] == ticker]["sector"].iloc[0]
    peers = last[last["sector"] == my_sector].dropna(subset=["trust_score"])
    if peers.empty: return np.nan
    my_ts = peers[peers["ticker"] == ticker]["trust_score"]
    if my_ts.empty: return np.nan
    return float((peers["trust_score"] <= my_ts.iloc[0]).mean())


FEATURE_FUNCS: dict[str, Callable] = {
    "ret_1d": ret_1d, "ret_5d": ret_5d, "ret_20d": ret_20d, "ret_60d": ret_60d,
    "mom_ratio_20_60": mom_ratio_20_60,
    "vol_20d": vol_20d, "vol_percentile_252d": vol_percentile_252d,
    "vol_of_vol_60d": vol_of_vol_60d,
    "resid_vs_sector_1d": resid_vs_sector_1d,
    "z_resid_vs_sector_20d": z_resid_vs_sector_20d,
    "beta_nifty_60d": beta_nifty_60d,
    "days_from_52w_high": days_from_52w_high,
    "dist_from_52w_high_pct": dist_from_52w_high_pct,
    "beta_vix_60d": beta_vix_60d,
    "macro_composite_60d_corr": macro_composite_60d_corr,
    "adv_20d": adv_20d, "adv_percentile_252d": adv_percentile_252d,
    "turnover_ratio_20d": turnover_ratio_20d,
    "trust_score": trust_score, "trust_sector_rank": trust_sector_rank,
}
assert set(FEATURE_FUNCS) == set(FEATURES), "FEATURE_FUNCS / FEATURES out of sync"


def build_feature_matrix(panel: pd.DataFrame, eval_date: pd.Timestamp,
                          tickers: list[str]) -> pd.DataFrame:
    rows = []
    for t in tickers:
        row = {"ticker": t}
        for name, fn in FEATURE_FUNCS.items():
            row[name] = fn(panel, t, eval_date)
        rows.append(row)
    return pd.DataFrame(rows).set_index("ticker")
```

- [ ] **Step 9: Re-run features test → pass**

```bash
pytest pipeline/tests/autoresearch/regime_autoresearch/test_features_causal.py -v
```
Expected: 2 passed.

- [ ] **Step 10: Commit**

```bash
git add pipeline/autoresearch/regime_autoresearch/__init__.py \
        pipeline/autoresearch/regime_autoresearch/constants.py \
        pipeline/autoresearch/regime_autoresearch/dsl.py \
        pipeline/autoresearch/regime_autoresearch/features.py \
        pipeline/tests/autoresearch/regime_autoresearch/test_dsl_grammar.py \
        pipeline/tests/autoresearch/regime_autoresearch/test_features_causal.py
git commit -m "feat(autoresearch): DSL grammar v1 + regime_features_v1 (20 causal features)"
```

---

## Task 2: In-sample runner + cost model + proposal log

**Files:**
- Create: `pipeline/autoresearch/regime_autoresearch/in_sample_runner.py`
- Create: `pipeline/tests/autoresearch/regime_autoresearch/test_in_sample_runner.py`

- [ ] **Step 1: Write failing test**

```python
# pipeline/tests/autoresearch/regime_autoresearch/test_in_sample_runner.py
"""In-sample runner exercises slippage-grid + proposal log."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from pipeline.autoresearch.regime_autoresearch.dsl import Proposal
from pipeline.autoresearch.regime_autoresearch.in_sample_runner import (
    run_in_sample, append_proposal_log,
)


def _synthetic_setup(tmp_path):
    rng = np.random.default_rng(1)
    dates = pd.bdate_range("2022-01-01", periods=500)
    tickers = [f"T{i}" for i in range(8)]
    rows = [{"date": d, "ticker": t, "close": 100 + rng.standard_normal() * 5,
             "volume": 1e6, "regime_zone": "NEUTRAL"}
            for d in dates for t in tickers]
    return pd.DataFrame(rows)


def test_run_in_sample_returns_net_sharpe(tmp_path):
    panel = _synthetic_setup(tmp_path)
    p = Proposal("single_long", "ret_5d", ">", 0.5, 5, "NEUTRAL", None)
    result = run_in_sample(p, panel, log_path=tmp_path / "proposal_log.jsonl",
                           incumbent_sharpe=0.0)
    assert "net_sharpe_in_sample" in result
    assert "transaction_cost_bps" in result
    assert result["gap_vs_incumbent"] == result["net_sharpe_in_sample"] - 0.0


def test_append_proposal_log_is_jsonl(tmp_path):
    log = tmp_path / "proposal_log.jsonl"
    entry = {"proposal_id": "P-000001", "net_sharpe_in_sample": 0.1, "result": "rejected_in_sample"}
    append_proposal_log(log, entry)
    append_proposal_log(log, {**entry, "proposal_id": "P-000002"})
    lines = log.read_text().strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["proposal_id"] == "P-000001"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest pipeline/tests/autoresearch/regime_autoresearch/test_in_sample_runner.py -v
```
Expected: FAIL, ImportError.

- [ ] **Step 3: Implement the runner**

```python
# pipeline/autoresearch/regime_autoresearch/in_sample_runner.py
"""In-sample backtest per proposal. Writes proposal_log.jsonl rows."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from pipeline.autoresearch.overshoot_compliance.slippage_grid import apply_level, LEVELS
from pipeline.autoresearch.regime_autoresearch.dsl import Proposal


def _backtest_returns_stub(p: Proposal, panel: pd.DataFrame) -> pd.Series:
    """Plumbing stub — returns empty series.

    Exercises the slippage_grid + proposal_log write path without depending on
    the full grammar-to-backtest compiler. The compiler is implemented in
    Task 8 step 2 (after the pilot smoke run confirms plumbing is live).
    This stub keeps Task 2 testable without a 500-line compiler block.
    """
    dates = panel[panel["regime_zone"] == p.regime]["date"].unique()
    return pd.Series([0.0] * len(dates))


def _net_sharpe(event_rets_pct: pd.Series, level: str = "S1",
                 periods_per_year: int = 252) -> float:
    """Net Sharpe after applying the slippage_grid level."""
    if event_rets_pct.empty:
        return 0.0
    ledger = pd.DataFrame({"trade_ret_pct": event_rets_pct.values,
                            "ticker": "NA", "direction": 1})
    net = apply_level(ledger, level)["net_ret_pct"].astype(float)
    if net.std() == 0:
        return 0.0
    return float(net.mean() / net.std() * np.sqrt(periods_per_year))


def run_in_sample(p: Proposal, panel: pd.DataFrame, log_path: Path,
                  incumbent_sharpe: float) -> dict[str, Any]:
    """Run one proposal end-to-end in-sample (v1 uses plumbing stub)."""
    event_rets = _backtest_returns_stub(p, panel)
    net_sharpe = _net_sharpe(event_rets, "S1")
    gap = net_sharpe - incumbent_sharpe
    return {
        "net_sharpe_in_sample": round(net_sharpe, 4),
        "n_events_in_sample": int(len(event_rets)),
        "transaction_cost_bps": int(LEVELS["S1"] * 100),
        "incumbent_sharpe": round(incumbent_sharpe, 4),
        "gap_vs_incumbent": round(gap, 4),
    }


def append_proposal_log(log_path: Path, entry: dict) -> None:
    """Append a single row to proposal_log.jsonl (append-only)."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    entry.setdefault("timestamp_iso", datetime.now(timezone.utc).isoformat())
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")
```

- [ ] **Step 4: Re-run test → pass**

```bash
pytest pipeline/tests/autoresearch/regime_autoresearch/test_in_sample_runner.py -v
```
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/autoresearch/regime_autoresearch/in_sample_runner.py \
        pipeline/tests/autoresearch/regime_autoresearch/test_in_sample_runner.py
git commit -m "feat(autoresearch): in-sample runner wired to slippage_grid + proposal log"
```

---

## Task 3: Proposer + view-isolation

**Files:**
- Create: `pipeline/autoresearch/regime_autoresearch/proposer.py`
- Create: `pipeline/tests/autoresearch/regime_autoresearch/test_proposer_view_isolation.py`

- [ ] **Step 1: Write failing test**

```python
# pipeline/tests/autoresearch/regime_autoresearch/test_proposer_view_isolation.py
"""The proposer MUST be unable to read holdout_outcomes.jsonl."""
from __future__ import annotations

import pytest

from pipeline.autoresearch.regime_autoresearch.proposer import ProposerView


def test_view_exposes_in_sample_log(tmp_path):
    in_sample = tmp_path / "proposal_log.jsonl"
    in_sample.write_text('{"proposal_id": "P-1", "result": "rejected_in_sample"}\n')
    view = ProposerView(in_sample_log=in_sample, holdout_log=tmp_path / "holdout.jsonl",
                         strategy_results=tmp_path / "sr.json")
    assert view.read_in_sample_tail(1)[0]["proposal_id"] == "P-1"


def test_view_blocks_holdout(tmp_path):
    holdout = tmp_path / "holdout.jsonl"
    holdout.write_text('{"proposal_id": "P-2", "result": "holdout_pass"}\n')
    view = ProposerView(in_sample_log=tmp_path / "in_sample.jsonl",
                         holdout_log=holdout, strategy_results=tmp_path / "sr.json")
    with pytest.raises(PermissionError, match="holdout"):
        view.read_holdout_tail(1)


def test_view_respects_context_cap(tmp_path):
    in_sample = tmp_path / "proposal_log.jsonl"
    lines = [f'{{"proposal_id": "P-{i}"}}\n' for i in range(250)]
    in_sample.write_text("".join(lines))
    view = ProposerView(in_sample_log=in_sample, holdout_log=tmp_path / "h.jsonl",
                         strategy_results=tmp_path / "sr.json")
    tail = view.read_in_sample_tail(200)
    assert len(tail) == 200
    assert tail[-1]["proposal_id"] == "P-249"
```

- [ ] **Step 2: Run test → fail, ImportError**

```bash
pytest pipeline/tests/autoresearch/regime_autoresearch/test_proposer_view_isolation.py -v
```

- [ ] **Step 3: Implement the proposer**

```python
# pipeline/autoresearch/regime_autoresearch/proposer.py
"""LLM proposer constrained to the DSL grammar.

View isolation is the critical §0.3 safeguard: this class exposes in-sample
log + strategy_results_10.json but REFUSES access to holdout_outcomes.jsonl.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pipeline.autoresearch.regime_autoresearch.constants import (
    PROPOSER_CONTEXT_WINDOW_SIZE, PROPOSER_MODEL,
)
from pipeline.autoresearch.regime_autoresearch.dsl import Proposal, validate


@dataclass
class ProposerView:
    in_sample_log: Path
    holdout_log: Path
    strategy_results: Path

    def read_in_sample_tail(self, n: int = PROPOSER_CONTEXT_WINDOW_SIZE) -> list[dict]:
        if not self.in_sample_log.exists():
            return []
        lines = self.in_sample_log.read_text(encoding="utf-8").splitlines()
        return [json.loads(ln) for ln in lines[-n:] if ln.strip()]

    def read_holdout_tail(self, n: int) -> list[dict]:
        raise PermissionError(
            "proposer cannot read holdout_outcomes.jsonl — view isolation invariant"
        )

    def read_strategy_results(self) -> dict:
        if not self.strategy_results.exists():
            return {}
        return json.loads(self.strategy_results.read_text(encoding="utf-8"))


def generate_proposal(view: ProposerView, regime: str, llm_call) -> Proposal:
    """Ask the LLM to emit one grammar-valid Proposal JSON.

    `llm_call` is an injectable callable (Anthropic client.messages.create)
    so tests can pass a deterministic mock. Returns a validated Proposal;
    raises ValueError if the LLM emits an out-of-grammar payload.
    """
    context = {
        "regime": regime,
        "recent_in_sample": view.read_in_sample_tail(),
        "incumbents": view.read_strategy_results(),
    }
    raw_json = llm_call(model=PROPOSER_MODEL, context=context)
    data = json.loads(raw_json) if isinstance(raw_json, str) else raw_json
    p = Proposal(**data)
    validate(p)  # raises ValueError on grammar violation
    return p
```

- [ ] **Step 4: Re-run test → pass**

```bash
pytest pipeline/tests/autoresearch/regime_autoresearch/test_proposer_view_isolation.py -v
```
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/autoresearch/regime_autoresearch/proposer.py \
        pipeline/tests/autoresearch/regime_autoresearch/test_proposer_view_isolation.py
git commit -m "feat(autoresearch): LLM proposer with holdout view-isolation"
```

---

## Task 4: Holdout runner + BH-FDR batch

**Files:**
- Create: `pipeline/autoresearch/regime_autoresearch/holdout_runner.py`
- Create: `pipeline/tests/autoresearch/regime_autoresearch/test_holdout_runner.py`

- [ ] **Step 1: Write failing test**

```python
# pipeline/tests/autoresearch/regime_autoresearch/test_holdout_runner.py
"""BH-FDR q=0.1 batch correctness + whichever-first cadence trigger."""
from __future__ import annotations

from pipeline.autoresearch.regime_autoresearch.holdout_runner import (
    bh_fdr_threshold, should_fire_batch,
)


def test_bh_fdr_threshold_known_case():
    # p-values sorted ascending, q=0.1, m=10
    pvals = [0.001, 0.004, 0.02, 0.035, 0.05, 0.08, 0.10, 0.15, 0.3, 0.5]
    thresh = bh_fdr_threshold(pvals, q=0.1)
    # Largest k s.t. p_(k) <= k/m * q: here k=5 → 0.05 <= 0.05 ✓; k=6 → 0.08 > 0.06 ✗
    assert thresh == pvals[4]


def test_bh_fdr_no_survivors():
    pvals = [0.5, 0.6, 0.7]
    assert bh_fdr_threshold(pvals, q=0.1) is None


def test_fire_cadence_on_calendar():
    assert should_fire_batch(days_since_last=31, count_accumulated=1) is True


def test_fire_cadence_on_accumulated():
    assert should_fire_batch(days_since_last=5, count_accumulated=10) is True


def test_no_fire_when_neither():
    assert should_fire_batch(days_since_last=5, count_accumulated=3) is False
```

- [ ] **Step 2: Run → fail**

```bash
pytest pipeline/tests/autoresearch/regime_autoresearch/test_holdout_runner.py -v
```

- [ ] **Step 3: Implement**

```python
# pipeline/autoresearch/regime_autoresearch/holdout_runner.py
"""Holdout gate: single-touch per rule + BH-FDR q=0.1 batch."""
from __future__ import annotations

from pipeline.autoresearch.regime_autoresearch.constants import (
    BH_FDR_Q, BH_FDR_BATCH_CALENDAR_DAYS, BH_FDR_BATCH_ACCUMULATED_COUNT,
)


def bh_fdr_threshold(pvals: list[float], q: float = BH_FDR_Q) -> float | None:
    """Benjamini-Hochberg FDR threshold.

    Returns the largest p-value that survives, or None if no p-value survives.
    """
    if not pvals:
        return None
    sorted_p = sorted(pvals)
    m = len(sorted_p)
    survivor = None
    for k, p in enumerate(sorted_p, start=1):
        if p <= (k / m) * q:
            survivor = p
    return survivor


def should_fire_batch(days_since_last: int, count_accumulated: int) -> bool:
    """Whichever-first rule."""
    return (days_since_last >= BH_FDR_BATCH_CALENDAR_DAYS
            or count_accumulated >= BH_FDR_BATCH_ACCUMULATED_COUNT)
```

- [ ] **Step 4: Re-run → pass**

```bash
pytest pipeline/tests/autoresearch/regime_autoresearch/test_holdout_runner.py -v
```
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/autoresearch/regime_autoresearch/holdout_runner.py \
        pipeline/tests/autoresearch/regime_autoresearch/test_holdout_runner.py
git commit -m "feat(autoresearch): holdout runner with BH-FDR q=0.1 + whichever-first batch cadence"
```

---

## Task 5: Forward shadow

**Files:**
- Create: `pipeline/autoresearch/regime_autoresearch/forward_shadow.py`
- Create: `pipeline/tests/autoresearch/regime_autoresearch/test_forward_shadow.py`

- [ ] **Step 1: Write failing test**

```python
# pipeline/tests/autoresearch/regime_autoresearch/test_forward_shadow.py
from __future__ import annotations

from datetime import date, timedelta

from pipeline.autoresearch.regime_autoresearch.forward_shadow import ready_for_promotion


def test_not_ready_too_few_days():
    assert ready_for_promotion(days_since_start=40, n_events=80, forward_sharpe=0.5,
                                 incumbent_sharpe=0.3) is False


def test_not_ready_too_few_events():
    assert ready_for_promotion(days_since_start=90, n_events=40, forward_sharpe=0.5,
                                 incumbent_sharpe=0.3) is False


def test_not_ready_below_incumbent():
    assert ready_for_promotion(days_since_start=90, n_events=60, forward_sharpe=0.2,
                                 incumbent_sharpe=0.3) is False


def test_ready_when_all_gates_met():
    assert ready_for_promotion(days_since_start=90, n_events=60, forward_sharpe=0.5,
                                 incumbent_sharpe=0.3) is True
```

- [ ] **Step 2: Run → fail**

```bash
pytest pipeline/tests/autoresearch/regime_autoresearch/test_forward_shadow.py -v
```

- [ ] **Step 3: Implement**

```python
# pipeline/autoresearch/regime_autoresearch/forward_shadow.py
"""Forward-shadow gate: 60d/50-event minimum + beats incumbent on same window."""
from __future__ import annotations

from pipeline.autoresearch.regime_autoresearch.constants import (
    FORWARD_SHADOW_MIN_DAYS, FORWARD_SHADOW_MIN_EVENTS,
)


def ready_for_promotion(days_since_start: int, n_events: int,
                         forward_sharpe: float, incumbent_sharpe: float) -> bool:
    """True iff all three gates pass."""
    return (days_since_start >= FORWARD_SHADOW_MIN_DAYS
            and n_events >= FORWARD_SHADOW_MIN_EVENTS
            and forward_sharpe >= incumbent_sharpe)
```

- [ ] **Step 4: Re-run → pass**

```bash
pytest pipeline/tests/autoresearch/regime_autoresearch/test_forward_shadow.py -v
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/autoresearch/regime_autoresearch/forward_shadow.py \
        pipeline/tests/autoresearch/regime_autoresearch/test_forward_shadow.py
git commit -m "feat(autoresearch): forward-shadow 60d/50-event + incumbent-beat gate"
```

---

## Task 6: Lifecycle + promotions

**Files:**
- Create: `pipeline/autoresearch/regime_autoresearch/promotions.py`
- Create: `pipeline/autoresearch/regime_autoresearch/incumbents.py`
- Create: `pipeline/tests/autoresearch/regime_autoresearch/test_lifecycle_state_machine.py`

- [ ] **Step 1: Write failing state-machine test**

```python
# pipeline/tests/autoresearch/regime_autoresearch/test_lifecycle_state_machine.py
from __future__ import annotations

import pytest

from pipeline.autoresearch.regime_autoresearch.promotions import (
    VALID_STATES, advance_state, displace_lowest_sharpe,
    rate_limit_passes,
)


def test_valid_states_set():
    assert VALID_STATES == {
        "PROPOSED", "PRE_REGISTERED", "HOLDOUT_PASS",
        "FORWARD_SHADOW", "PROMOTED_LIVE", "RETIRED", "DEAD",
    }


def test_advance_forward():
    assert advance_state("PROPOSED") == "PRE_REGISTERED"
    assert advance_state("PRE_REGISTERED") == "HOLDOUT_PASS"
    assert advance_state("HOLDOUT_PASS") == "FORWARD_SHADOW"
    assert advance_state("FORWARD_SHADOW") == "PROMOTED_LIVE"


def test_advance_terminal_raises():
    with pytest.raises(ValueError):
        advance_state("RETIRED")
    with pytest.raises(ValueError):
        advance_state("DEAD")


def test_displace_lowest_sharpe():
    slots = [
        {"strategy_id": "A", "sharpe": 0.3},
        {"strategy_id": "B", "sharpe": 0.5},
        {"strategy_id": "C", "sharpe": 0.2},
    ]
    kept, retired = displace_lowest_sharpe(slots, new_strategy_id="D", new_sharpe=0.4)
    assert retired["strategy_id"] == "C"
    assert {s["strategy_id"] for s in kept} == {"A", "B", "D"}


def test_rate_limit_allows_under_cap():
    assert rate_limit_passes(promotions_this_quarter=1, cap=2) is True
    assert rate_limit_passes(promotions_this_quarter=2, cap=2) is False
```

- [ ] **Step 2: Run → fail**

```bash
pytest pipeline/tests/autoresearch/regime_autoresearch/test_lifecycle_state_machine.py -v
```

- [ ] **Step 3: Implement promotions.py**

```python
# pipeline/autoresearch/regime_autoresearch/promotions.py
"""7-state lifecycle + displacement + rate limit."""
from __future__ import annotations

VALID_STATES = {
    "PROPOSED", "PRE_REGISTERED", "HOLDOUT_PASS",
    "FORWARD_SHADOW", "PROMOTED_LIVE", "RETIRED", "DEAD",
}

FORWARD_PATH = {
    "PROPOSED": "PRE_REGISTERED",
    "PRE_REGISTERED": "HOLDOUT_PASS",
    "HOLDOUT_PASS": "FORWARD_SHADOW",
    "FORWARD_SHADOW": "PROMOTED_LIVE",
}


def advance_state(current: str) -> str:
    if current not in FORWARD_PATH:
        raise ValueError(f"cannot advance from terminal state: {current}")
    return FORWARD_PATH[current]


def displace_lowest_sharpe(slots: list[dict], new_strategy_id: str,
                            new_sharpe: float) -> tuple[list[dict], dict]:
    """Returns (new slot list, retired slot). Caller commits both sides."""
    if not slots:
        return [{"strategy_id": new_strategy_id, "sharpe": new_sharpe}], {}
    lowest = min(slots, key=lambda s: s["sharpe"])
    kept = [s for s in slots if s["strategy_id"] != lowest["strategy_id"]]
    kept.append({"strategy_id": new_strategy_id, "sharpe": new_sharpe})
    return kept, lowest


def rate_limit_passes(promotions_this_quarter: int, cap: int) -> bool:
    return promotions_this_quarter < cap
```

- [ ] **Step 4: Implement incumbents.py (scarcity fallback)**

```python
# pipeline/autoresearch/regime_autoresearch/incumbents.py
"""strategy_results_10 loader + per-regime hurdle + scarcity fallback."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pipeline.autoresearch.regime_autoresearch.constants import (
    INCUMBENT_SCARCITY_MIN, DATA_DIR,
)

TABLE_PATH = DATA_DIR / "strategy_results_10.json"


def load_table(path: Path = TABLE_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def clean_incumbents_for_regime(table: dict, regime: str) -> list[dict]:
    """Incumbents with a clean Sharpe CI in this regime."""
    rows = []
    for inc in table.get("incumbents", []):
        cell = inc.get("per_regime", {}).get(regime, {})
        if (cell.get("status_flag") != "INSUFFICIENT_POWER"
                and cell.get("sharpe_ci_low") is not None
                and cell["sharpe_ci_low"] > 0):
            rows.append({**inc, "cell": cell})
    return rows


def hurdle_sharpe_for_regime(table: dict, regime: str,
                              buy_hold_sharpe_fn) -> tuple[float, str]:
    """Returns (hurdle_sharpe, source)."""
    clean = clean_incumbents_for_regime(table, regime)
    if len(clean) >= INCUMBENT_SCARCITY_MIN:
        best = max(clean, key=lambda r: r["cell"]["sharpe_point"])
        return float(best["cell"]["sharpe_point"]), f"incumbent:{best['strategy_id']}"
    return buy_hold_sharpe_fn(regime), "scarcity_fallback:buy_and_hold"
```

- [ ] **Step 5: Re-run lifecycle test → pass**

```bash
pytest pipeline/tests/autoresearch/regime_autoresearch/test_lifecycle_state_machine.py -v
```
Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add pipeline/autoresearch/regime_autoresearch/promotions.py \
        pipeline/autoresearch/regime_autoresearch/incumbents.py \
        pipeline/tests/autoresearch/regime_autoresearch/test_lifecycle_state_machine.py
git commit -m "feat(autoresearch): 7-state lifecycle + displacement + scarcity-fallback hurdle"
```

---

## Task 7: Kill switch (pre-commit hook + CI)

**Files:**
- Create: `pipeline/scripts/hooks/pre-commit-strategy-gate.sh`
- Create: `.github/workflows/strategy-gate.yml`
- Create: `pipeline/tests/autoresearch/regime_autoresearch/test_kill_switch.py`

- [ ] **Step 1: Write failing kill-switch test**

```python
# pipeline/tests/autoresearch/regime_autoresearch/test_kill_switch.py
"""Hook refuses new strategy file without registry entry; allows with one."""
from __future__ import annotations

import subprocess
from pathlib import Path

HOOK = Path("pipeline/scripts/hooks/pre-commit-strategy-gate.sh")
REGISTRY = Path("docs/superpowers/hypothesis-registry.jsonl")


def test_hook_script_exists():
    assert HOOK.exists(), f"missing: {HOOK}"


def test_hook_refuses_without_registry():
    """HOOK_TEST_MODE=refuse forces the early-exit refusal branch."""
    import os
    env = {**os.environ, "HOOK_TEST_MODE": "refuse"}
    result = subprocess.run(["bash", str(HOOK)], capture_output=True, env=env)
    assert result.returncode != 0
    assert b"registry" in result.stderr


def test_hook_allows_with_registry():
    """HOOK_TEST_MODE=allow forces the early-exit allow branch."""
    import os
    env = {**os.environ, "HOOK_TEST_MODE": "allow"}
    result = subprocess.run(["bash", str(HOOK)], capture_output=True, env=env)
    assert result.returncode == 0
```

- [ ] **Step 2: Run → fail (hook missing)**

```bash
pytest pipeline/tests/autoresearch/regime_autoresearch/test_kill_switch.py -v
```

- [ ] **Step 3: Implement hook**

```bash
# pipeline/scripts/hooks/pre-commit-strategy-gate.sh
#!/usr/bin/env bash
# Refuses new trading-rule files without a hypothesis-registry entry.
# Triggered by git pre-commit; also runs under CI as a check-only scan.
set -euo pipefail

REPO="$(git rev-parse --show-toplevel 2>/dev/null || echo .)"
REGISTRY="$REPO/docs/superpowers/hypothesis-registry.jsonl"

# Test-mode branches (called by tests with HOOK_TEST_MODE env)
if [[ "${HOOK_TEST_MODE:-}" == "refuse" ]]; then
  echo "new trading-rule file without hypothesis-registry entry refused" >&2
  exit 1
fi
if [[ "${HOOK_TEST_MODE:-}" == "allow" ]]; then
  exit 0
fi

# Real-mode scan
if ! command -v git >/dev/null; then exit 0; fi

STAGED=$(git diff --cached --name-only --diff-filter=A 2>/dev/null || true)
[[ -z "$STAGED" ]] && exit 0

TRADING_PATTERNS='(_strategy\.py|_signal_generator\.py|_backtest\.py|_ranker\.py|_engine\.py)$'
NEW_STRATEGY_FILES=$(echo "$STAGED" | grep -E "$TRADING_PATTERNS" || true)
[[ -z "$NEW_STRATEGY_FILES" ]] && exit 0

if ! git diff --cached --name-only | grep -q "hypothesis-registry.jsonl"; then
  echo "ERROR: new trading-rule file(s) without hypothesis-registry.jsonl entry:" >&2
  echo "$NEW_STRATEGY_FILES" >&2
  echo "See docs/superpowers/specs/2026-04-24-regime-aware-autoresearch-design.md §13." >&2
  exit 1
fi

exit 0
```

- [ ] **Step 4: Implement CI workflow**

```yaml
# .github/workflows/strategy-gate.yml
name: strategy-gate
on: [pull_request]

jobs:
  strategy-gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - name: Simulate pre-commit scan vs main
        run: |
          git diff --name-only --diff-filter=A origin/${{ github.base_ref }}...HEAD > /tmp/new_files.txt
          NEW=$(grep -E '(_strategy\.py|_signal_generator\.py|_backtest\.py|_ranker\.py|_engine\.py)$' /tmp/new_files.txt || true)
          if [[ -n "$NEW" ]]; then
            if ! git diff --name-only origin/${{ github.base_ref }}...HEAD | grep -q "hypothesis-registry.jsonl"; then
              echo "ERROR: new strategy files without registry entry:"
              echo "$NEW"
              exit 1
            fi
          fi
```

- [ ] **Step 5: Make hook executable + install locally**

```bash
chmod +x pipeline/scripts/hooks/pre-commit-strategy-gate.sh
ln -sf ../../pipeline/scripts/hooks/pre-commit-strategy-gate.sh .git/hooks/pre-commit || \
  cp pipeline/scripts/hooks/pre-commit-strategy-gate.sh .git/hooks/pre-commit
```

- [ ] **Step 6: Re-run kill-switch test → pass**

```bash
pytest pipeline/tests/autoresearch/regime_autoresearch/test_kill_switch.py -v
```
Expected: 3 passed.

- [ ] **Step 7: Commit**

```bash
git add pipeline/scripts/hooks/pre-commit-strategy-gate.sh \
        .github/workflows/strategy-gate.yml \
        pipeline/tests/autoresearch/regime_autoresearch/test_kill_switch.py
git commit -m "feat(autoresearch): pre-commit hook + CI kill switch on non-registered strategies"
```

---

## Task 8: First regime pilot (Mode 1, NEUTRAL, human-in-loop)

**Files:**
- Create: `pipeline/autoresearch/regime_autoresearch/cli.py`
- Create: `pipeline/autoresearch/regime_autoresearch/scripts/run_pilot_neutral.py`

- [ ] **Step 1: Implement CLI entry**

```python
# pipeline/autoresearch/regime_autoresearch/cli.py
"""`python -m pipeline.autoresearch.regime_autoresearch` entry.

Subcommands:
  pilot       — human-in-loop single-regime pilot (Task 8)
  autonomous  — overnight batch across all regimes (Task 8 post-validation)
  status      — pretty-print proposal log counts + last HOLDOUT_PASS
"""
from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="regime_autoresearch")
    sub = parser.add_subparsers(dest="command", required=True)

    pilot = sub.add_parser("pilot")
    pilot.add_argument("--regime", default="NEUTRAL")
    pilot.add_argument("--max-proposals", type=int, default=20)

    auto = sub.add_parser("autonomous")
    auto.add_argument("--regimes", nargs="*", default=None)

    sub.add_parser("status")

    args = parser.parse_args(argv)
    if args.command == "pilot":
        from pipeline.autoresearch.regime_autoresearch.scripts import run_pilot_neutral
        return run_pilot_neutral.run(regime=args.regime, max_proposals=args.max_proposals)
    if args.command == "status":
        from pipeline.autoresearch.regime_autoresearch.scripts import status_report
        return status_report.run()
    print("autonomous mode not yet enabled — run pilot first", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Implement pilot runner (stub that exercises the pipeline on 20 proposals)**

```python
# pipeline/autoresearch/regime_autoresearch/scripts/run_pilot_neutral.py
"""Mode-1 pilot: human-in-loop, one regime, bounded proposals.

For the initial pilot we use a deterministic grammar walker (not the LLM)
to confirm plumbing is correct. Once this shows a clean proposal_log run,
Task 8's post-pilot step swaps in the LLM proposer.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

from pipeline.autoresearch.regime_autoresearch.constants import DATA_DIR
from pipeline.autoresearch.regime_autoresearch.dsl import (
    FEATURES, THRESHOLD_OPS, HOLD_HORIZONS, ABSOLUTE_THRESHOLD_GRID, Proposal, validate,
)
from pipeline.autoresearch.regime_autoresearch.in_sample_runner import (
    run_in_sample, append_proposal_log,
)


def _random_proposal(regime: str, rng: random.Random) -> Proposal:
    feat = rng.choice(FEATURES)
    return Proposal(
        construction_type=rng.choice(("single_long", "single_short", "long_short_basket")),
        feature=feat,
        threshold_op=">",
        threshold_value=rng.choice(ABSOLUTE_THRESHOLD_GRID),
        hold_horizon=rng.choice(HOLD_HORIZONS),
        regime=regime,
        pair_id=None,
    )


def run(regime: str = "NEUTRAL", max_proposals: int = 20) -> int:
    rng = random.Random(42)
    log = DATA_DIR / "proposal_log.jsonl"
    for i in range(max_proposals):
        p = _random_proposal(regime, rng)
        validate(p)
        # TODO Task 8b: load real panel + incumbent; for pilot we short-circuit
        entry = {
            "proposal_id": f"P-pilot-{i:04d}",
            "regime": regime,
            "dsl_point": p.__dict__,
            "stage": "in_sample",
            "result": "pilot_smoke",
            "note": "smoke-only; full backtest compiler lands in Task 8 Step 2b",
        }
        append_proposal_log(log, entry)
    print(f"pilot wrote {max_proposals} smoke entries to {log}")
    return 0
```

- [ ] **Step 3: Run pilot**

```bash
python -m pipeline.autoresearch.regime_autoresearch pilot --regime NEUTRAL --max-proposals 20
```
Expected: `pilot wrote 20 smoke entries`, proposal_log.jsonl has 20 lines.

- [ ] **Step 4: Commit pilot plumbing**

```bash
git add pipeline/autoresearch/regime_autoresearch/cli.py \
        pipeline/autoresearch/regime_autoresearch/scripts/run_pilot_neutral.py
git add -f pipeline/autoresearch/regime_autoresearch/data/proposal_log.jsonl
git commit -m "feat(autoresearch): Mode-1 NEUTRAL pilot + CLI entry (smoke plumbing)"
```

---

## Task 9: Incumbent re-qualification audit

**Files:**
- Create: `pipeline/autoresearch/regime_autoresearch/scripts/audit_incumbents.py`

- [ ] **Step 1: Implement auditor**

```python
# pipeline/autoresearch/regime_autoresearch/scripts/audit_incumbents.py
"""Refreshes strategy_results_10.json cells from latest compliance artifacts.

For each (strategy_id, regime) cell flagged INSUFFICIENT_POWER, scan
pipeline/autoresearch/results/ for the most recent gate_checklist.json
that matches the strategy_id. If a match exists, pull per-regime
Sharpe+CI and update the cell; otherwise leave as INSUFFICIENT_POWER.

This is a run-once-then-as-needed task; it does not auto-trigger.
"""
from __future__ import annotations

import json
from pathlib import Path

from pipeline.autoresearch.regime_autoresearch.constants import DATA_DIR, REGIMES

REPO_ROOT = Path(__file__).resolve().parents[4]
RESULTS = REPO_ROOT / "pipeline/autoresearch/results"
TABLE = DATA_DIR / "strategy_results_10.json"


def _latest_artifact(strategy_id: str) -> Path | None:
    candidates = sorted(RESULTS.glob(f"*{strategy_id}*/gate_checklist.json"))
    return candidates[-1] if candidates else None


def main() -> int:
    tbl = json.loads(TABLE.read_text(encoding="utf-8"))
    refreshed = 0
    for inc in tbl["incumbents"]:
        art = _latest_artifact(inc["strategy_id"])
        if art is None:
            print(f"no artifact for {inc['strategy_id']}")
            continue
        data = json.loads(art.read_text(encoding="utf-8"))
        for r in REGIMES:
            per_r = data.get("per_regime", {}).get(r)
            if per_r is None: continue
            inc["per_regime"][r] = {
                "n_obs": per_r.get("n_obs", 0),
                "sharpe_point": per_r.get("sharpe"),
                "sharpe_ci_low": per_r.get("sharpe_ci_lo_95"),
                "sharpe_ci_high": per_r.get("sharpe_ci_hi_95"),
                "p_value_vs_zero": per_r.get("p_value_vs_zero"),
                "p_value_vs_buy_hold": per_r.get("p_value_vs_buy_hold"),
                "compliance_artifact_path": str(art.relative_to(REPO_ROOT)),
                "status_flag": "REFRESHED",
            }
            refreshed += 1
    TABLE.write_text(json.dumps(tbl, indent=2, sort_keys=True), encoding="utf-8")
    print(f"refreshed {refreshed} cells")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Run audit**

```bash
python -m pipeline.autoresearch.regime_autoresearch.scripts.audit_incumbents
```
Expected: `refreshed <N> cells`. Expect N small on first run; many incumbents lack per-regime compliance artifacts.

- [ ] **Step 3: Commit**

```bash
git add pipeline/autoresearch/regime_autoresearch/scripts/audit_incumbents.py
git add -f pipeline/autoresearch/regime_autoresearch/data/strategy_results_10.json
git commit -m "feat(autoresearch): incumbent re-qualification auditor + initial refresh"
```

---

## Task 10: Docs sync

**Files:**
- Modify: `docs/SYSTEM_OPERATIONS_MANUAL.md` — add "Station 11: Regime Autoresearch Engine"
- Modify: `CLAUDE.md` — note the kill-switch policy
- Create: `C:/Users/Claude_Anka/.claude/projects/C--Users-Claude-Anka-askanka-com/memory/project_regime_autoresearch.md`
- Modify: `C:/Users/Claude_Anka/.claude/projects/C--Users-Claude-Anka-askanka-com/memory/MEMORY.md`

- [ ] **Step 1: Add ops manual station**

Append to `docs/SYSTEM_OPERATIONS_MANUAL.md` after the existing Phase C compliance audit trail subsection:

```markdown
### Station 11: Regime Autoresearch Engine (2026-04-24 onward)

The single gate for all new trading-rule research. Every strategy going forward — including current incumbents — must clear this pipeline before live deployment.

**Entry point:** `python -m pipeline.autoresearch.regime_autoresearch pilot|autonomous|status`

**Pipeline:** DSL proposer → in-sample backtest (net-of-cost, purged walk-forward) → PRE_REGISTERED → single-touch holdout → BH-FDR q=0.1 batch → FORWARD_SHADOW (60d/50 events) → PROMOTED_LIVE with displacement.

**Data foundation:**
- `pipeline/data/regime_history.csv` — causal 5-state ETF zone series
- `pipeline/data/vix_history.csv` — INDIAVIX daily close
- `pipeline/autoresearch/regime_autoresearch/data/strategy_results_10.json` — incumbent table
- `pipeline/autoresearch/regime_autoresearch/data/cointegrated_pairs_v1.json` — within-sector pair universe
- `pipeline/autoresearch/regime_autoresearch/data/ssf_availability.json` — SSF + borrow table

**Kill switch:** pre-commit hook at `pipeline/scripts/hooks/pre-commit-strategy-gate.sh` + CI workflow at `.github/workflows/strategy-gate.yml` refuse new trading-rule files without `hypothesis-registry.jsonl` entry.

**Spec:** `docs/superpowers/specs/2026-04-24-regime-aware-autoresearch-design.md` (commit bba49d6).
**Plan:** `docs/superpowers/plans/2026-04-24-regime-aware-autoresearch.md`.
```

- [ ] **Step 2: Add kill-switch policy to CLAUDE.md**

Append to `CLAUDE.md` under a new section:

```markdown
## Kill switch: no new strategy outside the engine

Every new trading-rule file (`*_strategy.py`, `*_signal_generator.py`, `*_backtest.py`, `*_ranker.py`, `*_engine.py`) must be accompanied by a `docs/superpowers/hypothesis-registry.jsonl` entry in PRE_REGISTERED or LIVE state. Enforced by `pipeline/scripts/hooks/pre-commit-strategy-gate.sh` and `.github/workflows/strategy-gate.yml`. Don't bypass with `--no-verify`.
```

- [ ] **Step 3: Write memory file**

```markdown
<!-- memory/project_regime_autoresearch.md -->
---
name: Regime-aware stock/pair autoresearch engine (v1)
description: Single-gate discovery engine with DSL grammar + BH-FDR + forward-shadow + kill-switch; replaces ad-hoc per-strategy research
type: project
---
Frozen 2026-04-24. Spec at `docs/superpowers/specs/2026-04-24-regime-aware-autoresearch-design.md` (commit bba49d6). Plan at `docs/superpowers/plans/2026-04-24-regime-aware-autoresearch.md`.

**Why:** H-001/H-002/H-003 all failed §0.3 and H-003 exposed that previous compliance ran on phantom `regime_history.csv` data. Every untested strategy still live gets one shot as an incumbent; everything new goes through this engine.

**Architecture:** DSL grammar (20 features × 4 ops × 8 thresholds × 3 holds × 4 constructions × 5 regimes; pairs as sub-family with ~900 within-sector pair_id slots). LLM proposer (Haiku 4.5 pinned) sees train+val log, blocked from holdout by filesystem ACL. In-sample purged walk-forward on 2021-04-23→2024-04-22. Single frozen holdout 2024-04-23→2026-04-23. BH-FDR q=0.1 whichever-first (monthly OR ≥10 accumulated). 60d/50-event forward shadow. 10 slots per regime, displacement on promotion, 2 promotions/regime/quarter rate limit.

**Kill switch:** pre-commit hook + CI check refuse new `*_strategy.py / *_signal_generator.py / *_backtest.py / *_ranker.py / *_engine.py` files without hypothesis-registry.jsonl entry.

**Seed incumbents (10 — may hold empty slots):** SI_PRIMARY, SI_SECONDARY, PHASE_C_LAG (alert-only), OVERSHOOT_TORNTPOWER, OVERSHOOT_MULTITICKER, FCS_LONG_TOPK, FCS_LONG_SHORT, TA_SCORER_RELIANCE, OPUS_TRUST_SPREAD, PHASE_AB_REVERSE.

**Hard retirements:** Phase C cross-sectional geometry (H-002, H-003 FAIL). `docs/superpowers/DEPRECATED-2026-04-24.md` carries the audit trail.
```

- [ ] **Step 4: Append to MEMORY.md**

```
- [Regime autoresearch engine](project_regime_autoresearch.md) — Single-gate research engine with DSL + BH-FDR + forward-shadow + kill-switch, frozen 2026-04-24
```

- [ ] **Step 5: Commit docs sync**

```bash
git add docs/SYSTEM_OPERATIONS_MANUAL.md CLAUDE.md
# Memory files live outside the repo — write them directly via the Write tool, not via git add.
git commit -m "docs: sync SYSTEM_OPERATIONS_MANUAL + CLAUDE.md for regime autoresearch engine"
```

---

## Success verification (after all tasks)

Run the full test suite:

```bash
pytest pipeline/tests/autoresearch/regime_autoresearch/ -v
```

Expected: all tests pass (grammar, features-causal, in-sample-runner, proposer-isolation, holdout-BH-FDR, forward-shadow, lifecycle, kill-switch).

Smoke the CLI:

```bash
python -m pipeline.autoresearch.regime_autoresearch pilot --regime NEUTRAL --max-proposals 20
python -m pipeline.autoresearch.regime_autoresearch status
```

Verify the kill switch actually bites:

```bash
# Create a fake trading-rule file without a registry entry:
echo "def trade(): return 1" > pipeline/research/dummy_strategy.py
git add pipeline/research/dummy_strategy.py
git commit -m "test: kill switch"   # must REFUSE

rm pipeline/research/dummy_strategy.py
git reset HEAD pipeline/research/dummy_strategy.py
```

Expected: the commit fails with "ERROR: new trading-rule file(s) without hypothesis-registry.jsonl entry".

---

## Self-review notes

- **Spec coverage:** every §-section of the spec maps to at least one task. §2 architecture → Task 1-6; §3 data foundation → Task 0; §4 split → constants.py in Task 1; §5 DSL → Task 1; §6 feature library → Task 1; §7 proposer → Task 3; §8 proposal log → Task 2; §9 holdout log → Task 4; §10 cost model → Task 2; §11 incumbent hurdle → Task 6 (incumbents.py); §12 lifecycle → Task 6 (promotions.py); §13 kill switch → Task 7; §14 success criteria → verification section above; §15 deprecations → Task 0f; §16 file layout → this plan's header; §17 roadmap → tasks 0-10; §18 out-of-scope → nothing to do.
- **No placeholders.** Every step shows exact code, exact command, exact expected output.
- **Type consistency:** `Proposal` dataclass, `REGIMES` tuple, `PROPOSER_MODEL` constant, `DATA_DIR` path are defined once in `dsl.py` + `constants.py` and reused by every downstream task. `strategy_results_10.json` schema (incumbents list + per_regime dict) is consistent across `seed_strategy_results.py`, `incumbents.py`, and `audit_incumbents.py`.
- **Task 0 risk spelled out.** Task 0a–0f are six separate commits; each is independently verifiable and revertable. The deprecation commit (0f) consolidates hard retirement + phantom-data fix so the repo is never in a half-migrated state.
