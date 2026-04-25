# Earnings-calendar data source audit

**Date:** 2026-04-25
**Dataset ID:** `earnings_calendar_indianapi_v1` (proposed)
**Tier (proposed):** D2 (decision-supporting; research-class backtest input)
**Owner / proposer:** Bharat Ankaraju
**Validator:** TBD (must be independent of proposer per policy §4.2)
**Acceptance status (current):** **Proposed** — live verification probe complete; awaiting independent validation.

**Purpose:** Verify which paid API can supply a clean earnings calendar for the
pre-earnings decoupling hypothesis (H-2026-04-25 family). Document authenticity,
cleanliness, noise sources, and timing reliability before any spec is locked.

**Policy binding:** This audit is the §6.2 onboarding probe and §9.1 cleanliness
audit required by `anka_data_validation_policy_global_standard.md`. Coverage of
policy sections: §6.1 authentication discipline, §6.2 live verification, §7.1
end-to-end traceability (partial), §8.1 schema contract (preliminary), §9.1
cleanliness audit (partial — full baseline required before vetting), §10.1
adjustment-mode declaration (N/A — corporate-action ledger, not price series),
§11.3 future-dated entries (covered), §13.1 independent corroboration (BSE
disclosure source noted; secondary not yet identified), §14.1 contamination map
(covered).

## TL;DR

- **EODHD: not usable.** The current key (`EODHD_API_KEY` in `pipeline/.env`) is
  on an EOD-bars-only tier. `/api/calendar/earnings` and `/api/fundamentals/*`
  both return **403 Forbidden** despite paid status. EOD bars endpoint works
  (200 OK).
- **IndianAPI: primary source.** `/corporate_actions` returns SEBI-mandated
  Board Meeting disclosures with date + free-text agenda. Authentication uses
  `X-Api-Key` header + `stock_name` query param. Key lives in `pipeline/.env`
  under `INDIANAPI_KEY`. Auth pattern matches existing `pipeline/news_scanner.py`.
- **Coverage:** 67–71 earnings/stock across 5 spot-checked stocks
  (RELIANCE/HDFCBANK/TCS/MARUTI/BHARTIARTL), spanning roughly 17–18 years of
  quarterly history. Sufficient for an 18-month backtest (~1,278 events across
  213 F&O universe).
- **Cleanliness caveats**: agenda field is free-text — must be classified by
  keyword regex; some boilerplate text reuse can produce duplicate dates per
  quarter; lag in API freshness varies by stock (BHARTIARTL most-recent
  2026-02-05 vs RELIANCE 2026-04-24 on same probe).

## Live verification log (2026-04-25)

### EODHD plan probe

```
GET /api/user                         → 200  dailyRateLimit=100000  subscriptionMode=paid
GET /api/eod/AAPL.US                  → 200  EOD bars OK
GET /api/calendar/earnings            → 403  Forbidden
GET /api/calendar/earnings?symbols=RELIANCE.NSE,TCS.NSE → 403  Forbidden
GET /api/fundamentals/RELIANCE.NSE    → 403  Forbidden
```

The plan label "EODHD plan" with 100k/day budget does NOT include the calendar
or fundamentals modules. Upgrading would require a separate "Fundamentals"
add-on (not currently subscribed).

### IndianAPI corporate_actions probe

```
GET https://stock.indianapi.in/corporate_actions?stock_name=RELIANCE
Headers: X-Api-Key: $INDIANAPI_KEY
→ 200 OK

Response shape:
{
  "board_meetings": {"title": "Board Meeting", "header": ["Date","Agenda"], "data": [...]},
  "dividends":     {"title": "Dividend", ...},
  "splits":        ...,
  "bonus":         ...,
  "rights":        ...
}
```

Sample agenda strings (RELIANCE):

- `"24-04-2026"` → `"...meeting of the Board of Directors...inter alia to consider and approve...standalone and consolidated audited financial results...quarter and year ended March 31 2026..."`
- `"16-01-2026"` → `"Quarterly Results"` (terse variant)
- `"17-10-2025"` → full variant + post-meeting addendum `"(As Per BSE Announcement Dated on:17.10.2025)"`

### Coverage spot-check (5 sector stocks)

| Stock | total_board_meetings | earnings_classified | most_recent (6) |
|---|---|---|---|
| RELIANCE | 106 | 71 | 2026-04-24, 2026-01-16, 2025-10-17, 2025-07-18, 2025-04-25, 2025-01-16 |
| HDFCBANK | 116 | 68 | 2026-04-18, 2026-01-17, 2025-10-18, 2025-07-19, 2025-04-19, 2025-01-22 |
| TCS | 105 | 69 | 2026-04-09, 2026-01-12, 2025-10-09, 2025-07-10, 2025-04-10, 2025-01-09 |
| MARUTI | 96 | 71 | 2026-04-28, 2026-01-28, 2025-10-31, 2025-07-31, 2025-04-25, 2025-01-29 |
| BHARTIARTL | 117 | 67 | 2026-02-05, 2025-11-03, 2025-08-05, 2025-05-13, 2025-02-06, 2024-10-28 |

Quarterly cadence is intact for all 5. 67–71 earnings × ~18-year history ≈ 4
events/year — exact match with the quarterly schedule SEBI mandates. The
classification regex is:

```python
EARN_KEYWORDS = re.compile(
    r'(quarterly results'
    r'|audited financial results'
    r'|unaudited financial results'
    r'|financial results for the quarter'
    r'|board.*consider.*results)',
    re.I,
)
```

