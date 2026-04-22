# Feature Coincidence Scorer — Design Spec

**Date:** 2026-04-22
**Author:** Bharat + Claude (brainstorm)
**Status:** draft → pending review → to be planned

## 1. Problem statement

Every ticker surfaced by the trading pipeline (Phase B ranker picks, correlation breaks, candidates) today carries a conviction label (HIGH/MEDIUM/LOW/PROVISIONAL/NONE) and an episode-derived `entry_score`. The conviction label is sample-size-aware after B1 and B1.5 — it's now honest about being data-limited. But it's also **static for the day** and **episode-narrow**: a PROVISIONAL label says "we have too few exact-setup episodes to rate this," it says nothing about "how does this look *right now* given today's sector flow, breadth, and positioning?"

This spec defines a complementary layer: a **continuous per-ticker attractiveness score** that updates every 15 minutes with the intraday cycle and is learned from a broader feature set spanning 5 years of sectoral-index history. It's orthogonal to the conviction label — it ranks candidates *within* their conviction band, never across bands.

## 2. Design decisions (brainstormed)

| # | Decision | Locked choice |
|---|----------|---------------|
| 1 | Score use: gate, rank, or both | **Layered**: ranks within conviction bands. PROVISIONAL-with-score-80 never leapfrogs HIGH-with-score-55. |
| 2 | Prediction target (label) | **Simulated P&L ≥ 1.5% = win** using today's stop/trail hierarchy (B9 + B10). Not a price proxy. |
| 3 | Feature vocabulary | **Fixed 10 features v1**, revisit per-ticker L1 feature selection in v2 if AUC distribution warrants it. |
| 4 | Model | **Logistic regression + explicit interaction terms** (regime×trust, regime×PCR_z, sector_return×relative_strength). |
| 5 | Validation scheme | **Quarterly walk-forward**: 2y train, 3mo test, roll quarterly. Health gate = mean fold AUC. |
| 6 | Universe scope | **Full F&O (~215 tickers)**. Quarterly Sunday fit. |
| 7 | Intraday cadence | **15-min updates** with the intraday cycle (26x/day). Append-only feature snapshots. |
| 8a | UI surfaces | **Trading tab column + Positions tab badge + TA tab feature panel.** |
| 8b | Fallback for thin-history tickers | **Own model → sector cohort → single-fold → MODEL_UNAVAILABLE.** |

