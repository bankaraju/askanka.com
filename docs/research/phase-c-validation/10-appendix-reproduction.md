# Appendix — Reproduction

This document and its ledgers are reproducible from a clean clone of the repo at the pinned commits. The only non-reproducible dependencies are (1) Kite API historical responses, which are immutable for past sessions and (2) NSE bhavcopy archives, which are also immutable.

## Prerequisites

- Python 3.11+ (the repo's pinned interpreter).
- All package requirements from `pipeline/requirements.txt` (pandas, numpy, scipy, matplotlib, pyarrow, kiteconnect).
- A valid Kite API session — `KITE_API_KEY` and `KITE_ACCESS_TOKEN` environment variables, or an active session via `pipeline.kite_client`. The daily-bar fetcher can use any Anka session that has historical-data access.
- Network access to `nsearchives.nseindia.com` for the PCR backfill.

No proprietary data or vendor feeds other than Kite and NSE's public archive are required.

## Pinned commits

| layer | commit | message |
|---|---|---|
| bhavcopy PCR fetcher | `09e76c1` | feat(phase_c_backtest): historical per-stock PCR via NSE F&O bhavcopy |
| empty-bars guard | `e712785` | fix(phase_c_backtest): skip empty-bar symbols in profile training |
| orchestrator | `f237a9e` | fix(phase-c-bt): regime backfill lookback + label default + schema normalisation |
| run_backtest entry | `73ae546` | research(phase-c): run_backtest — orchestrator entrypoint |

Check out the tip of the Phase C feature branch (`feat/dashboard-restructure` at the time of writing, or whichever branch has merged `09e76c1`) to reproduce.

## Step-by-step

### 1. PCR backfill (one-time, ~5 min)

```bash
cd <repo-root>
python -c "
from pipeline.research.phase_c_backtest import bhavcopy
import logging; logging.basicConfig(level=logging.INFO)
out = bhavcopy.backfill('2024-10-01', '2026-04-20', sleep_s=0.3)
print(f'done: {len(out)} days')
"
```

Produces ~381 parquet files under `pipeline/data/research/phase_c/pcr_history/`. The 0.3s sleep throttle stays well inside NSE's rate-limit budget. Holidays (~30 missing days) are skipped and logged, not raised.

### 2. Daily-bar cache warm-up (one-time per symbol, ~1 min for 15 symbols)

```bash
python -c "
from pipeline.research.phase_c_backtest import fetcher
for sym in ['RELIANCE', 'HDFCBANK', 'TCS', 'INFY', 'ICICIBANK',
            'SBIN', 'AXISBANK', 'KOTAKBANK', 'ITC', 'LT',
            'BAJFINANCE', 'MARUTI', 'WIPRO', 'HCLTECH']:
    df = fetcher.fetch_daily(sym, days=1500)
    print(f'{sym}: {len(df)} rows')
"
```

Writes parquet files under `pipeline/data/research/phase_c/daily_bars/`. Skip symbols that return 0 rows (delisted / merged) — the profile trainer handles them via the empty-bars guard.

### 3. Run the backtest (~2–3 min)

```bash
python -m pipeline.research.phase_c_backtest.run_backtest \
  --in-sample-start 2024-10-01 \
  --in-sample-end 2026-03-31 \
  --forward-start 2026-04-01 \
  --forward-end 2026-04-20 \
  --symbols RELIANCE HDFCBANK TCS INFY ICICIBANK SBIN AXISBANK \
            KOTAKBANK ITC LT BAJFINANCE MARUTI WIPRO HCLTECH \
  --trade-label OPPORTUNITY
```

Writes to `docs/research/phase-c-validation/`:

- `in_sample_ledger.parquet` — 630 rows × 14 cols
- `forward_ledger.parquet` — 21 rows × 14 cols
- `in_sample_equity.png` and `forward_equity.png`
- `04-results-in-sample.md`, `05-results-forward.md`, `07-verdict.md`

Expected wall time on a Windows laptop: ~2 min for the in-sample leg (14 symbols × 378 days × 4 classifier calls per day), ~1 min for the forward leg (14 symbols × 20 sessions × ~3 1-min fetches per signal). Memory peak: ~400 MB.

### 4. Variant: degraded run (no PCR)

```bash
python -m pipeline.research.phase_c_backtest.run_backtest \
  --in-sample-start 2024-10-01 --in-sample-end 2026-03-31 \
  --forward-start 2026-04-01 --forward-end 2026-04-20 \
  --symbols <same list> \
  --trade-label POSSIBLE_OPPORTUNITY
```

Produces the comparison ledgers (1,807 / 48 trades). Swap file names if preserving both variants side-by-side.

### 5. Reproduce the robustness tables

```bash
python - <<'PY'
import pandas as pd
from pipeline.research.phase_c_backtest import robustness, stats as sm
inl = pd.read_parquet('docs/research/phase-c-validation/in_sample_ledger.parquet')
print(robustness.slippage_sweep(inl, [3.0, 5.0, 7.0, 10.0]).to_string(index=False))
print(robustness.top_n_sweep(inl, [1, 3, 5, 10, 15]).to_string(index=False))
rets = (inl.pnl_net_inr / inl.notional_inr).to_numpy()
pt, lo, hi = sm.bootstrap_sharpe_ci(rets, n_resamples=10_000, alpha=0.01, seed=7)
print(f'Sharpe pt={pt:.4f} 99%CI=[{lo:.4f}, {hi:.4f}]')
PY
```

All numbers in section `06-robustness.md` come out of that snippet.

## Live shadow leg (F3)

The `live_paper` module runs the same classifier over live production signals and persists them as paper-trade entries for forward validation. To bring it up:

1. Add a daily scheduled task that runs `live_paper.record_opens(...)` at 09:25 IST (right after `morning_scan.py`'s Phase C pass writes today's signal list).
2. Add a 14:30 IST task that runs `live_paper.close_at_1430(date, exit_prices)` — exit prices come from `pipeline/data/daily_prices.json` which is written intraday by the 14:30 scheduled task already in the inventory.
3. Inventory entry in `pipeline/config/anka_inventory.json`:
   ```json
   {
     "name": "AnkaPhaseCLiveShadow",
     "tier": "info",
     "cadence_class": "intraday",
     "expected_files": [
       "pipeline/data/research/phase_c/live_paper_ledger.json"
     ],
     "grace_multiplier": 1.5
   }
   ```

The ledger is a flat JSON file under `pipeline/data/research/phase_c/live_paper_ledger.json`. After ~100 trades (≈ 3–5 months at current signal density) the forward binomial test becomes statistically decisive at the Bonferroni-corrected α = 0.01.

## Known-good output

The run captured in this document ended with the verdict string:

```
{'H1_OPPORTUNITY': {'passes': False,
 'reason': 'in-sample Sharpe CI lower bound -3.59 <= 1.0; forward Sharpe CI lower bound -2.02 <= 0.5;
            hit rate (in 43.49%, fwd 76.19%) below 55%; binomial p (in 0.0012, fwd 0.0266) > 0.01;
            drawdown (in 58.85%, fwd 1.42%) > 20%; only 0/4 regimes passed (need >=3)'}}
```

If a reviewer reproduces this run and gets materially different numbers (say a sign flip on the in-sample Sharpe point estimate), the likely cause is Kite historical-data revisions on individual symbols between runs. Re-fetching the daily cache (`rm pipeline/data/research/phase_c/daily_bars/*.parquet`) and re-running should reconcile.
