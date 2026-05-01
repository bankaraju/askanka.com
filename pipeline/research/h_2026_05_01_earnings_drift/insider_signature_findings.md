# Pre-event insider signature study — findings 2026-05-01

**Stage A widen #75. Forensic only. NOT a hypothesis. No registry row.**

## Background

The originally-mentioned "INDUSIND / Goldman large-print" bulk-deals signature CANNOT be backtested per `reference_nse_bulk_deals_history_unavailable.md` — only forward-only collection from 2026-04-24 (~6 days as of 2026-05-01). Insider trade disclosures are the closest available substitute and span 2021-01 onward.

## Question

Does **operative-insider** (Promoter / Promoter Group / Director / KMP / Immediate Relative) buying or selling in the 30 days BEFORE a Banks/IT earnings event predict event direction (BEAT_LIKE vs MISS_LIKE)?

## Method (PIT-clean)

For each of 314 events in `event_factors.csv`:
- Window = `[event_date - 30, event_date - 1]`
- Filter `insider_trades` by:
  - matching `symbol`
  - `acq_to_date` in window
  - `filing_date <= event_date - 1` (PIT: signal must be observable before T-1)
  - `person_category` in {Promoters, Promoter Group, Director, KMP, Immediate relative}
  - `transaction_type` in {Buy, Sell}
- Aggregate buy_inr, sell_inr, net_inr per event

Insider-trade source: 31,028 operative Buy/Sell rows from 88,863 total 2021-2024 filings.

## Verdict — NEGATIVE (coverage too low + counterintuitive direction)

### 1. Coverage too low to be actionable

**Only 20 of 314 events (6.4%) have ANY operative-insider activity in the pre-event window.** Most Banks/IT names have closed-window blackouts around quarterly earnings — promoters and KMPs simply don't trade in the 30 days leading up to results.

| Direction | n events | n with insider activity | coverage |
|---|---|---|---|
| BEAT_LIKE | 160 | 8 | 5.0% |
| MISS_LIKE | 154 | 12 | 7.8% |

Even if the signal were strongly predictive, it would fire on at most ~2 holdout trades — insufficient for a v2 entry-rule add-on.

### 2. Signal direction is COUNTERINTUITIVE (where it does exist)

| Insider net | n | p(BEAT) | lift vs unconditional 51.0% |
|---|---|---|---|
| Net BUY (>0) | 14 | 35.7% | **−15.2pp** |
| Net SELL (<0) | 6 | 50.0% | −1.0pp |
| Zero | 294 | 51.7% | +0.7pp |

**Where insiders bought, the event was MORE LIKELY to MISS** (35.7% BEAT vs 51% baseline). Plausible mechanism: promoter top-ups in the pre-result blackout often reflect mandatory ESOP exercise / pledge-back / right-issue mechanics rather than fundamental conviction. This isn't a "smart money" signal in this universe.

### 3. The MISS_LIKE side has slightly more activity

12 of 154 MISS events (7.8%) had any insider activity vs 8 of 160 BEAT events (5.0%). MISS-side mean net insider INR is +₹4.9 lakhs while BEAT-side has a single huge sell skewing the mean to −₹69 cr. Both are dominated by 1-2 outlier filings; not statistically meaningful at this sample size.

## Files

- `insider_signature_study.py` — analysis script
- `insider_signature_per_event.csv` — 314 rows (one per event with insider aggregates)
- `insider_signature_summary.json` — aggregated stats incl. cross-tab + PIT signal strength
- `insider_signature_findings.md` — this memo

## Implications for v1

1. **Skip insider-net as a v2 entry feature** — coverage 6% kills it before signal even matters.
2. **Bulk-deals genuinely cannot be tested in 5y** until forward collection accumulates (need ≥1 year per `reference_nse_bulk_deals_history_unavailable.md`). Re-attempt 2027-04-24.
3. **Stage A widen track is exhausted** for now — peer drift was negative, insider signature is negative-and-thin. v1 single-name LONG cell is the only positive-prior cell available.

## Next-step decision

- **v1 holdout opens 2026-05-04** — let it run; verdict 2026-08-01 (auto-extend to 2026-10-31 if n<20).
- **No new pre-registrations** in the earnings-drift family pre-verdict.
- **2027-04-24** earliest re-test of bulk-deals signature (1y forward collection).
- **2026-Q4** (after v1 verdict): consider expanding universe (Pharma, FMCG quarterly results) and SHORT side as a v2 design.
