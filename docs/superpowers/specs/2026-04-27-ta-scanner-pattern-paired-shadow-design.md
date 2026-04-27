# Scanner (TA) Pattern Engine + Paired-Shadow Ledger — Design

**Date:** 2026-04-27
**Status:** Design (pre-implementation-plan)
**Substrate:** Daily F&O-universe candlestick + indicator pattern detection, with per-`(ticker × pattern)` historical occurrence stats, feeding a paired (futures + ATM monthly options) forward-only OOS shadow ledger for the daily Top-10.
**Type:** Forward-only OOS descriptive forensic — **no edge claim**, no hypothesis-registry entry, no kill-switch trigger, no §0-16 compliance pass for v1.

---

## 1. Motivation

The Scanner (TA) tab today consumes only fingerprint-pattern signals from `pipeline/terminal/api/candidates.py`. It does **not** consume the existing logistic-regression TA scorer (`pipeline/ta_scorer/`, daily 16:00 IST `AnkaTAScorerScore`), which produces a 0–100 score per ticker but has no direction field, no per-prediction confidence, and is interpretable only at the model level (mean AUC, fold AUC). The current screen also displays a column labelled "80% CI" that has no statistical-CI semantics — it is the band threshold for `score >= 80 = VERY_HIGH`, mislabelled as a confidence interval.

Bharat (2026-04-27): "we are saying there are many moves that happen and it is all captured in the TA scanner — it is not saying anything about what is the large move now ... lets try Bollinger bands, hammer, bullish engulfing ... we pick momentum, trending and structure review of the universe and that would then give us buy/sell options in options and in futures." Plus: "when the days are neutral we need more ideas and when the days are not neutral I think we have spread trades that seem to be promising money all the time."

The replacement design is **pattern-occurrence based**: every day, scan the F&O universe for stocks currently in a recognized pattern (hammer, engulfing, BB breakout, MACD cross, etc.), look up that `(ticker × pattern)` cell's historical occurrence stats, rank by `z_score × log(1 + n) × |mean_pnl|`, surface today's Top-10 with direction inferred from the pattern type. Each Top-10 row fires a paired (futures + ATM monthly options) shadow trade, mirroring the Phase C paired-shadow architecture (`docs/superpowers/specs/2026-04-27-phase-c-options-paired-shadow-design.md`).

Why this is better than the logistic scorer for the Scanner-tab use case:
- **Direction is intrinsic to the pattern** (bullish hammer → LONG, bearish engulfing → SHORT). The logistic scorer is a probability with no direction.
- **Confidence is interpretable**: `n=156 occurrences, won 62%, z=3.0` — that's the "fortified by stats" Bharat asked for, replacing the broken 80% CI.
- **Productivity tool framing**: the screen does the work a trader would otherwise do by manually flipping through 213 charts. Decision-support, not black box.
- **Regime-conditional value**: most useful in NEUTRAL regimes when spread trades go quiet. The Scanner fills that gap.
- **Cross-source comparison**: the paired-shadow ledger gives us a second (futures, options) realized-P&L stream alongside Phase C's, enabling per-source edge comparison.

**Backtesting framing (explicit, per Bharat 2026-04-27):** "backtesting here would mean the occurrences having played out positively or negatively." This is descriptive historical-occurrence accounting, not academic hypothesis testing. We compute: across all historical fires of pattern P on ticker T, what fraction moved in the predicted direction by ≥0.8% on T+1 open-to-close. We do **not** fit a model, we do **not** claim edge, we do **not** appeal to §0-16 compliance. The shadow ledger (Layer 5) does the real validation forward.

## 2. Goal

Daily, deterministically, by 16:30 IST after EOD bars lock:

1. Detect 12 candlestick / structural / momentum patterns across the full F&O universe.
2. Look up the `(ticker × pattern)` historical occurrence cell (computed weekly from 5-year daily bars).
3. Rank today's actual fires by composite score, emit Top-10 to a Scanner-tab data feed with direction, `n`, win-rate, z-score, mean P&L, fold-stability ratio.
4. For each Top-10 row, fire a paired (futures + ATM monthly options) forward-only OOS shadow trade with entry at next-session 09:25 IST and mechanical close at next-session 15:30 IST.
5. Accumulate paired realized P&L for ≥30 trades (descriptive readout, ~1 week — ~10 fires/day) and ≥100 (statistical readout, ~3 weeks).

