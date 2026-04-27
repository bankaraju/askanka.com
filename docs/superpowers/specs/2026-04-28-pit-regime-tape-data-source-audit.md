# PIT regime tape data source audit

**Date:** 2026-04-28
**Dataset ID:** `pit_regime_tape_v1`
**Tier (proposed):** D2 (Approved-for-research)
**Owner:** Bharat Ankaraju
**Acceptance status:** DRAFT — pending Bharat sign-off + first-build run
**Consumer hypotheses:** `H-2026-04-28-001` through `H-2026-04-28-004` (NEUTRAL_OVERLAY family)
**Governing policy:** `docs/superpowers/specs/anka_data_validation_policy_global_standard.md` §6 §8 §9 §11 §14 §21

## Purpose

The four NEUTRAL-overlay hypothesis engines need a regime label per (date, intraday-time) that is **point-in-time correct** — the value they read at any past timestamp `t` must be exactly the value the live engine produced *at or before* `t`. The existing `pipeline/data/regime_history.csv` does not satisfy this requirement (see §14 — contamination), and the live `pipeline/data/today_regime.json` is forward-only (no history depth).

This audit registers a hybrid tape, `pit_regime_tape_v1`, that supplies a defensible NEUTRAL filter for both backtest and live consumption.

## Why a new dataset

`memory/reference_regime_history_csv_contamination.md` and §A0-E3 of `NEUTRAL_Trading_Strategy_Framework.md`:

> `pipeline/data/regime_history.csv` is built with HINDSIGHT v2 weights, NOT a production audit trail. Do not use it for OOS comparisons.

The contamination is structural — the v2 ETF-weight optimization was fit on the full 5-year window, then the regime label for every historical date was *recomputed* using those globally-fit weights. Each historical row therefore embeds knowledge of every other row, making it useless for any backtest gate that compares "would-have-traded-this-day" against future P&L.

## Source — three feeds, one resolved tape

The PIT tape is built from three feeds with explicit precedence at each (date, time):

### Feed 1: Forward-only live tape (canonical, highest precedence)
- File: `pipeline/data/today_regime.json` (overwrites once daily at ~04:45 IST)
- Captured nightly to: `pipeline/data/pit_regime_tape/forward/<YYYY-MM-DD>.json`
- Coverage: from 2026-04-23 onwards (day v3-CURATED engine went live for forward-shadow per `memory/project_etf_v3_failed_2026_04_26.md`)
- Schema: `{date, zone, signal_score, engine_version, computed_at}`
- This feed is **trusted absolutely** — it is the live engine's output, written before market open, never revised.

### Feed 2: v3-CURATED replayed historical (research-only)
- Built by: `pipeline/scripts/backfill_pit_regime_tape.py --start 2021-04-23 --end 2026-04-22 --mode v3-replay`
- Mechanism: reload v3-CURATED ETF panel (`pipeline/data/research/phase_c/daily_bars/*.parquet`), replay the v3-CURATED scoring function day-by-day with **only data available at-or-before the date being scored** (lookback window strictly bounded by `as_of_date`).
- Output: `pipeline/data/pit_regime_tape/v3_replay/<YYYY-MM-DD>.json` (one file per date)
- Coverage: 2021-04-23 → 2026-04-22 (~1,250 trading days)
- Engine version baked into every row: `v3-CURATED-30 | replay-mode | seed=20260427`
- This feed is **research-only** — it is used to generate hypothesis candidates, rank in-sample variants, and compute correlation matrices. **It must not be used as the registered OOS gate's evidence basis.**

### Feed 3: v2 hindsight (for negative-control comparison only)
- File: existing `pipeline/data/regime_history.csv`
- No copy or transformation — referenced at its existing path with the contamination warning preserved.
- Coverage: 2021-04-23 → 2026-04-23 (1,256 rows)
- Use case: when `feed-2 v3-replay` produces a result, we cross-check against `feed-3 v2-hindsight` to confirm the *direction* of regime label agrees ≥ 70% of days. Disagreement above 30% is a flag that v3-replay has a bug, not evidence of edge.

## Resolved tape (what consumers read)

