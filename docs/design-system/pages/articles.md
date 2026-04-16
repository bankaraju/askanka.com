# Article pages — design override

**Applies to:** `articles/*.html` (daily generated long-form articles)

## Why a local override

Article pages are editorial long-form reading — closer to a newspaper essay than a dashboard. They run with a warmer, lower-contrast palette and a single-column reading layout that intentionally diverges from `index.html`'s dashboard-density feel.

## Local tokens

Article `:root` declares local aliases to keep the template short:

| Local var   | Value     | MASTER.md equivalent     |
|-------------|-----------|--------------------------|
| `--bg`      | `#0a0e1a` | `--bg-primary`           |
| `--card`    | `#111827` | `--bg-card`              |
| `--border`  | `#1e293b` | `--border`               |
| `--text`    | `#e5e7eb` | (slightly dimmer than `--text-primary` for long-form reading — intentional) |
| `--text2`   | `#9ca3af` | `--text-secondary` (near-equivalent) |
| `--gold`    | `#d4a855` | `--accent-gold-warm`     |

**Rule:** Article templates may use these short aliases. Any new token in an article must also map to a MASTER.md token — no inventing fresh colours.

## Headline treatment

- `h1` uses `DM Serif Display` at 36–48px with a gold gradient (`#f5f0e8 → #d4a855`) via `background-clip: text`. This is an editorial flourish specific to articles; not used on the dashboard.
- Body uses `DM Sans` at 16px with `line-height: 1.8` (longer than dashboard default 1.5) for reading comfort.
- First-paragraph drop-cap uses `--accent-gold-warm`.

## Market-anchor strip

Every article (for TOPIC_SCHEMAS grounded in markets, e.g. war) includes a `.market-anchor` strip showing spot prices that anchor the narrative. This uses `JetBrains Mono` for numerics per MASTER.md §3.

## What article pages MUST still follow

- Dark-default only (no light-mode variant)
- No AI purple/pink gradients
- No emoji as icons in body copy (gold drop-cap and the `.market-anchor` are the only decorative accents)
- `DM Serif Display` only for H1/H2; never mix serif + sans in one headline
