# Signal Universe v2 — Design Spec

**Date:** 2026-04-02
**Status:** Approved

---

## Goal

Expand the Anka Research signal pipeline from a purely geopolitical event engine into a two-track system: geopolitical spread signals (existing, extended) and macro-regime spread signals (new). Add a foolproof daily client track record sent automatically every evening. Expand the stock universe to cover macro-sensitive sectors. Apply a consistent colour system to all Telegram output.

---

## Architecture Overview

Three parallel components, built and deployed independently:

```
Component A: Daily Track Record       (EOD report, foolproof, schtask)
Component B: Macro Sentiment Index    (MSI engine + macro signal cards)
Component C: Expanded Stock Universe  (9 new stocks, 5 new spreads)
```

Components A and C are independent. Component B depends on C (new spreads must exist before MSI can select them). A and B+C can be built in parallel.

---

## Component A — Daily Client Track Record

### Purpose
Every trading day at 16:30 IST, automatically send a full P&L report to Telegram. No human intervention required. Runs even on flat days, even if no positions are open. Never silently fails — if it errors, it sends an error notice instead.

### What it shows

**Section 1 — Open Positions**
For each open signal:
- Spread name + tier badge (🔵 SIGNAL / 🟡 EXPLORING)
- Entry date and days held
- Current spread P&L with colour: 🟢 positive, 🟠 within 20% of stop, 🔴 beyond stop
- Stop level (data-derived, from spread_statistics)
- Long legs / short legs with current prices

**Section 2 — Closed This Week**
For each signal closed in the last 7 days:
- Result badge: 🟩 WIN or 🟥 LOSS
- Spread name, final P&L %, days held, exit reason (stopped / expired)

**Section 3 — Running Scorecard**
- Visual win/loss strip: `🟩🟩🟥🟩🟩🟩🟥🟩` (last 20 signals)
- SIGNAL tier: NW wins / NL losses / avg spread return %
- EXPLORING tier: NW wins / NL losses / avg spread return %
- Overall win rate % and total signals tracked

**Section 4 — Macro Context (one line)**
- Today's MSI score and regime label (once Component B is live; omitted until then)
- FII net flow today (₹ cr, colour coded)

### Trigger
- Windows Task Scheduler (`schtasks`) at 16:30 IST on trading days
- New script: `run_eod_report.py`
- Uses `trading_calendar.is_trading_day()` — if not a trading day, sends a brief "market closed" card instead of skipping silently

### Foolproof requirements
- Wraps entire execution in try/except — on any unhandled error, sends a "`⚠️ EOD report failed — {error}`" message to Telegram so the absence of a report is never invisible
- Lockfile pattern (same as run_signals.py) to prevent duplicate sends
- If Telegram send fails, writes to `logs/eod_report_YYYY-MM-DD.txt` as fallback

### New files
- `pipeline/run_eod_report.py` — main script
- `pipeline/telegram_bot.py` — add `format_eod_track_record(open_sigs, closed_sigs, stats)` formatter
- `scripts/eod_track_record.bat` — bat file for schtask
- Update `scripts/setup_tasks.bat` — add AnkaEOD1630 task

---

## Component B — Macro Sentiment Index (MSI)

### Purpose
Score India's macro stress daily on a 0–100 index. When the score crosses a threshold, identify which spreads have historically performed best in similar stress periods and fire a macro signal card.

### MSI Inputs and Weights

| Input | Source | Weight | Stress Direction |
|---|---|---|---|
| FII net flow (₹ cr, 3-day rolling) | NSE JSON API (free) | 30% | Negative outflow = stress |
| India VIX level vs 90-day avg | NSE allIndices API (free) | 25% | VIX > avg = stress |
| USD/INR 5-day change % | EODHD USDINR.FOREX | 20% | INR weakening = stress |
| Nifty 50 30-day return % | EODHD NSEI.INDX | 15% | Declining = stress |
| Brent oil 5-day change % | yfinance BZ=F fallback / MCX scrape | 10% | Rising = stress |

Each input normalised to 0–1 (0 = benign, 1 = maximum stress). MSI = weighted sum × 100.

**Regime thresholds:**
- MSI ≥ 65 → 🔴 MACRO_STRESS
- MSI 35–64 → 🟡 MACRO_NEUTRAL
- MSI < 35 → 🟢 MACRO_EASY