```
pit_regime_tape/
├── manifest.json          # build SHA, source feed versions, build timestamp
├── resolved/
│   └── <YYYY-MM-DD>.json  # one row per date, see schema below
├── forward/               # feed 1 (live)
│   └── <YYYY-MM-DD>.json
└── v3_replay/             # feed 2 (research)
    └── <YYYY-MM-DD>.json
```

**Per-date row schema (`resolved/<date>.json`):**
```json
{
  "date": "2026-04-28",
  "zone": "NEUTRAL",
  "signal_score": 8.2478,
  "engine_version": "v3-CURATED-30",
  "feed": "forward",
  "feed_captured_at": "2026-04-28T04:45:12+05:30",
  "v3_replay_zone": "NEUTRAL",
  "v3_replay_score": 8.31,
  "v2_hindsight_zone": "NEUTRAL",
  "feed_agreement": "all_three_agree"
}
```

`feed_agreement` ∈ {`all_three_agree`, `forward_v3_agree_v2_disagrees`, `forward_v2_agree_v3_disagrees`, `v3_v2_agree_no_forward`, `forward_only`, `disagreement`}.

**Resolution precedence at each date:**
1. If `forward` is present → that's the value. Other feeds are diagnostic.
2. Else if `v3_replay` is present → that's the value. `v2_hindsight` is diagnostic.
3. Else `unknown` (no feeds), zone = `null`. Backtest skips this date.

## Consumer contract

Hypothesis engines read the resolved tape via:

```python
from pipeline.data.pit_regime_tape import load_zone_for
zone = load_zone_for("2026-04-28", as_of="2026-04-28T09:30:00+05:30")
# returns "NEUTRAL", "RISK-ON", etc., or None for unknown
```

The `as_of` parameter is **mandatory** and must be no later than the current trade timestamp during backtests — the loader rejects requests where `as_of > date + 04:45 IST` for the date if `feed_captured_at` is unknown. This is the PIT enforcement boundary.

Live consumption (post-04:45 IST any trading day): `as_of` defaults to now, returns the forward feed.

## Cleanliness gates (policy §9)

- **Forward feed continuity:** missing-day count = 0 across all NSE trading days from 2026-04-23 onward (one snapshot per trading day).
- **v3-replay continuity:** missing-day count ≤ 0.5% of NSE trading days 2021-04-23 → 2026-04-22.
- **Engine-version stability per feed:** within `forward/`, `engine_version` may transition (v2 → v3), but each transition must be explicitly documented in `manifest.json` with a date stamp. Any silent version drift = build fails.
- **Zone vocabulary consistency:** every row's `zone` ∈ {`RISK-OFF`, `CAUTION`, `NEUTRAL`, `RISK-ON`, `EUPHORIA`, `null`}. Out-of-vocab = build fails.
- **No future timestamps:** every `feed_captured_at` ≤ `date + 12:00 IST` (regime is computed before market open).

## Adjustment mode (policy §10)

N/A — regime labels are categorical, not adjusted. Source ETF panel is split-adjusted upstream in `phase_c/daily_bars/*.parquet` per the existing audit.

## Point-in-time correctness (policy §11)

This is the audit's core question. Three guarantees:

**G1. Forward feed.** Captured nightly via cron at 05:00 IST (after AnkaETFSignal at 04:45). The captured copy is immutable — never overwritten. A new task `AnkaPitRegimeTapeCapture` must be added to `pipeline/config/anka_inventory.json`.

**G2. v3-replay feed.** Replays the v3-CURATED scoring function with `as_of_date = D` using only ETF panel data with `panel_date ≤ D`. The replay function `pipeline/scripts/backfill_pit_regime_tape.py` must:
- assert no peek into rows with `panel_date > D`
- use rolling statistics computed only over the trailing window ending at `D`
- ignore any feature that requires future weights (the v3-CURATED weights are themselves frozen at 2026-04-26 per `memory/project_etf_v3_failed_2026_04_26.md` — using them for historical replay introduces *backward* hindsight which is acceptable for research-only evidence per §C0 but not for a registered OOS gate)

**G3. Verdict gate isolation.** The four NEUTRAL-overlay hypothesis registry rows declare `data_deps: ["pit_regime_tape_v1"]` AND a separate field `verdict_gate_feed: "forward"`. Verdict-time evaluation reads only `feed="forward"` rows. Even if a backtest used v3-replay rows for in-sample exploration, the verdict cannot.

