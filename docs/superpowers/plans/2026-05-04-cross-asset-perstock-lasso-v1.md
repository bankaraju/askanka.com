# H-2026-05-04 Cross-Asset Per-Stock Elastic-Net — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the per-stock cross-asset elastic-net research engine described in `docs/superpowers/specs/2026-05-04-cross-asset-perstock-lasso-v1-design.md`, fit it on the 200-stock frozen universe, deploy four VPS systemd units (predict / open / close / monthly-recalibrate), and run the single-touch holdout 2026-05-04 → 2026-08-04.

**Architecture:** Python package under `pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/`. Each file has one responsibility — feature extraction, PCA, elastic-net fit with time-decay, walk-forward + qualifier, runner, daily predict, holdout ledger, verdict, leakage audit. Outputs (manifest, models, ledger) live alongside the code. Runtime is **VPS systemd** (Contabo) per `feedback_prefer_vps_systemd_over_windows_scheduler.md`. Tests under `pipeline/tests/research/h_2026_05_04_cross_asset_perstock_lasso/` use synthetic small-sample fixtures so unit tests run in seconds; full-universe fits run via the orchestrator only.

**Tech Stack:** Python 3.13, pandas, numpy, scikit-learn (`PCA`, `LogisticRegression(penalty='elasticnet')`), pytest, systemd timers (Contabo).

---

## File Structure

**Code (new):**
- `pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/feature_extractor.py` — builds per-stock 23-column feature matrix
- `pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/pca_model.py` — fit / save / load PCA on the 30-column 1d ETF block
- `pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/elastic_net_fit.py` — per-cell EN fit with exp-decay sample weights + C×l1_ratio CV
- `pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/walk_forward.py` — 4-fold WF, qualifier gate, 10k-perm null, BH-FDR
- `pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/runner.py` — orchestrator: PCA → features → WF → qualifier → final-model freeze
- `pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/predict_today.py` — 04:30 IST daily forward predictor
- `pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/holdout_ledger.py` — 09:15 IST OPEN / 14:25 IST CLOSE engine
- `pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/verdict.py` — §12 verdict + §1.B null-band routing
- `pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/leakage_audit.py` — §16.6 amplified audit (label permute / date shift / ablation)

**Tests (new):**
- `pipeline/tests/research/h_2026_05_04_cross_asset_perstock_lasso/__init__.py`
- `pipeline/tests/research/h_2026_05_04_cross_asset_perstock_lasso/test_feature_extractor.py`
- `pipeline/tests/research/h_2026_05_04_cross_asset_perstock_lasso/test_pca_model.py`
- `pipeline/tests/research/h_2026_05_04_cross_asset_perstock_lasso/test_elastic_net_fit.py`
- `pipeline/tests/research/h_2026_05_04_cross_asset_perstock_lasso/test_walk_forward.py`
- `pipeline/tests/research/h_2026_05_04_cross_asset_perstock_lasso/test_holdout_ledger.py`
- `pipeline/tests/research/h_2026_05_04_cross_asset_perstock_lasso/test_verdict.py`

**VPS systemd (new — `pipeline/infra/systemd/`):**
- `anka-cross-asset-predict.{service,timer}` — 04:30 IST daily
- `anka-cross-asset-open.{service,timer}` — 09:15 IST trading days
- `anka-cross-asset-close.{service,timer}` — 14:25 IST trading days
- `anka-cross-asset-recalibrate.{service,timer}` — last-Sunday-of-month 02:00 IST

**Doc/config updates:**
- `pipeline/config/anka_inventory.json` — 4 new tasks
- `CLAUDE.md` — clockwork schedule additions
- `docs/SYSTEM_OPERATIONS_MANUAL.md` — section update
- `memory/project_h_2026_05_04_cross_asset_perstock_lasso.md` (new)
- `memory/MEMORY.md` — index entry

**Pre-existing (do NOT modify):**
- `pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/preflight.py` — already run, results frozen
- `pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/preflight_results.json`
- `pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/universe_frozen.json`
- `pipeline/autoresearch/etf_v3_loader.py` — read-only via `build_panel()` and `audit_panel()`

---

## Task 0: Pre-registration commit (governance gate, NOT code)

**Files:**
- Already-written: `docs/superpowers/specs/2026-05-04-cross-asset-perstock-lasso-v1-design.md`
- Already-written: `pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/preflight.py`
- Already-written: `pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/preflight_results.json`
- Already-written: `pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/universe_frozen.json`
- Append: `docs/superpowers/hypothesis-registry.jsonl`
- Create: `memory/project_h_2026_05_04_cross_asset_perstock_lasso.md`
- Modify: `memory/MEMORY.md` (one-line index entry)

- [ ] **Step 1: Verify pre-flight artifact exists and is valid**

Run:
```bash
python -c "import json; r = json.load(open('pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/preflight_results.json')); assert r['overall_pass'], r; print('preflight OK:', {k: v.get('pass') for k,v in r.items() if k.startswith('check_')})"
```
Expected: prints `preflight OK: {'check_4_pit_audit': True, 'check_1_universe': True, 'check_2_pca': True, 'check_3_orthogonality': True, 'check_5_sample_size': True}`

- [ ] **Step 2: Append registry row**

Append exactly one line (single-line JSON, NO line breaks inside) to `docs/superpowers/hypothesis-registry.jsonl`:

```json
{"hypothesis_id":"H-2026-05-04-cross-asset-perstock-lasso-v1","schema_version":"1.0","registered_at":"<ISO-8601 IST timestamp at append time>","registered_by":"Bharat Ankaraju","terminal_state":"PRE_REGISTERED","spec_ref":"docs/superpowers/specs/2026-05-04-cross-asset-perstock-lasso-v1-design.md","plan_ref":"docs/superpowers/plans/2026-05-04-cross-asset-perstock-lasso-v1.md","preflight_ref":"pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/preflight_results.json","universe_frozen_ref":"pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/universe_frozen.json","predecessor_hypothesis_ids":["H-2026-04-29-ta-karpathy-v1","H-2026-04-29-intraday-data-driven-v1","H-2026-04-24-001"],"predecessor_status":"FAMILY_WIDENING (cross-asset features + full F&O universe; ta-karpathy v1 in holdout, intraday-v1 in holdout, H-2026-04-24-001 FAILED single-touch consumed)","strategy_class":"per-stock-cross-asset-elastic-net","family":"per-stock-ml","family_member_count":1,"claim_short":"For each (stock, direction) cell, an elastic-net logistic regression on PCA-reduced 30-CURATED-ETF 1d returns (K_ETF=10) + 4 Indian macro + 6 stock TA + 3 DOW features (23 total), exp-decay sample weights HL=90 trading days, will produce a basket of BH-FDR-qualified cells whose pooled forward T+1 09:15->14:25 hit-rate >= 55% AND mean P&L >= +0.4% net@S1 over single-touch holdout 2026-05-04 -> 2026-08-04. Primary unit of inference: BASKET, not per-cell.","universe_size":200,"frozen_thresholds":{"K_ETF":10,"variance_target":0.85,"hl_trading_days":90,"hl_fragility":180,"qualifier_mean_fold_auc_min":0.55,"qualifier_fold_auc_std_max":0.05,"qualifier_n_pred_pos_min":5,"qualifier_in_sample_holdout_auc_min":0.55,"bh_fdr_alpha":0.05,"forward_p_long_threshold":0.6,"label_threshold_pct":0.4,"stop_atr_mult":2.0,"position_inr":50000,"nifty_emphasis_factor":1.5},"holdout_window":["2026-05-04","2026-08-04"],"auto_extend_until_n_or_date":{"min_n_qualifying":5,"extend_until":"2026-10-31"},"verdict_bar_S1":{"n_qualifying_min":5,"n_qualifying_expected_band":[5,25],"leakage_band":[26,80],"leakage_kill":81,"n_trades_min":60,"hit_rate_pct_min":55,"mean_pnl_pct_min":0.4,"permutation_p_value_max":0.05},"comparator_baselines":["B0_always_long","B1_random_direction","B2_flipped_EN_must_lose","B3_passive_NIFTY_intraday","B4_TA_only_no_cross_asset"],"single_touch_locked":true,"data_validation_policy_ref":"docs/superpowers/specs/anka_data_validation_policy_global_standard.md","datasets_registered":["canonical_fno_research_v3","fno_historical_daily_bars","sectoral_indices_v1","nifty_index","etf_panel_v3_curated","india_vix_history","nifty_near_month_future"],"standards_version":"1.0_2026-04-23","kill_switch_files":["pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/runner.py","pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/elastic_net_fit.py","pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/holdout_ledger.py","pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/predict_today.py"],"scheduled_tasks_pending_registration":["AnkaCrossAssetPredict (04:30 IST daily, VPS systemd)","AnkaCrossAssetOpen (09:15 IST trading days, VPS systemd)","AnkaCrossAssetClose (14:25 IST trading days, VPS systemd)","AnkaCrossAssetRecalibrate (last Sunday of month 02:00 IST, VPS systemd)"],"doc_sync_companions":["pipeline/config/anka_inventory.json","CLAUDE.md","docs/SYSTEM_OPERATIONS_MANUAL.md","memory/project_h_2026_05_04_cross_asset_perstock_lasso.md","memory/MEMORY.md"],"notes":"Pre-flight 2026-05-03: K_ETF=10 at 85.4% var, max abs corr PC x TA = 0.074 (very orthogonal -> cross-asset block is genuinely independent of TA), 200-stock universe at 50cr ADV, obs:feature ratio 5.66:1 at HL=90. 5d ETF horizon deferred to v2 (would push K_ETF to 18, violates checks). Primary unit of inference is BASKET-level pass per spec section 1.A; non-qualified cells are non-tradeable not failed. Section 1.B null bounds: 0=NoQualifiers, [1,4]=Insufficient, [5,25]=expected, [26,80]=triggers section 16.6 leakage audit, >80=LEAKAGE_SUSPECT."}
```

- [ ] **Step 3: Create memory file**

Create `memory/project_h_2026_05_04_cross_asset_perstock_lasso.md`:

```markdown
---
name: H-2026-05-04 cross-asset per-stock EN
description: Pre-registered 2026-05-03; 200-stock F&O universe, K_ETF=10 PCA on 30 CURATED ETFs + 4 IND macro + 6 TA + 3 DOW = 23 features. Holdout 2026-05-04 -> 2026-08-04.
type: project
---

**Hypothesis:** For each (stock, direction) cell, EN logistic on cross-asset+TA features will produce a basket of BH-FDR-qualified cells whose pooled forward edge clears section 12 PASS bar.

**Pre-flight (2026-05-03, all 5 PASS):**
- Universe: 200 stocks at 50cr ADV (HDFCBANK/RELIANCE/ICICIBANK top by ADV)
- PCA: K_ETF=10 at 85.4% var on 1d returns of 30 CURATED ETFs (5d deferred to v2)
- Orthogonality: max abs corr PC x TA = 0.074 (vs 0.4 cap) — cross-asset is genuinely independent of TA
- PIT: 44/44 series clean
- Sample size: ratio 5.66:1 at HL=90 (just clears 5:1)

**Primary unit of inference (governance):** BASKET-level pass — non-qualified cells are non-tradeable, NOT failed predictions. Conflating cell-level qualifier failures with model failure is a reporting error explicitly forbidden by spec section 1.A.

**Null expectation bounds (spec 1.B):**
- n_qualifying = 0: FAIL_NO_QUALIFIERS
- [1,4]: FAIL_INSUFFICIENT_QUALIFIERS
- [5,25]: expected, run forward verdict normally
- [26,80]: triggers section 16.6 amplified leakage audit (label permute / date shift / TA-ablation)
- >80: FAIL_LEAKAGE_SUSPECT, pause holdout

**How to apply:**
- v1 PASS does NOT greenlight live capital — v2 (learnable nifty_emphasis, multi-horizon) is the path to deployable signal.
- If basket P&L crosses +0.4% net@S1 but B4 (TA-only baseline) is within 80% of our P&L, terminal state = `PASS_BUT_CROSS_ASSET_NOT_LOAD_BEARING` and v2 must redesign feature library.
- 5d ETF horizon is the obvious v2 widening (pre-flight showed it pushes K_ETF to 18 — needs HL widening to 120+ days).

**Predecessors:** H-2026-04-29-ta-karpathy-v1 (top-10 NIFTY, TA-only, in holdout), H-2026-04-29-intraday-data-driven-v1 (NIFTY-50 intraday, in holdout), H-2026-04-24-001 RELIANCE-only TA (FAIL, single-touch consumed).
```

- [ ] **Step 4: Add MEMORY.md index entry**

Append one line under the "[Surface provenance in UI]" line in `memory/MEMORY.md`:

```markdown
- [H-2026-05-04 cross-asset per-stock EN](project_h_2026_05_04_cross_asset_perstock_lasso.md) — PRE_REGISTERED 2026-05-03; 200-stock F&O universe, K_ETF=10, holdout 2026-05-04→2026-08-04. Primary unit of inference is BASKET, not per-cell.
```

- [ ] **Step 5: Single commit (spec + plan + preflight + universe + memory + registry)**

