# Anka Terminal Coherence — Unified Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every data artifact the system already produces — regime, positioning, scanner, news, trust, P&L — reaches every surface that should render it. Stops stop losing trades not winning ones. Website narrates what the book actually did. Nothing ships live without a backtest behind it.

**Architecture:** 15 wiring gaps across 4 phases (data integrity → model coherence → ops → UX) + docs. Each phase composes on the previous one. No new data sources. No new math that isn't backtested against historical replay before it can gate a live trade. This replaces the separate `2026-04-22-spread-bootstrap.md` and the unwritten pin-workflow plan — both are folded in.

**Tech Stack:** Python 3.13 / pytest / FastAPI / vanilla-JS ES modules / pandas-numpy / EODHD / Kite / Windows Task Scheduler.

**Fix-order (user's standing rule from `memory/feedback_fix_order_data_model_ops_first.md`):** data → model → ops → UX.

**Backtest-first mandate (`memory/feedback_scientific_validation.md`):** every change to stop logic, gate logic, or conviction scoring ships with a backtest task that proves the new behavior outperforms the old against ≥60 historical samples. The backtest is a gating dependency on the live rollout, not an afterthought.

---

## Gap inventory

| # | Phase | Gap | Observed symptom | ETA |
|---|-------|-----|-------------------|-----|
| W5 | A data | `today_regime.zone` key rename leaves consumers blind | Dashboard shows regime None | 30m |
| W2 | A data | New spreads never get stats; only known ones refresh Sunday | Pharma vs Banks / Banks vs IT / Reliance vs OMCs → INSUFFICIENT_DATA | 2h |
| W12 | A data | `fno_news.json` not derived from `news_verdicts.json` | Website News panel empty despite 185 fresh verdicts | 1h |
| W11 | A data | Market-segment articles not generated; only war/epstein | `articles_index.json`: 15/15 editorial, 0/15 market | 2h |
| W1 | B model | Gate output (conviction, z) not written back into `eligible_spreads` | All 6 static spreads show NONE in Trading tab | 1h |
| W7 | B model | News verdicts don't modify candidate scoring | News panel populates but nothing acts on it | 2h |
| W8 | B model | Trust scores not consumed at candidate scoring | 210 grades computed, zero influence on what trades | 1h |
| W9 | B model | Daily stop fires on single-day move, killing multi-day winners | Sovereign Shield Alpha +11.11%→forced exit on single -1.10% day | 2h + backtest |
| W10 | B model | Trail stop doesn't dominate daily stop after arming | Fossil Arbitrage +7.07%→-4.04% no retrace protection | 1h + backtest |
| W3 | C ops | 532 scanner signals never meet confluence gate | UNCERTAIN / HOLD across the board | 3h + backtest |
| W14 | C ops | No post-mortem artifact per closed trade | Fossil peak→final lesson ungathered, unpublishable | 1h |
| W4 | D UX | OI/PCR has no UI surface | Options tab shows only empty leverage matrices | 1h |
| W6 | D UX | Ticker cells not clickable to TA detail | User has to type ticker into TA search manually | 2h |
| W13 | D UX | No narrative generator from book state | Book up +8.66% on Sovereign, website silent on it | 3h |
| W15 | D UX | No article mix discipline | 15/15 war-epstein, public reads as doom-only | 1h |
| Z  | Z docs | SYSTEM_OPERATIONS_MANUAL + MEMORY + inventory sync | Doc-sync mandate | 1h |

Total: ~24 hours execution (plus backtest compute time, parallelizable).

---

## Phase A — Data Integrity

### Task A5: `today_regime` key rename — restore `zone`

**Problem:** `pipeline/data/today_regime.json` has a `regime` key but no `zone`. Multiple consumers (scenario-strip.js, `/api/candidates`, banner) read `.zone`. Terminal renders `None`.

**Files:**
- Modify: `pipeline/regime_scanner.py` — write BOTH keys for one release cycle, then fix consumers.
- Modify: any consumer reading `today_regime["zone"]` — grep for it.

- [ ] **Step 1: Grep every consumer**

```bash
cd pipeline && grep -rn "today_regime.*zone\|\.zone\|\"zone\"" --include="*.py" --include="*.js" | grep -v ".git\|node_modules"
```

- [ ] **Step 2: Write a failing test**

```python
# pipeline/tests/test_today_regime_schema.py
import json
from pathlib import Path

def test_today_regime_has_zone_key():
    p = Path(__file__).resolve().parent.parent / "data" / "today_regime.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data.get("zone"), "today_regime.json must expose 'zone' (consumers read it)"
    # Both keys acceptable during transition
    assert data.get("zone") == data.get("regime")
```

- [ ] **Step 3: Fix writer**

In `pipeline/regime_scanner.py` around line 219 (the `today_regime = {...}` assignment), include:

```python
today_regime = {
    "timestamp": ...,
    "zone": etf_regime,       # canonical
    "regime": etf_regime,     # alias for legacy consumers
    ...
}
```

- [ ] **Step 4: Run test — pass**

- [ ] **Step 5: Audit consumers** — confirm every `"zone"` reader now succeeds. Remove `.regime` fallbacks from consumers that read `.zone`.

- [ ] **Step 6: Commit**
```
fix(regime): write canonical `zone` key to today_regime.json

Consumers across UI + API read .zone; writer was emitting only .regime.
Both keys written for one release cycle to avoid breaking callers we miss.
```

ETA: 30 min.

---

### Task A2: Spread stats same-day backfill (tiered)

Replaces `docs/superpowers/plans/2026-04-22-spread-bootstrap.md` — full content lives here. Reference the file map / test pattern from that draft; porting verbatim would double-document.

**Summary:**
- New module `pipeline/spread_bootstrap.py` with `ensure(name, long_legs, short_legs)`, `tier_from_n(n)`.
- Constants: `MIN_SAMPLES_FULL=30`, `MIN_SAMPLES_PROVISIONAL=15`. Below 15, dropped at write.
- Called from `regime_scanner.scan_regime()` inline after `eligible_spreads` is built.
- Defensive `_maybe_bootstrap` from `spread_intelligence.compute_gate`.
- `spread_statistics.compute_regime_stats` aligned to same floor.

Tier is read-time only: on-disk schema stays `{n_samples, mean, std}`; tier derived via `tier_from_n`.

**Tests (new file `pipeline/tests/test_spread_bootstrap.py`):**
- `test_ensure_tiers_buckets_by_sample_count` — 40/20/10 sample fixture; expects FULL + PROVISIONAL + dropped.
- `test_ensure_skips_if_already_present`
- `test_ensure_returns_skipped_on_fetch_failure`
- `test_regime_scanner_calls_bootstrap_for_unknown_spreads`
- `test_gate_calls_bootstrap_when_stats_missing`

**Commits (3):**
1. `feat(spread_bootstrap): same-day backfill with FULL/PROVISIONAL tiering`
2. `feat(regime_scanner): bootstrap unknown eligible_spreads inline`
3. `feat(spread_intelligence): defensive bootstrap before INSUFFICIENT_DATA`

ETA: 2h.

---

### Task A12: `fno_news.json` exported from `news_verdicts.json`

**Problem:** `data/fno_news.json` is empty (0 items). `pipeline/data/news_verdicts.json` has 185 rows with category, symbol, recommendation, impact. The website expects HIGH_IMPACT + MODERATE rows with ADD/CUT recommendations. No exporter wires the two.

**Files:**
- Modify: `pipeline/website_exporter.py` — add `export_fno_news()`.
- Create: `pipeline/tests/test_fno_news_export.py`.

- [ ] **Step 1: Failing test**

```python
# pipeline/tests/test_fno_news_export.py
import json, pathlib
def test_fno_news_carries_high_impact_verdicts(tmp_path, monkeypatch):
    verdicts = [
        {"symbol": "SUZLON", "category": "results_announcement", "recommendation": "ADD", "impact": "HIGH_IMPACT", "event_title": "Q4 beat"},
        {"symbol": "X",     "category": "x",                     "recommendation": "NO_ACTION", "impact": "LOW", "event_title": "x"},
    ]
    vfile = tmp_path / "nv.json"; vfile.write_text(json.dumps(verdicts))
    out = tmp_path / "fno.json"
    from pipeline.website_exporter import export_fno_news
    export_fno_news(source=vfile, out=out)
    rows = json.loads(out.read_text(encoding="utf-8"))
    assert len(rows) == 1
    assert rows[0]["ticker"] == "SUZLON"
    assert rows[0]["direction"] in ("ADD", "CUT")
```

- [ ] **Step 2: Implement `export_fno_news`**

```python
def export_fno_news(source: Path = None, out: Path = None) -> int:
    source = source or VERDICTS_FILE
    out = out or (DATA_OUT / "fno_news.json")
    if not source.exists(): return 0
    rows_in = json.loads(source.read_text(encoding="utf-8"))
    rows_out = []
    for v in rows_in:
        if v.get("impact") not in ("HIGH_IMPACT", "MODERATE"): continue
        if v.get("recommendation") not in ("ADD", "CUT"): continue
        rows_out.append({
            "ticker": v.get("symbol"),
            "category": v.get("category"),
            "direction": v.get("recommendation"),
            "impact": v.get("impact"),
            "title": v.get("event_title", ""),
            "hit_rate": v.get("historical_avg_5d"),
        })
    rows_out.sort(key=lambda r: (r.get("impact") != "HIGH_IMPACT", -(r.get("hit_rate") or 0)))
    out.write_text(json.dumps(rows_out, indent=2, ensure_ascii=False), encoding="utf-8")
    return len(rows_out)
```

- [ ] **Step 3: Wire into `website_exporter.main()`** — call `export_fno_news()` alongside `export_live_status()`.

- [ ] **Step 4: Run — test passes; manually verify file populates**

- [ ] **Step 5: Commit**
```
feat(website_exporter): derive fno_news from news_verdicts

HIGH_IMPACT + MODERATE verdicts with ADD/CUT recommendations flow into
data/fno_news.json. Previously empty despite 185 fresh verdicts daily.
```

ETA: 1h.

---

### Task A11: Market-segment daily article generation

**Problem:** `data/articles_index.json` has 15 articles, 100% in `war` + `epstein` segments. No market/trading content published. `AnkaDailyArticles` (04:45) generates from chat exports → vault pillars; the pipeline for market segment was never built.

**Files:**
- Modify: `pipeline/daily_articles.py` (or wherever article generation lives)
- Create: `pipeline/market_article_generator.py`
- Create: `pipeline/tests/test_market_article_generator.py`

- [ ] **Step 1: Survey** — read `pipeline/daily_articles.py`. Understand segment dispatch. Identify where a new segment can be plugged in.

- [ ] **Step 2: Write `market_article_generator.py`** that composes a daily market article from today's book state:
  - `today_regime.json` — zone + eligible_spreads
  - `live_status.json` — open positions + peaks
  - `closed_signals.json` — last 7d closed trades
  - `news_verdicts.json` — top 5 HIGH_IMPACT events
  - `correlation_breaks.json` — top 3 z-score outliers with confluence

Output: a Jinja-rendered HTML article `articles/2026-04-22-markets.html` written to disk and an entry appended to `articles_index.json` with `segment: "markets"`, `color: "#d4a855"` (gold), `category: "MARKET SNAPSHOT"`.

- [ ] **Step 3: Failing test**

```python
def test_market_article_reflects_book_state(tmp_path, monkeypatch):
    # Fixture: 1 open position +5%, 1 closed -1%, 1 high-impact news
    ...
    result = generate_market_article(target_date="2026-04-22")
    html = result["html"]
    assert "Sovereign Shield Alpha" in html
    assert "+5.14%" in html or "+5.1%" in html
    assert "SUZLON" in html
```

- [ ] **Step 4: Wire into scheduled task** — `daily_articles.py` invokes `market_article_generator.generate(today)` after war/epstein passes.

- [ ] **Step 5: Commit**
```
feat(daily_articles): generate daily markets segment from book state

New article type 'markets' summarizes open positions, closed trades,
top news verdicts, and flagged correlation breaks. Website article mix
no longer 100% war/epstein.
```

ETA: 2h.

---

## Phase B — Model Coherence

### Task B1: Gate output written back into `eligible_spreads`

**Problem:** `eligible_spreads[name]` carries `best_win, 1d_win, ...` but no `conviction`, `z_score`, or `gate_status`. Candidate builder (`candidates.py:39`) falls back to `NONE` for every row.

**Files:**
- Modify: `pipeline/regime_scanner.py` — after bootstrap + before writing today_regime, run gate for each eligible spread and annotate.
- Create: `pipeline/tests/test_eligible_spreads_annotated.py`.

- [ ] **Step 1: Failing test**

```python
def test_eligible_spreads_carry_conviction_and_z(monkeypatch, tmp_path):
    # Fixture: eligible_spreads has 1 entry, spread_stats has matching bucket
    ...
    from regime_scanner import scan_regime
    result = scan_regime(...)
    entry = result["eligible_spreads"]["Pharma vs Banks"]
    assert "conviction" in entry         # HIGH / MEDIUM / LOW / PROVISIONAL / NONE
    assert "z_score" in entry
    assert "gate_status" in entry        # DIVERGENT / AT_MEAN / INSUFFICIENT_DATA / ...
    assert "tier" in entry               # FULL / PROVISIONAL (from spread_bootstrap)
```

- [ ] **Step 2: Implement annotation**

In `regime_scanner.py` — after Task A2's bootstrap call, before `_TODAY_REGIME_FILE.write_text(...)`:

```python
from spread_intelligence import gate_spread
from spread_bootstrap import tier_from_n

for name, entry in eligible_spreads.items():
    today_return = _compute_today_spread_return(name, entry["long_legs"], entry["short_legs"])
    gate_result = gate_spread(
        spread_name=name,
        regime_data={"eligible_spreads": eligible_spreads, "regime": etf_regime},
        spread_stats=spread_stats,
        regime=etf_regime,
        today_spread_return=today_return,
    )
    entry["gate_status"] = gate_result.get("status")
    entry["z_score"] = gate_result.get("z_score")
    # Conviction from z + hit_rate:
    # HIGH if |z|>=2 AND best_win>=65%
    # MEDIUM if |z|>=1.5 AND best_win>=55%
    # LOW if in-gate but below thresholds
    # PROVISIONAL if the matched regime bucket is provisional tier
    matched_bucket = spread_stats.get(name, {}).get("regimes", {}).get(etf_regime, {})
    entry["tier"] = tier_from_n(matched_bucket.get("n_samples", 0))
    entry["conviction"] = _classify_conviction(entry, gate_result)
```

- [ ] **Step 3: Implement `_classify_conviction` with explicit thresholds** (document them in a module docstring).

- [ ] **Step 4: Run test — pass**

- [ ] **Step 5: Commit**
```
feat(regime_scanner): annotate eligible_spreads with gate output

Every spread now carries conviction / z_score / gate_status / tier
inline — candidate builder reads these directly, ending the NONE
default across the Trading tab.
```

ETA: 1h.

---

### Task B7: News verdicts modify candidate conviction

**Problem:** `news_verdicts.json` carries 185 daily verdicts with HIGH_IMPACT / MODERATE tags and ADD/CUT recommendations tied to (symbol, category). No consumer at the conviction-scoring layer looks at them. A stock with a HIGH_IMPACT ADD headline today gets no uplift in its signal score.

**Files:**
- Modify: `pipeline/signal_enrichment.py` — add `_news_modifier(signal) -> int` returning score delta.
- Modify: `pipeline/regime_scanner.py::_classify_conviction` to consume verdicts for spreads too.

- [ ] **Step 1: Failing test**

```python
def test_news_add_lifts_candidate_score(tmp_path, monkeypatch):
    verdicts = [{"symbol": "SUZLON", "category": "results_announcement", "recommendation": "ADD", "impact": "HIGH_IMPACT"}]
    # Candidate on SUZLON with entry_score=50, category matches
    signal = {"ticker": "SUZLON", "category": "results_announcement", "entry_score": 50, ...}
    from signal_enrichment import apply_news_modifier
    enriched = apply_news_modifier(signal, verdicts)
    assert enriched["news_modifier"] == 10   # HIGH_IMPACT + ADD = +10
    assert enriched["entry_score"] == 60
```

- [ ] **Step 2: Implement with explicit rules**
  - HIGH_IMPACT + ADD aligned with direction: `+10`
  - MODERATE + ADD aligned: `+5`
  - HIGH_IMPACT + CUT opposite to position direction: `-10` (fade signal)
  - No match: `0`

- [ ] **Step 3: Wire into candidates builder** — `candidates.py:_build_static_spreads` and Phase B ranker both apply the modifier.

- [ ] **Step 4: Commit**
```
feat(signal_enrichment): news verdicts modify candidate conviction

HIGH_IMPACT / MODERATE verdicts with ADD or CUT recommendations adjust
the candidate's entry_score when (symbol, category) matches. Captures
news impact directly in the trade grade instead of leaving it decorative.
```

ETA: 2h.

---

### Task B8: Trust scores consumed at conviction time

**Problem:** `data/trust_scores.json` has grades A/B/C/D/F for 210 tickers. `signal_enrichment` reads them but only for display — they don't feed the gate/conviction.

**Per `memory/project_scorecard_alpha_test.md`:** "Grade is NOT standalone alpha. D/F outperform A/B overall. Only works as regime-conditional modifier in NEUTRAL."

**Files:**
- Modify: `pipeline/signal_enrichment.py::gate_signal` to apply conditional trust modifier.

- [ ] **Step 1: Failing test**

```python
def test_trust_modifier_neutral_regime(monkeypatch):
    # NEUTRAL regime + D-grade + LONG → slight penalty (conditional alpha per memory)
    signal = {"ticker": "X", "trust_grade": "D", "direction": "LONG", "entry_score": 60}
    regime = {"zone": "NEUTRAL"}
    from signal_enrichment import apply_trust_modifier
    out = apply_trust_modifier(signal, regime)
    assert out["entry_score"] == 55       # -5 penalty
    assert out["trust_modifier"] == -5

def test_trust_modifier_non_neutral_is_zero():
    signal = {"ticker": "X", "trust_grade": "A", "direction": "LONG", "entry_score": 60}
    regime = {"zone": "RISK-OFF"}
    from signal_enrichment import apply_trust_modifier
    out = apply_trust_modifier(signal, regime)
    assert out["trust_modifier"] == 0      # no modifier outside NEUTRAL
    assert out["entry_score"] == 60
```

- [ ] **Step 2: Implement** — in NEUTRAL only; A/B → `+0`, C → `0`, D/F → `-5` for LONG side, `+5` for SHORT side (fade low-trust on the long side). Thresholds per backtest.

- [ ] **Step 3: Backtest task**

```python
# pipeline/tests/backtest/test_trust_modifier_edge.py
# Replay 60 days of signals through apply_trust_modifier vs no-modifier.
# Success: Sharpe improves by ≥0.1 in NEUTRAL regime cohort.
```

- [ ] **Step 4: Commit**
```
feat(signal_enrichment): trust grade as conditional modifier in NEUTRAL

Per scorecard_alpha_test memory: trust is only edge in NEUTRAL regime.
A/B +0, D/F -5 on LONG / +5 on SHORT. Backtest confirms Sharpe lift.
```

ETA: 1h + backtest runtime.

---

### Task B9: Stop hierarchy redesign — trail dominates once armed

**Problem:** Observed in `closed_signals.json`:
- Sovereign Shield Alpha: held 13 days, peaked +11.11%, closed +8.66% on a single -1.10% daily move (daily stop -0.98% triggered). Position was still deeply profitable.
- Fossil Arbitrage: peaked +7.07%, round-tripped to -4.04% with no trail intervention.

Current logic (`pipeline/signal_tracker.py`): daily stop and trail stop both live as fields; checks happen independently. Whichever evaluates to "stop triggered" first wins. Daily stop is always evaluated, so it can kill a winning multi-day trade on a single bad day.

**Design (user-approved structure):**

| Condition | Active stop |
|-----------|-------------|
| Peak ≤ daily_stop_magnitude | daily_stop (protects entries) |
| Peak > daily_stop_magnitude AND trail not armed | trail arms; daily still protects floor |
| Trail armed | **trail_stop dominates**; daily becomes inactive |

Once trail arms, the question is "did we give back too much of the peak?" not "did we have a bad single day?"

**Files:**
- Modify: `pipeline/signal_tracker.py::check_signal_status` — stop hierarchy block.
- Modify: `pipeline/signal_tracker.py` — log which stop triggered + why.

- [ ] **Step 1: Failing test — reproduces Sovereign case**

```python
def test_trail_dominates_daily_stop_on_winning_position():
    signal = {"ticker": "X", "spread_pnl_pct": 8.66, "peak_pnl": 11.11,
              "daily_stop_pct": -0.98, "trail_stop_pct": 5.50, ...}
    today_return = -1.10   # single-day move
    result = check_signal_status(signal, today_return)
    # Trail armed (peak>|daily|), daily should NOT fire; trail still above current
    assert result["status"] == "OPEN"
    assert "trail" in result.get("evaluated", "").lower()

def test_trail_stop_fires_on_peak_retracement():
    signal = {"ticker": "X", "spread_pnl_pct": 5.40, "peak_pnl": 11.11,
              "daily_stop_pct": -0.98, "trail_stop_pct": 5.50, ...}
    today_return = -1.10
    result = check_signal_status(signal, today_return)
    assert result["status"] == "STOPPED_OUT"
    assert "trail" in result.get("stop_reason", "").lower()
```

- [ ] **Step 2: Run — expect fail**

- [ ] **Step 3: Implement the hierarchy in `check_signal_status`**

```python
# Pseudocode; see existing variables for exact names
daily_mag = abs(daily_stop_pct or 0)
trail_armed = (peak_pnl or 0) > daily_mag

if trail_armed:
    # Trail dominates. Daily stop is inert once the position proved it can run.
    if current_pnl <= trail_stop_pct:
        return ("STOPPED_OUT_TRAIL", current_pnl)
else:
    # Pre-profit: daily stop is the floor.
    if today_return <= daily_stop_pct:
        return ("STOPPED_OUT_DAILY", current_pnl)
```

- [ ] **Step 4: Run — tests pass**

- [ ] **Step 5: BACKTEST**

```python
# pipeline/tests/backtest/test_stop_hierarchy_replay.py
# Replay last 60 closed signals from closed_signals.json through the
# new hierarchy. Assert:
#   - Count of positions closed while net PnL was positive drops by
#     at least 50% vs the old logic
#   - Total realized P&L over replay window is ≥ old logic's total
# Output a diff table to backtest_results/stop_hierarchy_2026-04-22.csv
```

- [ ] **Step 6: Commit — code only, data later**
```
feat(signal_tracker): trail stop dominates daily stop once armed

Trail arms when peak exceeds daily_stop magnitude. Once armed, daily
stop is inert — only trail can close. Fixes Sovereign Shield Alpha
pattern: +11.11% peak killed on a single -1.10% day.
```

- [ ] **Step 7: Backtest commit**
```
test(backtest): stop hierarchy replay proves +X% realized PnL vs old
```

ETA: 2h + backtest runtime.

---

### Task B10: Trail stop arming logic fix

**Problem:** `Fossil Arbitrage: peak +7.07% → final -4.04%, no trail fired during the 11-point retrace`. The trail either never armed or the computation stayed anchored to an old peak.

**Files:**
- Modify: `pipeline/signal_tracker.py` — the `update_trail_stop(signal, today_pnl)` function.

- [ ] **Step 1: Inspect current logic** — read the existing trail function. Document the armed-vs-not state.

- [ ] **Step 2: Failing test — repeat the Fossil pattern**

```python
def test_trail_tracks_peak_and_fires_on_retracement():
    seq = [0.5, 3.0, 5.5, 7.07, 5.0, 2.0, -1.0, -4.04]
    signal = {..., "daily_stop_pct": -1.19, "spread_pnl_pct": seq[0]}
    for v in seq[1:]:
        signal = update_trail_stop(signal, v)
    # Trail should have armed around 2-3% (peak>|daily|=1.19)
    assert signal["trail_armed"] is True
    # Trail should have fired well before -4.04% — no later than -1% retrace from peak 7.07
    # i.e., trail_stop should be at or above ~5% at some point, so the closing check fires there
    assert signal["trail_stop_pct"] >= 3.0
```

- [ ] **Step 3: Fix — arm when peak > daily_stop_magnitude; ratchet up on every new peak; compute trail as `peak - (avg_favorable * sqrt(days_since_arm))`**.

- [ ] **Step 4: BACKTEST** — replay same 60 trades, show profit-capture ratio (realized / peak) improves.

- [ ] **Step 5: Commit**
```
fix(signal_tracker): trail stop arms when peak > daily_stop magnitude

Fossil Arbitrage pattern — +7.07% peak → -4.04% close without trail
firing — was the trail never arming. Now arms at first peak above daily
stop magnitude and ratchets up on subsequent peaks.
```

ETA: 1h + backtest.

---

## Phase C — Ops (signal assembly)

### Task C3: Confluence gate — scanner → pin-worthy

**Problem:** 532 scanner signals today; zero become trades. `UNCERTAIN` / `HOLD` across the board.

**Design — multi-source confluence gate, NONE of which alone is sufficient, ALL of which must align:**

1. **Scanner side:** `|z_score| >= 2.0` AND `action in {REDUCE, ADD, FADE}` — scanner's own confidence filter.
2. **OI side** (from `positioning.json`):
   - For LONG thesis (mean-revert oversold): `PCR ≤ 0.60` OR pin label `STRONG_PIN` with pin strike ≤ 2% above LTP.
   - For SHORT thesis (mean-revert overbought): `PCR ≥ 1.40` OR pin label `STRONG_PIN` with pin strike ≤ 2% below LTP.
3. **TA side** (from `pipeline/data/ta_fingerprints/<ticker>.json`): at least one pattern with `win_rate ≥ 60%` same direction in last-7d lookback.
4. **Regime-fit side:** ticker's sector NOT on the opposite side of any eligible_spread. (HCLTECH is IT, IT is SHORT leg in Banks-vs-IT → LONG HCLTECH fails regime fit.)
5. **News blackout side:** no HIGH_IMPACT verdict on this ticker with contradictory direction in last 2 days.
6. **Time-of-day side:** current IST < 13:30 (gives 1h+ runway before 14:30 auto-close).
7. **Sector concentration side:** no more than 2 active pins per sector.

Anything failing any of the 7 → confluence score < 7 → not pin-worthy.

**Files:**
- Create: `pipeline/intraday_pin.py` with `check_confluence(ticker, direction) -> dict`.
- Create: `pipeline/terminal/api/pin.py` with `POST /api/pin` (writes `pipeline/data/intraday_pins.json`).
- Modify: `pipeline/signal_tracker.py` — handle new source `INTRADAY_PIN` with `TIME_STOP_1430` exit trigger (reuse Phase C shadow close machinery; generalize trigger to `TIME_STOP_<HHMM>`).
- Modify: positions-table.js — render source badge `INTRADAY_PIN` + exit `TIME_STOP 14:30`.
- Create: tests for each layer.

- [ ] **Step 1: Failing test for `check_confluence`**

```python
def test_hcltech_long_fails_regime_fit(monkeypatch):
    # HCLTECH in IT; IT on SHORT side of eligible spreads → fail
    monkeypatch.setattr("intraday_pin._get_eligible_spreads",
                        lambda: {"Banks vs IT": {"long_legs":["HDFCBANK"],"short_legs":["TCS","INFY","HCLTECH"]}})
    result = check_confluence("HCLTECH", direction="LONG")
    assert result["confluence_score"] < 7
    assert "regime_fit_fail" in result["fails"]
```

Plus a "green path" test: mock all 7 layers positive, assert `confluence_score == 7` and `result["status"] == "PIN_WORTHY"`.

- [ ] **Step 2: Implement 7-layer gate**

- [ ] **Step 3: `POST /api/pin` endpoint** — idempotent by ticker; writes entry to intraday_pins.json with `open_ltp`, `direction`, `confluence_snapshot`, `open_timestamp`, `exit_trigger: "TIME_STOP_1430"`.

- [ ] **Step 4: Signal-tracker integration** — new source class; trail stop armed from minute 1 (not day-2); TIME_STOP_<HHMM> generic trigger; auto-close at the specified time at LTP.

- [ ] **Step 5: BACKTEST — confluence gate replay**

```python
# pipeline/tests/backtest/test_confluence_gate_edge.py
# Replay last 60 days of scanner signals through check_confluence().
# For every day, count:
#   - signals that would have been pinned
#   - of those, what would next-day realized return have been
#   - win rate > 55% required to ship live
# Output backtest_results/confluence_gate_2026-04-22.csv with per-day results.
```

- [ ] **Step 6: Commit (3 separate)**

1. `feat(intraday_pin): 7-layer confluence gate (regime + TA + OI + news + time + sector)`
2. `feat(terminal): POST /api/pin endpoint + intraday_pins.json storage`
3. `feat(signal_tracker): INTRADAY_PIN source + TIME_STOP_<HHMM> exit trigger`
4. `test(backtest): confluence gate replay proves ≥ 55% win rate`

ETA: 3h + backtest runtime.

---

### Task C14: Post-mortem artifact per closed trade

**Problem:** Closed trades flow into `closed_signals.json` but no human-readable post-mortem is captured. Fossil's peak→final lesson is invisible.

**Files:**
- Create: `pipeline/trade_postmortem.py` — generates markdown per close.
- Modify: `pipeline/eod_review.py` — calls post-mortem for each close today.

- [ ] **Step 1: Failing test**

```python
def test_postmortem_captures_peak_to_final_gap():
    trade = {"spread_name": "Fossil Arbitrage", "peak_pnl": 7.07, "final_pnl": -4.04,
             "daily_stop_pct": -1.19, "exit_reason": "Daily stop"}
    md = render_postmortem(trade)
    assert "peak" in md.lower() and "7.07" in md
    assert "final" in md.lower() and "-4.04" in md
    assert "surrendered" in md.lower() or "gave back" in md.lower()
    # Should name the lesson: "trail did not arm" or similar
    assert "trail" in md.lower()
```

- [ ] **Step 2: Implement** — template captures entry, peak, final, days, exit_reason, and a rule-based "lesson" line (trail didn't arm, daily stopped a winner, clean mean-reversion target, etc.).

- [ ] **Step 3: Write to `articles/postmortem-<date>-<slug>.md`** and append to `articles_index.json` as `segment: "postmortem"`.

- [ ] **Step 4: Commit**
```
feat(trade_postmortem): per-close markdown with peak/final + lesson

Every close in eod_review writes a post-mortem. Feeds into articles_index
so website publishes what the book did, not just what editorial thinks.
```

ETA: 1h.

---

## Phase D — UX

### Task D4: OI/PCR panel in Options tab

**Problem:** `positioning.json` has 212 stocks, fresh; `/api/oi` + `/api/oi/pins/top` exist; zero JS calls either.

**Files:**
- Modify: `pipeline/terminal/static/js/pages/options.js` — add OI panel above leverage-matrix block.

- [ ] **Step 1: Failing Node test**

```python
# pipeline/tests/terminal/test_options_oi_panel.py
# Mock /api/oi response; assert rendered HTML contains ticker + pcr + pin_label.
```

- [ ] **Step 2: Implement**

```javascript
async function renderOIPanel(container) {
  const data = await get('/oi?limit=20');
  const rows = data.rows
    .filter(r => r.pinning?.pin_label !== 'UNRELIABLE')
    .sort((a, b) => Math.abs(a.pinning?.pin_distance_pct || 99) - Math.abs(b.pinning?.pin_distance_pct || 99))
    .slice(0, 12);
  const tbody = rows.map(r => `
    <tr>
      <td>${r.symbol}</td>
      <td class="mono">${r.ltp?.toFixed(2) ?? '—'}</td>
      <td class="mono">${r.pcr?.toFixed(2) ?? '—'}</td>
      <td>${r.sentiment ?? '—'}</td>
      <td>${r.pinning?.pin_label ?? '—'}</td>
      <td class="mono">${r.pinning?.pin_strike ?? '—'}</td>
      <td class="mono">${(r.pinning?.pin_distance_pct ?? 0).toFixed(2)}%</td>
      <td class="mono">${r.pinning?.days_to_expiry ?? '—'}</td>
    </tr>`).join('');
  container.insertAdjacentHTML('afterbegin', `
    <div class="card"><h3>Positioning (OI + PCR, closest to pin)</h3>
    <table class="data-table"><thead><tr>
      <th>Ticker</th><th>LTP</th><th>PCR</th><th>Sentiment</th>
      <th>Pin</th><th>Strike</th><th>Dist%</th><th>DTE</th>
    </tr></thead><tbody>${tbody}</tbody></table></div>`);
}
```

- [ ] **Step 3: Commit**
```
feat(options): OI/PCR panel consumes /api/oi

Data was flowing (212 stocks/15min) but no UI rendered it. Panel shows
top 12 stocks closest to pin, sortable, PCR + sentiment + DTE inline.
```

ETA: 1h.

---

### Task D6: Click-to-TA on ticker cells

**Problem:** Every ticker mention (positions table, candidates, breaks, news) is plain text. User must copy-paste into TA search.

**Files:**
- Modify: positions-table.js, candidates-table.js, news.js, scanner.js — every ticker → `<a class="ticker-link" data-ticker="HAL">HAL</a>`.
- Modify: `pipeline/terminal/static/js/app.js` — delegated listener for `.ticker-link` click → navigates to `#ta?ticker=<T>`.
- Modify: `pages/ta.js` — reads query param, loads that ticker automatically.

- [ ] **Step 1: Failing Node test (click handler)**

- [ ] **Step 2: Implement delegated listener + query-param handling**

- [ ] **Step 3: Commit**
```
feat(terminal): ticker cells are links to TA detail

One delegated listener routes every <a.ticker-link data-ticker> to
#ta?ticker=T. Positions/candidates/breaks/news all participate.
```

ETA: 2h.

---

### Task D13: Narrative generator from book state

**Problem:** Market is making moves; website publishes nothing about them. Articles are 100% editorial (war/epstein). Book activity is invisible to the public.

**Architecture:** A daily narrator that takes book state + news + regime as input and emits a market-segment HTML article. Runs at EOD (16:15). Uses Gemini 2.5 Flash (primary LLM per `memory/reference_llm_providers.md`), Haiku fallback.

**Files:**
- Create: `pipeline/narrative/market_narrator.py`
- Create: `pipeline/narrative/prompt_templates.py`
- Create: `pipeline/tests/test_market_narrator.py`

- [ ] **Step 1: Schema for input bundle** — dict with keys `regime`, `open_positions`, `closed_today`, `news_top5`, `breaks_top3`, `track_record_7d`. Assembled from the existing JSON files.

- [ ] **Step 2: Prompt template** — disciplined, short, factual, no hype. Output format: HTML article body with headline, lede, regime-para, positions-para, closed-para, news-para, forward-looking-para.

- [ ] **Step 3: Failing test**

```python
def test_narrator_mentions_open_positions_and_closes(mock_llm):
    bundle = {
        "regime": {"zone": "NEUTRAL"},
        "open_positions": [{"spread_name": "Sovereign Shield Alpha", "spread_pnl_pct": 5.14, ...}],
        "closed_today": [{"spread_name": "Energy Chain", "final_pnl": -1.58}],
        ...
    }
    mock_llm.return_value = "<h1>Markets</h1><p>Sovereign Shield Alpha +5.14%...</p>"
    article = generate_market_article(bundle)
    assert "Sovereign Shield Alpha" in article["html"]
    assert "Energy Chain" in article["html"]
    assert "+5.14%" in article["html"]
```

- [ ] **Step 4: Wire into `AnkaEODReview` (16:00) or `AnkaEODTrackRecord` (16:15)** — after track record writes, narrator composes the article.

- [ ] **Step 5: Commit**
```
feat(narrative): market_narrator composes daily book-state article

EOD narrator ingests regime + open + closed + news + breaks, produces
HTML via Gemini, appends to articles_index with segment='markets'.
Public site now narrates what the book did every day.
```

ETA: 3h.

---

### Task D15: Website article mix discipline

**Problem:** 15/15 articles are `war` + `epstein`. No editorial rule that the homepage carries a balanced mix.

**Files:**
- Modify: `pipeline/website_exporter.py::export_articles_index` — enforce per-segment quota for the homepage view.

- [ ] **Step 1: Add config**

```python
ARTICLE_MIX_POLICY = {
    "markets":    {"min_homepage": 1, "max_homepage": 4},
    "war":        {"min_homepage": 0, "max_homepage": 3},
    "epstein":    {"min_homepage": 0, "max_homepage": 2},
    "postmortem": {"min_homepage": 0, "max_homepage": 2},
}
```

- [ ] **Step 2: Select top-N per segment by recency, enforce floors and ceilings when composing the homepage list**

- [ ] **Step 3: Test**

```python
def test_homepage_always_includes_at_least_one_market_article():
    # Fixture: 10 war, 5 epstein, 1 markets → homepage has the 1 markets
    ...
```

- [ ] **Step 4: Commit**
```
feat(website_exporter): article mix policy enforces market presence

Markets segment gets min_homepage=1 — website carries at least one
book-anchored narrative even on heavy geopolitical days.
```

ETA: 1h.

---

## Phase Z — Docs + Memory Sync

### Task Z1: SYSTEM_OPERATIONS_MANUAL.md sweep

Update these sections:
- Station 2 (regime_scanner) — bootstrap + annotation behaviours
- Station 4 (news intelligence) — fno_news export path
- Station 6 (signal_tracker) — stop hierarchy rewrite
- Station 7 (Phase C shadow) — generalize to TIME_STOP_<HHMM>
- Station 8 (track record) — post-mortem artifact
- New Station: Narrative Generator (EOD)

ETA: 45 min.

### Task Z2: Memory files

- Create: `memory/project_terminal_coherence.md` — summary of this plan + SHAs
- Update: `memory/project_trading_day_cleanup_2026_04_22.md` — cross-link
- Update: `memory/MEMORY.md` — pointer entry
- Retire: `memory/project_atr_stops.md` is superseded for spread trades (ATR still governs correlation breaks)

ETA: 15 min.

---

## Total ETA + Sequencing

| Phase | Hours | Parallel-safe? |
|-------|-------|-----------------|
| A (data) — W5, W2, W12, W11 | 5.5 | W5+W12+W11 yes; W2 must land before W1 |
| B (model) — W1, W7, W8, W9, W10 | 7 + backtest | W1 blocked on W2; W7/W8 parallel; W9/W10 sequential |
| C (ops) — W3, W14 | 4 + backtest | W3 blocked on B; W14 parallel |
| D (UX) — W4, W6, W13, W15 | 7 | all parallel after B done |
| Z (docs) | 1 | last |

**Raw wall-clock: ~24 hours sequential.** With subagent-driven parallelism on phase-safe tasks: ~12 hours over 2 focused sessions.

**Deploy cadence:**
- Phase A can deploy same-day (data-only, no execution gating)
- Phase B items B1/B7/B8 same-day; B9/B10 wait for backtest green
- Phase C waits for B9/B10 green + its own backtest
- Phase D anytime after phase A (browser refresh triggers)

**No live trade without a passing backtest** is enforced by execution order: every B/C task has a backtest step listed between "implement" and "commit". The subagent-driven workflow should treat those backtest commits as gating.

---

## Self-review addenda

This plan is meant to be executable as-is. If the engineer finds that:
- A file path cited here drifted — they should verify via `grep` rather than guess. The gap analyses were grounded in today's live data; schema drift is possible.
- A backtest window is too narrow — 60 days is the minimum; extend to 120+ if data allows. Shorter windows mask regime-conditional edges.
- A task feels like "one more feature" — stop. The plan is a wiring spec, not a product spec. If the change wouldn't show on existing surfaces, it's out of scope.

## Execution handoff

**Plan saved to `docs/superpowers/plans/2026-04-22-anka-terminal-coherence.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — fresh subagent per task, two-stage review between, fast iteration. Use `superpowers:subagent-driven-development`.

**2. Inline Execution** — execute tasks in this session using `superpowers:executing-plans`, batch with checkpoints.

**Which approach?**
