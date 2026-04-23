# Waiver — H-2026-04-23-001 Survivorship Coverage

**Hypothesis / Strategy:** H-2026-04-23-001 (phase-c-residual-reversion-eod)
**Section waived:** 6.2 (survivorship coverage disclosure — currently UNCORRECTED because `pipeline/data/fno_universe_history.json` has not been built yet)
**Reason:** NSE monthly F&O membership history fetcher is not yet implemented. Strategy cannot wait indefinitely for that build; formal pre-registration and Sections 1-5, 7-14 testing can proceed in parallel while Section 6 is the explicit gate before any LIVE promotion.
**Scope of waiver:** Permits progression through RESEARCH-tier only. No promotion to PAPER-SHADOW under this waiver.
**Expiry:** 2026-07-23 (90 days). Must either build `fno_universe_history.json` by then or re-justify in a new waiver.
**Signing principal:** Bharat Ankaraju
**Date signed:** 2026-04-23 (today, pre-deviation per Section 15.4)

---

## Exit plan
1. Implement NSE F&O monthly membership fetcher in `pipeline/ingest/nse_fno_universe.py`
2. Backfill 2021-04 through 2026-04 monthly snapshots
3. Commit to `pipeline/data/fno_universe_history.json`
4. Re-run H-2026-04-23-001 against the point-in-time universe
5. If coverage_ratio < 10% still after backfill, file a further waiver with quantified bias estimate