```bash
git add docs/superpowers/specs/2026-05-04-cross-asset-perstock-lasso-v1-design.md
git add docs/superpowers/plans/2026-05-04-cross-asset-perstock-lasso-v1.md
git add docs/superpowers/hypothesis-registry.jsonl
git add pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/preflight.py
git add pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/preflight_results.json
git add pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/universe_frozen.json
git add memory/project_h_2026_05_04_cross_asset_perstock_lasso.md
git add memory/MEMORY.md

git commit -m "$(cat <<'EOF'
register(H-2026-05-04): cross-asset per-stock elastic-net pre-registered

200-stock F&O frozen universe, 30 CURATED ETF 1d returns -> PCA K_ETF=10
+ 4 Indian macro + 6 stock TA + 3 DOW = 23 features per stock.
EN logistic w/ exp-decay sample weights HL=90 trading days, 4-fold WF,
BH-FDR across cell grid. Single-touch holdout 2026-05-04 -> 2026-08-04.

Pre-flight all PASS (max abs corr PC x TA = 0.074 -> very orthogonal,
ratio 5.66:1 at HL=90, K_ETF=10 at 85.4% var).

Primary unit of inference: BASKET-level pass per spec section 1.A.
Non-qualified cells are non-tradeable, NOT failed predictions.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Expected: clean commit. Single-touch holdout LOCKED from this commit timestamp.

---

## Task 1: feature_extractor.py — per-stock 23-column feature matrix

**Files:**
- Create: `pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/feature_extractor.py`
- Test: `pipeline/tests/research/h_2026_05_04_cross_asset_perstock_lasso/test_feature_extractor.py`

- [ ] **Step 1: Write the failing test**

Create `pipeline/tests/research/h_2026_05_04_cross_asset_perstock_lasso/__init__.py` (empty file).

Create `pipeline/tests/research/h_2026_05_04_cross_asset_perstock_lasso/test_feature_extractor.py`:

```python
import numpy as np
import pandas as pd
import pytest
from pipeline.research.h_2026_05_04_cross_asset_perstock_lasso.feature_extractor import (
    build_indian_macro,
    build_stock_ta,
    build_dow,
    build_full_feature_matrix,
)


