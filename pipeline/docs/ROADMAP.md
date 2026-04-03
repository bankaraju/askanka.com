# Anka Research — Roadmap & Work Queue

## Completed ✅

### Signal Pipeline V2 (2026-03-29 → 2026-04-02)
- 25 spread pairs across 5 themes (geopolitical, USD/INR, India stress, RBI, FII flows)
- 18 event categories with RSS keyword detection + Claude API fallback
- 90 historical events backtested with 4yr price data
- 35 high-conviction setups (≥65% hit rate, n≥5)
- Data-driven stops: daily stop + 2-day running stop (no arbitrary percentages)
- MSI engine (0-100 macro stress index, 5 components)
- Volatility-adjusted stops (1.5× in MACRO_STRESS)
- Kite Connect integration (real-time NSE prices)
- Telegram delivery: signal cards, P&L updates, EOD dashboard, leaderboard
- Scheduled tasks: pre-market 08:30, signals 09:15-15:30 every 30min, EOD 16:30
- Track record system: open_signals.json, closed_signals.json
- Subscriber welcome message sent to @ANKASIGNALS

### Website V1 (2026-03-20 → 2026-03-28)
- Static homepage with pipeline flow visual
- Weekly report: week-001.html (wartime market analysis)
- Report pages: hedge-fund-ideas, india-deep-dive, singapore-market, model-portfolio
- GitHub Pages hosting on askanka.com (CNAME configured)

---

## In Progress 🔄

### Website V2 — LIVE Market Intelligence Hub
**Spec:** docs/specs/2026-04-03-website-v2-spec.md
**Goal:** Transform static site into live dashboard with real P&L, MSI gauge, track record
**Phases:**
1. Data export module (`website_exporter.py`) — pipeline writes JSON for website
2. Homepage redesign — live dashboard with active positions, P&L, MSI
3. Charts & interactivity — MSI history, equity curve, spread heatmap
4. Auto-generated weekly reports
5. Polish & launch

---

## Backlog 📋

### Pipeline Enhancements
- [ ] India VIX spike trigger in macro_stress.py (VIX > 1.5× 30d avg)
- [ ] FII buying trigger in macro_stress.py (3d avg > +5000 cr)
- [ ] Intraday stop checks (currently EOD only for 2-day stop)
- [ ] Dynamic stop multiplier using VIX percentile (not just 1.5× binary)
- [ ] Re-entry logic after stop-out (wait for spread to return to entry zone)
- [ ] ARCBE (Adaptive Regime Correlation Break Engine) — partially built

### Weekly Reports
- [ ] Week 002: Hedge Fund Strategies for Retail Investors (plan exists: week002_strategy_plan.md)
- [ ] Auto-generation from pipeline data (P&L tables, MSI chart, signal summary)

### Marketing & Growth
- [ ] Twitter/X presence — share signal results
- [ ] WhatsApp group as alternative to Telegram
- [ ] SEO optimization for askanka.com
- [ ] Google Analytics integration
