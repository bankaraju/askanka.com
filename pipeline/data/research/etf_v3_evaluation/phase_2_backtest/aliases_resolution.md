# Phase 1 → Phase 2 Alias Resolution

**Sources verified:**
- `pipeline/data/kite_cache/instruments_nse.csv` (NSE EQ spot instruments, cache date 2026-04-26)
- `pipeline/data/kite_cache/instruments_nfo.csv` (NFO futures instruments, cache date 2026-04-26)
- `pipeline/data/fno_universe_history.json` (monthly FNO universe snapshots 2024-01 → 2026-03)
- `docs/superpowers/specs/tickers list .xlsx` (PIT name-change registry, 9 entries)

**Verified:** 2026-04-26

---

## Resolution Table

| Original | Resolved | Status | Citation | Backfill outcome |
|---|---|---|---|---|
| L&TFH | LTF | resolved | NSE instruments: `LTF` (name: "L&T FINANCE", token 6386689); FNO Feb 2026 snapshot confirmed. Phase 1 failure: "&" in symbol caused Kite token lookup to fail; modern symbol has no special chars. | 13,500 rows (2026-02-26 → 2026-04-23) |
| LTIM | LTM | resolved | FNO universe history: LTIM present through Jan 2026, dropped in Feb 2026; LTM added in same transition (Jan→Feb delta: removed=[IRCTC, LTIM], added=[LTM]). NSE instruments: `LTM` (token 4561409), NFO futures `LTM26APRFUT` confirmed. xlsx row: "LTIM: LTI / MINDTREE merger" — the post-merger entity was subsequently renamed LTM in the Kite token refresh. The v0.2 window (2026-02-26 → 2026-04-23) lies entirely after the rename. | 13,500 rows (2026-02-26 → 2026-04-23) |
| ZOMATO | ETERNAL | resolved | NSE instruments: `ETERNAL` (name: "ETERNAL - ZOMATO", token 1304833); NFO futures `ETERNAL26APRFUT` confirmed; FNO Feb 2026 snapshot confirmed. Zomato Ltd rebranded to Eternal Limited effective 2026. | 13,500 rows (2026-02-26 → 2026-04-23) |
| MCDOWELL-N | UNITDSPR | resolved | NSE instruments: `UNITDSPR` (name: "UNITED SPIRITS", token 2674433); NFO futures `UNITDSPR26APRFUT` confirmed; FNO Feb 2026 snapshot confirmed. McDowell & Company Ltd trades as United Spirits (UNITDSPR) on NSE. | 13,500 rows (2026-02-26 → 2026-04-23) |

All 4 mappings resolved. No documented exclusions (None values) required.

---

## Effective Phase 2 Universe

**147 tickers** were in the Phase 1 requested list.  
**143** succeeded in Phase 1 backfill.  
**4** failed Phase 1 with "no instrument_token" (alias gaps).  
**4** resolved via `alias_resolver.py` and successfully backfilled in Phase 2.

**Effective Phase 2 universe: 147/147 tickers** covering the 60-day v0.2 window (2026-02-26 → 2026-04-23).

Aliased bars are in: `pipeline/autoresearch/data/intraday_break_replay_60d_v0.2_minute_bars_aliased.parquet`  
(54,000 rows total, 13,500 per ticker; tagged with original symbol in `ticker` column for downstream joins)

---

## Caveats

1. **LTIM mid-window rename complexity:** LTIM was active in the FNO universe through January 2026 but LTM took its place from February 2026 onward. The entire v0.2 backfill window (2026-02-26 → 2026-04-23) falls after the rename, so LTM data cleanly covers the window. There is no gap within the window, but any historical lookback extending before 2026-02-01 would require stitching LTIM + LTM bars.

2. **Downstream ticker column:** The aliased parquet stores the original symbol (e.g. "LTIM", "ZOMATO") in the `ticker` column. The underlying Kite data was fetched under the modern symbol but tagged back. Callers that need to filter by modern symbol must use `resolve_alias()` to translate before lookup.

3. **Instrument cache freshness:** NSE/NFO instruments CSVs were generated 2026-04-26 04:45 (as recorded by file mtime). These are the same instruments used by the live clockwork — any subsequent Kite token regeneration could change `instrument_token` values but not tradingsymbols.
