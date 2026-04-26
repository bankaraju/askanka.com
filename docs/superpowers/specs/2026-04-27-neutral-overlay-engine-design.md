# NEUTRAL Overlay Engine — Design Doc (Task #107)

**Status:** SCOPING (pre-implementation)
**Owner:** Anka research
**Started:** 2026-04-27 after Phase 2 Test 1c verdict (commit `36eca98`)
**Estimated build time:** 2-3 weeks across multiple sessions
**Pre-requisite:** Phase 2 Test 1 + Test 1c + H-2026-04-27 pre-registration shipped

---

## 1 — Why this exists

Phase 2 Test 1 showed NEUTRAL is the dominant zone (412 of 493 OOS days = 83.8%
of trading days). Test 1's per-zone NIFTY directional accuracy on NEUTRAL is
54.1% up — essentially the long-run drift, no information for direction-of-
NIFTY trades.

But the catalog notes structural NEUTRAL-day asymmetry by sector:
**short-fades work in PSU BANK / BANKPSE / ENERGY / INFRA, lose in
AUTO / IT / FMCG**. Test 1b's *unconditional* sector-mean check inverted that
claim (fade_works bucket leans MORE long than fade_loses bucket on NEUTRAL
days). The catalog claim is about *triggered* fades — i.e., on days the
sector spikes >2σ intraday, fade-shorts in the catalog-named sectors profit.

This engine evaluates that triggered claim. If it holds, NEUTRAL becomes the
single biggest tradable surface in the v3 pipeline (~83% of days).

## 2 — Data gap that drives the staging

| Need | What we have | What we lack |
|---|---|---|
| Daily 5-zone label (412 NEUTRAL days, 2024-04-23 → 2026-04-23) | `runs_smoke/wf_lb756_u126_seed0/test_1_raw_zones.csv` | none |
| Per-sector 2σ-cross trigger | Daily sectoral OHLC for all 10 NIFTY sectoral indices | minute-bar sectoral data over 2y |
| Per-ticker 2σ-cross intraday events | `intraday_break_replay_60d_v0.2_minute_bars.parquet` | 60-day window only (covers ~50 NEUTRAL days) |
| Per-ticker → sector mapping | `pipeline/data/canonical_fno_research_v3.json` (270 tickers) | none |
| Coef-delta marker (per-window weight rotation magnitude) | `runs_smoke/.../rolling_refit.json` per_window_detail.weights | none |

**Key constraint:** the intraday triggered-fade claim needs minute-level data
across the full 2-year NEUTRAL window. We only have minute data for the
last 60 days.

## 3 — Two-stage build plan

### Stage A — Daily-cadence proxy (1 week)

Build a daily-cadence "ZCROSS-like" trigger using sectoral DAILY returns
(>|Z|σ where Z is rolling 21d std of daily sector returns). This is a
*proxy* for the intraday 2σ trigger but covers the full 2-year window,
giving us n ~ 412 NEUTRAL days × 10 sectors of trigger candidates instead of
~50 days.

**Modules:**
- `daily_zcross_proxy.py` — for each (sector, NEUTRAL-day) pair, flag if
  daily return > Z×rolling-21d-std. Output: `(date, sector, z, direction)` events.
- `coef_delta_marker.py` — per-window weight L2-delta from previous window
  (already implemented in `markers/coef_delta.py`); apply to refit dates.
- `neutral_sector_overlay.py` — restrict events to catalog's fade_works
  sectors (NIFTYPSUBANK, NIFTYENERGY) and a control set (AUTO/IT/FMCG).
- `neutral_overlay_runner.py` — compose markers (each-alone + stacked),
  compute fade-short next-day P&L per filtered event, attribute by slice.

**Verdict gate (Stage A):** does the daily-cadence proxy show:
- fade_works bucket fade-short P&L > 0 with hit rate > 55%
- fade_loses bucket fade-short P&L ≤ 0 (or below fade_works by ≥ 0.10pp/event)
- stacked markers (ZCROSS + sector_overlay + coef_delta) > any individual marker

If YES → proceed to Stage B (intraday triggered backtest on the 60-day
window). If NO → catalog claim does not hold even at daily cadence; archive.

### Stage B — Intraday minute-bar backtest (1-2 weeks)

If Stage A passes, wire the EXISTING marker modules
(`zone_gate`, `sector_overlay`, `coef_delta`, `sigma_bucket`) against the
60-day intraday replay parquet, restricted to NEUTRAL official days from the
test_1_raw_zones.csv overlap.

**Modules:**
- Use existing `markers/*.py` as designed (event-cadence inputs).
- New `neutral_intraday_runner.py` — orchestrate the pipeline:
  events → zone_gate (NEUTRAL-restricted) → sector_overlay (catalog sectors)
  → sigma_bucket (Z thresholds) → fade-short next-day P&L.
- Per-marker attribution + stacked attribution + Bonferroni-adjusted
  significance threshold given the marker-combo search space.

**Verdict gate (Stage B):**
- per-marker stacked P&L > +0.30pp/event net of slippage
- hit rate ≥ 60%
- Bonferroni-adjusted permutation-null p-value ≤ 0.000417 (matches
  H-2026-04-26-001 pattern; α=0.05 / 120-cell search space)