**Not in goal:** propose a tradeable strategy, fire any kill switch, append to `hypothesis-registry.jsonl`, complete a §0-16 compliance pass. v1 is descriptive measurement.

## 3. Scope

### In scope (v1)

- A new `pipeline/pattern_scanner/` package with: `detect.py` (daily scan), `stats.py` (weekly historical fit + walk-forward fold stability), `rank.py` (Top-10 composite ranker), `runner.py` (orchestration).
- 12 patterns: 4 bullish candles + 4 bearish candles + 2 BB structures + 2 MACD events.
- Daily artifact: `pipeline/data/scanner/pattern_signals_today.json` — what fires today, with direction + historical stats.
- Daily audit artifact: `pipeline/data/scanner/pattern_signals_history.parquet` — append-only audit log of every daily emission (provenance, regime tag at fire-time, frozen stats snapshot). Watchdog covers freshness.
- Weekly artifact: `pipeline/data/scanner/pattern_stats.parquet` — per `(ticker × pattern)` historical occurrence cells with walk-forward fold-stability columns.
- Scanner UI rewire: `pipeline/terminal/static/js/pages/scanner.js` reads the new daily artifact, renders Top-10 table with direction badge + stat columns, **and** the existing logistic-scorer column survives as an annotation (per Q1=B).
- Click-to-chart restored on every ticker (regression in task #269).
- Paired shadow sidecar `pipeline/scanner_paired_shadow.py` with `cmd_open` (09:25 IST next session) and `cmd_close` (15:30 IST same session), reusing Phase C's helper modules (`options_atm_helpers`, `options_quote`, `options_greeks`, `cost_model`).
- New scheduled tasks: `AnkaPatternScannerScan` (daily 16:30 IST), `AnkaPatternScannerFit` (Sunday 02:00 IST), `AnkaScannerPairedOpen` (next-day 09:25 IST), `AnkaScannerPairedClose` (next-day 15:30 IST).
- Reporting: `pipeline/pattern_scanner_report.py` writes a Markdown one-pager after each close, stratified by `is_expiry_day`, regime, pattern, direction.
- New endpoint `/api/scanner/pattern-signals` returning today's Top-10 + cumulative paired-shadow stats.

### Out of scope (deferred)

- Sunsetting the logistic-regression TA scorer. Survives as an annotation column. Decision deferred 30 days; if the score column adds zero predictive value to Top-10 ranking by Y2026-05-27, then sunset.
- Pattern-specific win thresholds (uses fixed 0.8% in v1; ATR-scaled in v2 if data warrants).
- Multi-horizon stats (v1 is T+1 open-to-close only; 3d / 5d may follow in v2).
- §0-16 compliance pass (deferred — only if shadow-ledger forward-OOS confirms the pattern set).
- Permutation-null testing (descriptive z-score against H0=50/50 only in v1).
- Multi-leg options structures, weekly options, position sizes other than 1 lot (inherited constraints from Phase C spec).

## 4. Decisions locked during brainstorming

| # | Decision | Value |
|---|---|---|
| Q1 | Relationship to existing logistic-regression TA scorer | **B — keep both, side-by-side**. Pattern scanner is the primary Scanner-tab driver. Logistic score becomes an annotation column. 30-day stay-of-execution; sunset if it adds no value. |
| Q2 | Backtest + live-shadow return horizon | **A — open-to-close intraday on T+1**. Pattern fires at today's close; backtest measures T+1 open→T+1 close; live shadow opens 09:25 next session, closes 15:30 same session. Backtest and live measure identical bars. |
| Q3 | Pattern set for v1 | **A — Curated 12** (4 bullish candles + 4 bearish candles + 2 BB structures + 2 MACD events). Full list in §9. |
| Q4 | Backtest rigor for v1 | **A — Lightweight forensic** with walk-forward fold-stability check. Descriptive only; no §0-16 pass. |
| - | Win threshold | **±0.8% T+1 open-to-close** (positive for bullish patterns, negative for bearish). Same as existing TA scorer; consistent semantics; comfortably above options round-trip cost. |
| - | Direction inference | **From pattern type**. Bullish patterns → LONG signal → ATM CE on options leg. Bearish patterns → SHORT signal → ATM PE on options leg. No inference needed. |
| - | Top-N rank rule | **Top 10**, ranked by composite `score = z_score × log(1 + n_occurrences) × abs(mean_pnl_pct)`. Take top-10 regardless of direction (don't force LONG/SHORT balance). |
| - | Minimum N for ranking eligibility | **n_occurrences ≥ 30**. Below that, z-score is unreliable. The cell may still appear on screen as "INSUFFICIENT_N" if today is its first/recent fire — but it doesn't qualify for the Top-10. |
| - | Health gate | **Fold-stability ratio ≥ 0.5**. If win-rate ranges across folds by more than 50% of the mean, the cell is flagged unstable and excluded from Top-10 ranking. |
| - | Universe | **Full F&O universe** (~213 stocks, source: `pipeline/data/fno_historical/` per the canonical-bar validator). |
| - | Architecture | **Sidecar paired-shadow** mirroring Phase C spec; reuses Phase C helper modules. |
| - | Hold horizon for paired shadow | **Same-session intraday on T+1 (09:25 → 15:30 IST)**. Paper engine exempt from 14:30 cutoff (per memory `feedback_1430_ist_signal_cutoff`). |

## 5. Architecture (5 layers)

```
Layer 1 — DETECTION                    Layer 2 — STATS (weekly)
─────────────────────                  ──────────────────────────
detect.py                              stats.py
  daily_scan(date)                       fit_universe()
    for each ticker:                       for each (ticker, pattern):
      load daily bars                        compute 5y occurrences
      apply 12 pattern detectors             measure T+1 open→close return
      output today's flags                   walk-forward 4 folds
                                             aggregate: n, win_rate, z, fold_stability
                                           write → pattern_stats.parquet


Layer 3 — RANK + EMIT (daily, 16:30 IST)
────────────────────────────────────
rank.py / runner.py
  load today's flags from L1
  join pattern_stats.parquet from L2
  filter: n >= 30 AND fold_stability >= 0.5
  rank by composite score
  take Top-10
  write → pattern_signals_today.json


Layer 4 — UI                                      Layer 5 — PAIRED SHADOW (sidecar, like Phase C)
─────                                             ──────────────────────────────────────────────
scanner.js (rewired)                              scanner_paired_shadow.py
  GET /api/scanner/pattern-signals                  cmd_open  ← 09:25 IST T+1
  render Top-10 table + click-to-chart                for each row in pattern_signals_today.json:
                                                        open futures shadow leg
                                                        open options shadow leg (try/except)
                                                          - reuses options_atm_helpers, options_quote,
                                                            options_greeks, cost_model from Phase C spec
                                                        write → live_paper_scanner_options_ledger.json
                                                  cmd_close ← 15:30 IST T+1
                                                    fetch quotes, compute pnl, mark CLOSED
```

**Decoupling guarantees** (mirroring Phase C):
- Sidecar exceptions are caught at the call site. Futures leg unaffected if options leg fails.
- Paired ledger is a separate artifact file; joins to a futures-side ledger by `signal_id`.
- Paper engine — exempt from the 14:30 IST live-engine cutoff.

## 6. Components & contracts

### 6.1 `pipeline/pattern_scanner/detect.py`

```python
def daily_scan(date: date,
               universe: list[str],
               bars_loader: Callable) -> list[PatternFlag]:
    """
    For each ticker, load daily bars up to and including `date`,
    apply 12 pattern detectors, return flags currently active at close
    of `date`. Pure pandas-ta calls; vectorized over universe.
    """

@dataclass
class PatternFlag:
    date: date
    ticker: str
    pattern_id: str           # one of the 12 — see §9
    direction: Literal["LONG", "SHORT"]
    raw_features: dict        # debug — raw indicator values at fire time
```

Pandas-ta provides every detector we need natively. No custom heuristics in v1.

### 6.2 `pipeline/pattern_scanner/stats.py`

```python
def fit_universe(start: date, end: date,
                 universe: list[str],
                 bars_loader: Callable,
                 win_threshold: float = 0.008) -> DataFrame:
    """
    For each (ticker, pattern), find every historical fire over [start, end],
    compute T+1 open-to-close return, aggregate.
    Walk-forward: split [start, end] into 4 contiguous folds, compute per-fold
    win-rate, return both pooled stats and fold-stability ratio.
    Writes pattern_stats.parquet with one row per (ticker, pattern).
    """

# Output schema (parquet):
#   ticker (str)
#   pattern_id (str)
#   direction (str)               # LONG for bullish, SHORT for bearish
#   n_occurrences (int)
#   wins (int)                    # |return| >= win_threshold in pattern direction
#   losses (int)
#   win_rate (float)
#   mean_pnl_pct (float)          # cost-adjusted via cost_model
#   stddev_pnl_pct (float)
#   z_score (float)               # (win_rate - 0.5) / sqrt(0.25 / n)
#   fold_win_rates (list[float])  # 4 folds — for stability check
#   fold_stability (float)        # 1 - (max(fold_wr) - min(fold_wr)) / mean(fold_wr)
#   last_seen (date)
#   first_seen (date)
#   computed_at (timestamp)
```

The cost model (`pipeline/research/phase_c_v5/cost_model.py`) is applied to every historical fire's P&L before aggregation. Mean P&L is net of slippage + STT + stamp.

### 6.3 `pipeline/pattern_scanner/rank.py`

```python
def rank_today(flags: list[PatternFlag],
               stats: DataFrame,
               min_n: int = 30,
               min_fold_stability: float = 0.5,
               top_n: int = 10) -> list[ScannerSignal]:
    """
    Join today's flags against historical stats.
    Filter: n_occurrences >= min_n AND fold_stability >= min_fold_stability.
    Composite score: z_score * log1p(n_occurrences) * abs(mean_pnl_pct).
    Return top_n by composite score.
    """

@dataclass
class ScannerSignal:
    signal_id: str           # {date}_{ticker}_{pattern_id}
    date: date
    ticker: str
    pattern_id: str
    direction: Literal["LONG", "SHORT"]
    composite_score: float
    n_occurrences: int
    win_rate: float
    z_score: float
    mean_pnl_pct: float
    fold_stability: float
    last_seen: date
```

### 6.4 `pipeline/pattern_scanner/runner.py`

Orchestrator. Loads today's bars, calls `detect.daily_scan`, joins stats, calls `rank.rank_today`, writes `pattern_signals_today.json`. Invoked daily 16:30 IST via `AnkaPatternScannerScan`.

### 6.5 `pipeline/scanner_paired_shadow.py`

Sidecar mirroring `phase_c_options_shadow.py` from the Phase C spec. Same contracts:

```python
def open_options_pair(scanner_signal: ScannerSignal) -> dict:
    """
    Called from AnkaScannerPairedOpen at 09:25 IST next session.
    Opens futures shadow row + paired options row (try/except).
    Returns options ledger row.
    """

def close_options_pair(signal_id: str) -> dict:
    """
    Called from AnkaScannerPairedClose at 15:30 IST next session.
    Fetches close mid, computes pnl, updates row to CLOSED.
    """
```

Reuses, no duplication: `options_atm_helpers.resolve_atm_strike`, `options_atm_helpers.resolve_nearest_monthly_expiry`, `options_quote.fetch_mid_with_liquidity_check`, `options_greeks.backsolve_iv`, `options_greeks.compute_greeks`, `cost_model.apply_to_pnl(instrument='option')`.

### 6.6 `pipeline/terminal/static/js/pages/scanner.js` (rewire)

- New API call: `GET /api/scanner/pattern-signals`.
- Render a single "Today's Top-10 Patterns" table:
  - Columns: `Direction badge | Ticker | Pattern | n | Win% | Z-score | μ P&L | Fold-stability | Last seen`
  - Optional annotation column: logistic TA score (from `/api/ta_attractiveness`) — small, low-emphasis.
- Restore click-to-chart: each ticker cell wraps the value in a click handler that navigates to `#chart/{ticker}` (the existing chart route). Was working before, gone now.
- Empty state when fewer than 10 cells qualify: render the count we have and a "+ N more below action threshold (n<30 / unstable folds) — hidden" footer (consistent with the Regime-tab actionable-row design rule).

### 6.7 `pipeline/terminal/api/scanner.py` (new endpoint)

```python
@router.get("/api/scanner/pattern-signals")
def get_pattern_signals():
    """
    Returns the full pattern_signals_today.json contents merged with a
    cumulative_paired_shadow rollup computed from the close ledgers:

      {
        # all keys from pattern_signals_today.json (§7.2):
        as_of: "2026-04-27T16:30:00+05:30",
        universe_size: 213,
        today_flags_total: 47,
        qualified_count: 18,
        below_threshold_count: 29,
        top_10: [ScannerSignal, ...],

        # added by the endpoint:
        cumulative_paired_shadow: {
          n_closed: int,
          win_rate: float,
          mean_options_pnl_pct: float,
          mean_futures_pnl_pct: float,
          mean_paired_diff: float,
        }
      }
    """
```

## 7. Schemas

### 7.1 `pipeline/data/scanner/pattern_stats.parquet` (Layer 2 output, weekly fit)

One row per `(ticker × pattern)`. See §6.2 for full column list. ~2,556 rows total at full universe coverage (213 × 12).

### 7.2 `pipeline/data/scanner/pattern_signals_today.json` (Layer 3 output, daily scan)

```jsonc
{
  "as_of": "2026-04-27T16:30:00+05:30",
  "universe_size": 213,
  "today_flags_total": 47,
  "qualified_count": 18,            // n>=30 AND fold_stability>=0.5
  "below_threshold_count": 29,
  "top_10": [
    {
      "signal_id": "2026-04-27_BPCL_BULLISH_HAMMER",
      "date": "2026-04-27",
      "ticker": "BPCL",
      "pattern_id": "BULLISH_HAMMER",
      "direction": "LONG",
      "composite_score": 4.27,
      "n_occurrences": 156,
      "win_rate": 0.62,
      "z_score": 3.0,
      "mean_pnl_pct": 0.012,
      "fold_stability": 0.78,
      "last_seen": "2026-03-12"
    },
    ...
  ]
}
```

### 7.3 `pipeline/data/research/scanner/live_paper_scanner_options_ledger.json` (Layer 5 paired-shadow ledger)

Identical row schema to the Phase C paired-shadow ledger (`docs/superpowers/specs/2026-04-27-phase-c-options-paired-shadow-design.md` §7), with three additions:

```jsonc
{
  // ... all Phase C paired-shadow fields ...

  // Scanner-specific provenance
  "pattern_id": "BULLISH_HAMMER",
  "scanner_composite_score_at_entry": 4.27,
  "scanner_z_score_at_entry": 3.0
}
```

`signal_id` joins to a sibling futures-only ledger `live_paper_scanner_futures_ledger.json` (created the same way as the Phase C futures ledger).

## 8. Data flow

### 8.1 Weekly fit (Sunday 02:00 IST)

`AnkaPatternScannerFit` invokes `pattern_scanner.stats.fit_universe(start=today-5y, end=today)`. Walk-forward 4 folds; writes `pattern_stats.parquet` atomically.

### 8.2 Daily scan (16:30 IST, after EOD bars lock)

1. `AnkaPatternScannerScan` invokes `runner.main(date=today)`.
2. `detect.daily_scan(today)` → list of active flags.
3. Join against `pattern_stats.parquet`.
4. `rank.rank_today(flags, stats)` → Top-10.
5. Write `pattern_signals_today.json`.
6. Write a row to `pipeline/data/scanner/pattern_signals_history.parquet` for audit.

### 8.3 Paired-shadow open (T+1 09:25 IST)

1. `AnkaScannerPairedOpen` reads `pattern_signals_today.json` from yesterday.
2. For each Top-10 row: open futures shadow leg → write `live_paper_scanner_futures_ledger.json` row.
3. Sidecar `open_options_pair` (try/except) opens paired options leg → write `live_paper_scanner_options_ledger.json` row. Liquidity floor + skip semantics are inherited from the Phase C paired-shadow spec.

### 8.4 Paired-shadow close (T+1 15:30 IST)

1. `AnkaScannerPairedClose` closes futures rows.
2. Sidecar `close_options_pair` for each open options row.
3. Update statuses to CLOSED.
4. Write reporting one-pager via `pattern_scanner_report.py`.

## 9. The 12 patterns (v1)

All detectable via pandas-ta with no custom heuristics. Each row below is `pattern_id | direction | pandas-ta call | semantic`.

| # | Pattern ID | Dir | pandas-ta | Semantic |
|---|---|---|---|---|
| 1 | `BULLISH_HAMMER` | LONG | `cdl_pattern("hammer")` | Reversal-up after downtrend |
| 2 | `BULLISH_ENGULFING` | LONG | `cdl_pattern("engulfing")` (positive sign) | Strong reversal-up |
| 3 | `MORNING_STAR` | LONG | `cdl_pattern("morningstar")` | 3-candle reversal-up |
| 4 | `PIERCING_LINE` | LONG | `cdl_pattern("piercing")` | 2-candle reversal-up |
| 5 | `SHOOTING_STAR` | SHORT | `cdl_pattern("shootingstar")` | Reversal-down after uptrend |
| 6 | `BEARISH_ENGULFING` | SHORT | `cdl_pattern("engulfing")` (negative sign) | Strong reversal-down |
| 7 | `EVENING_STAR` | SHORT | `cdl_pattern("eveningstar")` | 3-candle reversal-down |
| 8 | `DARK_CLOUD_COVER` | SHORT | `cdl_pattern("darkcloudcover")` | 2-candle reversal-down |
| 9 | `BB_BREAKOUT` | LONG | `bbands` + custom: close > upper after squeeze (band width < 20-day avg × 0.7) | Volatility-expansion-up |
| 10 | `BB_BREAKDOWN` | SHORT | same as 9, close < lower after squeeze | Volatility-expansion-down |
| 11 | `MACD_BULL_CROSS` | LONG | `macd` + custom: line crosses signal from below | Momentum reversal-up |
| 12 | `MACD_BEAR_CROSS` | SHORT | `macd` + custom: line crosses signal from above | Momentum reversal-down |

The two BB structures and two MACD events use pandas-ta indicators + a thin custom layer (~5 lines each) for the cross/breakout detection. Everything else is a single pandas-ta call.

## 10. Backtest methodology (Layer 2)

**Per Bharat (2026-04-27):** "backtesting here would mean the occurrences having played out positively or negatively." Treated as descriptive historical-occurrence accounting, **not academic hypothesis testing**.

**For each `(ticker, pattern)` cell**, over `[today − 5y, today]`:

1. Apply the pattern detector to historical daily bars; collect every fire date.
2. For each fire date `d`, compute `T+1 open-to-close return = (close[d+1] − open[d+1]) / open[d+1]`. Apply cost model (15bps options round-trip + STT + stamp) to convert gross to net.
3. Tag as **win** if (`direction == LONG` AND `net_return ≥ +0.008`) OR (`direction == SHORT` AND `net_return ≤ −0.008`); else **loss**.
4. Compute **per-trade P&L**: for LONG, `pnl = net_return`; for SHORT, `pnl = −net_return` (so a 1% stock drop on a SHORT pattern is a +1% trade P&L). Then aggregate: `n_occurrences`, `wins`, `losses`, `win_rate = wins / n`, `mean_pnl_pct = mean of per-trade P&L`, `stddev_pnl_pct`.
5. Z-score: `z = (win_rate − 0.5) / sqrt(0.25 / n)`. This tests H0 = "pattern is no better than coin-flip." Z > 2 = statistically significant; Z > 3 = strong.
6. **Walk-forward fold stability**: split the 5-year history into 4 contiguous folds (~15 months each). Compute `win_rate` per fold. Report `fold_stability = 1 − (max(fold_wr) − min(fold_wr)) / max(0.01, mean(fold_wr))`. Cells with `fold_stability < 0.5` (i.e., >50% range across folds) are flagged unstable and **excluded from Top-10 ranking**.

**What this is not:**
- Not an out-of-sample predictive validation.
- Not a §0-16 compliance pass.
- Not a permutation null (z-score is against H0=50/50; a permutation null would be more rigorous and is deferred).
- Not survivorship-corrected beyond what the canonical-bar dataset already provides (the F&O universe-history file `fno_universe_history.json` from EDB T0b is point-in-time correct).

**What we DO display on screen so the trader can judge the stat:**
- `n` (small n = thin data; honest).
- `Z` (against random; large Z = real signal).
- `Fold-stability ratio` (high = consistent across years; low = year-dependent).
- `Last seen` (recent fires get a freshness signal; ancient last-seen warns of regime drift).

## 11. Error handling

| Failure | Effect | Recovery |
|---|---|---|
| `pattern_stats.parquet` missing or stale (>14d) | Daily scan fails fast with `STATS_STALE` error. No Top-10 emitted. UI shows banner: "Pattern stats stale — Sunday fit may have failed." | Manual: rerun `AnkaPatternScannerFit`. Watchdog catches the parquet's freshness contract. |
| Fewer than 10 qualified fires today | Emit what we have; UI renders short list + `+N below threshold` footer. No error. | None. |
| Zero qualified fires today | Emit empty `top_10`. UI shows `No qualified pattern fires today` empty state. Paired shadow opens nothing tomorrow. No error. | None — this is expected on quiet days. |
| Bars loader returns insufficient history for a ticker (<60d) | Skip that ticker silently this scan; log to `pipeline/logs/pattern_scanner.log`. | Will recover when bar history fills. |
| pandas-ta detector returns NaN for a flagged date | Treat as not-fired. Log warning. | Investigate detector edge case. |
| Sidecar paired-shadow exception | Inherits Phase C spec error semantics (status `ERROR` row in options ledger; futures shadow unaffected). | Inherits Phase C recovery path. |
| Liquidity floor skip on options leg | Inherits Phase C: `status=SKIPPED_LIQUIDITY` row; counts as a population row but not P&L. | None. |
| Click-to-chart route missing for a ticker | Fallback: render ticker as plain text, no link; log error. | Verify chart route exists for the tradeable F&O universe. |

## 12. Testing strategy

**TDD per component.**

### Unit tests
- `test_pattern_scanner_detect.py`: each of the 12 detectors on synthetic OHLC fixtures (e.g., a constructed bullish hammer day → `BULLISH_HAMMER` flag; a non-hammer day → no flag). Edge cases: doji, gap-open hammers, one-candle vs multi-candle patterns.
- `test_pattern_scanner_stats.py`: synthetic 5-year panel with known win rate (e.g., construct 100 synthetic fires of which exactly 60 win) → assert `win_rate=0.60`, `z` correct to 2 decimals; walk-forward folds compute correct ratios.
- `test_pattern_scanner_rank.py`: composite-score ordering, min-n filter, fold-stability filter, top-10 truncation.
- Reuses unit tests for `options_atm_helpers`, `options_quote`, `options_greeks` from the Phase C spec — already covered.

### Integration tests
- `test_pattern_scanner_runner.py`: mock `bars_loader` + mock pandas-ta detectors → end-to-end produces correct `pattern_signals_today.json`.
- `test_scanner_paired_shadow.py`: mocked Kite quote → `open_options_pair` writes correct row; widely-spread mock → `SKIPPED_LIQUIDITY`; reuses Phase C paired-shadow integration test scaffolding.
- `test_scanner_api.py`: GET `/api/scanner/pattern-signals` returns expected shape on a fixture day.

### Smoke test
- Pre-merge dry run on real Kite data for 2 trading days. Verify:
  - Pattern stats parquet builds end-to-end on the full F&O universe in <30 minutes.
  - At least 1 fire today qualifies for Top-10.
  - Sidecar opens at least 1 paired options row without ERROR.
  - Liquidity floor fires on at least 1 illiquid strike (sanity check for the gate).
  - Click-to-chart works on each Top-10 ticker.

## 13. Reporting & verdict

`pipeline/pattern_scanner_report.py` runs after each close cycle, writes `pipeline/data/research/scanner/paired_shadow_report.md`. Stratified tables:

- **Table A — Headline paired diff** (always two rows: `is_expiry_day=true`, `is_expiry_day=false`): `mean(options_pnl_pct − futures_pnl_pct)`, bootstrap 95% CI, N.
- **Table B — Win rate by `pattern_id`**: which of the 12 patterns are confirming forward? Rows = patterns; cols = N_fires, win-rate, mean P&L (futures), mean P&L (options).
- **Table C — Win rate by regime** (NEUTRAL / RISK_ON / RISK_OFF): tests Bharat's prior that the scanner is most useful in NEUTRAL regimes.
- **Table D — Win rate by `direction`** (LONG vs SHORT).
- **Table E — Skip rate** (paired-shadow rows skipped at liquidity floor) by ticker.
- **Table F — Logistic TA scorer attribution** (Q1=B residual): for each closed paired trade, what was the logistic score at entry? Does score-≥80 correlate with realized win? After 30 days of data, this is the test for whether the logistic scorer adds value to Top-10 ranking. If it doesn't, we sunset (Q1 escalation).

**Verdict cadence**: descriptive readout at N=30 paired closes (~3 days at ~10/day), bootstrap-inference at N=100 (~10 days). Ledger only — no kill-switch trigger.

## 14. Documentation sync (mandatory at merge)

Per CLAUDE.md "Documentation Sync Rule":

- `docs/SYSTEM_OPERATIONS_MANUAL.md` — add Section "Scanner Pattern Engine" covering Layers 1–5, schedule, artifacts.
- `pipeline/config/anka_inventory.json` — add 4 new tasks (`AnkaPatternScannerScan`, `AnkaPatternScannerFit`, `AnkaScannerPairedOpen`, `AnkaScannerPairedClose`) with tier (info / warn), cadence, expected output paths, grace_multiplier.
- `CLAUDE.md` — add a "Pattern Scanner" subsection under the Clockwork Schedule.
- New memory: `memory/project_pattern_scanner.md` — purpose, schemas, scheduled tasks, verdict cadence, why no edge claim.
- `memory/MEMORY.md` — pointer line.

## 15. Risks & open questions

1. **pandas-ta Windows-install reliability.** pandas-ta is pure-Python so usually fine, but its TA-Lib-style candle-pattern functions are wrappers around `talib` in some installs. Verify pure-pandas-ta install path before committing to it; fallback is to write the 12 detectors in numpy directly (~80 LOC).
2. **Pattern definition stability across pandas-ta versions.** Pin the version in `requirements.txt` and re-validate detectors against fixtures on upgrade.
3. **`Engulfing` in pandas-ta is direction-agnostic** (returns +/− sign). Ensure the wrapper splits to BULLISH_ENGULFING / BEARISH_ENGULFING by sign.
4. **N=30 minimum may exclude many cells in v1.** Some `(ticker × pattern)` cells will have <30 fires over 5 years (e.g., `MORNING_STAR` is rare). The screen will show fewer Top-10 rows on quiet days. Flag as informational, not error.
5. **Fold-stability threshold (0.5) is heuristic.** Consider validating against a synthetic stationary panel + a synthetic regime-switch panel to confirm the threshold separates them. Tune if needed.
6. **Logistic scorer 30-day stay-of-execution** (Q1=B): no formal mechanism enforces the 30-day deadline. If it adds no value at Y2026-05-27 we manually sunset; calendar reminder via memory.
7. **Paired shadow firing rate.** ~10/day is high — paired shadow ledger grows ~50 rows/week, ~2.6K rows/year. JSON file size still trivial but reporting may want pagination at year scale.
8. **Cross-engine collision with Phase C paired shadow.** A ticker can fire both a Phase C `OPPORTUNITY_LAG` shadow AND a Scanner pattern shadow on the same day. Two paired shadow trades on the same ticker on the same day. Acceptable for v1 — they're separate ledgers, signal-source attributable, no double-counting if reporting joins per ledger. Flag for v2 if it causes confusion.

## 16. Implementation sequencing (preview)

The implementation plan (next document) sequences as TDD red-green-commit:

1. T0: Verify pandas-ta install + pin version; run candle-pattern fixtures.
2. T1: `pattern_scanner/detect.py` (TDD on synthetic OHLC).
3. T2: `pattern_scanner/stats.py` (TDD on synthetic panel; walk-forward folds).
4. T3: `pattern_scanner/rank.py` (TDD on composite-score ordering).
5. T4: `pattern_scanner/runner.py` (TDD with mocked detectors + stats).
6. T5: New endpoint `/api/scanner/pattern-signals` (TDD on fixture).
7. T6: `scanner.js` rewire + click-to-chart fix (manual + golden fixture).
8. T7: `scanner_paired_shadow.py` (TDD with mocked Kite quote, reuses Phase C scaffolding).
9. T8: Scheduled-task `.bat` files + `anka_inventory.json` entries.
10. T9: First weekly fit on full 5y F&O universe; verify parquet.
11. T10: Smoke run for 2 trading days end-to-end (dry-run flag).
12. T11: Reporting module `pattern_scanner_report.py` (TDD on synthetic ledger).
13. T12: Docs + memory sync per §14; commit and merge.

No `hypothesis-registry` append. No edge claim.

---

**End of design.**