### MSI Visual Bar (in Telegram)
```
MSI: 73/100  🟥🟥🟥🟥🟥🟥🟥🟨⬜⬜  STRESS
```
10-block bar: blocks 1–7 filled 🟥, block 8 🟨 (caution), blocks 9–10 ⬜.
Colour of filled blocks: 🟥 if STRESS, 🟨 if NEUTRAL, 🟩 if EASY.

### Historical Backtest (spread × MSI regime)
Using the existing daily dump files (`data/daily/YYYY-MM-DD.json`), for each spread pair compute:
- Average spread return on days following a STRESS reading
- Average spread return on days following a NEUTRAL reading
- Win rate (% of days spread moved in long direction) per regime

Stored in `data/msi_spread_backtest.json`, recomputed weekly.

### Macro Signal Card trigger
- Fires when MSI crosses from NEUTRAL → STRESS (crossing 65 upward)
- Selects top 2 spreads by historical STRESS-regime win rate (minimum 5 data points)
- One signal card per crossing event (not repeated daily while in STRESS)
- Card format: see Colour System section below

### New files
- `pipeline/macro_stress.py` — MSI computation, NSE data fetch, regime classification
- `pipeline/run_signals.py` — add MSI check to `_run_once_inner()`, fire macro card on regime crossing
- `pipeline/telegram_bot.py` — add `format_macro_signal_card(msi, regime, spreads, backtest)` formatter
- `data/msi_history.json` — daily MSI scores (appended each day)
- `data/msi_spread_backtest.json` — spread performance by regime (weekly recompute)

---

## Component C — Expanded Stock Universe

### New Stocks (9)

| Ticker | EODHD Symbol | Sector | Group | New Spread Role |
|---|---|---|---|---|
| SBI | SBI.NSE | Banking/PSU | neutral | PSU Banks vs Private Banks (long) |
| BANKBARODA | BANKBARODA.NSE | Banking/PSU | neutral | PSU Banks vs Private Banks (long) |
| AXISBANK | AXISBANK.NSE | Banking/Private | neutral | PSU Banks vs Private Banks (short) |
| HINDALCO | HINDALCO.NSE | Metals/Aluminium | winner | Metals vs IT (long) |
| TATASTEEL | TATASTEEL.NSE | Metals/Steel | winner | Metals vs IT (long) |
| JSPL | JSPL.NSE | Metals/Steel PSU | winner | Metals vs Auto (long) |
| HUL | HUL.NSE | FMCG/Defensive | neutral | FMCG vs Cyclicals (long) |
| ITC | ITC.NSE | FMCG/Conglomerate | neutral | FMCG vs Cyclicals (long) |
| BAJFINANCE | BAJFINANCE.NSE | NBFC/Private | loser | Private Finance vs PSU Banks (short) |

All added to `INDIA_SIGNAL_STOCKS` in `config.py` with `yf`, `eodhd`, `sector`, `group` keys.

### New Spreads (5)

| Spread Name | Long | Short | Primary Trigger |
|---|---|---|---|
| PSU Banks vs Private Banks | SBI, BANKBARODA | HDFCBANK, ICICIBANK, AXISBANK | MACRO_STRESS (fiscal risk, NPA fears) |
| Metals vs IT | HINDALCO, TATASTEEL | TCS, INFY | MACRO_STRESS (China commodity cycle, FII rotation) |
| FMCG vs Cyclicals | HUL, ITC | TATAMOTORS, M&M | MACRO_STRESS (defensive flight, inflation) |
| Metals vs Auto | HINDALCO, JSPL | TATAMOTORS, MARUTI | MACRO_STRESS + oil_positive |
| Private Finance vs PSU Energy | BAJFINANCE, HDFCBANK | ONGC, COALINDIA | de_escalation + MACRO_EASY |

Added to `INDIA_SPREAD_PAIRS` in `config.py`.

### Event category → new spread mappings (additions to existing)
- `escalation` + `sanctions` → now also triggers **Metals vs IT** (metals as hard asset / IT as FII exit)
- `de_escalation` + `diplomacy` → now also triggers **Private Finance vs PSU Energy**
- `MACRO_STRESS` → triggers **PSU Banks vs Private**, **Metals vs IT**, **FMCG vs Cyclicals**
- `oil_positive` + `MACRO_STRESS` → **Metals vs Auto** added

---

## Colour System — All Telegram Cards