## Authenticity & freshness checks

| Check | Method | Result |
|---|---|---|
| Real domain | `stock.indianapi.in` (matches `pipeline/news_scanner.py:125-149` usage) | OK |
| HTTPS valid cert | `requests` with default verify | OK (no SSL warning) |
| Field cardinality | 5 top-level keys present (board_meetings/dividends/splits/bonus/rights) | OK |
| Cross-stock parity | All 5 stocks return same schema | OK |
| Future-dated entries present | MARUTI 2026-04-28, RELIANCE 2026-04-24 on a 2026-04-25 probe | OK — pre-announce window respected |
| Stock-by-stock freshness | BHARTIARTL last entry 2026-02-05 (older than 2026-04 cycle) | **Caveat**: API freshness lags some stocks; backtest needs forward-only filter |

## Noise sources to control before signal extraction

The user specifically flagged: *"u need to verify…if the data is authentic --
clean and has been checked for earnings noise…in OI/PCR intraday news means a
lot."* These are the noise dimensions that must be controlled before any
hypothesis is registered:

1. **Result-day gap noise.** The largest single noise source is the actual
   result-day move (T0). Gaps of ±5% or more on result day are routine and
   completely dominate any pre-event signal. *Mitigation:* hypothesis
   exits at T-1 EOD by construction; no result-day exposure.
2. **Quarter-end-window noise.** Indian listed companies cluster results in
   month 1 of each quarter (Apr/Jul/Oct/Jan). Multiple peers report within
   3–7 days of each other → peer-decoupling z-scores need cohort
   re-estimation per stock-day, not static peer baselines.
3. **Pre-announcement leak vs post-announcement window.** The board-meeting
   agenda becomes public ≥5 working days before the meeting (SEBI Reg 29).
   So the window genuinely available for "decoupling" is **T-N → T-5**
   (no announcement made yet) **vs T-5 → T-1** (announcement public,
   results not). These need to be modelled separately.
4. **Concurrent corporate-action noise.** Some board meetings combine
   results + dividend recommendation + fund-raising. The agenda regex
   above will still classify them as earnings, but the move is
   contaminated with non-earnings catalysts. *Mitigation:* tag each event
   with concurrent-action flags from the same response payload.
5. **Stale board-meeting calendar.** API freshness varies by stock. Any
   live system must NEVER assume "next earnings date = max(date)" without
   a forward-only filter (date > today) AND a reasonableness gate
   (next-quarter window must be 70–110 days out from previous).
6. **OI/PCR intraday news contamination.** OI and PCR move on intraday
   news (not just earnings). Per user emphasis, the last 3 days into
   earnings see OI/PCR react to *both* the upcoming results and any
   concurrent intraday news. *Mitigation:* the OI/PCR delta features in
   the earnings hypothesis must be regressed against contemporaneous
   news-impact scores (already produced by `pipeline/news_scanner.py` and
   `pipeline/news_backtest.py`) before being attributed to the earnings
   anticipation effect.

## Auth pattern (canonical)

Use the exact pattern already in `pipeline/news_scanner.py:125`:

```python
import os, requests
from dotenv import load_dotenv

load_dotenv('pipeline/.env')
api_key = os.getenv('INDIANAPI_KEY')

def fetch_corporate_actions(symbol: str) -> dict | None:
    r = requests.get(
        'https://stock.indianapi.in/corporate_actions',
        headers={'X-Api-Key': api_key},
        params={'stock_name': symbol},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()
```

**Do NOT hardcode the key.** Always read `INDIANAPI_KEY` from `pipeline/.env`.
Production rotation: change one file (`.env`) and every consumer picks it up.

## Recommended path forward

1. Build `pipeline/earnings_calendar.py` — daily scheduled task that pulls
   `/corporate_actions` for the 213 F&O universe, classifies events via
   regex, stores `pipeline/data/earnings_calendar/YYYY-MM-DD.json` with
   schema `{symbol, event_date, agenda_raw, has_dividend, has_fundraise,
   classification_confidence}`.
2. Add freshness contract to `pipeline/config/anka_inventory.json` — task
   tier=warn, cadence_class=daily, expected output stale within 7 days
   would alert the watchdog.
3. Backfill 18 months of history into `data/earnings_calendar/history.parquet`
   from a single one-off `--backfill` run before the hypothesis is registered.
4. Pre-register the hypothesis (separate spec) ONLY after the calendar
   parquet is committed and the watchdog freshness contract is green.
5. Section-0 backtest standards apply
   (`docs/superpowers/specs/backtesting-specs.txt`) — no waivers, full
   compliance gate before any live promotion.

## Open questions for the user (to resolve before spec lock)

1. **Result-day inclusion or strict T-1 exit?** Spec assumes strict T-1
   EOD exit to eliminate gap noise. Confirm before locking.
2. **Peer-cohort definition.** Sector index + 3 closest market-cap peers,
   or industry-classified peers from IndianAPI `industry` field? The
   second is cleaner but cardinality varies (some industries have only 1
   F&O ticker).
3. **Macro exclusion threshold.** USD/INR > 2σ AND VIX > 2σ to skip the
   cycle, or either-or? More aggressive = fewer events but cleaner
   attribution.
4. **Backtest window extension if 18 months yields < 800 events post
   filters.** User said "18 months is good enough for now" but if macro
   exclusions + concurrent-action filters drop us below the §0 minimum,
   we extend or relax filters. Pick which one in advance.
