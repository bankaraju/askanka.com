# Article Grounding — Truth-Anchored Daily Articles — Design Spec

**Date:** 2026-04-15
**Status:** Approved for implementation
**Trigger incident:** `articles/2026-04-15-war.html` claimed "crude oil spiked another 3% today to $103 a barrel" while `pipeline/data/daily/2026-04-15.json` shows Brent close = $95.07 (–8% from claim). Repeat of the failure mode logged in `memory/feedback_stale_data_disqualifies_article.md`.
**Successor (deferred):** Wave 4 — multi-day market-context drift detection, source-link validation.

---

## Goal

Eliminate hallucinated market numbers from the daily article generator (`pipeline/daily_articles.py`) by:

1. **Visibly anchoring** every article to a "Today's Numbers" panel populated from authoritative pipeline data (topic-scoped fixed schema).
2. **Strictly enforcing** that the LLM-written narrative below the panel does not contradict the panel — via a deterministic regex number-scanner that rejects any draft whose numeric claims diverge >2% from the ground truth.

Reject-on-violation is non-negotiable: a wrong number disqualifies the entire article (per `feedback_stale_data_disqualifies_article.md`).

---

## Non-goals

- Multi-day drift detection (e.g., "Brent rose 5% over the week" claims) — Wave 4
- Source URL liveness checks
- Auto-regeneration loops on rejection (a rejected draft requires human review)
- Changes to article topics, badge colors, layout beyond the new panel
- Backfill of historical bad articles
- Telegram briefings or other publishing surfaces (separate work)

---

## Architecture

```
                          ┌─────────────────────────────────┐
                          │  pipeline/article_grounding.py  │
                          │  (NEW MODULE)                   │
                          │                                 │
                          │  load_market_context(date)      │
                          │  build_topic_panel(topic, ctx)  │
                          │  verify_narrative(text, panel)  │
                          └────────────┬────────────────────┘
                                       │
        ┌──────────────────────────────┼─────────────────────────────────┐
        ▼                              ▼                                  ▼
pipeline/data/daily/         pipeline/data/                       pipeline/data/
  {date}.json                  today_regime.json                    fii_flows.json
(Brent, WTI, indices,        (regime + components)                (FII equity net)
 commodities, fx)
                                       │
                                       ▼
                          ┌─────────────────────────────────┐
                          │  pipeline/daily_articles.py     │
                          │  (MODIFIED)                     │
                          │                                 │
                          │  for each topic in [war, eps]:  │
                          │    panel = build_topic_panel    │
                          │    prompt = inject(panel)       │
                          │    draft = call_llm(prompt)     │
                          │    issues = verify_narrative    │
                          │    if issues:                   │
                          │      → articles/_failed/        │
                          │      → logs/violations.log      │
                          │      → telegram alert (if avail)│
                          │      skip publish               │
                          │    else:                        │
                          │      html = panel + body        │
                          │      publish to articles/       │
                          └─────────────────────────────────┘
```

The grounding module is a pure library — no I/O side effects beyond reading source JSONs. All publish/reject decisions live in `daily_articles.py`.

---

## Topic schemas (fixed lists)

Schemas are dictionaries from human label to a dotted source path into the loaded context dict. Missing fields render as `—` and are excluded from the verification scan.

### `war` (geopolitics / oil / defence focus)

| Label | Source path |
|---|---|
| Brent | `commodities.Brent Crude.close` |
| WTI | `commodities.WTI Crude.close` |
| Gold | `commodities.Gold.close` |
| Nifty Defence | `indices.NIFTY DEFENCE.close` |
| Nifty 50 | `indices.NIFTY 50.close` |
| USD/INR | `fx.USDINR.close` |
| India VIX | `indices.INDIA VIX.close` |
| FII flow (₹ Cr) | `flows.fii_equity_net` |

### `epstein` (US politics / global risk barometer)

| Label | Source path |
|---|---|
| Dow | `indices.DJI.close` |
| S&P 500 | `indices.GSPC.close` |
| VIX (US) | `indices.VIX.close` |
| Gold | `commodities.Gold.close` |
| DXY | `fx.DXY.close` |
| US 10Y yield | `bonds.US10Y.close` |
| Bitcoin | `crypto.BTC.close` |

### Schema registry

In `pipeline/article_grounding.py`:

```python
TOPIC_SCHEMAS = {
    "war":     [("Brent", "commodities.Brent Crude.close"),
                ("WTI", "commodities.WTI Crude.close"),
                ("Gold", "commodities.Gold.close"),
                ("Nifty Defence", "indices.NIFTY DEFENCE.close"),
                ("Nifty 50", "indices.NIFTY 50.close"),
                ("USD/INR", "fx.USDINR.close"),
                ("India VIX", "indices.INDIA VIX.close"),
                ("FII flow ₹Cr", "flows.fii_equity_net")],
    "epstein": [("Dow", "indices.DJI.close"),
                ("S&P 500", "indices.GSPC.close"),
                ("VIX (US)", "indices.VIX.close"),
                ("Gold", "commodities.Gold.close"),
                ("DXY", "fx.DXY.close"),
                ("US 10Y", "bonds.US10Y.close"),
                ("Bitcoin", "crypto.BTC.close")],
}
```