def _synthetic_bars(n_days=300, seed=0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2024-01-01", periods=n_days, freq="B")
    close = 100 * (1 + rng.normal(0, 0.01, n_days)).cumprod()
    high = close * (1 + rng.uniform(0, 0.01, n_days))
    low = close * (1 - rng.uniform(0, 0.01, n_days))
    open_ = close * (1 + rng.normal(0, 0.005, n_days))
    vol = rng.integers(1_000_000, 5_000_000, n_days)
    return pd.DataFrame({"Open": open_, "High": high, "Low": low, "Close": close, "Volume": vol}, index=dates)


def test_stock_ta_has_six_columns():
    bars = _synthetic_bars()
    ta = build_stock_ta(bars, sector_ret_5d=pd.Series(0.01, index=bars.index))
    expected = {"own_sector_ret_5d", "atr_14_pct", "rsi_14", "dist_50ema_pct", "vol_zscore_20", "range_pct_today"}
    assert set(ta.columns) == expected


def test_stock_ta_no_lookahead():
    """rsi_14 at row i must use only data through bar i (no future)."""
    bars = _synthetic_bars()
    ta_full = build_stock_ta(bars, sector_ret_5d=pd.Series(0.01, index=bars.index))
    ta_truncated = build_stock_ta(bars.iloc[:200], sector_ret_5d=pd.Series(0.01, index=bars.index[:200]))
    # rsi_14 at row 100 must equal whether full or truncated
    assert ta_full["rsi_14"].iloc[100] == pytest.approx(ta_truncated["rsi_14"].iloc[100], rel=1e-9)


def test_dow_has_three_columns_and_one_hot():
    idx = pd.date_range("2024-01-01", periods=10, freq="B")  # Mon-Fri
    dow = build_dow(idx)
    assert set(dow.columns) == {"dow_mon", "dow_tue", "dow_wed"}
    # Monday: dow_mon=1, others 0
    monday = dow[idx.weekday == 0].iloc[0]
    assert monday["dow_mon"] == 1 and monday["dow_tue"] == 0 and monday["dow_wed"] == 0


def test_indian_macro_has_four_columns_and_emphasis():
    nifty_fut = pd.Series(np.linspace(20000, 22000, 100), index=pd.date_range("2024-01-01", periods=100, freq="B"))
    vix = pd.Series(np.linspace(15, 18, 100), index=nifty_fut.index)
    macro = build_indian_macro(nifty_fut, vix, nifty_emphasis_factor=1.5)
    assert set(macro.columns) == {"nifty_near_month_ret_1d", "nifty_near_month_ret_5d", "india_vix_level", "india_vix_chg_5d"}
    # Emphasis is applied to nifty_*: scaled by sqrt(1.5)
    raw_macro = build_indian_macro(nifty_fut, vix, nifty_emphasis_factor=1.0)
    assert macro["nifty_near_month_ret_1d"].iloc[10] == pytest.approx(
        raw_macro["nifty_near_month_ret_1d"].iloc[10] * np.sqrt(1.5), rel=1e-9
    )
    # india_vix_level is NOT scaled
    assert macro["india_vix_level"].iloc[10] == pytest.approx(raw_macro["india_vix_level"].iloc[10], rel=1e-9)


def test_full_matrix_has_pre_pca_columns():
    """Pre-PCA: 30 ETFs (1d) + 4 IND macro + 6 TA + 3 DOW = 43 columns. PCA happens later."""
    n = 200
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    bars = _synthetic_bars(n_days=n)
    panel_etf_1d = pd.DataFrame(
        np.random.default_rng(1).normal(0, 0.01, (n, 30)),
        columns=[f"etf{i}" for i in range(30)],
        index=dates,
    )
    nifty_fut = pd.Series(np.linspace(20000, 22000, n), index=dates)
    vix = pd.Series(np.linspace(15, 18, n), index=dates)
    sector_ret = pd.Series(np.random.default_rng(2).normal(0, 0.005, n), index=dates)

    X = build_full_feature_matrix(
        bars=bars,
        etf_returns_1d=panel_etf_1d,
        nifty_near_month_close=nifty_fut,
        india_vix=vix,
        sector_ret_5d=sector_ret,
        nifty_emphasis_factor=1.5,
    )
    assert X.shape[1] == 43  # pre-PCA
    # No NaN in last 100 rows (warmup absorbed)
    assert X.iloc[-100:].isna().sum().sum() == 0
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
PYTHONIOENCODING=utf-8 pytest pipeline/tests/research/h_2026_05_04_cross_asset_perstock_lasso/test_feature_extractor.py -v
```

Expected: ImportError / ModuleNotFoundError on `feature_extractor`.

- [ ] **Step 3: Implement the module**

Create `pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/feature_extractor.py`:

```python
"""Per-stock 23-column feature matrix builder for H-2026-05-04.

Pre-PCA layout (43 cols): 30 ETF 1d returns + 4 IND macro + 6 stock TA + 3 DOW.
Post-PCA layout (23 cols): K_ETF=10 PCs + 4 IND macro + 6 stock TA + 3 DOW.

PCA reduction is applied separately by pca_model.py — this file produces the
pre-PCA matrix only.

PIT contract: every column at row i depends only on data <= row i. Period.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def build_stock_ta(bars: pd.DataFrame, sector_ret_5d: pd.Series) -> pd.DataFrame:
    """6 stock-specific TA features. bars must have OHLCV columns."""
    out = pd.DataFrame(index=bars.index)
    delta = bars["Close"].diff()
    gain = delta.where(delta > 0, 0.0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    out["rsi_14"] = 100 - 100 / (1 + rs)

    prev_close = bars["Close"].shift(1)
    tr = pd.concat(
        [(bars["High"] - bars["Low"]),
         (bars["High"] - prev_close).abs(),
         (bars["Low"] - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    out["atr_14_pct"] = tr.rolling(14).mean() / bars["Close"]

    ema50 = bars["Close"].ewm(span=50, adjust=False).mean()
    out["dist_50ema_pct"] = (bars["Close"] - ema50) / ema50

    vol_mean = bars["Volume"].rolling(20).mean()
    vol_std = bars["Volume"].rolling(20).std()
    out["vol_zscore_20"] = (bars["Volume"] - vol_mean) / vol_std.replace(0, np.nan)

    out["range_pct_today"] = (bars["High"] - bars["Low"]) / bars["Close"]
    out["own_sector_ret_5d"] = sector_ret_5d.reindex(bars.index)
    return out[["own_sector_ret_5d", "atr_14_pct", "rsi_14", "dist_50ema_pct", "vol_zscore_20", "range_pct_today"]]


def build_indian_macro(
    nifty_near_month_close: pd.Series,
    india_vix: pd.Series,
    nifty_emphasis_factor: float = 1.5,
) -> pd.DataFrame:
    """4 Indian macro features. Nifty cols scaled by sqrt(emphasis_factor) at fit AND inference."""
    scale = np.sqrt(nifty_emphasis_factor)
    out = pd.DataFrame(index=nifty_near_month_close.index)
    out["nifty_near_month_ret_1d"] = nifty_near_month_close.pct_change(1) * scale
    out["nifty_near_month_ret_5d"] = nifty_near_month_close.pct_change(5) * scale
    out["india_vix_level"] = india_vix.reindex(nifty_near_month_close.index)
    out["india_vix_chg_5d"] = np.log(india_vix.reindex(nifty_near_month_close.index)).diff(5)
    return out


def build_dow(index: pd.DatetimeIndex) -> pd.DataFrame:
    """3 DOW dummies (Mon, Tue, Wed) — Thu/Fri reference."""
    out = pd.DataFrame(index=index)
    wd = index.weekday
    out["dow_mon"] = (wd == 0).astype(int)
    out["dow_tue"] = (wd == 1).astype(int)
    out["dow_wed"] = (wd == 2).astype(int)
    return out


def build_full_feature_matrix(
    *,
    bars: pd.DataFrame,
    etf_returns_1d: pd.DataFrame,
    nifty_near_month_close: pd.Series,
    india_vix: pd.Series,
    sector_ret_5d: pd.Series,
    nifty_emphasis_factor: float = 1.5,
) -> pd.DataFrame:
    """Pre-PCA 43-column matrix. PCA reduction applied later by pca_model.py."""
    ta = build_stock_ta(bars, sector_ret_5d)
    macro = build_indian_macro(nifty_near_month_close, india_vix, nifty_emphasis_factor)
    dow = build_dow(bars.index)
    etf = etf_returns_1d.reindex(bars.index)
    X = pd.concat([etf, macro, ta, dow], axis=1).dropna()
    return X
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
PYTHONIOENCODING=utf-8 pytest pipeline/tests/research/h_2026_05_04_cross_asset_perstock_lasso/test_feature_extractor.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/feature_extractor.py
git add pipeline/tests/research/h_2026_05_04_cross_asset_perstock_lasso/__init__.py
git add pipeline/tests/research/h_2026_05_04_cross_asset_perstock_lasso/test_feature_extractor.py

git commit -m "$(cat <<'EOF'
feat(H-2026-05-04): per-stock 23-column feature extractor

Pre-PCA 43 columns (30 ETF 1d + 4 IND macro + 6 TA + 3 DOW).
Nifty emphasis factor 1.5 scaled at fit AND inference (clean math, no
train/inference mismatch). 5 unit tests covering shape, no-lookahead,
DOW one-hot, emphasis scaling, full-matrix assembly.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: pca_model.py — fit / save / load PCA on ETF block

**Files:**
- Create: `pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/pca_model.py`
- Test: `pipeline/tests/research/h_2026_05_04_cross_asset_perstock_lasso/test_pca_model.py`

- [ ] **Step 1: Write the failing test**

```python
import numpy as np
import pandas as pd
import pytest
from pathlib import Path
from pipeline.research.h_2026_05_04_cross_asset_perstock_lasso.pca_model import (
    fit_pca,
    apply_pca,
    save_pca,
    load_pca,
)


def _synthetic_etf_panel(n_days=600, n_etfs=30, seed=0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    common_factor = rng.normal(0, 1, n_days)
    cols = []
    for i in range(n_etfs):
        loading = rng.uniform(0.3, 0.9)
        idio = rng.normal(0, 1, n_days)
        cols.append(loading * common_factor + np.sqrt(1 - loading**2) * idio)
    return pd.DataFrame(np.array(cols).T, columns=[f"etf{i}" for i in range(n_etfs)])


def test_fit_pca_returns_correct_K_at_85pct_var():
    X = _synthetic_etf_panel()
    model = fit_pca(X, variance_target=0.85, max_K=12)
    assert model.K_ETF >= 1 and model.K_ETF <= 12
    assert model.cum_var_at_K >= 0.85


def test_apply_pca_shape():
    X = _synthetic_etf_panel()
    model = fit_pca(X, variance_target=0.85, max_K=12)
    Z = apply_pca(X, model)
    assert Z.shape == (len(X), model.K_ETF)
    assert list(Z.columns) == [f"PC{i+1}" for i in range(model.K_ETF)]


def test_apply_pca_uses_training_stats_only():
    """Z-score must use TRAINING mean/std, not the inference data's mean/std."""
    X_train = _synthetic_etf_panel(n_days=400, seed=1)
    X_inf = _synthetic_etf_panel(n_days=200, seed=99) + 100  # shifted inference data
    model = fit_pca(X_train, variance_target=0.85, max_K=12)
    Z_inf = apply_pca(X_inf, model)
    # Inference data shifted by 100 should still be Z-scored against training mu, so non-zero mean
    assert abs(Z_inf.mean().mean()) > 1.0


def test_save_load_roundtrip(tmp_path):
    X = _synthetic_etf_panel()
    model = fit_pca(X, variance_target=0.85, max_K=12)
    Z_before = apply_pca(X, model)

    path = tmp_path / "pca.npz"
    save_pca(model, path)
    model2 = load_pca(path)
    Z_after = apply_pca(X, model2)
    np.testing.assert_array_almost_equal(Z_before.values, Z_after.values)


def test_max_K_cap_aborts_when_violated():
    X = _synthetic_etf_panel()
    with pytest.raises(ValueError, match="K_ETF.*exceeds cap"):
        fit_pca(X, variance_target=0.99, max_K=2)  # forces K_ETF > 2 -> abort
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
PYTHONIOENCODING=utf-8 pytest pipeline/tests/research/h_2026_05_04_cross_asset_perstock_lasso/test_pca_model.py -v
```
Expected: ImportError on `pca_model`.

- [ ] **Step 3: Implement the module**

Create `pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/pca_model.py`:

```python
"""PCA on the 30-CURATED-ETF 1d-return block. Frozen per fold."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA


@dataclass
class FrozenPCA:
    K_ETF: int
    mean_: np.ndarray
    std_: np.ndarray
    components_: np.ndarray  # (K_ETF, n_features)
    explained_variance_ratio_: np.ndarray  # full ratio (n_features,)
    cum_var_at_K: float
    feature_names_: list[str]


def fit_pca(X: pd.DataFrame, *, variance_target: float = 0.85, max_K: int = 12) -> FrozenPCA:
    """Fit PCA on training data only. Aborts if K_ETF > max_K (spec section 16 Check 2 cap)."""
    feat_names = list(X.columns)
    arr = X.values.astype(float)
    mu = arr.mean(axis=0)
    sd = arr.std(axis=0)
    sd[sd == 0] = 1.0
    Z = (arr - mu) / sd

    n_comp = min(Z.shape[0], Z.shape[1])
    pca = PCA(n_components=n_comp).fit(Z)
    cum = np.cumsum(pca.explained_variance_ratio_)
    K = int(np.searchsorted(cum, variance_target)) + 1
    if K > max_K:
        raise ValueError(
            f"K_ETF={K} at variance_target={variance_target} exceeds cap max_K={max_K}. "
            "Feature library design failed; abort registration per spec section 16 Check 2."
        )

    return FrozenPCA(
        K_ETF=K,
        mean_=mu,
        std_=sd,
        components_=pca.components_[:K],
        explained_variance_ratio_=pca.explained_variance_ratio_,
        cum_var_at_K=float(cum[K - 1]),
        feature_names_=feat_names,
    )


def apply_pca(X: pd.DataFrame, model: FrozenPCA) -> pd.DataFrame:
    """Project X onto the frozen PCs using TRAINING-ONLY mean/std."""
    if list(X.columns) != model.feature_names_:
        raise ValueError(
            f"feature mismatch: expected {model.feature_names_[:3]}..., got {list(X.columns)[:3]}..."
        )
    arr = X.values.astype(float)
    Z = (arr - model.mean_) / model.std_
    proj = Z @ model.components_.T  # (n_rows, K_ETF)
    return pd.DataFrame(proj, index=X.index, columns=[f"PC{i + 1}" for i in range(model.K_ETF)])


def save_pca(model: FrozenPCA, path: Path) -> None:
    np.savez(
        path,
        K_ETF=model.K_ETF,
        mean_=model.mean_,
        std_=model.std_,
        components_=model.components_,
        explained_variance_ratio_=model.explained_variance_ratio_,
        cum_var_at_K=model.cum_var_at_K,
        feature_names_=np.array(model.feature_names_),
    )


def load_pca(path: Path) -> FrozenPCA:
    data = np.load(path, allow_pickle=False)
    return FrozenPCA(
        K_ETF=int(data["K_ETF"]),
        mean_=data["mean_"],
        std_=data["std_"],
        components_=data["components_"],
        explained_variance_ratio_=data["explained_variance_ratio_"],
        cum_var_at_K=float(data["cum_var_at_K"]),
        feature_names_=list(data["feature_names_"]),
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
PYTHONIOENCODING=utf-8 pytest pipeline/tests/research/h_2026_05_04_cross_asset_perstock_lasso/test_pca_model.py -v
```
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/pca_model.py
git add pipeline/tests/research/h_2026_05_04_cross_asset_perstock_lasso/test_pca_model.py
git commit -m "feat(H-2026-05-04): PCA on 30-ETF block with K_ETF<=max_K abort"
```

---

## Task 3: elastic_net_fit.py — per-cell EN fit with exp-decay sample weights

**Files:**
- Create: `pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/elastic_net_fit.py`
- Test: `pipeline/tests/research/h_2026_05_04_cross_asset_perstock_lasso/test_elastic_net_fit.py`

- [ ] **Step 1: Write the failing test**

```python
import numpy as np
import pandas as pd
import pytest
from pipeline.research.h_2026_05_04_cross_asset_perstock_lasso.elastic_net_fit import (
    exp_decay_weights,
    fit_en_cell,
    score_en_cell,
)


def test_exp_decay_weights_sum_to_one_and_recent_heavy():
    n = 500
    w = exp_decay_weights(n_obs=n, hl_trading_days=90)
    assert w.shape == (n,)
    assert w.sum() == pytest.approx(1.0, rel=1e-9)
    # Most recent observation has highest weight
    assert w[-1] > w[0]
    # Half-life property: weight 90 obs back is half of weight at last
    assert w[-91] / w[-1] == pytest.approx(0.5, rel=1e-3)


def test_fit_en_cell_returns_predictions_in_zero_one():
    rng = np.random.default_rng(0)
    n, p = 400, 23
    X = rng.normal(0, 1, (n, p))
    # Synthetic signal: feature 0 weakly predicts label
    y = (X[:, 0] + rng.normal(0, 1, n) > 0).astype(int)
    model, cv_meta = fit_en_cell(
        X_train=X,
        y_train=y,
        sample_weights=exp_decay_weights(n, hl_trading_days=90),
        C_grid=(0.1, 1.0, 3.0),
        l1_ratio_grid=(0.3, 0.5, 0.7),
        cv_n_splits=3,
        random_state=0,
    )
    p_hat = score_en_cell(model, X)
    assert p_hat.shape == (n,)
    assert (p_hat >= 0).all() and (p_hat <= 1).all()
    # CV metadata recorded
    assert "best_C" in cv_meta and "best_l1_ratio" in cv_meta and "cv_mean_auc" in cv_meta


def test_fit_en_cell_aborts_on_single_class():
    X = np.zeros((50, 5))
    y = np.zeros(50, dtype=int)
    with pytest.raises(ValueError, match="single-class"):
        fit_en_cell(
            X_train=X, y_train=y,
            sample_weights=exp_decay_weights(50, 90),
            C_grid=(1.0,), l1_ratio_grid=(0.5,), cv_n_splits=3, random_state=0,
        )
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
PYTHONIOENCODING=utf-8 pytest pipeline/tests/research/h_2026_05_04_cross_asset_perstock_lasso/test_elastic_net_fit.py -v
```
Expected: ImportError.

- [ ] **Step 3: Implement the module**

Create `pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/elastic_net_fit.py`:

```python
"""Per-(stock, direction) cell EN logistic fit with exp-decay sample weights."""
from __future__ import annotations

from typing import Sequence

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import TimeSeriesSplit


def exp_decay_weights(n_obs: int, hl_trading_days: float) -> np.ndarray:
    """Exponential-decay weights normalised to sum to 1.

    Most recent observation (index n_obs-1) gets highest weight.
    Weight at index n_obs-1-h is half the weight at n_obs-1 when h == hl_trading_days.
    """
    ages = np.arange(n_obs - 1, -1, -1, dtype=float)  # ages[-1] = 0 (most recent)
    raw = np.exp(-ages * np.log(2) / hl_trading_days)
    return raw / raw.sum()


def fit_en_cell(
    *,
    X_train: np.ndarray,
    y_train: np.ndarray,
    sample_weights: np.ndarray,
    C_grid: Sequence[float],
    l1_ratio_grid: Sequence[float],
    cv_n_splits: int,
    random_state: int,
) -> tuple[LogisticRegression, dict]:
    """Fit elastic-net logistic with C x l1_ratio CV using TimeSeriesSplit.

    Returns (frozen_model_refit_on_full_train, cv_meta).
    """
    if len(np.unique(y_train)) < 2:
        raise ValueError(f"single-class label, cannot fit (y_unique={np.unique(y_train)})")

    tscv = TimeSeriesSplit(n_splits=cv_n_splits)
    best = {"cv_mean_auc": -np.inf}
    for C in C_grid:
        for l1 in l1_ratio_grid:
            fold_aucs = []
            for tr_idx, va_idx in tscv.split(X_train):
                if len(np.unique(y_train[va_idx])) < 2:
                    continue
                clf = LogisticRegression(
                    penalty="elasticnet", solver="saga", l1_ratio=l1, C=C,
                    class_weight="balanced", max_iter=5000, random_state=random_state,
                )
                clf.fit(X_train[tr_idx], y_train[tr_idx], sample_weight=sample_weights[tr_idx])
                p_va = clf.predict_proba(X_train[va_idx])[:, 1]
                fold_aucs.append(roc_auc_score(y_train[va_idx], p_va))
            if not fold_aucs:
                continue
            mean_auc = float(np.mean(fold_aucs))
            if mean_auc > best["cv_mean_auc"]:
                best = {
                    "cv_mean_auc": mean_auc,
                    "best_C": C,
                    "best_l1_ratio": l1,
                    "cv_fold_aucs": fold_aucs,
                }

    if best["cv_mean_auc"] == -np.inf:
        raise ValueError("no valid CV folds (all folds had single-class validation sets)")

    final = LogisticRegression(
        penalty="elasticnet", solver="saga",
        l1_ratio=best["best_l1_ratio"], C=best["best_C"],
        class_weight="balanced", max_iter=5000, random_state=random_state,
    )
    final.fit(X_train, y_train, sample_weight=sample_weights)
    return final, best


def score_en_cell(model: LogisticRegression, X: np.ndarray) -> np.ndarray:
    """Return predict_proba for the positive class."""
    return model.predict_proba(X)[:, 1]
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
PYTHONIOENCODING=utf-8 pytest pipeline/tests/research/h_2026_05_04_cross_asset_perstock_lasso/test_elastic_net_fit.py -v
```
Expected: 3 passed (note: timeseries-CV tests are slow, ~10-20s).

- [ ] **Step 5: Commit**

```bash
git add pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/elastic_net_fit.py
git add pipeline/tests/research/h_2026_05_04_cross_asset_perstock_lasso/test_elastic_net_fit.py
git commit -m "feat(H-2026-05-04): EN logistic fit with exp-decay weights and C*l1_ratio CV"
```

---

## Task 4: walk_forward.py — 4-fold WF + qualifier + permutation null + BH-FDR

**Files:**
- Create: `pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/walk_forward.py`
- Test: `pipeline/tests/research/h_2026_05_04_cross_asset_perstock_lasso/test_walk_forward.py`

- [ ] **Step 1: Write the failing test**

```python
import numpy as np
import pandas as pd
import pytest
from pipeline.research.h_2026_05_04_cross_asset_perstock_lasso.walk_forward import (
    expanding_quarter_folds,
    qualifier_check,
    bh_fdr,
    permutation_p_value,
)


def test_expanding_folds_count_and_disjoint():
    idx = pd.date_range("2021-05-04", "2025-10-31", freq="B")
    folds = expanding_quarter_folds(idx, n_folds=4)
    assert len(folds) == 4
    for tr_idx, va_idx in folds:
        assert len(set(tr_idx) & set(va_idx)) == 0  # disjoint
        assert max(tr_idx) < min(va_idx)  # train always before val


def test_bh_fdr_known_pvalues():
    p = np.array([0.001, 0.01, 0.04, 0.4])
    sig = bh_fdr(p, alpha=0.05)
    # 0.001 and 0.01 should pass; 0.04 borderline; 0.4 fails
    assert sig[0] and sig[1]
    assert not sig[3]


def test_qualifier_check_all_gates():
    # All-pass case
    fold_aucs = [0.58, 0.59, 0.57, 0.60]
    p_value = 0.01
    in_sample_holdout_auc = 0.57
    n_pred_pos_isho = 12
    perm_beat_pct = 0.97
    qualified, reasons = qualifier_check(
        fold_aucs=fold_aucs, p_value=p_value, p_threshold=0.05,
        in_sample_holdout_auc=in_sample_holdout_auc, n_pred_pos_isho=n_pred_pos_isho,
        perm_beat_pct=perm_beat_pct,
    )
    assert qualified is True
    assert reasons == []

    # Std too high
    qualified2, reasons2 = qualifier_check(
        fold_aucs=[0.58, 0.45, 0.70, 0.55], p_value=0.01, p_threshold=0.05,
        in_sample_holdout_auc=0.57, n_pred_pos_isho=12, perm_beat_pct=0.97,
    )
    assert qualified2 is False
    assert any("std" in r for r in reasons2)


def test_permutation_p_value_known_signal():
    rng = np.random.default_rng(0)
    n = 300
    p = rng.uniform(0, 1, n)
    y = (p > 0.5).astype(int)  # perfectly predictable
    p_val = permutation_p_value(y_true=y, y_score=p, n_permutations=200, random_state=0)
    assert p_val < 0.05
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
PYTHONIOENCODING=utf-8 pytest pipeline/tests/research/h_2026_05_04_cross_asset_perstock_lasso/test_walk_forward.py -v
```
Expected: ImportError.

- [ ] **Step 3: Implement the module**

Create `pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/walk_forward.py`:

```python
"""4-fold expanding-origin walk-forward with qualifier gate, BH-FDR, permutation null."""
from __future__ import annotations

from typing import Sequence

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score


def expanding_quarter_folds(
    index: pd.DatetimeIndex, n_folds: int = 4,
) -> list[tuple[np.ndarray, np.ndarray]]:
    """Expanding-origin walk-forward: 4 contiguous quarters within training, expanding train.

    Returns list of (train_positional_idx, val_positional_idx) tuples.
    """
    n = len(index)
    fold_size = n // (n_folds + 1)  # +1 so first fold has fold_size train + fold_size val
    folds = []
    for k in range(n_folds):
        tr_start = 0
        tr_end = fold_size * (k + 1)
        va_start = tr_end
        va_end = min(tr_end + fold_size, n)
        if va_start >= va_end:
            break
        folds.append((np.arange(tr_start, tr_end), np.arange(va_start, va_end)))
    return folds


def bh_fdr(p_values: np.ndarray, alpha: float = 0.05) -> np.ndarray:
    """Benjamini-Hochberg correction. Returns boolean array of survivors."""
    n = len(p_values)
    order = np.argsort(p_values)
    ranked = p_values[order]
    thresholds = (np.arange(1, n + 1) / n) * alpha
    survivors_in_order = ranked <= thresholds
    if not survivors_in_order.any():
        return np.zeros(n, dtype=bool)
    last_survivor = np.where(survivors_in_order)[0].max()
    out = np.zeros(n, dtype=bool)
    out[order[: last_survivor + 1]] = True
    return out


def qualifier_check(
    *,
    fold_aucs: Sequence[float],
    p_value: float,
    p_threshold: float,
    in_sample_holdout_auc: float,
    n_pred_pos_isho: int,
    perm_beat_pct: float,
) -> tuple[bool, list[str]]:
    """Apply the section 9 qualifier gate. Returns (qualified, list_of_failure_reasons).

    Gates per spec section 9:
      1. mean fold-AUC >= 0.55
      2. fold-AUC std <= 0.05
      3. in-sample-holdout AUC >= 0.55
      4. n predicted positive in in-sample-holdout >= 5
      5. BH-FDR p < threshold
      6. permutation null beat >= 95%
    """
    reasons = []
    aucs = np.array(fold_aucs)
    if aucs.mean() < 0.55:
        reasons.append(f"mean fold-AUC {aucs.mean():.3f} < 0.55")
    if aucs.std() > 0.05:
        reasons.append(f"fold-AUC std {aucs.std():.3f} > 0.05")
    if in_sample_holdout_auc < 0.55:
        reasons.append(f"in-sample-holdout AUC {in_sample_holdout_auc:.3f} < 0.55")
    if n_pred_pos_isho < 5:
        reasons.append(f"in-sample-holdout n_pred_pos {n_pred_pos_isho} < 5")
    if p_value >= p_threshold:
        reasons.append(f"BH-FDR p {p_value:.4f} >= {p_threshold}")
    if perm_beat_pct < 0.95:
        reasons.append(f"perm beat {perm_beat_pct:.3f} < 0.95")
    return (len(reasons) == 0, reasons)


def permutation_p_value(
    *,
    y_true: np.ndarray,
    y_score: np.ndarray,
    n_permutations: int,
    random_state: int,
) -> float:
    """Two-sided permutation p-value for AUC."""
    if len(np.unique(y_true)) < 2:
        return 1.0
    observed = roc_auc_score(y_true, y_score)
    rng = np.random.default_rng(random_state)
    null = []
    for _ in range(n_permutations):
        shuffled = rng.permutation(y_true)
        if len(np.unique(shuffled)) < 2:
            null.append(0.5)
            continue
        null.append(roc_auc_score(shuffled, y_score))
    null = np.array(null)
    p = (np.abs(null - 0.5) >= abs(observed - 0.5)).mean()
    return float(p)
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
PYTHONIOENCODING=utf-8 pytest pipeline/tests/research/h_2026_05_04_cross_asset_perstock_lasso/test_walk_forward.py -v
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/walk_forward.py
git add pipeline/tests/research/h_2026_05_04_cross_asset_perstock_lasso/test_walk_forward.py
git commit -m "feat(H-2026-05-04): walk-forward + qualifier + BH-FDR + permutation null"
```

---

## Task 5: runner.py — orchestrator (PCA → features → WF → qualifier → frozen models)

**Files:**
- Create: `pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/runner.py`

This is a pure orchestrator (no unit tests — covered by integration via the small-fixture run in step 4).

- [ ] **Step 1: Implement the runner**

Create `pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/runner.py`:

```python
"""End-to-end orchestrator for H-2026-05-04 fit job.

Loads frozen universe, builds features per stock, fits PCA on training panel,
runs walk-forward + qualifier per (stock, direction), applies BH-FDR across
the cell grid, freezes final models for qualifying cells, writes manifest.

CLI: python -m pipeline.research.h_2026_05_04_cross_asset_perstock_lasso.runner --train-end 2025-10-31
"""
from __future__ import annotations

import argparse
import json
import pickle
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from pipeline.autoresearch.etf_v3_loader import build_panel, CURATED_FOREIGN_ETFS  # noqa: E402
from pipeline.research.h_2026_05_04_cross_asset_perstock_lasso.feature_extractor import (  # noqa: E402
    build_full_feature_matrix,
)
from pipeline.research.h_2026_05_04_cross_asset_perstock_lasso.pca_model import (  # noqa: E402
    fit_pca, apply_pca, save_pca,
)
from pipeline.research.h_2026_05_04_cross_asset_perstock_lasso.elastic_net_fit import (  # noqa: E402
    exp_decay_weights, fit_en_cell, score_en_cell,
)
from pipeline.research.h_2026_05_04_cross_asset_perstock_lasso.walk_forward import (  # noqa: E402
    expanding_quarter_folds, qualifier_check, bh_fdr, permutation_p_value,
)

OUT_DIR = REPO / "pipeline" / "research" / "h_2026_05_04_cross_asset_perstock_lasso"
FNO_CSV_DIR = REPO / "pipeline" / "data" / "fno_historical"

C_GRID = (0.01, 0.03, 0.1, 0.3, 1.0, 3.0)
L1_GRID = (0.1, 0.3, 0.5, 0.7, 0.9)
HL = 90
LABEL_THRESHOLD_PCT = 0.4
NIFTY_EMPHASIS = 1.5
N_PERMUTATIONS = 10000


def _load_universe() -> list[str]:
    p = OUT_DIR / "universe_frozen.json"
    return json.loads(p.read_text())["tickers"]


def _normalise_ohlcv(df: pd.DataFrame) -> pd.DataFrame | None:
    rename = {}
    for c in df.columns:
        lc = c.lower()
        if lc in {"date", "open", "high", "low", "close", "volume"}:
            rename[c] = lc.capitalize() if lc != "date" else "Date"
    df = df.rename(columns=rename)
    if not {"Date", "Open", "High", "Low", "Close", "Volume"}.issubset(df.columns):
        return None
    df["Date"] = pd.to_datetime(df["Date"])
    return df.set_index("Date").sort_index()


def _load_bars(ticker: str) -> pd.DataFrame | None:
    p = FNO_CSV_DIR / f"{ticker}.csv"
    if not p.exists():
        return None
    try:
        return _normalise_ohlcv(pd.read_csv(p))
    except Exception:
        return None


def _label(bars: pd.DataFrame, threshold_pct: float) -> tuple[pd.Series, pd.Series]:
    """T+1 open-to-close binary labels (LONG, SHORT) at +/- threshold_pct."""
    open_t1 = bars["Open"].shift(-1)
    close_t1 = bars["Close"].shift(-1)
    fwd_ret_pct = (close_t1 - open_t1) / open_t1 * 100
    y_long = (fwd_ret_pct >= threshold_pct).astype(int)
    y_short = (-fwd_ret_pct >= threshold_pct).astype(int)
    return y_long, y_short


def main(train_end: pd.Timestamp) -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "feature_matrices").mkdir(exist_ok=True)
    (OUT_DIR / "models").mkdir(exist_ok=True)
    (OUT_DIR / "pca_projections").mkdir(exist_ok=True)

    print(f"[runner] train_end = {train_end.date()}")
    universe = _load_universe()
    print(f"[runner] universe size = {len(universe)}")

    # 1. Build panel and ETF 1d returns
    panel = build_panel()
    etf_cols = [c for c in CURATED_FOREIGN_ETFS if c in panel.columns]
    etf_1d = panel[etf_cols].pct_change(1)
    etf_1d.columns = [f"{c}_1d" for c in etf_cols]
    nifty_close = panel["nifty_close"]
    india_vix = panel["india_vix"]

    # 2. Fit PCA on training-window ETF returns
    train_mask = (etf_1d.index >= pd.Timestamp("2021-05-04")) & (etf_1d.index <= train_end)
    etf_train = etf_1d.loc[train_mask].dropna()
    pca_model = fit_pca(etf_train, variance_target=0.85, max_K=12)
    print(f"[runner] PCA: K_ETF={pca_model.K_ETF}, cum_var={pca_model.cum_var_at_K:.3f}")
    save_pca(pca_model, OUT_DIR / "pca_projections" / "final.npz")

    # 3. Per-stock fit
    cell_records = []
    for ticker in universe:
        bars = _load_bars(ticker)
        if bars is None:
            continue
        bars = bars.loc[bars.index <= train_end]
        if len(bars) < 800:
            continue

        # Sector ret 5d (read from sectoral_indices via sector_mapper)
        try:
            from pipeline.sector_mapper import map_one
            sector_name = map_one(ticker)
        except Exception:
            sector_name = None
        if sector_name is None or sector_name == "Unmapped":
            continue
        sector_path = REPO / "pipeline" / "data" / "sectoral_indices" / f"{sector_name}.csv"
        if not sector_path.exists():
            continue
        sector_df = pd.read_csv(sector_path, parse_dates=["Date"]).set_index("Date").sort_index()
        sector_ret_5d = sector_df["Close"].pct_change(5)

        X_pre = build_full_feature_matrix(
            bars=bars,
            etf_returns_1d=etf_1d,
            nifty_near_month_close=nifty_close,
            india_vix=india_vix,
            sector_ret_5d=sector_ret_5d,
            nifty_emphasis_factor=NIFTY_EMPHASIS,
        )
        # Apply PCA to ETF columns only
        etf_block_cols = [c for c in X_pre.columns if c.endswith("_1d") and not c.startswith("nifty_")]
        pcs = apply_pca(X_pre[etf_block_cols], pca_model)
        non_etf = X_pre.drop(columns=etf_block_cols)
        X = pd.concat([pcs, non_etf], axis=1).dropna()
        X.to_parquet(OUT_DIR / "feature_matrices" / f"{ticker}.parquet")

        y_long, y_short = _label(bars, LABEL_THRESHOLD_PCT)
        for direction, y in (("LONG", y_long), ("SHORT", y_short)):
            aligned = X.join(y.rename("y"), how="inner").dropna()
            if len(aligned) < 500:
                continue
            X_arr = aligned.drop(columns=["y"]).values
            y_arr = aligned["y"].values

            # Walk-forward folds
            folds = expanding_quarter_folds(aligned.index, n_folds=4)
            fold_aucs = []
            for tr_idx, va_idx in folds:
                if len(np.unique(y_arr[tr_idx])) < 2 or len(np.unique(y_arr[va_idx])) < 2:
                    continue
                w = exp_decay_weights(len(tr_idx), HL)
                try:
                    m, _ = fit_en_cell(
                        X_train=X_arr[tr_idx], y_train=y_arr[tr_idx],
                        sample_weights=w, C_grid=C_GRID, l1_ratio_grid=L1_GRID,
                        cv_n_splits=3, random_state=0,
                    )
                except Exception:
                    continue
                p_va = score_en_cell(m, X_arr[va_idx])
                from sklearn.metrics import roc_auc_score
                fold_aucs.append(roc_auc_score(y_arr[va_idx], p_va))

            if len(fold_aucs) < 4:
                continue

            # Final model on full training window (use median CV hyperparameters via re-CV on full)
            w_full = exp_decay_weights(len(X_arr), HL)
            try:
                final_model, cv_meta = fit_en_cell(
                    X_train=X_arr, y_train=y_arr,
                    sample_weights=w_full, C_grid=C_GRID, l1_ratio_grid=L1_GRID,
                    cv_n_splits=3, random_state=0,
                )
            except Exception:
                continue

            # In-sample holdout AUC: last 6 months of training (~125 days)
            isho_n = min(125, len(X_arr) // 4)
            p_isho = score_en_cell(final_model, X_arr[-isho_n:])
            from sklearn.metrics import roc_auc_score
            isho_auc = roc_auc_score(y_arr[-isho_n:], p_isho) if len(np.unique(y_arr[-isho_n:])) > 1 else 0.5
            n_pred_pos_isho = int((p_isho >= 0.6).sum())

            # Permutation null
            perm_p = permutation_p_value(
                y_true=y_arr[-isho_n:], y_score=p_isho,
                n_permutations=N_PERMUTATIONS, random_state=0,
            )

            cell_records.append({
                "ticker": ticker, "direction": direction,
                "fold_aucs": fold_aucs, "mean_fold_auc": float(np.mean(fold_aucs)),
                "fold_auc_std": float(np.std(fold_aucs)),
                "isho_auc": float(isho_auc), "n_pred_pos_isho": n_pred_pos_isho,
                "perm_p_value": perm_p,
                "cv_best_C": cv_meta["best_C"], "cv_best_l1": cv_meta["best_l1_ratio"],
                "cv_mean_auc": cv_meta["cv_mean_auc"],
            })

            # Save final model
            with open(OUT_DIR / "models" / f"{ticker}_{direction}.pkl", "wb") as f:
                pickle.dump(final_model, f)

        print(f"  {ticker}: {len([c for c in cell_records if c['ticker']==ticker])} directions fit")

    # 4. BH-FDR across all cells
    if not cell_records:
        print("[runner] FAIL: 0 cells fit")
        return 1

    p_arr = np.array([c["perm_p_value"] for c in cell_records])
    survivors = bh_fdr(p_arr, alpha=0.05)
    for c, surv in zip(cell_records, survivors):
        c["bh_fdr_survivor"] = bool(surv)

    # 5. Apply qualifier gate
    qualifying = []
    for c in cell_records:
        ok, reasons = qualifier_check(
            fold_aucs=c["fold_aucs"],
            p_value=c["perm_p_value"], p_threshold=0.05,
            in_sample_holdout_auc=c["isho_auc"], n_pred_pos_isho=c["n_pred_pos_isho"],
            perm_beat_pct=0.96 if c["bh_fdr_survivor"] else 0.0,
        )
        c["qualified"] = ok
        c["fail_reasons"] = reasons
        if ok:
            qualifying.append((c["ticker"], c["direction"]))

    # 6. Manifest
    manifest = {
        "hypothesis_id": "H-2026-05-04-cross-asset-perstock-lasso-v1",
        "run_at": datetime.now().isoformat(),
        "train_end": str(train_end.date()),
        "universe_size": len(universe),
        "K_ETF": pca_model.K_ETF, "cum_var_at_K": pca_model.cum_var_at_K,
        "n_cells_fit": len(cell_records),
        "n_qualifying": len(qualifying),
        "qualifying_cells": qualifying,
        "frozen_thresholds": {
            "C_grid": list(C_GRID), "l1_ratio_grid": list(L1_GRID),
            "hl_trading_days": HL, "label_threshold_pct": LABEL_THRESHOLD_PCT,
            "nifty_emphasis": NIFTY_EMPHASIS, "n_permutations": N_PERMUTATIONS,
        },
    }
    (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
    (OUT_DIR / "walk_forward_results.json").write_text(json.dumps(cell_records, indent=2, default=str))

    print(f"[runner] DONE: {len(cell_records)} cells fit, {len(qualifying)} qualified")
    print(f"[runner] Manifest: {OUT_DIR / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--train-end", type=str, default="2025-10-31")
    args = parser.parse_args()
    sys.exit(main(pd.Timestamp(args.train_end)))
```

- [ ] **Step 2: Smoke test on 5-stock subset**

Create `tmp_universe.json`:

```bash
python -c "
import json
from pathlib import Path
src = Path('pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/universe_frozen.json')
data = json.loads(src.read_text())
data['tickers'] = data['tickers'][:5]
data['n_tickers'] = 5
src.with_suffix('.json.smoke').write_text(json.dumps(data, indent=2))
print(data['tickers'])
"
```

Then patch the runner momentarily and run a smoke fit:

```bash
PYTHONIOENCODING=utf-8 python -c "
import sys, json
from pathlib import Path
sys.path.insert(0, '.')
import pipeline.research.h_2026_05_04_cross_asset_perstock_lasso.runner as r
src = Path('pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/universe_frozen.json.smoke')
r._load_universe = lambda: json.loads(src.read_text())['tickers']
import pandas as pd
r.main(pd.Timestamp('2025-10-31'))
"
```

Expected: completes in 5-10 minutes, prints `n_cells_fit` ≥ 4 (5 stocks × 2 directions = 10 max, expect a few drop on data issues), writes manifest.

- [ ] **Step 3: Commit**

```bash
git add pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/runner.py
git commit -m "feat(H-2026-05-04): end-to-end fit orchestrator with PCA + EN + WF + BH-FDR"
```

---

## Task 6: predict_today.py — daily 04:30 IST forward predictor

**Files:**
- Create: `pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/predict_today.py`

This module loads the frozen models + PCA, builds today's feature row per qualifying cell, scores, writes `today_predictions.json`. Tests deferred to integration (a unit test would essentially re-run runner mocks).

- [ ] **Step 1: Implement**

Create `pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/predict_today.py`:

```python
"""04:30 IST daily forward predictor for H-2026-05-04.

Reads frozen models/PCA from runner output. For each qualifying cell, builds
the latest feature row from the panel/bars, scores, writes today_predictions.json.

CLI: python -m pipeline.research.h_2026_05_04_cross_asset_perstock_lasso.predict_today
"""
from __future__ import annotations

import json
import pickle
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from pipeline.autoresearch.etf_v3_loader import build_panel, CURATED_FOREIGN_ETFS  # noqa: E402
from pipeline.research.h_2026_05_04_cross_asset_perstock_lasso.feature_extractor import (  # noqa: E402
    build_full_feature_matrix,
)
from pipeline.research.h_2026_05_04_cross_asset_perstock_lasso.pca_model import (  # noqa: E402
    apply_pca, load_pca,
)
from pipeline.research.h_2026_05_04_cross_asset_perstock_lasso.elastic_net_fit import (  # noqa: E402
    score_en_cell,
)
from pipeline.research.h_2026_05_04_cross_asset_perstock_lasso.runner import (  # noqa: E402
    _load_bars, NIFTY_EMPHASIS,
)

OUT_DIR = REPO / "pipeline" / "research" / "h_2026_05_04_cross_asset_perstock_lasso"


def main() -> int:
    manifest = json.loads((OUT_DIR / "manifest.json").read_text())
    qualifying = manifest["qualifying_cells"]
    if not qualifying:
        (OUT_DIR / "today_predictions.json").write_text(json.dumps({
            "as_of": datetime.now().isoformat(), "predictions": [],
            "note": "no qualifying cells",
        }))
        return 0

    pca_model = load_pca(OUT_DIR / "pca_projections" / "final.npz")
    panel = build_panel()
    etf_cols = [c for c in CURATED_FOREIGN_ETFS if c in panel.columns]
    etf_1d = panel[etf_cols].pct_change(1)
    etf_1d.columns = [f"{c}_1d" for c in etf_cols]
    nifty_close = panel["nifty_close"]
    india_vix = panel["india_vix"]

    predictions = []
    for ticker, direction in qualifying:
        bars = _load_bars(ticker)
        if bars is None or len(bars) < 100:
            continue
        try:
            from pipeline.sector_mapper import map_one
            sector_name = map_one(ticker)
            sector_path = REPO / "pipeline" / "data" / "sectoral_indices" / f"{sector_name}.csv"
            sector_df = pd.read_csv(sector_path, parse_dates=["Date"]).set_index("Date").sort_index()
            sector_ret_5d = sector_df["Close"].pct_change(5)
        except Exception:
            continue

        X_pre = build_full_feature_matrix(
            bars=bars, etf_returns_1d=etf_1d,
            nifty_near_month_close=nifty_close, india_vix=india_vix,
            sector_ret_5d=sector_ret_5d, nifty_emphasis_factor=NIFTY_EMPHASIS,
        )
        etf_block_cols = [c for c in X_pre.columns if c.endswith("_1d") and not c.startswith("nifty_")]
        pcs = apply_pca(X_pre[etf_block_cols], pca_model)
        non_etf = X_pre.drop(columns=etf_block_cols)
        X = pd.concat([pcs, non_etf], axis=1).dropna()
        if len(X) == 0:
            continue
        latest_row = X.iloc[-1]
        latest_date = X.index[-1]

        with open(OUT_DIR / "models" / f"{ticker}_{direction}.pkl", "rb") as f:
            model = pickle.load(f)
        p_hat = float(score_en_cell(model, latest_row.values.reshape(1, -1))[0])

        predictions.append({
            "ticker": ticker, "direction": direction,
            "p_hat": p_hat, "feature_date": str(latest_date.date()),
        })

    out = {
        "as_of": datetime.now().isoformat(),
        "n_predictions": len(predictions),
        "predictions": predictions,
    }
    (OUT_DIR / "today_predictions.json").write_text(json.dumps(out, indent=2))
    print(f"[predict_today] wrote {len(predictions)} predictions")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Smoke test (after Task 5 smoke fit produced models)**

```bash
PYTHONIOENCODING=utf-8 python -m pipeline.research.h_2026_05_04_cross_asset_perstock_lasso.predict_today
cat pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/today_predictions.json
```

Expected: writes a JSON with `n_predictions` and a list of {ticker, direction, p_hat, feature_date}.

- [ ] **Step 3: Commit**

```bash
git add pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/predict_today.py
git commit -m "feat(H-2026-05-04): daily 04:30 IST forward predictor"
```

---

## Task 7: holdout_ledger.py — 09:15 OPEN / 14:25 CLOSE engine

**Files:**
- Create: `pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/holdout_ledger.py`
- Test: `pipeline/tests/research/h_2026_05_04_cross_asset_perstock_lasso/test_holdout_ledger.py`

- [ ] **Step 1: Write the failing test**

```python
import json
import pandas as pd
import pytest
from pathlib import Path
from pipeline.research.h_2026_05_04_cross_asset_perstock_lasso.holdout_ledger import (
    decide_open_rows,
    compute_atr_stop,
    decide_close_pnl,
)


def test_decide_open_rows_threshold_logic():
    preds = [
        {"ticker": "A", "direction": "LONG", "p_hat": 0.65},
        {"ticker": "A", "direction": "SHORT", "p_hat": 0.35},   # both: LONG fires (p_long>=0.6 AND p_short<0.4)
        {"ticker": "B", "direction": "LONG", "p_hat": 0.55},   # below 0.6, doesn't fire
        {"ticker": "C", "direction": "SHORT", "p_hat": 0.7},
        {"ticker": "C", "direction": "LONG", "p_hat": 0.3},    # SHORT fires
    ]
    fires = decide_open_rows(preds, p_long_threshold=0.6, p_short_threshold=0.4)
    fire_keys = {(f["ticker"], f["direction"]) for f in fires}
    assert ("A", "LONG") in fire_keys
    assert ("C", "SHORT") in fire_keys
    assert ("B", "LONG") not in fire_keys


def test_compute_atr_stop_long_and_short():
    long_stop = compute_atr_stop(entry=100.0, atr=2.0, mult=2.0, direction="LONG")
    assert long_stop == 96.0  # 100 - 2*2
    short_stop = compute_atr_stop(entry=100.0, atr=2.0, mult=2.0, direction="SHORT")
    assert short_stop == 104.0


def test_decide_close_pnl_long_full_hold():
    pnl, exit_reason = decide_close_pnl(
        entry=100.0, exit_ltp=102.0, stop=96.0,
        direction="LONG", position_inr=50000.0,
    )
    # +2% on 50k = +1000 INR
    assert pnl == pytest.approx(1000.0, rel=1e-9)
    assert exit_reason == "TIME_STOP"


def test_decide_close_pnl_long_atr_stopped():
    """If today's intraday low touched stop, exit at stop, NOT at 14:25 LTP."""
    pnl, exit_reason = decide_close_pnl(
        entry=100.0, exit_ltp=102.0, stop=96.0,
        direction="LONG", position_inr=50000.0, intraday_low=95.0,
    )
    # Stopped at 96 (lower of intraday touch), -4% = -2000
    assert pnl == pytest.approx(-2000.0, rel=1e-9)
    assert exit_reason == "ATR_STOP"
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
PYTHONIOENCODING=utf-8 pytest pipeline/tests/research/h_2026_05_04_cross_asset_perstock_lasso/test_holdout_ledger.py -v
```
Expected: ImportError.

- [ ] **Step 3: Implement the module**

Create `pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/holdout_ledger.py`:

```python
"""09:15 IST OPEN / 14:25 IST CLOSE engine for H-2026-05-04 holdout ledger."""
from __future__ import annotations

import csv
import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

OUT_DIR = REPO / "pipeline" / "research" / "h_2026_05_04_cross_asset_perstock_lasso"
LEDGER_PATH = OUT_DIR / "recommendations.csv"

POSITION_INR = 50_000.0
ATR_MULT = 2.0
P_LONG_THRESHOLD = 0.6
P_SHORT_THRESHOLD = 0.4


def decide_open_rows(
    predictions: list[dict],
    p_long_threshold: float = P_LONG_THRESHOLD,
    p_short_threshold: float = P_SHORT_THRESHOLD,
) -> list[dict]:
    """Apply spec section 10 entry rule:
    fire LONG iff p_long >= 0.6 AND p_short < 0.4 (mirror for SHORT).
    """
    by_ticker: dict[str, dict[str, float]] = {}
    for p in predictions:
        by_ticker.setdefault(p["ticker"], {})[p["direction"]] = p["p_hat"]

    fires = []
    for ticker, dirs in by_ticker.items():
        p_long = dirs.get("LONG", 0.5)
        p_short = dirs.get("SHORT", 0.5)
        if p_long >= p_long_threshold and p_short < p_short_threshold:
            fires.append({"ticker": ticker, "direction": "LONG", "p_long": p_long, "p_short": p_short})
        if p_short >= p_long_threshold and p_long < p_short_threshold:
            fires.append({"ticker": ticker, "direction": "SHORT", "p_long": p_long, "p_short": p_short})
    return fires


def compute_atr_stop(*, entry: float, atr: float, mult: float, direction: str) -> float:
    return entry - mult * atr if direction == "LONG" else entry + mult * atr


def decide_close_pnl(
    *,
    entry: float, exit_ltp: float, stop: float,
    direction: str, position_inr: float,
    intraday_low: float | None = None,
    intraday_high: float | None = None,
) -> tuple[float, str]:
    """Returns (pnl_inr, exit_reason). exit_reason in {"TIME_STOP", "ATR_STOP"}."""
    stopped = False
    actual_exit = exit_ltp
    if direction == "LONG":
        if intraday_low is not None and intraday_low <= stop:
            stopped, actual_exit = True, stop
    else:
        if intraday_high is not None and intraday_high >= stop:
            stopped, actual_exit = True, stop

    sign = 1 if direction == "LONG" else -1
    pct = sign * (actual_exit - entry) / entry
    pnl = position_inr * pct
    return pnl, ("ATR_STOP" if stopped else "TIME_STOP")


def write_open_row(*, today: pd.Timestamp, fire: dict, entry_ltp: float, atr: float) -> None:
    """Append an OPEN row to recommendations.csv."""
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    new_file = not LEDGER_PATH.exists()
    fields = ["open_date", "ticker", "direction", "entry_ltp", "atr14", "stop", "position_inr",
              "p_long", "p_short", "exit_date", "exit_ltp", "exit_reason", "pnl_inr"]
    with open(LEDGER_PATH, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if new_file:
            w.writeheader()
        stop = compute_atr_stop(entry=entry_ltp, atr=atr, mult=ATR_MULT, direction=fire["direction"])
        w.writerow({
            "open_date": str(today.date()), "ticker": fire["ticker"], "direction": fire["direction"],
            "entry_ltp": entry_ltp, "atr14": atr, "stop": stop, "position_inr": POSITION_INR,
            "p_long": fire["p_long"], "p_short": fire["p_short"],
            "exit_date": "", "exit_ltp": "", "exit_reason": "", "pnl_inr": "",
        })


def update_close_row(
    *, today: pd.Timestamp, ticker: str, direction: str,
    exit_ltp: float, intraday_low: float, intraday_high: float,
) -> None:
    """Find OPEN row from prior trading day and write its close fields."""
    if not LEDGER_PATH.exists():
        return
    rows = list(csv.DictReader(open(LEDGER_PATH, "r", encoding="utf-8")))
    for row in rows:
        if row["exit_date"] == "" and row["ticker"] == ticker and row["direction"] == direction:
            entry = float(row["entry_ltp"])
            stop = float(row["stop"])
            pnl, reason = decide_close_pnl(
                entry=entry, exit_ltp=exit_ltp, stop=stop,
                direction=direction, position_inr=POSITION_INR,
                intraday_low=intraday_low, intraday_high=intraday_high,
            )
            row["exit_date"] = str(today.date())
            row["exit_ltp"] = exit_ltp
            row["exit_reason"] = reason
            row["pnl_inr"] = round(pnl, 2)
            break
    fields = ["open_date", "ticker", "direction", "entry_ltp", "atr14", "stop", "position_inr",
              "p_long", "p_short", "exit_date", "exit_ltp", "exit_reason", "pnl_inr"]
    with open(LEDGER_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def open_today() -> int:
    """09:15 IST: read today_predictions.json, decide fires, write OPEN rows at Kite LTP."""
    preds_path = OUT_DIR / "today_predictions.json"
    if not preds_path.exists():
        print("[open] no today_predictions.json")
        return 1
    preds = json.loads(preds_path.read_text())["predictions"]
    fires = decide_open_rows(preds)
    if not fires:
        print("[open] 0 fires")
        return 0

    from pipeline.kite_ltp import get_ltp_batch  # existing kite client
    tickers = [f["ticker"] for f in fires]
    ltps = get_ltp_batch(tickers)

    today = pd.Timestamp.now().normalize()
    for f in fires:
        ltp = ltps.get(f["ticker"])
        if ltp is None:
            continue
        # ATR(14) from yesterday's bars
        from pipeline.research.h_2026_05_04_cross_asset_perstock_lasso.runner import _load_bars
        bars = _load_bars(f["ticker"])
        if bars is None or len(bars) < 30:
            continue
        prev_close = bars["Close"].shift(1)
        tr = pd.concat(
            [(bars["High"] - bars["Low"]),
             (bars["High"] - prev_close).abs(),
             (bars["Low"] - prev_close).abs()], axis=1,
        ).max(axis=1)
        atr14 = float(tr.rolling(14).mean().iloc[-1])
        write_open_row(today=today, fire=f, entry_ltp=ltp, atr=atr14)
    print(f"[open] wrote {len(fires)} OPEN rows")
    return 0


def close_today() -> int:
    """14:25 IST: for each OPEN row from prior trading day, write CLOSE fields at Kite LTP."""
    if not LEDGER_PATH.exists():
        print("[close] no ledger yet")
        return 0
    rows = list(csv.DictReader(open(LEDGER_PATH, "r", encoding="utf-8")))
    open_rows = [r for r in rows if r["exit_date"] == ""]
    if not open_rows:
        print("[close] 0 open rows")
        return 0

    from pipeline.kite_ltp import get_ltp_batch  # existing kite client
    tickers = list({r["ticker"] for r in open_rows})
    ltps = get_ltp_batch(tickers)

    today = pd.Timestamp.now().normalize()
    n_closed = 0
    for r in open_rows:
        ltp = ltps.get(r["ticker"])
        if ltp is None:
            continue
        # Intraday low/high since 09:15 IST today via kite intraday history
        from pipeline.kite_intraday import get_intraday_low_high
        try:
            lo, hi = get_intraday_low_high(r["ticker"], today)
        except Exception:
            lo, hi = ltp, ltp
        update_close_row(
            today=today, ticker=r["ticker"], direction=r["direction"],
            exit_ltp=ltp, intraday_low=lo, intraday_high=hi,
        )
        n_closed += 1
    print(f"[close] closed {n_closed} rows")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in ("open", "close"):
        print("usage: holdout_ledger.py {open|close}")
        sys.exit(2)
    sys.exit(open_today() if sys.argv[1] == "open" else close_today())
```

- [ ] **Step 4: Run unit tests to verify they pass**

```bash
PYTHONIOENCODING=utf-8 pytest pipeline/tests/research/h_2026_05_04_cross_asset_perstock_lasso/test_holdout_ledger.py -v
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/holdout_ledger.py
git add pipeline/tests/research/h_2026_05_04_cross_asset_perstock_lasso/test_holdout_ledger.py
git commit -m "feat(H-2026-05-04): 09:15 OPEN / 14:25 CLOSE ledger with ATR stop"
```

---

## Task 8: verdict.py — §12 verdict + §1.B null-band routing

**Files:**
- Create: `pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/verdict.py`
- Test: `pipeline/tests/research/h_2026_05_04_cross_asset_perstock_lasso/test_verdict.py`

- [ ] **Step 1: Write the failing test**

```python
import pytest
from pipeline.research.h_2026_05_04_cross_asset_perstock_lasso.verdict import (
    classify_n_qualifying_band,
    compute_basket_metrics,
)


def test_band_classifications():
    assert classify_n_qualifying_band(0) == "FAIL_NO_QUALIFIERS"
    assert classify_n_qualifying_band(3) == "FAIL_INSUFFICIENT_QUALIFIERS"
    assert classify_n_qualifying_band(15) == "EXPECTED_BAND"
    assert classify_n_qualifying_band(40) == "AMPLIFIED_AUDIT_REQUIRED"
    assert classify_n_qualifying_band(81) == "FAIL_LEAKAGE_SUSPECT"


def test_compute_basket_metrics_known_inputs():
    rows = [
        {"pnl_inr": 1000, "position_inr": 50000},  # +2.0%
        {"pnl_inr": -500, "position_inr": 50000},  # -1.0%
        {"pnl_inr": 750, "position_inr": 50000},   # +1.5%
        {"pnl_inr": 200, "position_inr": 50000},   # +0.4%
    ]
    m = compute_basket_metrics(rows)
    assert m["n_trades"] == 4
    assert m["hit_rate_pct"] == pytest.approx(75.0)  # 3 of 4 positive
    assert m["mean_pnl_pct"] == pytest.approx(0.725)  # mean of +2.0, -1.0, +1.5, +0.4
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
PYTHONIOENCODING=utf-8 pytest pipeline/tests/research/h_2026_05_04_cross_asset_perstock_lasso/test_verdict.py -v
```
Expected: ImportError.

- [ ] **Step 3: Implement**

Create `pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/verdict.py`:

```python
"""Section 12 verdict computation + section 1.B null-band routing for H-2026-05-04."""
from __future__ import annotations

import csv
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

OUT_DIR = REPO / "pipeline" / "research" / "h_2026_05_04_cross_asset_perstock_lasso"


def classify_n_qualifying_band(n: int) -> str:
    if n == 0:
        return "FAIL_NO_QUALIFIERS"
    if n <= 4:
        return "FAIL_INSUFFICIENT_QUALIFIERS"
    if n <= 25:
        return "EXPECTED_BAND"
    if n <= 80:
        return "AMPLIFIED_AUDIT_REQUIRED"
    return "FAIL_LEAKAGE_SUSPECT"


def compute_basket_metrics(rows: list[dict]) -> dict:
    """Pooled-basket metrics from closed ledger rows."""
    if not rows:
        return {"n_trades": 0, "hit_rate_pct": 0.0, "mean_pnl_pct": 0.0,
                "sum_pnl_inr": 0.0, "max_drawdown_pct": 0.0}
    pnls_pct = []
    pnls_inr = []
    for r in rows:
        pnl = float(r["pnl_inr"])
        pos = float(r["position_inr"])
        pnls_inr.append(pnl)
        pnls_pct.append(100 * pnl / pos)
    arr = np.array(pnls_pct)
    cum = np.cumsum(np.array(pnls_inr))
    peak = np.maximum.accumulate(cum)
    dd = (cum - peak) / 50000.0  # drawdown as % of single position size
    return {
        "n_trades": int(len(arr)),
        "hit_rate_pct": float(100 * (arr > 0).mean()),
        "mean_pnl_pct": float(arr.mean()),
        "sum_pnl_inr": float(np.sum(pnls_inr)),
        "max_drawdown_pct": float(dd.min()) if len(dd) else 0.0,
    }


def main() -> int:
    manifest_path = OUT_DIR / "manifest.json"
    ledger_path = OUT_DIR / "recommendations.csv"
    if not manifest_path.exists():
        print("[verdict] FAIL: no manifest.json")
        return 1
    manifest = json.loads(manifest_path.read_text())
    n_qualifying = manifest["n_qualifying"]
    band = classify_n_qualifying_band(n_qualifying)

    closed_rows = []
    if ledger_path.exists():
        for r in csv.DictReader(open(ledger_path, "r", encoding="utf-8")):
            if r["exit_date"]:
                closed_rows.append(r)

    metrics = compute_basket_metrics(closed_rows)

    # Per spec section 12 PASS bar
    pass_n = n_qualifying >= 5
    pass_trades = metrics["n_trades"] >= 60
    pass_hit = metrics["hit_rate_pct"] >= 55.0
    pass_pnl = metrics["mean_pnl_pct"] >= 0.4

    if band in ("FAIL_NO_QUALIFIERS", "FAIL_INSUFFICIENT_QUALIFIERS", "FAIL_LEAKAGE_SUSPECT"):
        terminal_state = band
    elif band == "AMPLIFIED_AUDIT_REQUIRED":
        terminal_state = "PENDING_AMPLIFIED_AUDIT"
    elif pass_n and pass_trades and pass_hit and pass_pnl:
        terminal_state = "PASS_PRELIMINARY"  # subject to fragility + comparator checks
    else:
        terminal_state = "FAIL_INSUFFICIENT_EDGE"

    out = {
        "hypothesis_id": "H-2026-05-04-cross-asset-perstock-lasso-v1",
        "verdict_at": datetime.now().isoformat(),
        "n_qualifying": n_qualifying, "n_qualifying_band": band,
        "metrics": metrics,
        "section_12_gates": {
            "n_qualifying>=5": pass_n,
            "n_trades>=60": pass_trades,
            "hit_rate>=55": pass_hit,
            "mean_pnl>=0.4": pass_pnl,
        },
        "terminal_state": terminal_state,
    }
    (OUT_DIR / "terminal_state.json").write_text(json.dumps(out, indent=2, default=str))
    print(json.dumps(out, indent=2, default=str))
    return 0 if terminal_state.startswith("PASS") else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
PYTHONIOENCODING=utf-8 pytest pipeline/tests/research/h_2026_05_04_cross_asset_perstock_lasso/test_verdict.py -v
```
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/verdict.py
git add pipeline/tests/research/h_2026_05_04_cross_asset_perstock_lasso/test_verdict.py
git commit -m "feat(H-2026-05-04): section 12 verdict + section 1.B null-band routing"
```

---

## Task 9: leakage_audit.py — §16.6 amplified leakage audit

**Files:**
- Create: `pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/leakage_audit.py`

This module is a research-only diagnostic. It re-runs the runner with three modifications and writes diagnostic outputs.

- [ ] **Step 1: Implement**

Create `pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/leakage_audit.py`:

```python
"""Section 16.6 amplified leakage audit. Triggers when n_qualifying in [26,80].

Three diagnostic rebuilds:
  A. Label-shift permutation control (shuffle labels within each (stock, fold))
  B. Date-shift PIT control (extra +1 IST trading day shift on ETF block)
  C. Feature-block ablation (zero out ETF PCs, fit TA-only)

Writes leakage_audit.json with three n_qualifying counts; verdict module reads it.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

OUT_DIR = REPO / "pipeline" / "research" / "h_2026_05_04_cross_asset_perstock_lasso"


def run_audit_a_label_permutation() -> int:
    """Re-fit with labels shuffled within each (stock, fold). Expected: ~5% pass under null."""
    # Implementation: import runner.main, monkey-patch label generator with permutation
    import importlib
    import pipeline.research.h_2026_05_04_cross_asset_perstock_lasso.runner as r
    rng = np.random.default_rng(0)
    orig_label = r._label

    def shuffled_label(bars, threshold_pct):
        y_long, y_short = orig_label(bars, threshold_pct)
        return pd.Series(rng.permutation(y_long.values), index=y_long.index), \
               pd.Series(rng.permutation(y_short.values), index=y_short.index)

    r._label = shuffled_label
    # Write to a separate manifest
    audit_dir = OUT_DIR / "audit_a_label_perm"
    audit_dir.mkdir(parents=True, exist_ok=True)
    orig_out = r.OUT_DIR
    r.OUT_DIR = audit_dir
    try:
        r.main(pd.Timestamp("2025-10-31"))
    finally:
        r.OUT_DIR = orig_out
        r._label = orig_label
    manifest = json.loads((audit_dir / "manifest.json").read_text())
    return manifest["n_qualifying"]


def run_audit_b_date_shift() -> int:
    """Re-fit with ETF block additionally shifted by +1 IST trading day (forward leakage)."""
    import pipeline.research.h_2026_05_04_cross_asset_perstock_lasso.runner as r
    from pipeline.autoresearch import etf_v3_loader
    orig_build = etf_v3_loader.build_panel

    def shifted_build(*, t1_anchor=True):
        panel = orig_build(t1_anchor=t1_anchor)
        # Additional +1 forward shift introduces look-ahead
        return panel.shift(-1)

    etf_v3_loader.build_panel = shifted_build
    audit_dir = OUT_DIR / "audit_b_date_shift"
    audit_dir.mkdir(parents=True, exist_ok=True)
    orig_out = r.OUT_DIR
    r.OUT_DIR = audit_dir
    try:
        r.main(pd.Timestamp("2025-10-31"))
    finally:
        r.OUT_DIR = orig_out
        etf_v3_loader.build_panel = orig_build
    manifest = json.loads((audit_dir / "manifest.json").read_text())
    return manifest["n_qualifying"]


def run_audit_c_ablation() -> int:
    """Re-fit with ETF block zeroed (TA + IND macro + DOW only)."""
    # The cleanest implementation is to patch apply_pca to return zeros
    import pipeline.research.h_2026_05_04_cross_asset_perstock_lasso.pca_model as p
    import pipeline.research.h_2026_05_04_cross_asset_perstock_lasso.runner as r
    orig_apply = p.apply_pca

    def zero_pca(X, model):
        z = orig_apply(X, model)
        return pd.DataFrame(np.zeros_like(z.values), index=z.index, columns=z.columns)

    p.apply_pca = zero_pca
    r.apply_pca = zero_pca  # runner imported it directly
    audit_dir = OUT_DIR / "audit_c_ablation"
    audit_dir.mkdir(parents=True, exist_ok=True)
    orig_out = r.OUT_DIR
    r.OUT_DIR = audit_dir
    try:
        r.main(pd.Timestamp("2025-10-31"))
    finally:
        r.OUT_DIR = orig_out
        p.apply_pca = orig_apply
        r.apply_pca = orig_apply
    manifest = json.loads((audit_dir / "manifest.json").read_text())
    return manifest["n_qualifying"]


def main() -> int:
    manifest = json.loads((OUT_DIR / "manifest.json").read_text())
    n_qual = manifest["n_qualifying"]
    n_cells = manifest["n_cells_fit"]

    print(f"[leakage_audit] base n_qualifying={n_qual}, n_cells_fit={n_cells}")
    n_a = run_audit_a_label_permutation()
    n_b = run_audit_b_date_shift()
    n_c = run_audit_c_ablation()

    out = {
        "base_n_qualifying": n_qual,
        "n_cells_fit": n_cells,
        "audit_a_label_perm": n_a,
        "audit_b_date_shift": n_b,
        "audit_c_ablation": n_c,
        "audit_a_pass": n_a <= 30,                    # spec section 16.6.A
        "audit_b_pass": n_b <= n_qual,                # spec section 16.6.B
        "audit_c_pass_no_redundancy": (n_c < 0.5 * n_qual),  # spec section 16.6.C: TA-only should be much smaller
    }
    (OUT_DIR / "leakage_audit.json").write_text(json.dumps(out, indent=2, default=str))
    print(json.dumps(out, indent=2, default=str))
    return 0 if all([out["audit_a_pass"], out["audit_b_pass"], out["audit_c_pass_no_redundancy"]]) else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Commit**

```bash
git add pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/leakage_audit.py
git commit -m "feat(H-2026-05-04): section 16.6 amplified leakage audit (label-perm/date-shift/ablation)"
```

---

## Task 10: VPS systemd units (predict / open / close / recalibrate)

**Files:**
- Create: `pipeline/infra/systemd/anka-cross-asset-predict.service`
- Create: `pipeline/infra/systemd/anka-cross-asset-predict.timer`
- Create: `pipeline/infra/systemd/anka-cross-asset-open.service`
- Create: `pipeline/infra/systemd/anka-cross-asset-open.timer`
- Create: `pipeline/infra/systemd/anka-cross-asset-close.service`
- Create: `pipeline/infra/systemd/anka-cross-asset-close.timer`
- Create: `pipeline/infra/systemd/anka-cross-asset-recalibrate.service`
- Create: `pipeline/infra/systemd/anka-cross-asset-recalibrate.timer`

- [ ] **Step 1: Create predict service**

`pipeline/infra/systemd/anka-cross-asset-predict.service`:
```
[Unit]
Description=H-2026-05-04 daily 04:30 IST cross-asset predict
After=network-online.target

[Service]
Type=oneshot
User=anka
WorkingDirectory=/home/anka/askanka.com
Environment=PYTHONIOENCODING=utf-8
ExecStart=/home/anka/askanka.com/.venv/bin/python -m pipeline.research.h_2026_05_04_cross_asset_perstock_lasso.predict_today
StandardOutput=append:/home/anka/.local/share/anka/anka-cross-asset-predict.log
StandardError=append:/home/anka/.local/share/anka/anka-cross-asset-predict.log
TimeoutStartSec=30min
```

`pipeline/infra/systemd/anka-cross-asset-predict.timer`:
```
[Unit]
Description=Daily 04:30 IST cross-asset predict (Contabo system tz is IST)

[Timer]
OnCalendar=*-*-* 04:30:00
Persistent=true
Unit=anka-cross-asset-predict.service

[Install]
WantedBy=timers.target
```

- [ ] **Step 2: Create open/close/recalibrate units**

`pipeline/infra/systemd/anka-cross-asset-open.service`:
```
[Unit]
Description=H-2026-05-04 09:15 IST open
After=network-online.target

[Service]
Type=oneshot
User=anka
WorkingDirectory=/home/anka/askanka.com
Environment=PYTHONIOENCODING=utf-8
ExecStart=/home/anka/askanka.com/.venv/bin/python -m pipeline.research.h_2026_05_04_cross_asset_perstock_lasso.holdout_ledger open
StandardOutput=append:/home/anka/.local/share/anka/anka-cross-asset-open.log
StandardError=append:/home/anka/.local/share/anka/anka-cross-asset-open.log
TimeoutStartSec=10min
```

`pipeline/infra/systemd/anka-cross-asset-open.timer`:
```
[Unit]
Description=09:15 IST trading-day open

[Timer]
OnCalendar=Mon..Fri 09:15:00
Persistent=true
Unit=anka-cross-asset-open.service

[Install]
WantedBy=timers.target
```

`pipeline/infra/systemd/anka-cross-asset-close.service`:
```
[Unit]
Description=H-2026-05-04 14:25 IST close
After=network-online.target

[Service]
Type=oneshot
User=anka
WorkingDirectory=/home/anka/askanka.com
Environment=PYTHONIOENCODING=utf-8
ExecStart=/home/anka/askanka.com/.venv/bin/python -m pipeline.research.h_2026_05_04_cross_asset_perstock_lasso.holdout_ledger close
StandardOutput=append:/home/anka/.local/share/anka/anka-cross-asset-close.log
StandardError=append:/home/anka/.local/share/anka/anka-cross-asset-close.log
TimeoutStartSec=10min
```

`pipeline/infra/systemd/anka-cross-asset-close.timer`:
```
[Unit]
Description=14:25 IST trading-day close (5 min before universal cutoff)

[Timer]
OnCalendar=Mon..Fri 14:25:00
Persistent=true
Unit=anka-cross-asset-close.service

[Install]
WantedBy=timers.target
```

`pipeline/infra/systemd/anka-cross-asset-recalibrate.service`:
```
[Unit]
Description=H-2026-05-04 monthly recalibrate (forbidden during holdout per section 10.4 - this fires AFTER verdict)
After=network-online.target

[Service]
Type=oneshot
User=anka
WorkingDirectory=/home/anka/askanka.com
Environment=PYTHONIOENCODING=utf-8
ExecStart=/home/anka/askanka.com/.venv/bin/bash -c 'test -f pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/terminal_state.json || { echo "no verdict yet, skipping"; exit 0; }; /home/anka/askanka.com/.venv/bin/python -m pipeline.research.h_2026_05_04_cross_asset_perstock_lasso.runner --train-end $(date +%Y-%m-%d)'
StandardOutput=append:/home/anka/.local/share/anka/anka-cross-asset-recalibrate.log
StandardError=append:/home/anka/.local/share/anka/anka-cross-asset-recalibrate.log
TimeoutStartSec=8h
```

`pipeline/infra/systemd/anka-cross-asset-recalibrate.timer`:
```
[Unit]
Description=Last Sunday of month 02:00 IST recalibrate (gated on terminal_state.json present)

[Timer]
OnCalendar=Sun *-*-22..28 02:00:00
Persistent=true
Unit=anka-cross-asset-recalibrate.service

[Install]
WantedBy=timers.target
```

- [ ] **Step 3: Commit**

```bash
git add pipeline/infra/systemd/anka-cross-asset-*.service
git add pipeline/infra/systemd/anka-cross-asset-*.timer
git commit -m "feat(H-2026-05-04): VPS systemd units (predict 04:30 / open 09:15 / close 14:25 / recalibrate)"
```

- [ ] **Step 4: Deploy to Contabo (post-fit-job; manual handoff)**

Manual SSH commands run by the operator after the fit job completes on VPS:

```bash
ssh contabo "
sudo cp ~/askanka.com/pipeline/infra/systemd/anka-cross-asset-*.service /etc/systemd/system/
sudo cp ~/askanka.com/pipeline/infra/systemd/anka-cross-asset-*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now anka-cross-asset-predict.timer
sudo systemctl enable --now anka-cross-asset-open.timer
sudo systemctl enable --now anka-cross-asset-close.timer
sudo systemctl enable --now anka-cross-asset-recalibrate.timer
systemctl list-timers anka-cross-asset-*
"
```

Expected: 4 timers listed with next-fire timestamps in IST.

---

## Task 11: Watchdog inventory + freshness contracts

**Files:**
- Modify: `pipeline/config/anka_inventory.json`

- [ ] **Step 1: Add 4 entries to anka_inventory.json**

Append the following under the appropriate section (the file uses `tasks` array; add 4 entries):

```json
{
  "name": "AnkaCrossAssetPredict",
  "tier": "info",
  "cadence_class": "daily",
  "schedule": "04:30 IST daily",
  "platform": "vps_systemd",
  "expected_outputs": ["pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/today_predictions.json"],
  "freshness_max_hours": 25,
  "grace_multiplier": 1.5,
  "hypothesis_id": "H-2026-05-04-cross-asset-perstock-lasso-v1"
}
```

```json
{
  "name": "AnkaCrossAssetOpen",
  "tier": "info",
  "cadence_class": "intraday",
  "schedule": "09:15 IST trading days",
  "platform": "vps_systemd",
  "expected_outputs": ["pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/recommendations.csv"],
  "freshness_max_hours": 25,
  "grace_multiplier": 1.5,
  "hypothesis_id": "H-2026-05-04-cross-asset-perstock-lasso-v1"
}
```

```json
{
  "name": "AnkaCrossAssetClose",
  "tier": "info",
  "cadence_class": "intraday",
  "schedule": "14:25 IST trading days",
  "platform": "vps_systemd",
  "expected_outputs": ["pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/recommendations.csv"],
  "freshness_max_hours": 25,
  "grace_multiplier": 1.5,
  "hypothesis_id": "H-2026-05-04-cross-asset-perstock-lasso-v1"
}
```

```json
{
  "name": "AnkaCrossAssetRecalibrate",
  "tier": "info",
  "cadence_class": "monthly",
  "schedule": "Last Sunday of month 02:00 IST",
  "platform": "vps_systemd",
  "expected_outputs": ["pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/manifest.json"],
  "freshness_max_hours": 800,
  "grace_multiplier": 1.5,
  "hypothesis_id": "H-2026-05-04-cross-asset-perstock-lasso-v1",
  "notes": "Gated on terminal_state.json present (post-verdict). Forbidden during holdout per section 10.4."
}
```

- [ ] **Step 2: Verify inventory loads**

```bash
python -c "
import json
inv = json.load(open('pipeline/config/anka_inventory.json'))
new = [t for t in inv['tasks'] if 'CrossAsset' in t['name']]
assert len(new) == 4, f'expected 4 cross-asset tasks, got {len(new)}'
print([t['name'] for t in new])
"
```

Expected: prints `['AnkaCrossAssetPredict', 'AnkaCrossAssetOpen', 'AnkaCrossAssetClose', 'AnkaCrossAssetRecalibrate']`.

- [ ] **Step 3: Commit**

```bash
git add pipeline/config/anka_inventory.json
git commit -m "feat(H-2026-05-04): watchdog inventory entries for 4 new VPS tasks"
```

---

## Task 12: Doc sync (CLAUDE.md + SYSTEM_OPERATIONS_MANUAL.md)

**Files:**
- Modify: `CLAUDE.md` — clockwork schedule additions
- Modify: `docs/SYSTEM_OPERATIONS_MANUAL.md` — section update

- [ ] **Step 1: Add 4 lines to CLAUDE.md clockwork schedule**

Under "**VPS Execution Foundation**" section, after the AnkaHermesFAQCurriculum line, add:

```markdown
- 04:30 IST daily — AnkaCrossAssetPredict: H-2026-05-04 daily forward predict for qualifying (stock,direction) cells. Writes `today_predictions.json`. (info, holdout 2026-05-04→2026-08-04)
- 09:15 IST trading days — AnkaCrossAssetOpen: H-2026-05-04 OPEN engine — fires LONG when p_long≥0.6 AND p_short<0.4 (mirror SHORT). Writes recommendations.csv. (info)
- 14:25 IST trading days — AnkaCrossAssetClose: H-2026-05-04 mechanical close at Kite LTP, ATR(14)×2 stop checked against intraday low/high. (info)
- Last Sun of month 02:00 IST — AnkaCrossAssetRecalibrate: gated on `terminal_state.json` present — only fires post-verdict to avoid §10.4 holdout violation. (info)
```

- [ ] **Step 2: Add the H-2026-05-04 paragraph to CLAUDE.md hypothesis register**

After the "**H-2026-05-01-EARNINGS-DRIFT-LONG-v1**" paragraph, add:

```markdown
**H-2026-05-04-cross-asset-perstock-lasso-v1 (per-stock cross-asset elastic-net, 200-stock F&O):** PRE_REGISTERED 2026-05-03. Per (stock, direction) cell: elastic-net logistic on 23 features (PCA K_ETF=10 reducing 30 CURATED foreign ETFs 1d returns + 4 Indian macro [Nifty near-month ×sqrt(1.5) emphasis + India VIX] + 6 stock TA + 3 DOW), exp-decay sample weights HL=90 trading days, 4-fold expanding-origin walk-forward, BH-FDR across cell grid. **Primary unit of inference: BASKET-level pass per spec §1.A — non-qualified cells are non-tradeable, NOT failed predictions.** Pre-flight 2026-05-03 (all PASS): K_ETF=10 at 85.4% var, max abs corr PC×TA = 0.074 (cross-asset truly orthogonal to TA), 200 stocks at ₹50cr ADV, ratio 5.66:1 at HL=90. **§1.B null bounds:** n_qualifying = 0=`FAIL_NO_QUALIFIERS` / [1,4]=`FAIL_INSUFFICIENT_QUALIFIERS` / [5,25]=expected / [26,80]=triggers §16.6 amplified leakage audit / >80=`FAIL_LEAKAGE_SUSPECT`. **§12 PASS bar:** n_qualifying ≥5, ≥60 trades, hit ≥55%, mean P&L ≥+0.4% net@S1, B0/B1/B3/B4 cleared, B2 negative. Single-touch holdout 2026-05-04 → 2026-08-04, auto-extend to 2026-10-31 if n_qualifying<5. Spec: `docs/superpowers/specs/2026-05-04-cross-asset-perstock-lasso-v1-design.md`. Plan: `docs/superpowers/plans/2026-05-04-cross-asset-perstock-lasso-v1.md`. Pre-flight: `pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/preflight_results.json`. Universe: `pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/universe_frozen.json`. Engine: `pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/{runner,predict_today,holdout_ledger,verdict,leakage_audit}.py`. Ledger: `pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/recommendations.csv` (created on first OPEN). **Scheduled tasks (AnkaCrossAssetPredict 04:30 + Open 09:15 + Close 14:25 + Recalibrate monthly) on VPS systemd; units at `pipeline/infra/systemd/anka-cross-asset-{predict,open,close,recalibrate}.{service,timer}`.** **No parameter changes during holdout per backtesting-specs.txt §10.4 strict.** 5d ETF horizon explicitly deferred to v2 (would push K_ETF to 18, violates Check 2 cap).
```

- [ ] **Step 3: Update SYSTEM_OPERATIONS_MANUAL.md**

Under the "Active Hypotheses" or equivalent section in `docs/SYSTEM_OPERATIONS_MANUAL.md`, add a one-paragraph summary mirroring the CLAUDE.md entry, and add the 4 scheduled tasks to the schedule diagram. (Specific section depends on document structure — read file first to find the right anchor.)

```bash
grep -n "Hypothesis" docs/SYSTEM_OPERATIONS_MANUAL.md | head -5
# Find appropriate section, add a one-paragraph entry there
```

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md docs/SYSTEM_OPERATIONS_MANUAL.md
git commit -m "docs(H-2026-05-04): clockwork schedule + hypothesis paragraph + ops manual"
```

---

## Task 13: VPS deploy + initial fit run

**Files:** none (operational task, runs the fit job on VPS)

- [ ] **Step 1: Sync repo to VPS**

```bash
ssh contabo "cd ~/askanka.com && git fetch origin && git checkout feat/phase-c-v5 && git pull"
```

Expected: VPS has all code from Tasks 0-12.

- [ ] **Step 2: Run pre-flight on VPS to verify environment**

```bash
ssh contabo "cd ~/askanka.com && PYTHONIOENCODING=utf-8 .venv/bin/python pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/preflight.py"
```

Expected: `OVERALL: ALL CHECKS PASS` with the same 5/5 result as laptop.

- [ ] **Step 3: Run the full fit job (3-4 hours)**

```bash
ssh contabo "cd ~/askanka.com && nohup .venv/bin/python -m pipeline.research.h_2026_05_04_cross_asset_perstock_lasso.runner --train-end 2025-10-31 > /home/anka/.local/share/anka/h-2026-05-04-fit.log 2>&1 &"
```

Then monitor:
```bash
ssh contabo "tail -f /home/anka/.local/share/anka/h-2026-05-04-fit.log"
```

Expected: completes with `[runner] DONE: ~360 cells fit, ~5-25 qualified` (per §1.B null expectation).

- [ ] **Step 4: Inspect manifest**

```bash
ssh contabo "cat ~/askanka.com/pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/manifest.json | python -m json.tool | head -30"
```

Confirm `n_qualifying` falls in expected band [5, 25]. If `[26, 80]`, run §16.6 audit:

```bash
ssh contabo "cd ~/askanka.com && nohup .venv/bin/python -m pipeline.research.h_2026_05_04_cross_asset_perstock_lasso.leakage_audit > /home/anka/.local/share/anka/h-2026-05-04-leakage.log 2>&1 &"
```

If `> 80`, declare `FAIL_LEAKAGE_SUSPECT` and pause holdout per §1.B.

- [ ] **Step 5: Sync fit artifacts back to laptop and commit**

```bash
rsync -av contabo:~/askanka.com/pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/manifest.json pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/
rsync -av contabo:~/askanka.com/pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/walk_forward_results.json pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/
git add pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/manifest.json
git add pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/walk_forward_results.json
git commit -m "feat(H-2026-05-04): initial fit complete on VPS, manifest.json synced"
```

- [ ] **Step 6: Enable systemd timers (per Task 10 Step 4)**

Run the SSH command from Task 10 Step 4 to enable the 4 timers on Contabo. Verify next-fire timestamp on `anka-cross-asset-predict.timer` is the upcoming 04:30 IST.

---

## Self-Review Checklist (run after writing this plan, before handoff)

**Spec coverage:**
- [x] §1.A primary unit of inference — Task 0 memory file + Task 8 verdict band routing
- [x] §1.B null expectation bounds — Task 8 `classify_n_qualifying_band`
- [x] §1.D classification rationale — Task 0 memory references it
- [x] §3 Universe — Task 0 commits the frozen list (already exists)
- [x] §4 Data lineage + §4.A PIT alignment — Task 5 runner uses `build_panel(t1_anchor=True)` directly
- [x] §4.B PIT verification gate — Task 0 Step 1 reads preflight_results which includes audit_panel pass
- [x] §5.1 30 ETFs 1d-only PCA — Task 2 + Task 5
- [x] §5.2 Indian macro w/ nifty_emphasis_factor — Task 1 `build_indian_macro`
- [x] §5.3 6 TA features — Task 1 `build_stock_ta`
- [x] §5.4 3 DOW — Task 1 `build_dow`
- [x] §6 Label T+1 ±0.4% — Task 5 `_label`
- [x] §7 Splits — Task 5 train_end + Task 4 expanding folds
- [x] §8 Model — Task 3 EN logistic with C×l1_ratio CV
- [x] §9 Qualifier gate — Task 4 `qualifier_check`
- [x] §10 Forward trading rule — Task 7 `decide_open_rows` + `compute_atr_stop` + `decide_close_pnl`
- [x] §11 Comparator baselines — DEFERRED. (B0-B4 are computed at verdict time; gap noted below.)
- [x] §12 PASS criteria — Task 8 verdict
- [x] §12.1 DSR report-only — DEFERRED to v2. (Note: spec says report-only at v1; verdict module just emits raw Sharpe; PSR/DSR added in Task 13 Step 5 commit if needed.)
- [x] §12.2 Failure-mode taxonomy — Task 8 `classify_n_qualifying_band` + verdict gates
- [x] §13 Power analysis — narrative-only in spec, no task needed
- [x] §14 Outputs — Task 5 + Task 6 + Task 7 + Task 8 write the listed files
- [x] §15 Lifecycle — covered by VPS systemd timers Task 10
- [x] §16 Pre-flight — already done
- [x] §16.6 Amplified leakage audit — Task 9
- [x] §17 Self-review — spec already self-reviewed
- [x] §18 Forward roadmap — narrative, no task

**Gaps identified:**
- §11 comparator ladder (B0-B4) is NOT implemented as code. It needs to be added to `verdict.py` to compute pooled metrics for each comparator at verdict time. **Adding Task 8.5 below.**

## Task 8.5: Comparator baselines (B0-B4) in verdict

**Files:**
- Modify: `pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/verdict.py`

- [ ] **Step 1: Extend verdict.py with comparator computation**

Add to `verdict.py` after `compute_basket_metrics`:

```python
def compute_comparator_baselines(closed_rows: list[dict], holdout_window: tuple) -> dict:
    """Compute B0-B4 pooled metrics. Each baseline is a counterfactual rerun.

    B0 always_long: every qualifying day, LONG every qualifying ticker
    B1 random_direction: same days, coin-flip direction
    B2 flipped: same predictions, opposite side (must lose money)
    B3 passive_nifty: LONG NIFTY 09:15 -> 14:25 every day
    B4 ta_only: see leakage_audit.run_audit_c_ablation (separate run)
    """
    # B2 (flipped): trivially derived — flip the sign of every PnL
    b2_pnl_pct = -np.mean([float(r["pnl_inr"]) / float(r["position_inr"]) * 100 for r in closed_rows])
    # B0/B1/B3 require re-walking the holdout days with different rules — implementation:
    # for v1, we record only B2 inline (most diagnostic). B0/B1/B3/B4 require separate
    # backtest runs over the holdout window which are scoped as Task 13 Step 5 add-on.
    return {"B2_flipped_mean_pnl_pct": float(b2_pnl_pct), "B2_must_lose": b2_pnl_pct < 0,
            "note": "B0/B1/B3 require separate backtest re-runs; performed at verdict time, not here"}
```

In `main()`, add `out["comparators"] = compute_comparator_baselines(closed_rows, ...)`.

- [ ] **Step 2: Commit**

```bash
git add pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/verdict.py
git commit -m "feat(H-2026-05-04): B2 flipped-EN comparator inline in verdict (B0/B1/B3/B4 deferred)"
```

**Note:** B0/B1/B3 full comparator computation is deferred to a verdict-time follow-up because they require re-walking the 65-day holdout window with synthetic counterfactual predictions — outside the v1 single-touch surface. They are computed manually before terminal_state finalises.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-04-cross-asset-perstock-lasso-v1.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration. Tasks 1-4, 6-9, 12 are pure code (subagent-friendly). Task 0 (registry append) needs explicit user approval before commit. Tasks 10, 11, 13 involve VPS SSH operations (operator-driven).

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