If YES → register as a new pre-registered hypothesis (H-2026-MM-DD-NNN)
with its own single-touch holdout, do NOT deploy without OOS confirmation.
If NO → archive the marker stack approach; NEUTRAL is not tradable as
designed.

## 4 — What this engine does NOT do

- **Does not modify the v3-CURATED model.** Trading direction on NEUTRAL
  comes from the marker stack, not from the regime label.
- **Does not touch H-2026-04-27 RISK-ON inversion.** That hypothesis is on
  its own holdout schedule. NEUTRAL overlay is a separate work-stream.
- **Does not consume any holdout window.** Stage A + Stage B are both
  in-sample evidence collection; any successful stack must be re-registered
  with a fresh holdout per backtesting-specs section 10.4.
- **Does not assume the catalog claim is right.** Stage A is the gate that
  decides whether to spend Stage B compute.

## 5 — Module file paths (planned)

```
pipeline/autoresearch/etf_v3_eval/phase_2/neutral_overlay/
  __init__.py
  daily_zcross_proxy.py        # Stage A trigger
  coef_delta_marker.py         # Stage A wrapper around existing marker
  neutral_sector_overlay.py    # Stage A sector whitelisting
  stage_a_runner.py            # Stage A orchestrator + report
  neutral_intraday_runner.py   # Stage B orchestrator (only if Stage A passes)
  reports/                     # Per-stage Markdown outputs

pipeline/tests/test_etf_v3_eval/
  test_daily_zcross_proxy.py
  test_neutral_sector_overlay.py
  test_stage_a_runner.py
  test_neutral_intraday_runner.py
```

## 6 — Implementation order (fresh-session safe)

1. **Today (or next session):** Build `daily_zcross_proxy.py` + tests. Pure
   function: takes sectoral panel + NEUTRAL day list, returns event DataFrame.
2. **Session 2:** Build `neutral_sector_overlay.py` + tests. Trivial
   filtering wrapper.
3. **Session 3:** Build `coef_delta_marker.py` wrapper that applies the
   existing `markers/coef_delta.py` code to refit-window cadence; output is
   a per-NEUTRAL-day "rotation magnitude" feature.
4. **Session 4:** Build `stage_a_runner.py` — composes the three Stage A
   inputs + sector overlay + computes fade-short next-day P&L per slice.
   Writes Stage-A report.
5. **Session 5 (decision point):** Read Stage A report. Decide proceed or stop.
6. **Sessions 6-9 (only on Stage A pass):** Build Stage B wiring against the
   minute-bar replay; pre-register hypothesis; run; write verdict.

## 7 — Open questions for next session

- **Z threshold for daily-cadence proxy:** 2σ matches the intraday
  convention but daily returns have different fat-tail structure. May need
  to sweep [1.5, 2.0, 2.5] and report sensitivity (cohort-robustness check
  per Tier C in H-2026-04-26-001).
- **Coef-delta cadence:** the marker is per-refit-window (5-day cadence in
  the smoke run). How does that map onto daily NEUTRAL trade decisions?
  Likely: classify each refit as "high rotation" or "low rotation," then
  apply that label to all NEUTRAL days in the next 5-day OOS window.
- **Slippage model for sector index trades:** sectoral indices aren't directly
  tradable; the proxy is a basket of constituent stocks. Slippage assumption
  needs to be ~0.10-0.15% per side for full sector-basket execution, NOT
  the ~0.05% used for single-name trades.

## 8 — Success vs failure modes

**Success looks like:** Stage A shows fade_works fade-short mean > +0.10pp/
event with hit ≥ 55%, AND fade_loses bucket lags by ≥ 0.10pp. Stage B then
ratifies on intraday data with margin > +0.30pp/event and Bonferroni-clearing
permutation-null p-value. The successful stack is pre-registered as a new
hypothesis with its own forward-shadow holdout. NEUTRAL becomes ~83% of
trading-day surface tradable.

**Failure looks like:** Stage A shows the catalog claim does not hold even
at daily cadence (fade_works ~ fade_loses or fade_works negative). Engine
is archived; NEUTRAL stays as "no trade" in the v3 pipeline; the v3
production trading thesis collapses to ~17% of days (EUPHORIA + RISK-ON if
inverted + CAUTION + RISK-OFF).

**Mixed looks like:** Stage A clears for daily-cadence proxy but Stage B
fails on minute-bar data — proxy was a tease, real intraday triggers don't
have edge. Document and archive Stage B; revisit only if minute-bar
coverage extends past 60 days.

## 9 — Cross-references

- Phase 2 Test 1 verdict: commit `43afb37`
- Test 1c gap-fade diagnostic: commit `f9d7963`
- H-2026-04-27 RISK-ON inversion pre-registration: commit `36eca98`
- Existing marker modules: `pipeline/autoresearch/etf_v3_eval/phase_2/markers/`
- Catalog claim source: `memory/project_mechanical_60day_replay.md` +
  `memory/feedback_psu_sector_spreads.md`
- Single-touch discipline: `docs/superpowers/specs/backtesting-specs.txt §10.4`