Adding a new topic = adding one entry. No code changes elsewhere.

---

## Number-scan enforcer rules

### What gets scanned
The narrative text only — the `<p>` body the LLM writes. NOT the panel itself (that's the source of truth). NOT HTML attributes.

### Patterns extracted

```
DOLLAR  : \$\s?[\d,]+(?:\.\d+)?           e.g. $103, $1,234.56
RUPEE   : ₹\s?[\d,]+(?:\.\d+)?            e.g. ₹85, ₹1,200
PCT_BPS : [\d,]+(?:\.\d+)?\s?(?:%|bps)    e.g. 5.7%, 25 bps
INDEX   : (?i)(?:Nifty|Sensex|Dow|S&P|BSE)[\s\w]{0,15}?\s+(?:at|@|of|to)\s+[\d,]+(?:\.\d+)?
```

### Verification logic per extracted number

For each numeric extraction `n`:

1. Normalize `n` to a float (strip $, ₹, %, bps, commas).
2. **Whitelist check** — if the surrounding text matches a known-safe pattern, mark OK and continue:
   - `\d+%\s+of\s+\w+` ("85% of crude imports")
   - `₹\s?[\d.]+\s+per\s+(liter|kg|share|barrel)` ("₹5-7 per liter")
   - `\d+(?:-\d+)?\s+(year|month|day|week)s?` ("next 2-3 years")
   - `\d+(?:,\d{3})*\s+jobs` ("3,000 jobs")
   - `\d+%\s+(?:increase|decrease|growth|decline)\s+in\s+\w+\s+(?:revenue|outlook|projections)` (forward-looking forecasts)
3. **Panel check** — if `n` is within **±2% tolerance** of any panel value, mark OK.
4. Otherwise → record a `Violation(number, surrounding_text, line_number, panel_values_compared)`.

### Disposition

- **Zero violations** → article is published normally; the panel HTML is prepended to the body.
- **One or more violations** → article is **NOT published**. The draft is written to `articles/_failed/{date}-{topic}.html`, the violation list (number + line + nearest panel value) is appended to `pipeline/logs/article_violations.log`, and an alert is sent via the existing `telegram_bot.send_message` if available. The run continues with the next topic.

### Concrete behaviour on today's bug

Today's draft says "spiked another 3% today to $103 a barrel". Panel shows Brent = $95.07. `$103` is extracted. `|95.07 − 103| / 95.07 = 8.3%` > 2% tolerance → violation. Article rejected.

---

## Panel HTML format (visible to readers)

Inserted between the existing hero block and the article body. Same dark gold theme:

```html
<section class="market-anchor">
  <div class="anchor-title">Today's Numbers <span class="anchor-date">15 Apr 2026</span></div>
  <div class="anchor-grid">
    <div><span class="lbl">Brent</span><span class="val">$95.07</span></div>
    <div><span class="lbl">WTI</span><span class="val">$92.02</span></div>
    <div><span class="lbl">Gold</span><span class="val">$2,478</span></div>
    <div><span class="lbl">Nifty Defence</span><span class="val">8,142</span></div>
    <!-- … -->
  </div>
  <div class="anchor-source">Source: NSE / yfinance, last close. Numbers in this article must match this panel.</div>
</section>
```

CSS lives inside the existing article `<style>` block. Grid layout: 4 columns desktop, 2 mobile.

---

## File contracts

### `pipeline/article_grounding.py` (new)

```python
def load_market_context(date_str: str) -> dict:
    """Load the merged authoritative market data for the given YYYY-MM-DD.

    Reads pipeline/data/daily/{date_str}.json (mandatory — raise if missing),
    pipeline/data/today_regime.json (optional), pipeline/data/fii_flows.json (optional).
    Returns a single dict with stable keys: indices, commodities, fx, bonds, crypto, flows, regime.
    """

def build_topic_panel(topic: str, context: dict) -> dict:
    """Resolve the topic's schema against the context. Returns ordered dict
    {label: formatted_value_str}. Missing fields render as '—'.
    Also returns _raw: {label: float_or_None} for the verifier."""

def verify_narrative(narrative_html: str, panel: dict) -> list[Violation]:
    """Scan narrative text, return list of Violations (empty if clean)."""

@dataclass
class Violation:
    number: float
    text_excerpt: str   # 60-char window around the match
    pattern_kind: str   # "dollar" | "rupee" | "pct_bps" | "index"
    closest_panel_value: tuple[str, float] | None  # (label, value) or None if no comparable
```

### `pipeline/daily_articles.py` (modified)

Add at the top of the per-topic loop:

```python
from article_grounding import load_market_context, build_topic_panel, verify_narrative

today = datetime.now(IST).strftime("%Y-%m-%d")
ctx = load_market_context(today)

for topic in TOPICS:                          # existing list
    panel = build_topic_panel(topic, ctx)
    prompt = build_prompt(topic, panel)        # MODIFIED to inject panel + rules
    draft_body = call_llm(prompt)              # existing call

    violations = verify_narrative(draft_body, panel)
    if violations:
        write_failed_draft(date, topic, draft_body, violations)
        log_violations(date, topic, violations)
        try_send_telegram_alert(topic, violations)
        continue                               # skip publish

    html = render_article(topic, panel, draft_body)   # MODIFIED to prepend panel
    publish(html)
```

The `call_llm` signature does not change. The `build_prompt` function gains a panel argument and includes this verbatim block in the system prompt:

> ```
> # GROUNDING — DO NOT VIOLATE
> The following panel will be displayed to the reader at the top of the article:
> {panel as bullet list}
>
> Rules:
> 1. Every market number you cite (oil/gold/index/currency/yield) must match the panel within ±2%.
> 2. If a number you want to cite is not in the panel, OMIT it. Do not invent.
> 3. Non-market figures (population, percentages of imports, retail prices, forecasts) are allowed
>    but should not contradict the panel direction.
> ```

---

## Failure mode matrix

| Condition | Behavior |
|---|---|
| `pipeline/data/daily/{date}.json` missing | `load_market_context` raises `MarketDataMissing`. `daily_articles.py` catches, logs, sends telegram alert, exits without publishing anything. |
| Panel field missing | Render `—` in display, exclude from verifier comparison set. |
| Verifier returns ≥1 violation | Draft written to `articles/_failed/`, violation log appended, telegram alert sent, this topic skipped, next topic continues. |
| Telegram unavailable | Log "telegram_unavailable" and continue (alerts are best-effort). |
| Regex false positive (legitimate non-market number flagged) | Operator extends the whitelist patterns and re-runs. The whitelist is in code; treat each new pattern as a small change, not a config tweak. |

---

## Verification plan

### Unit tests (`pipeline/tests/test_article_grounding.py`)

- `test_load_market_context_reads_brent_from_fixture` — fixture has Brent 95.07; loader returns it.
- `test_load_market_context_missing_dump_raises` — expect `MarketDataMissing`.
- `test_panel_war_full_population` — every label has a value (no `—`).
- `test_panel_epstein_missing_fields_become_dash` — fixture omits DXY → label renders `—`.
- `test_verifier_clean_narrative` — narrative cites $95 oil and Brent panel value $95.07 → 0 violations.
- `test_verifier_catches_today_bug` — narrative contains "$103 a barrel", panel Brent=$95.07 → exactly 1 violation, kind=dollar, closest_panel_value=("Brent", 95.07).
- `test_verifier_whitelist_85pct_of_imports` — "85% of crude imports" → 0 violations.
- `test_verifier_whitelist_per_liter` — "₹5-7 per liter" → 0 violations.
- `test_verifier_index_mention` — "Nifty Defence at 8,200" with panel value 8,142 → within 2%, 0 violations.
- `test_verifier_index_mention_violation` — same with panel 7,500 → violation.

### End-to-end smoke test

After implementation:
- Run `python -X utf8 pipeline/daily_articles.py` against today's data.
- Confirm: today's `_failed/2026-04-15-war.html` is created with the $103 violation logged (because the LLM may still hallucinate the same number).
- Manually inspect `articles/_failed/2026-04-15-war.html` and `logs/article_violations.log` to confirm the violation captures the right line + closest panel value.
- Either re-run until clean, or accept and document.

---

## Open questions for Wave 4 (logged, not blocking)

1. Multi-day drift assertions ("Brent has fallen 8% this week") — needs historical context loader and a different verifier rule.
2. Source URL liveness — flag dead `Source:` links.
3. Auto-regenerate loop — currently a rejection requires human re-run; a bounded auto-retry (max 2) with a stricter prompt could reduce ops burden.
4. Whitelist as YAML config rather than code constants — once we have ≥10 patterns.

---

## Acceptance criteria

- [ ] `pipeline/article_grounding.py` exists, exports `load_market_context`, `build_topic_panel`, `verify_narrative`, `Violation`, `MarketDataMissing`.
- [ ] All unit tests above pass.
- [ ] `daily_articles.py` invokes the grounding module per topic, prepends the panel HTML, and gates publish on verification.
- [ ] On a contrived test draft containing "$103 a barrel" with Brent panel value $95.07, the article is rejected and written to `articles/_failed/`.
- [ ] On a clean draft, the article is published with the panel visible above the narrative.
- [ ] `pipeline/logs/article_violations.log` records each rejection with date, topic, violation count.
- [ ] Today's `2026-04-15-war.html` and `2026-04-15-epstein.html` are regenerated (or rejected and human-fixed) using the new pipeline.
- [ ] Live verification on https://askanka.com — open a published article, see the panel, see numbers in the prose match the panel within tolerance.
