# Intraday News Intelligence Layer — Design Spec

**Date:** 2026-04-14
**Status:** Approved
**Author:** Bharat + Claude

## Problem

The trading terminal consumes news but doesn't act on it. 13 spreads sit INACTIVE most days. F&O stock-specific news (mergers, policy, fraud, regulation) flows past undetected. The user gets no intraday feedback on what's happening to their positions or the broader F&O universe.

## Two-Phase Architecture

### Phase 1: Intraday Alert (Real-Time)
News hits → classify → identify affected stocks → Telegram alert.
**No directional opinion.** Just: "This happened. These stocks are affected. Manage your position."

### Phase 2: Overnight Backtest (Evidence)
Same news events get run through the pattern engine overnight.
**Now the system has an opinion:** "This type of news historically moved SBIN +2.3% over 5 days. Recommendation: ADD / CUT / EXIT / NO IMPACT."
Goes into the morning brief.

## News Sources (Priority Order)

1. **BSE Corporate Announcements** — board meetings, mergers, results, insider trades, regulation. Real-time, authoritative, zero junk. BSE RSS feed.
2. **IndianAPI.in** — market news with stock tags. API key already in .env.
3. **Google News RSS** — per-stock search. Free, broad coverage, some junk, 1-2 hour delay.

## Stock Identification: Two Tiers

### Tier 1: Name-Matched (High Confidence)
News headline explicitly mentions a stock name or ticker.
- "HDFC Bank acquires XYZ" → HDFCBANK flagged, HIGH confidence
- "Reliance Jio tariff hike" → RELIANCE flagged, HIGH confidence

### Tier 2: Policy-Mapped (Medium Confidence)
News matches a policy category, mapped to affected sector/stocks.
- "RBI cuts repo rate" → all banks flagged, MEDIUM confidence
- "FAME III EV subsidy announced" → EV stocks flagged, MEDIUM confidence

Policy categories (from existing news_scanner.py + new):
- rbi_policy → Banks (PSU + Private)
- defence_procurement → HAL, BEL, BDL
- ev_policy → EV stocks
- pharma_regulation → Pharma stocks
- oil_policy → OMCs, Upstream
- merger_acquisition → name-matched stock + sector peers
- fraud_investigation → name-matched stock (negative)
- block_deal → name-matched stock
- results_announcement → name-matched stock
- govt_infra_spend → Infra/Power stocks
- rating_action → name-matched stock (upgrade/downgrade)

## Scanning Schedule

### Dynamic Scanning (Option C)
- **Top 40 F&O stocks** — every 15 min (09:30-15:30)
- **Full 213 F&O stocks** — twice daily: 09:25 (morning scan) + 12:30 (mid-session)
- Top 40 = most liquid names covering ~80% of F&O volume

### Per Cycle
1. BSE corporate announcements RSS (all stocks, one feed) — ~2 seconds
2. IndianAPI.in latest news — ~3 seconds
3. Google News RSS for top 40 — ~30 seconds
4. Total: ~35 seconds per 15-min cycle

## Intraday Alert Format (Telegram)

```
NEWS ALERT: [HIGH/MEDIUM]

HDFC Bank to acquire ABC Finance for Rs 2,400 Cr
Source: BSE Filing | 11:42 IST

Affected: HDFCBANK (direct), BAJFINANCE (sector peer)
Category: MERGER_ACQUISITION

Current: HDFCBANK +1.8% today | Your position: Defence vs IT (not directly affected)

Action: Monitor HDFCBANK. No position change required.
```

For position-affecting news:
```
⚠️ NEWS ALERT: [HIGH] — AFFECTS YOUR POSITION

RBI announces 25bps rate cut effective immediately
Source: BSE/RBI | 10:15 IST

Affected: SBIN (+), PNB (+), BANKBARODA (+), HDFCBANK (+), ICICIBANK (+)
Category: RBI_POLICY

Your position: Defence vs IT — NOT directly affected
Related spread: Banks vs IT — historically +3.1% on rate cuts (7 episodes, 71% hit)

Action: Consider entering Banks vs IT if z-score confirms.
Overnight backtest will provide evidence-based recommendation by 04:45 AM.
```

## Overnight Backtest (Pattern Engine Extension)

### New Event Categories Added to Pattern Engine
Current: 18 event categories (escalation, ceasefire, oil_positive, etc.)
New: +11 categories from news intelligence:
- merger_acquisition, fraud_investigation, block_deal
- results_beat, results_miss, rating_upgrade, rating_downgrade
- rbi_rate_cut, rbi_rate_hold, govt_infra_announcement
- sector_regulation_change

### Overnight Flow
1. Collect all intraday news events from `data/news_events_today.json`
2. For each event: look up stock × category in pattern_lookup.json
3. If historical precedent exists: compute forward return expectation
4. Classify: NO_IMPACT / MODERATE / HIGH_IMPACT
5. For HIGH_IMPACT: generate recommendation (ADD / CUT / EXIT)
6. Include in morning brief and Telegram

### News Shelf Life
- News captured intraday is stored with timestamp
- Overnight backtest marks each event as:
  - EXPIRED: price already captured the move (gap > drift)
  - ACTIVE: drift remains after gap (teeth — keep watching)
  - EMERGING: event just announced, no price reaction yet (opportunity)
- ACTIVE events carry forward to next morning brief until either:
  - 5 trading days pass (auto-expire)
  - Price reaches historical mean move (target hit)

## Data Storage

```
pipeline/data/
  news_events_today.json     ← today's classified events (overwritten daily)
  news_events_history.json   ← append-only log (all events + outcomes)
  news_impact_lookup.json    ← historical: event category × stock → returns
```

## Output Destinations

| Output | Destination | Frequency |
|--------|-------------|-----------|
| Intraday alert | Telegram | Real-time on detection |
| News events log | news_events_today.json | Every 15 min |
| Overnight verdict | Morning brief Telegram | 04:45 AM |
| Impact lookup | news_impact_lookup.json | Weekly rebuild |
| Dashboard news | data/fno_news.json (website) | Every 15 min |

## Junk Filter Rules

Hard filters to keep signal clean:
1. Skip headlines < 30 chars (too vague)
2. Skip if no F&O stock name/ticker match AND no policy keyword match
3. Skip "market outlook" / "expert view" / "technical analysis" headlines (opinion, not news)
4. Skip duplicate headlines (same event from multiple sources within 2 hours)
5. Skip headlines older than 6 hours
6. Require BSE filing OR 2+ sources for HIGH confidence classification

## Integration Points

- **Spread Intelligence** — news becomes a modifier signal (±15 score, same as today)
- **Phase C Breaks** — if a correlation break + news event coincide → OPPORTUNITY confidence increases
- **Pattern Engine** — new event categories added to backtest framework
- **Dashboard** — news scroll (already built today) shows latest headlines
- **Morning Brief** — overnight verdicts included in pre-market Telegram

## What This Does NOT Do

- Does NOT auto-execute trades (alert + recommendation only)
- Does NOT replace the regime engine (regime remains the primary gate)
- Does NOT track social media / Twitter (too noisy, junk ratio too high)
- Does NOT generate articles from intraday news (article pipeline stays separate)
- Does NOT override backtest evidence with LLM opinion

## Success Criteria

- At least 5 stock-specific news events detected per trading day
- Zero junk alerts (false positive rate < 5%)
- Overnight backtest processes all intraday events before 04:45 AM
- At least 1 actionable recommendation per week from news-impact analysis
- News events with "teeth" correctly identified >60% of the time (drift > gap)
