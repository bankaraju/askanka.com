# Anka Research — Unified Design System (MASTER)

Single source of truth for visual design across all three user-facing surfaces:

1. **Website** (`askanka.com/*.html`, `articles/*.html`, `reports/*.html`)
2. **Trading terminal** (planned — live signal monitor, not yet built)
3. **Telegram bot** (`pipeline/telegram_bot.py` — digests and signal cards)

**Origin:** Derived 2026-04-16 from the `ui-ux-pro-max` plugin recommendation for "fintech investment research dashboard editorial serif gold" reconciled against the existing website palette and user-locked font preferences.

**Rule:** When building or modifying any of the three surfaces, tokens defined here override ad-hoc choices. Add new tokens here first, then consume them — never inline raw hex or fonts in components.

---

## 1. Design Pattern

- **Name:** Trust & Authority (institutional research)
- **Feel:** Editorial, precise, data-dense but legible, dark-default
- **Hierarchy:** Oversized serif headlines over hyperlegible sans body; gold used sparingly to mark "signal" vs "noise"

## 2. Palette (dark-default)

Single palette shared across surfaces. CSS variables are the source; Telegram ports these as emoji semantics only.

| Role                    | Hex         | CSS var                | Semantic use                                    |
|-------------------------|-------------|------------------------|-------------------------------------------------|
| Background (page)       | `#0a0e1a`   | `--bg-primary`         | Body background                                 |
| Background (card)       | `#111827`   | `--bg-card`            | Card surface                                    |
| Background (card-hover) | `#1a2332`   | `--bg-card-hover`      | Hover/active card                               |
| Border                  | `#1e293b`   | `--border`             | Dividers, card borders                          |
| Text primary            | `#f1f5f9`   | `--text-primary`       | Headings, body                                  |
| Text secondary          | `#94a3b8`   | `--text-secondary`     | Metadata, labels                                |
| Text muted              | `#64748b`   | `--text-muted`         | Captions, timestamps                            |
| **Accent gold**         | `#f59e0b`   | `--accent-gold`        | Primary brand, SIGNAL tier, validated           |
| Accent gold (warm)      | `#d4a855`   | `--accent-gold-warm`   | Editorial/article headline gradient             |
| Accent gold (deep)      | `#b8860b`   | `--accent-gold-deep`   | Gradient stop / hover                           |
| Accent gold (dim)       | `rgba(245,158,11,0.15)` | `--accent-gold-dim` | Badge bg, subtle highlight           |
| Accent green (risk-off) | `#10b981`   | `--accent-green`       | Positive P&L, RISK_OFF, MACRO_EASY regime       |
| Accent red (risk-on)    | `#ef4444`   | `--accent-red`         | Negative P&L, RISK_ON (danger), MACRO_STRESS    |
| Accent blue             | `#3b82f6`   | `--accent-blue`        | Neutral info, links in articles                 |
| Accent amber (explore)  | `#fbbf24`   | `--accent-amber`       | EXPLORING tier, MIXED regime                    |

Dim variants: `rgba(…,0.15)` for green/red/gold/blue — used for regime pill backgrounds.

**Contrast check:** `--text-primary` on `--bg-primary` = 15.7:1 (AAA). `--accent-gold` on `--bg-primary` = 7.4:1 (AAA large, AA normal).

**Anti-patterns:**
- AI purple/pink gradients — explicitly banned per `ui-ux-pro-max`.
- Playful or cartoony accents — the product is investment research.
- Inverted light-mode colours at runtime — use a dedicated light-mode theme file only if we ship light mode (not currently planned).

## 3. Typography (locked — do not substitute)

| Role              | Family               | Weights     | Size scale                  | Notes                               |
|-------------------|----------------------|-------------|-----------------------------|-------------------------------------|
| Editorial / hero  | `DM Serif Display`   | 400         | clamp(2.5rem, 6vw, 5rem)    | Article titles, hero headlines      |
| UI sans body      | `Inter`              | 400 / 500 / 600 | 14 / 16 / 18 base        | Nav, cards, UI copy                 |
| Article body      | `DM Sans`            | 400 / 500   | 16 / 18                     | Long-form reading within articles   |
| Numeric / mono    | `JetBrains Mono`     | 400 / 500   | 13 / 14 / 16                | Prices, tickers, timestamps         |
| Bangla / IN vern. | (system fallback)    | —           | —                           | Not used currently                  |

```css
@import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@400;500;600&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
```

**Rule:** Prices, P&L, tickers, timestamps → `JetBrains Mono` (tabular figures prevent layout jitter). Narrative / copy → `Inter` or `DM Sans`. Headlines → `DM Serif Display`. Never mix serif + sans within a single headline.

## 4. Spacing & Layout