## Independent corroboration (policy §13)

For the in-sample window 2026-04-23 → 2026-04-26 (where both `forward` and `v3-replay` cover the same dates), agreement on `zone` must be 4/4. Any disagreement requires a debug commit before the dataset acceptance is granted.

For the deeper history (2021-04-23 → 2026-04-22), `v3-replay` vs `v2-hindsight` agreement on `zone` must be ≥ 70%. The 30% disagreement budget reflects the two engines being structurally different (CURATED-30 ETF subset vs v2's full panel). Below 70% = `v3-replay` build is broken.

## Contamination map (policy §14)

| Channel                            | Risk                                                                                  | Mitigation                                                                                       |
|------------------------------------|---------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------|
| ETF panel survivorship             | If `phase_c/daily_bars/*.parquet` was rebuilt after a constituent change              | Audit doc `2026-04-25-canonical-fno-research-dataset-audit.md` already addresses this           |
| v3-CURATED weight contamination    | Weights fit using full 5-year history → applied to historical dates = backward hindsight | Mark all `v3-replay` rows as research-only via `feed_agreement` field; verdict gate uses `forward` only |
| Live engine drift                  | If `etf_signal.py` is patched mid-holdout, `forward` feed values shift                | Engine version pinned per row; mid-holdout engine bumps require fresh hypothesis IDs (per §10.4 strict) |
| Cron capture failure               | If `AnkaPitRegimeTapeCapture` fails, we miss a trading day                            | Watchdog freshness contract: `forward/<YYYY-MM-DD>.json` must exist within 90 min of 05:00 IST  |
| Time-zone confusion                | Mixing UTC and IST timestamps                                                         | All timestamps in IST with explicit `+05:30` offset; loader rejects naive datetimes              |
| Earnings-calendar overlap          | None — regime is market-level, not stock-level                                        | —                                                                                                |

## Build procedure (one-shot, then daily delta)

**One-shot historical build (run once before 2026-04-28 09:00 IST):**
```bash
python -m pipeline.scripts.backfill_pit_regime_tape \
  --start 2021-04-23 \
  --end 2026-04-22 \
  --mode v3-replay \
  --out pipeline/data/pit_regime_tape/v3_replay/

python -m pipeline.scripts.backfill_pit_regime_tape \
  --start 2026-04-23 \
  --end 2026-04-27 \
  --mode forward-from-archive \
  --out pipeline/data/pit_regime_tape/forward/

python -m pipeline.scripts.resolve_pit_regime_tape \
  --start 2021-04-23 \
  --end 2026-04-27 \
  --out pipeline/data/pit_regime_tape/resolved/
```

**Daily delta (cron-driven from 2026-04-28 onward):**
- 05:00 IST: `AnkaPitRegimeTapeCapture` reads `today_regime.json`, writes `forward/<today>.json`
- 05:05 IST: `AnkaPitRegimeTapeResolve` rebuilds `resolved/<today>.json` from feeds 1-3
- 05:10 IST: provenance sidecar written; watchdog freshness contract checks at 06:00

## Acceptance gates

This dataset is `Approved-for-research, Tier D2` once ALL of:

- [ ] One-shot build completes without errors (≥ 1,250 dates with non-null zone in `resolved/`)
- [ ] Forward-vs-v3-replay agreement = 4/4 on overlap dates
- [ ] v3-replay-vs-v2-hindsight agreement ≥ 70% on full overlap window
- [ ] PIT enforcement test: loader rejects `as_of > date + 04:45 IST` requests for unknown-feed dates
- [ ] `AnkaPitRegimeTapeCapture` and `AnkaPitRegimeTapeResolve` registered in `anka_inventory.json` with `tier: warn`, `cadence_class: daily`, `grace_multiplier: 1.5`
- [ ] Bharat sign-off recorded in this file's frontmatter (status: `Approved-for-research, Tier D2`)

## Verdict

DRAFT — not yet accepted. Must clear acceptance gates above before any of the four NEUTRAL-overlay hypothesis engines may register or run in-sample backtests. **This is the load-bearing prerequisite for the entire NEUTRAL_OVERLAY family.**

## Revision history

- v0.1 (2026-04-28): initial DRAFT — Bharat / Claude Opus 4.7. Pending build run + Bharat acceptance.