## 3. Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  Quarterly (Sunday 01:00 IST — new scheduled task)               │
│                                                                   │
│   AnkaFeatureScorerFit                                           │
│     └─ for each of 215 F&O tickers:                              │
│        ├─ build feature matrix (2y lookback)                     │
│        ├─ build label vector (simulated P&L ≥ 1.5% / day)        │
│        ├─ fit logistic (with interactions)                       │
│        ├─ 4-fold quarterly walk-forward validation               │
│        ├─ compute mean AUC, health band                          │
│        └─ save coefficients + metadata                           │
│                                                                   │
│   Output: pipeline/data/ticker_feature_models.json               │
│     {ticker: {coefficients, interactions, train_auc_folds,      │
│               mean_auc, health, updated_at, fallback_sector}}    │
└──────────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│  Intraday (every 15 min — piggybacks AnkaIntraday####)           │
│                                                                   │
│   feature_scorer.score_universe()                                 │
│     └─ for each ticker with a GREEN/AMBER model:                 │
│        ├─ build live feature vector (sector_5d, PCR_z, ...)      │
│        ├─ apply cached coefficients → attractiveness 0-100       │
│        ├─ compute top-3 contributing features                    │
│        └─ append to snapshots                                     │
│                                                                   │
│   Outputs:                                                        │
│     - pipeline/data/attractiveness_scores.json  (latest snapshot)│
│     - pipeline/data/attractiveness_snapshots.jsonl (history)     │
└──────────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│  Terminal (FastAPI + JS, reads cache only)                       │
│                                                                   │
│   /api/attractiveness/{ticker}  → {score, band, top_features,   │
│                                    model_health, updated_at}     │
│                                                                   │
│   UI:                                                             │
│     Trading tab  → new "Attractiveness" column                   │
│     Positions tab → "live attractiveness: 67 ↑ from 62" badge    │
│     TA tab → feature contribution panel (bar chart of top-5)     │
└──────────────────────────────────────────────────────────────────┘
```

## 4. Feature vocabulary (v1 fixed)

All features computed at EOD snapshot or 15-min intraday snapshot. All available without leakage (using only information known before the scoring moment).

| # | Feature | Formula | Source |
|---|---------|---------|--------|
| 1 | `sector_5d_return` | (sector_close_today − sector_close_5d_ago) / sector_close_5d_ago | `pipeline/data/india_historical/indices/{sector}_daily.csv` |
| 2 | `sector_20d_return` | same, 20d window | same |
| 3 | `ticker_rs_10d` | ticker_10d_return − sector_10d_return | prices + sector |
| 4 | `ticker_3d_momentum` | (close_today − close_3d_ago) / close_3d_ago | ticker prices |
| 5 | `nifty_breadth_5d` | count(constituents with 5d_return > 0) / 50 | NIFTY + `sector_concentration.json` |
| 6 | `regime_one_hot` | 5-dim vector: [RISK-OFF, NEUTRAL, RISK-ON, EUPHORIA, CRISIS] | `today_regime` history or point-in-time ETF engine reconstruction |
| 7 | `pcr_z_score` | (today_pcr − trailing_20d_mean) / trailing_20d_std. 0 if unavailable. | `positioning.json` (thin pre-2026) |
| 8 | `dte_bucket` | 3-dim one-hot: [0-5, 6-15, 16+] days-to-expiry | computed from current expiry |
| 9 | `trust_grade_ordinal` | A=5, B=4, C=3, D=2, F=1, UNKNOWN=0 | `trust_scores.json` |
| 10 | `realized_vol_60d` | annualized stdev of 60d log returns | ticker prices |

**Interaction terms (added explicitly):**

| Pair | Why |
|------|-----|
| `regime_one_hot × trust_grade_ordinal` | Trust is only conditional alpha in NEUTRAL (memory: `project_scorecard_alpha_test.md`). |
| `regime_one_hot × pcr_z_score` | Extreme positioning signals flip their predictive direction across regimes. |
| `sector_5d_return × ticker_rs_10d` | Lagging within a hot sector is different from lagging within a cold sector. |

Total coefficient count per ticker: **10 linear + ~15 interaction = ~25 coefficients**. Fits comfortably in 500-day training windows.

## 5. Label generation

For each historical day `t` in the training window:

1. Assume a simulated LONG position opened at close-of-`t` at the close price.
2. Compute stops and trails using the **current** stop hierarchy (B9 + B10 logic) with `avg_favorable` derived from the ticker's trailing 30d favorable-move history as-of date `t`.
3. Simulate the position day-by-day for up to **5 trading days** (matching the widest spread horizon in use).
4. Record the realized P&L at simulated exit (whichever comes first: trail stop, daily stop, time-stop at day 5, target).
5. **Label `y_t = 1` if realized P&L ≥ 1.5%, else 0.**

**Why 1.5%:** aligned with typical spread-trade target magnitudes in the existing system. Matches the trader's practical "worth holding for" bar. Configurable via `config["win_threshold_pct"]`.

**Implementation:** reuse `pipeline/signal_tracker.check_signal_status` and the recently-fixed stop/trail helpers directly, invoking them in a deterministic replay loop. No new simulation logic.

## 6. Model + validation

**Model:** `sklearn.linear_model.LogisticRegression(penalty="l2", C=1.0, max_iter=500)` with standardized features (z-scored per ticker before fitting). One-hot and ordinal features pass through unstandardized.

**Walk-forward scheme** (quarterly):

```
Given ticker history ranging [2021-01-01, today]:
  folds = []
  for fold_end in rolling 3-month windows ending at [today, today-3mo, today-6mo, ...]:
      train = [fold_end - 2y - 3mo, fold_end - 3mo]
      test  = [fold_end - 3mo, fold_end]
      if len(train) < 500 or len(test) < 30:  break
      fold_auc = fit_on(train).evaluate_on(test).auc
      folds.append(fold_auc)
```

Emits up to ~6 fold AUCs per mature ticker.

**Health gate (on `mean(folds)` with stability check):**

| Band | Condition |
|------|-----------|
| **GREEN** | `mean_auc ≥ 0.55` AND `min_fold_auc ≥ 0.50` |
| **AMBER** | `0.52 ≤ mean_auc < 0.55` OR `min_fold_auc < 0.50` but mean ≥ 0.55 |
| **RED**   | `mean_auc < 0.52` OR fewer than 3 folds computed |

**Thin-history fallback priority (from decision 8b):**

1. Ticker has ≥3 folds → use own model with own health band.
2. Ticker has 1-2 folds → try sector-cohort model. If cohort is GREEN, use it; score carries `source=sector_cohort` flag and the UI badges it AMBER.
3. Sector cohort also unavailable → fall back to ticker's single-fold model, force-label AMBER with tooltip "single-fold estimate."
4. No viable path → store `health=UNAVAILABLE`; UI renders no score, shows "—" in the column.

**Sector cohort definition:** use `pipeline/config/sector_concentration.json` — each sector (NIFTYIT, BANKNIFTY, NIFTYMETAL, NIFTYAUTO, NIFTYPHARMA, NIFTYENERGY, NIFTYFMCG, NIFTYPSUBANK) has a constituent list with weights. A ticker belongs to a cohort if it's a named constituent. Mid/small-caps not in any sector index fall into a `MIDCAP_GENERIC` cohort (built from MIDCPNIFTY + NIFTYNXT50 constituents). For the cohort model, we pool all constituents' feature vectors and labels, weighted by the inverse of their individual coverage (so the 50th-percentile-by-n constituent gets typical weight, not the 100-day-old IPO).

## 7. Storage schemas

### `pipeline/data/ticker_feature_models.json` (quarterly, ~2 KB × 215 = 430 KB)

```json
{
  "version": "1.0",
  "fitted_at": "2026-04-22T01:00:00+05:30",
  "universe_size": 215,
  "models": {
    "KAYNES": {
      "coefficients": {
        "sector_5d_return": 0.412,
        "sector_20d_return": 0.133,
        "ticker_rs_10d": -0.089,
        "ticker_3d_momentum": 0.205,
        "nifty_breadth_5d": 0.310,
        "regime_RISK-OFF": -0.245,
        "regime_NEUTRAL": 0.101,
        "...": "..."
      },
      "interactions": {
        "regime_NEUTRAL__x__trust_grade_ordinal": 0.180,
        "...": "..."
      },
      "standardization": {"sector_5d_return": {"mean": 0.003, "std": 0.021}, "...": "..."},
      "folds_auc": [0.52, 0.58, 0.61, 0.54],
      "mean_auc": 0.5625,
      "min_fold_auc": 0.52,
      "health": "GREEN",
      "n_train_days": 600,
      "source": "own",
      "fallback_sector": "NIFTYIT",
      "fitted_date": "2026-04-22"
    },
    "KOTAKBANK": {
      "source": "own",
      "health": "RED",
      "mean_auc": 0.49,
      "reason": "AUC below 0.52 threshold",
      "...": "..."
    },
    "TINY_IPO": {
      "source": "sector_cohort",
      "cohort": "NIFTYIT",
      "health": "AMBER",
      "coefficients": "...from cohort model..."
    }
  }
}
```

### `pipeline/data/attractiveness_scores.json` (latest snapshot, rewritten every 15 min, ~50 KB)

```json
{
  "updated_at": "2026-04-22T14:45:00+05:30",
  "scores": {
    "KAYNES": {
      "score": 67,
      "band": "AMBER",
      "source": "sector_cohort",
      "top_features": [
        {"name": "sector_5d_return", "contribution": 24, "value": 0.031},
        {"name": "ticker_rs_10d",    "contribution": 18, "value": 0.012},
        {"name": "regime_NEUTRAL",   "contribution": 15, "value": 1.0}
      ],
      "computed_at": "2026-04-22T14:45:00+05:30"
    },
    "...": "..."
  }
}
```

### `pipeline/data/attractiveness_snapshots.jsonl` (append-only history, one line per ticker per cycle)

```
{"ts":"2026-04-22T09:30:00+05:30","ticker":"KAYNES","score":62,"band":"AMBER","features":{...}}
{"ts":"2026-04-22T09:30:00+05:30","ticker":"PGEL","score":54,"band":"GREEN","features":{...}}
...
```

Rotated monthly to `snapshots/YYYY-MM.jsonl.gz` to keep append-only files manageable.

## 8. Scheduled-task wiring

**New task:** `AnkaFeatureScorerFit`

| Field | Value |
|-------|-------|
| Trigger | Sunday 01:00 IST weekly |
| Command | `python -m pipeline.feature_scorer.fit_universe` |
| Expected output | `pipeline/data/ticker_feature_models.json` |
| Tier | `warn` (important but not critical — the pipeline still functions without scores) |
| Grace multiplier | 2.0 (re-fit can run late without alarm) |
| Cadence class | `weekly` |

**Inventory entry** in `pipeline/config/anka_inventory.json`.

**Modified intraday task:** `AnkaIntraday####` (every 15-min cycle, 26x/day) — add a post-step invocation to `pipeline.feature_scorer.score_universe()`. Cheap (~1 sec per cycle for 215 tickers).

**Watchdog coverage:**
- `ticker_feature_models.json` freshness ≤ 8 days (weekly + grace).
- `attractiveness_scores.json` freshness ≤ 20 min (intraday grace).

## 9. UI surfaces

### Trading tab (new column)

Between the existing `Score` column and `Horizon` column, add:

| Header | `Attractiveness` |
|--------|-------------------|
| Cell | `score` colored by `band` (GREEN=gold, AMBER=amber dot, RED/UNAVAILABLE=em-dash). Right-aligned, monospace. |
| Tooltip | Top-3 contributing features as bulleted list with signed contribution ("+24 from sector_5d_return"). Footer: "model health: GREEN — mean AUC 0.58 across 4 folds". |
| Sort | Primary: conviction tier (HIGH > MEDIUM > LOW > PROVISIONAL > NONE). Secondary: Attractiveness desc within tier. |

### Positions tab (badge)

Each open position row gets a small badge next to the P&L column:

```
[Attract 67 ↑]   — GREEN, score rose from 62 at open
[Attract 42 ↓]   — AMBER, score fell from 67 at open
```

Clicking the badge opens a mini-sparkline of the score's trajectory since position open (pulled from snapshots file).

### TA tab (feature contribution panel)

When a ticker is selected, render below the main chart:

```
┌─ Feature Contributions — KAYNES (updated 14:45) ─┐
│                                                   │
│  +24  ████████████ sector_5d_return  (+3.1%)    │
│  +18  ██████████   ticker_rs_10d      (+1.2%)   │
│  +15  █████████    regime_NEUTRAL                │
│  +10  ██████       nifty_breadth_5d   (62%)     │
│  +0   —            pcr_z_score       (n/a today)│
│  -8   ██           ticker_3d_momentum (-0.5%)   │
│                                                   │
│  Model health: AMBER (sector cohort, 2 folds)   │
└───────────────────────────────────────────────────┘
```

## 10. Downstream integration (explicit non-changes)

The Attractiveness score **does not** modify:
- `entry_score` (stays as-is — episode-based + news modifier + trust modifier).
- `conviction` tier (stays as-is — episode-count-based).
- Any stop logic.
- Any signal-generation gating.

The Attractiveness score **does** affect:
- **Sort order** within the Trading tab (after conviction band tie-break).
- The Positions tab badge (pure display).
- The TA tab panel (pure display).

This deliberate decoupling means the Attractiveness layer can be turned off (`config["feature_scorer_enabled"] = False`) without affecting any trade decision the system produces. It's a ranking and visualization layer, not a gate.

## 11. Testing strategy

**Unit tests:**
- Feature extraction: each feature produces expected values on a toy fixture.
- Label generator: deterministic output for a known price sequence (uses the existing `check_signal_status`).
- Model fit: AUC ≥ random on a synthetic dataset where the true function is known.
- Walk-forward: folds cover the expected date ranges; mean AUC computed correctly.
- Health gating: every boundary condition (AUC at exactly 0.55, 0.52, thin history).
- Fallback: priority order confirmed with fixtures (own → cohort → single-fold → UNAVAILABLE).

**Integration tests:**
- Fit universe on a 5-ticker fixture → produces a valid models JSON.
- Score universe against cached models → produces valid scores JSON.
- Scheduled-task wiring: `AnkaFeatureScorerFit` runs start-to-finish on a fixture.

**Backtest:**
- Full-universe fit against 5y history. Report: health-band distribution, mean AUC distribution, ticker count per fallback source. Written to `backtest_results/feature_scorer_fit_<date>.csv`.
- Per-ticker attribution: did GREEN-model tickers in the last 60d produce more winning simulated positions than AMBER/RED? That's the validity check for the whole scorer.

**Regression tests:**
- Turning the scorer off → Trading tab renders cleanly without the column.
- Corrupt models file → attractiveness column shows "—" across all rows without breaking the page.

## 12. Scope boundary — v1 vs v2

**In scope for v1:**
- All 8 brainstormed decisions implemented.
- 10 fixed features + 3 interaction terms.
- Full F&O universe quarterly fit + 15-min intraday apply.
- 3 UI surfaces (Trading column, Positions badge, TA panel).
- Sector-cohort fallback.
- `AnkaFeatureScorerFit` scheduled task.

**Deferred to v2 (separate spec, not this one):**
- L1-regularized per-ticker feature selection from a wider candidate pool.
- GBM (LightGBM) as an alternative model for comparison.
- More feature candidates: FII net flow, VIX, gap size, event-proximity flag.
- Feature-importance-weighted hyperparameter sweep.
- Automated weekly re-tuning of coefficients (currently quarterly).
- Alerts when a position's attractiveness decays rapidly (e.g., 67 → 42 within a session).

**Out-of-scope entirely (philosophical):**
- Using Attractiveness as a trade gate. It ranks; it does not block.
- Using Attractiveness to size positions. Sizing stays with existing spread-stats / trust / news logic.
- Reinforcement learning or online updating. Quarterly cadence is the rhythm; no continual learning.

## 13. Open questions for the planner (not the brainstormer)

These are implementation questions that the plan should answer but don't require a design decision:

1. How does `feature_scorer.fit_universe` handle tickers not in `india_historical/indices/` for sector data? (Likely answer: sector-cohort fallback immediately.)
2. How are intraday sector index bars fetched — Kite or EODHD? (Existing Phase C v5 code has the answer.)
3. Is there a need for a `config["feature_scorer_config"]` block for thresholds (win_pct, AUC bands, n_folds_min), or are they hardcoded constants with module docstrings?
4. Migration: do we commit the first `ticker_feature_models.json` into the repo, or let the first Sunday run produce it?

## 14. Success criteria

At rollout, the Feature Coincidence Scorer is considered successful if:

1. **Coverage:** ≥70% of the F&O universe has a GREEN or AMBER model (not RED/UNAVAILABLE).
2. **Signal quality:** over the last 60 days of forward data, GREEN-model tickers chosen by score ≥60 produced winning simulated positions at a rate ≥5 percentage points above base rate. (Base rate ≈ 35% for 1.5% threshold in Indian F&O.)
3. **Latency:** intraday scoring completes in <5 seconds; never blocks the 15-min scheduled cycle.
4. **Storage:** `ticker_feature_models.json` < 1 MB; snapshot files rotate cleanly to monthly archives.
5. **UX:** trader reports that the Positions-tab attractiveness badge surfaces at least one useful "should I cut this" moment per week.

## 15. Appendix — rejected alternatives

Recorded so future-us doesn't re-litigate:

- **LightGBM as v1 model:** rejected because interpretability matters more than marginal AUC gains on thin data.
- **Per-ticker L1 feature selection in v1:** rejected to ship faster; deferred to v2 contingent on v1 AUC distribution signal.
- **Score as a gate (not just a rank):** rejected; would reduce trade frequency on days with broadly weak features, which is not behavior we've sanctioned yet.
- **EOD-only scoring:** rejected; loses the "watching with interest during the day" intent that motivated the spec.
- **Expanding-window validation:** rejected; Indian markets changed structurally post-COVID + rate cycle; stationarity assumption is weak.

## 16. Next steps

1. **User review** — read this spec, flag anything unclear or misaligned before we proceed.
2. **Writing-plans** — once the spec is approved, invoke `superpowers:writing-plans` to produce an executable implementation plan broken into bite-sized tasks.
3. **Execution** — via `superpowers:subagent-driven-development` once the plan is written.

---

*End of spec.*