- Base unit: **8px**. Valid values: 4, 8, 12, 16, 20, 24, 32, 48, 64, 96.
- Container: `max-width: 1200px` for content, `1400px` for dashboards.
- Breakpoints: `375 / 768 / 1024 / 1440` (mobile-first).
- Card padding: 24px default, 32px for hero cards.
- Radius: 6px small / 10px card / 14px modal.

## 5. Motion

- Micro-interactions: 150–300ms, `ease-out` entering, `ease-in` exiting.
- Never animate `width/height/top/left` — use `transform` + `opacity` only.
- Respect `prefers-reduced-motion`.
- Exit ~70% of enter duration.

## 6. Telegram surface — conventions

Telegram has no CSS, so the palette is encoded as **emoji semantics** and **structural markers**:

| Concept                | Marker   | Example                              |
|------------------------|----------|--------------------------------------|
| SIGNAL tier (gold)     | 🟢       | `🟢 SIGNAL — Defence long / IT short` |
| EXPLORING tier (amber) | 🟡       | `🟡 EXPLORING — Pharma pair`          |
| NO_DATA tier (muted)   | ⚪       | `⚪ NO_DATA — Cement spread`          |
| RISK_ON regime (red)   | 🔴       | `🔴 RISK_ON day`                      |
| RISK_OFF regime (green)| 🟢       | `🟢 RISK_OFF day`                     |
| MIXED regime (amber)   | 🟡       | `🟡 MIXED day`                        |
| Alert / urgent         | 🚨       | `🚨 Anka Watchdog — 16:20 IST`        |
| Resolved / recovered   | ✅       | `✅ AnkaMorningBrief0730 — fresh again` |
| Positive P&L           | `+` prefix | `₹+12,450`                         |
| Negative P&L           | `-` prefix | `₹-3,200`                          |
| Paper-only (NO_DATA)   | "paper"  | `paper`                              |
| Section separator      | `• ` bullet + newline | `  • AnkaWeeklyReport — task stale`  |

**Structural rules:**
- `telegram_bot.send_message` defaults to `parse_mode="Markdown"` with an automatic fallback to plain text if Telegram rejects the payload (retry path in `_send_to_chat_http`). For task/ticker-dense alerts where underscores, dashes, or parens would collide with Markdown (watchdog digests, `ANKA*` task names), pass `parse_mode=None` explicitly.
- Headlines use 🚨 (alert) / 🟢 🟡 🔴 (regime). Never mix emojis within a headline.
- ₹ for INR; `K / M / Cr` suffixes for large numbers.
- Tabular data uses `|` separators: `AAPL | +1.2% | ₹+12,450 | IT-sector`.
- Keep a message to one scroll-height on mobile Telegram (~12 lines). Longer → split into two messages.

## 7. Icons

- **Website / terminal:** Use Lucide SVG set (`lucide.dev`). Stroke 1.5px, 20×20 or 24×24.
- **Telegram:** Emoji-only (see §6). No inline SVG supported.
- **Never:** Emoji as icons on website or terminal. Emoji reserved for Telegram.

## 8. Chart conventions

- Background-tier data: `var(--text-muted)` gridlines.
- Primary series: `var(--accent-gold)`.
- Positive series: `var(--accent-green)`.
- Negative series: `var(--accent-red)`.
- Candles: red-on-gold-on-green, NOT traditional red/green-only — user is red/green colour-blind in certain light; hue + shape (filled vs hollow) together.
- Always label axes, always show legend, never rely on colour alone.

## 9. Regime pill component (shared across website + terminal)

```html
<span class="regime regime-MACRO_EASY">Risk-off</span>
<span class="regime regime-MACRO_NEUTRAL">Neutral</span>
<span class="regime regime-MACRO_STRESS">Risk-on</span>
```

```css
.regime { padding: 4px 10px; border-radius: 6px; font: 500 13px/1 'JetBrains Mono', monospace; letter-spacing: 0.02em; }
.regime-MACRO_EASY    { background: var(--accent-green-dim); color: var(--accent-green); border: 1px solid rgba(16,185,129,0.3); }
.regime-MACRO_NEUTRAL { background: var(--accent-gold-dim);  color: var(--accent-gold);  border: 1px solid rgba(245,158,11,0.3); }
.regime-MACRO_STRESS  { background: var(--accent-red-dim);   color: var(--accent-red);   border: 1px solid rgba(239,68,68,0.3); }
```

Telegram pair for the same regime: `🟢 RISK_OFF day` / `🟡 MIXED day` / `🔴 RISK_ON day`.

## 10. Enforcement & audit

- **Before editing any .html or component**: check the palette + font variables above.
- **Before editing telegram_bot.py formatters**: check §6.
- **Before building the trading terminal**: bootstrap it with this token set. Don't invent a third palette.
- **Drift check**: search the repo for raw hex or ad-hoc font-family outside this file and the `index.html` `:root` block — any match is a bug.

## Page-level overrides

Page-specific deviations (if any) live in `docs/design-system/pages/<page-name>.md`. When styling a specific page, check the page override first; if none exists, use this Master.