### Signal type headers
| Type | Header Emoji | Example |
|---|---|---|
| Geopolitical escalation | 🔴 | `🔴 GEOPOLITICAL SIGNAL — ESCALATION` |
| Geopolitical de-escalation | 🟢 | `🟢 GEOPOLITICAL SIGNAL — DE-ESCALATION` |
| Macro stress crossing | 📊 | `📊 MACRO SIGNAL — STRESS REGIME` |
| EOD track record | 📋 | `📋 ANKA DAILY RECORD — 02 Apr 2026` |
| Stop loss | 🚨 | `🚨 STOP LOSS — EXIT NOW` |
| Entry call | 📢 | `📢 ENTRY CALL` |

### P&L colour coding (applied everywhere P&L is shown)
| State | Emoji | Condition |
|---|---|---|
| In profit | 🟢 | spread_pnl_pct > 0 |
| Near stop (warning) | 🟠 | spread_pnl_pct < 0 and within 20% of stop threshold |
| Beyond stop / loss | 🔴 | spread_pnl_pct < stop_level |
| Flat / tiny move | ⚪ | abs(spread_pnl_pct) < 0.1% |

### Tier badges
| Tier | Badge |
|---|---|
| SIGNAL (≥65% hit rate, ≥3 precedents) | 🔵 |
| EXPLORING (below gates) | 🟡 |

### Win/loss strip (track record)
- Win: 🟩
- Loss: 🟥
- Open (ongoing): 🔷
- Example 8-signal strip: `🟩🟩🟥🟩🟩🟩🟥🟩`

### MSI regime colours
| Regime | Colour | Bar blocks |
|---|---|---|
| MACRO_STRESS | 🔴 | 🟥 filled |
| MACRO_NEUTRAL | 🟡 | 🟨 filled |
| MACRO_EASY | 🟢 | 🟩 filled |

---

## Data Sources Summary

| Data | Source | Frequency | Cost |
|---|---|---|---|
| NSE stock prices | EODHD (all .NSE symbols) | 30-min (15-min delayed) | Paid (existing) |
| Nifty 50, S&P 500, Nikkei | EODHD .INDX symbols | 30-min | Paid (existing) |
| USD/INR | EODHD USDINR.FOREX | 30-min | Paid (existing) |
| FII/DII daily flows | NSE JSON API (nseindia.com/api/fiidiiTradeReact) | Daily (post-market) | Free |
| India VIX | NSE allIndices API | 30-min | Free |
| Brent crude | yfinance BZ=F (fallback only — parquet error risk) | 30-min | Free (fragile) |
| EOD historical prices | Daily dump files (data/daily/YYYY-MM-DD.json) | Daily | Existing |

**Brent crude gap:** EODHD macro plan required for Brent on EODHD. Short-term: use `os.environ["YFINANCE_CACHE_DISABLED"] = "1"` + yfinance as workaround. Medium-term: MCX commodity scrape or EODHD plan upgrade.

---

## Telegram Channel Management

As a prerequisite before launching v2 signals, implement a clean channel reset:

- `telegram_bot.py` — add `log_sent_message(chat_id, message_id)` that appends to `data/telegram_message_log.json`
- `telegram_bot.py` — add `clear_channel_messages()` that reads the log and deletes each message via `bot.delete_message()`
- One-shot: `python -c "from telegram_bot import clear_channel_messages; clear_channel_messages()"` to wipe the channel before v2 launch
- From this point forward, all sent messages are logged

---

## Non-Goals (explicitly out of scope)

- Options trading (deferred to future phase)
- Real-time (sub-15 min) price data — 15-min delay acceptable for multi-day spread holding
- AMFI monthly MF redemption data — too slow to be actionable
- RBI macro data (CPI, fiscal deficit) — monthly cadence, better suited to weekly report than signal triggers
- Web UI / dashboard — Telegram is the delivery channel

---

## File Change Summary

| File | Action | Component |
|---|---|---|
| `pipeline/config.py` | Add 9 stocks, 5 spread pairs, update event→spread mappings | C |
| `pipeline/macro_stress.py` | Create — MSI engine, NSE data fetch | B |
| `pipeline/run_eod_report.py` | Create — daily track record script | A |
| `pipeline/run_signals.py` | Add MSI check + macro card trigger | B |
| `pipeline/telegram_bot.py` | Add format_eod_track_record, format_macro_signal_card, message logging, colour system updates | A + B |
| `pipeline/signal_tracker.py` | Add get_weekly_closed_signals() helper | A |
| `scripts/eod_track_record.bat` | Create | A |
| `scripts/setup_tasks.bat` | Add AnkaEOD1630 task | A |
| `data/msi_history.json` | Created at runtime | B |
| `data/msi_spread_backtest.json` | Created at runtime | B |
| `data/telegram_message_log.json` | Created at runtime | Channel reset |
