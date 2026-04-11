"""
Anka Research Pipeline — Weekly HTML Report Generator
Converts weekly aggregation JSON into a self-contained HTML report.
Automatically updates index.html and library.html on askanka.com.

Usage:
    python weekly_report_generator.py                  # generate latest week
    python weekly_report_generator.py --week 5         # generate specific week
    python weekly_report_generator.py --deploy          # generate + git push
"""

import argparse
import json
import logging
import os
import subprocess
import sys
import requests
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

log = logging.getLogger("anka.weekly_report")

PIPELINE_DIR = Path(__file__).parent
DATA_DIR = PIPELINE_DIR / "data" / "weekly"
SITE_DIR = PIPELINE_DIR.parent
REPORTS_DIR = SITE_DIR / "reports"


def _load_week_data(week_num: int) -> dict:
    """Load a weekly JSON aggregation file."""
    fname = f"week-{week_num:03d}.json"
    fpath = DATA_DIR / fname
    if not fpath.exists():
        raise FileNotFoundError(f"Weekly data not found: {fpath}")
    return json.loads(fpath.read_text(encoding="utf-8"))


def _find_latest_week() -> int:
    """Find the highest week number available."""
    weeks = sorted(DATA_DIR.glob("week-*.json"))
    if not weeks:
        raise FileNotFoundError("No weekly data files found")
    return int(weeks[-1].stem.split("-")[1])


def _pct_class(val: float) -> str:
    """Return CSS class for a percentage value."""
    if val > 0.5:
        return "up"
    elif val < -0.5:
        return "down"
    return "neutral"


def _fmt_pct(val: float) -> str:
    """Format percentage with sign."""
    if val is None:
        return "N/A"
    return f"{val:+.2f}%"


def _fmt_price(val: float, currency: str = "USD") -> str:
    """Format price with currency symbol."""
    if val is None:
        return "N/A"
    symbols = {"USD": "$", "GBP": "\u00a3", "EUR": "\u20ac", "JPY": "\u00a5",
               "INR": "\u20b9", "KRW": "\u20a9", "CNY": "\u00a5"}
    sym = symbols.get(currency, "")
    return f"{sym}{val:,.2f}"


def _sector_badge(sector: str) -> str:
    """Return badge CSS class based on sector name."""
    s = sector.lower()
    if "defen" in s: return "badge-defense"
    if "energy" in s or "oil" in s or "refin" in s: return "badge-energy"
    if "commod" in s or "min" in s: return "badge-commodity"
    if "tech" in s or "it" in s or "semi" in s: return "badge-tech"
    if "ship" in s or "tanker" in s: return "badge-shipping"
    if "pharma" in s or "health" in s: return "badge-pharma"
    if "ev" in s or "batter" in s: return "badge-tech"
    return "badge-commodity"


def _generate_stock_commentary(stocks: dict) -> dict:
    """Generate brief 3-5 line Anka Take for each stock using Gemini API.
    Returns dict of {ticker: commentary_html}."""
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        log.warning("No GEMINI_API_KEY — skipping stock commentary")
        return {}

    # Build a batch prompt for all stocks at once (cheaper, faster)
    stock_summaries = []
    for ticker, s in sorted(stocks.items(), key=lambda x: abs(x[1].get("wow_change_pct", 0)), reverse=True)[:12]:
        wow = s.get("wow_change_pct", 0)
        price = s.get("end_price", 0)
        sector = s.get("sector", "")
        desc = s.get("desc", "")
        rec = s.get("analyst", {}).get("recommendation", "")
        n_analysts = s.get("analyst", {}).get("num_analysts", 0)
        target = s.get("analyst", {}).get("target_mean")
        fwd_pe = s.get("valuation", {}).get("forward_pe")
        div_yield = s.get("valuation", {}).get("dividend_yield")
        inst_pct = s.get("ownership", {}).get("institutional_pct")

        stock_summaries.append(
            f"TICKER: {ticker}\n"
            f"SECTOR: {sector}\n"
            f"DESC: {desc}\n"
            f"PRICE: {price:.2f}, WOW CHANGE: {wow:+.2f}%\n"
            f"ANALYST: {rec} ({n_analysts} analysts), Target: {target}\n"
            f"FWD P/E: {fwd_pe}, DIV YIELD: {div_yield}, INST%: {inst_pct}"
        )

    prompt = f"""You are the Anka Research analyst writing brief stock commentary for a weekly report.
For each stock below, write exactly 3-4 sentences as an "Anka Take":
- Line 1: What this company does (use the DESC provided, make it accessible)
- Line 2-3: Why it moved this week and what's driving sentiment (use the data: WoW change, sector trends, analyst consensus)
- Line 4: Forward outlook — is there more upside or is it priced in? Reference P/E, target, or yield if relevant.

TONE: Confident but measured. Like a Bloomberg terminal note. No hype, no disclaimers.
FORMAT: Return a JSON object with ticker as key and commentary string as value. Nothing else.

STOCKS:
{chr(10).join(stock_summaries)}"""

    try:
        resp = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}",
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "maxOutputTokens": 8192,
                    "temperature": 0.3,
                    "responseMimeType": "application/json",
                    "thinkingConfig": {"thinkingBudget": 0},
                },
            },
            timeout=120,
        )
        resp.raise_for_status()
        result = resp.json()
        candidates = result.get("candidates", [])
        if not candidates:
            raise ValueError("No candidates in Gemini response")
        parts = candidates[0].get("content", {}).get("parts", [])
        raw = parts[0].get("text", "") if parts else ""
        # Extract JSON from response
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        commentary = json.loads(raw.strip())
        log.info(f"Generated commentary for {len(commentary)} stocks")
        return commentary
    except Exception as e:
        log.warning(f"Stock commentary generation failed: {e}")
        return {}


def _build_stock_cards(stocks: dict, commentary: dict = None) -> str:
    """Build detailed stock cards with metrics, analyst data, and financials."""
    if commentary is None:
        commentary = {}
    cards = []
    sorted_stocks = sorted(
        stocks.items(),
        key=lambda x: abs(x[1].get("wow_change_pct", 0)),
        reverse=True,
    )
    for ticker, s in sorted_stocks[:12]:  # Top 12 movers
        wow = s.get("wow_change_pct", 0)
        price = s.get("end_price", 0)
        sector = s.get("sector", "")
        index_name = s.get("index", "")
        desc = s.get("desc", "")
        badge_cls = _sector_badge(sector)
        pct_cls = "positive" if wow > 0 else "negative"

        # Analyst data
        analyst = s.get("analyst", {})
        target_mean = analyst.get("target_mean")
        rec = analyst.get("recommendation", "").title()
        n_analysts = analyst.get("num_analysts", 0)

        # Valuation
        val = s.get("valuation", {})
        fwd_pe = val.get("forward_pe")
        div_yield = val.get("dividend_yield")
        pb = val.get("price_to_book")

        # Financials
        fin = s.get("financials", {})
        profit_margin = fin.get("profit_margin")
        rev_growth = fin.get("revenue_growth")

        # Ownership
        own = s.get("ownership", {})
        inst_pct = own.get("institutional_pct")
        short_ratio = own.get("short_ratio")

        # Ratings bar
        ratings = s.get("recent_ratings", [])
        ratings_html = ""
        if ratings and ratings[0]:
            r = ratings[0]
            total_r = r.get("strongBuy", 0) + r.get("buy", 0) + r.get("hold", 0) + r.get("sell", 0) + r.get("strongSell", 0)
            if total_r > 0:
                ratings_html = f"""
                <div class="ratings-bar">
                  <span class="rb-segment" style="width:{r.get('strongBuy',0)/total_r*100:.0f}%;background:#10b981;" title="Strong Buy: {r.get('strongBuy',0)}"></span>
                  <span class="rb-segment" style="width:{r.get('buy',0)/total_r*100:.0f}%;background:#34d399;" title="Buy: {r.get('buy',0)}"></span>
                  <span class="rb-segment" style="width:{r.get('hold',0)/total_r*100:.0f}%;background:#f59e0b;" title="Hold: {r.get('hold',0)}"></span>
                  <span class="rb-segment" style="width:{r.get('sell',0)/total_r*100:.0f}%;background:#f87171;" title="Sell: {r.get('sell',0)}"></span>
                  <span class="rb-segment" style="width:{r.get('strongSell',0)/total_r*100:.0f}%;background:#ef4444;" title="Strong Sell: {r.get('strongSell',0)}"></span>
                </div>
                <div style="font-size:11px;color:#6b7280;margin-top:4px;">
                  {r.get('strongBuy',0)} Strong Buy | {r.get('buy',0)} Buy | {r.get('hold',0)} Hold | {r.get('sell',0)} Sell | {r.get('strongSell',0)} Strong Sell
                </div>"""

        upside = ""
        if target_mean and price and price > 0:
            upside_pct = ((target_mean / price) - 1) * 100
            upside = f'<div class="metric"><div class="metric-label">Target Upside</div><div class="metric-value {"positive" if upside_pct > 0 else "negative"}">{upside_pct:+.1f}%</div></div>'

        card = f"""
<div class="stock-card" id="stock-{ticker.lower().replace('.', '')}">
  <div class="stock-header">
    <div><span class="ticker">{ticker}</span><span class="name">{index_name}</span></div>
    <span class="badge {badge_cls}">{sector}</span>
  </div>
  {f'<p class="stock-desc">{desc}</p>' if desc else ''}
  {f'<div class="anka-take">{commentary.get(ticker, "")}</div>' if commentary.get(ticker) else ''}
  <div class="metrics-grid">
    <div class="metric"><div class="metric-label">Price</div><div class="metric-value">{_fmt_price(price)}</div></div>
    <div class="metric"><div class="metric-label">WoW Change</div><div class="metric-value {pct_cls}">{_fmt_pct(wow)}</div></div>
    <div class="metric"><div class="metric-label">Consensus</div><div class="metric-value neutral">{rec} ({n_analysts})</div></div>
    {f'<div class="metric"><div class="metric-label">Fwd P/E</div><div class="metric-value">{fwd_pe:.1f}x</div></div>' if fwd_pe else ''}
    {f'<div class="metric"><div class="metric-label">Div Yield</div><div class="metric-value positive">{div_yield:.1f}%</div></div>' if div_yield else ''}
    {upside}
  </div>
  <div class="two-col">
    <div class="factor-box macro">
      <h4>Fundamentals</h4>
      <ul>
        {f"<li>P/B Ratio: {pb:.2f}x</li>" if pb else ""}
        {f"<li>Profit Margin: {profit_margin*100:.1f}%</li>" if profit_margin else ""}
        {f"<li>Revenue Growth: {rev_growth*100:+.1f}%</li>" if rev_growth else ""}
        {f"<li>Target: {_fmt_price(target_mean)} ({n_analysts} analysts)</li>" if target_mean else ""}
      </ul>
    </div>
    <div class="factor-box specific">
      <h4>Ownership & Flow</h4>
      <ul>
        {f"<li>Institutional: {inst_pct*100:.1f}%</li>" if inst_pct else ""}
        {f"<li>Short Ratio: {short_ratio:.1f} days</li>" if short_ratio else ""}
        {f"<li>Dividend Yield: {div_yield:.2f}%</li>" if div_yield else ""}
      </ul>
    </div>
  </div>
  {f'<h4>Analyst Consensus</h4>{ratings_html}' if ratings_html else ''}
</div>"""
        cards.append(card)
    return "\n".join(cards)


def generate_report_html(data: dict) -> str:
    """Generate a publication-quality HTML report with sidebar nav, Plotly charts,
    stock cards, and sector analysis from weekly JSON data."""
    week_num = data["week_number"]
    week_label = data["week_label"]
    period = data["period"]
    indices = data.get("indices", {})
    stocks = data.get("stocks", {})
    rankings = data.get("rankings", {})
    commodities = data.get("commodities", {})
    fx = data.get("fx", {})
    volatility = data.get("volatility", {})
    sector_etfs = data.get("sector_etfs", {})

    # Derived data
    winners = rankings.get("top_5_winners", [])
    losers = rankings.get("top_5_losers", [])
    best_idx_raw = rankings.get("best_index", ["N/A", 0])
    worst_idx_raw = rankings.get("worst_index", ["N/A", 0])
    best_idx = {"name": best_idx_raw[0], "wow_pct": best_idx_raw[1]} if isinstance(best_idx_raw, list) else best_idx_raw
    worst_idx = {"name": worst_idx_raw[0], "wow_pct": worst_idx_raw[1]} if isinstance(worst_idx_raw, list) else worst_idx_raw
    vix = volatility.get("VIX", {})
    vix_price = vix.get("end_price") or vix.get("end_level") or 0
    vix_change = vix.get("wow_change_pct", 0) or 0

    # Brent data for dashboard
    brent = commodities.get("Brent Crude", {})
    brent_price = brent.get("end_price", 0) or 0
    brent_change = brent.get("wow_change_pct", 0) or 0
    gold = commodities.get("Gold", {})
    gold_price = gold.get("end_price", 0) or 0
    gold_change = gold.get("wow_change_pct", 0) or 0

    # Build Plotly chart data
    # Index bar chart data
    idx_names_json = json.dumps(list(indices.keys()))
    idx_changes_json = json.dumps([indices[n].get("wow_change_pct", 0) for n in indices])
    idx_colors_json = json.dumps(["#10b981" if indices[n].get("wow_change_pct", 0) >= 0 else "#ef4444" for n in indices])

    # Sector ETF bar chart data
    etf_names_json = json.dumps(list(sector_etfs.keys()))
    etf_changes_json = json.dumps([sector_etfs[n].get("wow_change_pct", 0) for n in sector_etfs])
    etf_colors_json = json.dumps(["#10b981" if sector_etfs[n].get("wow_change_pct", 0) >= 0 else "#ef4444" for n in sector_etfs])

    # FX bar chart data
    fx_names_json = json.dumps(list(fx.keys()))
    fx_changes_json = json.dumps([fx[n].get("wow_change_pct", 0) for n in fx])
    fx_colors_json = json.dumps(["#3b82f6" if fx[n].get("wow_change_pct", 0) >= 0 else "#f97316" for n in fx])

    # Commodity bar data
    comm_names_json = json.dumps(list(commodities.keys()))
    comm_changes_json = json.dumps([commodities[n].get("wow_change_pct", 0) for n in commodities])
    comm_colors_json = json.dumps(["#f59e0b" if commodities[n].get("wow_change_pct", 0) >= 0 else "#ef4444" for n in commodities])

    # Stock scatter data (WoW change vs sector)
    stock_tickers = [t for t, _ in sorted(stocks.items(), key=lambda x: x[1].get("wow_change_pct", 0))]
    stock_changes = [stocks[t].get("wow_change_pct", 0) for t in stock_tickers]
    stock_sectors = [stocks[t].get("sector", "") for t in stock_tickers]
    stock_tickers_json = json.dumps(stock_tickers)
    stock_changes_json = json.dumps(stock_changes)
    stock_colors_json = json.dumps(["#10b981" if c >= 0 else "#ef4444" for c in stock_changes])

    # Winner/loser table rows
    winner_rows = "\n".join(
        f'<tr><td><strong>{w["ticker"]}</strong></td><td>{w.get("sector", "")}</td>'
        f'<td>{w.get("index", "")}</td>'
        f'<td class="positive">{_fmt_pct(w["wow_pct"])}</td></tr>'
        for w in winners
    )
    loser_rows = "\n".join(
        f'<tr><td><strong>{l["ticker"]}</strong></td><td>{l.get("sector", "")}</td>'
        f'<td>{l.get("index", "")}</td>'
        f'<td class="negative">{_fmt_pct(l["wow_pct"])}</td></tr>'
        for l in losers
    )

    # FX table
    fx_rows = "\n".join(
        f'<tr><td>{pair}</td><td>{fdata.get("end_rate", fdata.get("end_price", 0)):.4f}</td>'
        f'<td class="{"positive" if fdata.get("wow_change_pct", 0) >= 0 else "negative"}">'
        f'{_fmt_pct(fdata.get("wow_change_pct", 0))}</td></tr>'
        for pair, fdata in fx.items()
    )

    # Index performance table
    idx_table_rows = "\n".join(
        f'<tr><td><strong>{name}</strong></td>'
        f'<td>{_fmt_price(idx.get("end_price", 0), idx.get("currency", "USD"))}</td>'
        f'<td>{_fmt_price(idx.get("start_price", 0), idx.get("currency", "USD"))}</td>'
        f'<td class="{"positive" if idx.get("wow_change_pct", 0) >= 0 else "negative"}">'
        f'{_fmt_pct(idx.get("wow_change_pct", 0))}</td></tr>'
        for name, idx in indices.items()
    )

    # Stock cards with AI-generated commentary
    stock_commentary = _generate_stock_commentary(stocks)
    stock_cards_html = _build_stock_cards(stocks, commentary=stock_commentary)

    # Sidebar nav entries for top stocks
    stock_nav = "\n".join(
        f'    <a href="#stock-{t.lower().replace(".", "")}">{t}</a>'
        for t, _ in sorted(stocks.items(), key=lambda x: abs(x[1].get("wow_change_pct", 0)), reverse=True)[:12]
    )

    # Sector ETF table
    etf_table_rows = "\n".join(
        f'<tr><td><strong>{name}</strong></td>'
        f'<td>{_fmt_price(edata.get("end_price", 0))}</td>'
        f'<td class="{"positive" if edata.get("wow_change_pct", 0) >= 0 else "negative"}">'
        f'{_fmt_pct(edata.get("wow_change_pct", 0))}</td></tr>'
        for name, edata in sector_etfs.items()
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Anka Research | {week_label} — {period['start']} to {period['end']}</title>
<meta name="description" content="Anka Research {week_label}: AI-augmented weekly wartime market analysis across 8 global indices, 20 stocks, commodities, and FX.">
<script src="https://cdn.plot.ly/plotly-2.35.0.min.js"></script>
<style>
:root {{
  --bg-primary: #0a0e1a;
  --bg-secondary: #111827;
  --bg-card: #1a2035;
  --bg-card-hover: #1f2847;
  --text-primary: #e5e7eb;
  --text-secondary: #9ca3af;
  --text-muted: #6b7280;
  --accent-green: #10b981;
  --accent-red: #ef4444;
  --accent-gold: #f59e0b;
  --accent-blue: #3b82f6;
  --accent-purple: #8b5cf6;
  --accent-cyan: #06b6d4;
  --border-color: #1f2937;
  --border-highlight: #374151;
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
  font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif;
  background: var(--bg-primary);
  color: var(--text-primary);
  line-height: 1.6;
  display: flex;
}}
#sidebar {{
  position: fixed; left: 0; top: 0; width: 260px; height: 100vh;
  background: var(--bg-secondary); border-right: 1px solid var(--border-color);
  overflow-y: auto; z-index: 100; padding: 20px 0;
}}
#sidebar .logo {{
  padding: 0 20px 20px; border-bottom: 1px solid var(--border-color);
  margin-bottom: 15px;
}}
#sidebar .logo h2 {{ font-size: 14px; color: var(--accent-gold); text-transform: uppercase; letter-spacing: 2px; }}
#sidebar .logo p {{ font-size: 11px; color: var(--text-muted); margin-top: 4px; }}
#sidebar nav a {{
  display: block; padding: 8px 20px; color: var(--text-secondary);
  text-decoration: none; font-size: 13px; border-left: 3px solid transparent;
  transition: all 0.2s;
}}
#sidebar nav a:hover, #sidebar nav a.active {{
  background: var(--bg-card); color: var(--text-primary);
  border-left-color: var(--accent-gold);
}}
#sidebar nav a.section-head {{ font-weight: 700; color: var(--text-primary); font-size: 12px; text-transform: uppercase; letter-spacing: 1px; margin-top: 15px; }}
#main {{
  margin-left: 260px; padding: 30px 40px; width: calc(100% - 260px);
  max-width: 1200px;
}}
h1 {{ font-size: 28px; color: var(--accent-gold); margin-bottom: 5px; }}
h2 {{ font-size: 22px; color: var(--text-primary); margin: 40px 0 15px; padding-bottom: 8px; border-bottom: 1px solid var(--border-color); }}
h3 {{ font-size: 17px; color: var(--accent-cyan); margin: 25px 0 10px; }}
h4 {{ font-size: 14px; color: var(--accent-gold); margin: 15px 0 8px; text-transform: uppercase; letter-spacing: 1px; }}
p, li {{ font-size: 14px; color: var(--text-secondary); margin-bottom: 8px; }}
.subtitle {{ font-size: 15px; color: var(--text-muted); margin-bottom: 30px; }}
.dashboard {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; margin: 20px 0; }}
.dash-card {{
  background: var(--bg-card); border-radius: 8px; padding: 18px;
  border: 1px solid var(--border-color);
}}
.dash-card .label {{ font-size: 11px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 1px; }}
.dash-card .value {{ font-size: 24px; font-weight: 700; margin: 5px 0; }}
.dash-card .change {{ font-size: 13px; font-weight: 600; }}
.positive {{ color: var(--accent-green); }}
.negative {{ color: var(--accent-red); }}
.neutral {{ color: var(--accent-gold); }}
table {{ width: 100%; border-collapse: collapse; margin: 15px 0; font-size: 13px; }}
th {{
  background: var(--bg-secondary); color: var(--accent-gold); padding: 10px 12px;
  text-align: left; font-size: 11px; text-transform: uppercase; letter-spacing: 1px;
  border-bottom: 2px solid var(--border-highlight);
}}
td {{ padding: 10px 12px; border-bottom: 1px solid var(--border-color); color: var(--text-secondary); }}
tr:hover td {{ background: var(--bg-card-hover); }}
.stock-card {{
  background: var(--bg-card); border-radius: 10px; padding: 25px;
  border: 1px solid var(--border-color); margin: 20px 0;
  transition: border-color 0.3s;
}}
.stock-card:hover {{ border-color: var(--accent-gold); }}
.stock-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; }}
.stock-header .ticker {{ font-size: 22px; font-weight: 700; color: var(--accent-gold); }}
.stock-header .name {{ font-size: 15px; color: var(--text-primary); margin-left: 12px; }}
.stock-desc {{ font-size: 13px; color: #9ca3af; line-height: 1.5; margin: -8px 0 12px 0; padding: 0; }}
.anka-take {{ font-size: 13px; color: #d1d5db; line-height: 1.6; margin: 0 0 14px 0; padding: 10px 14px; background: rgba(212,168,85,0.08); border-left: 3px solid var(--accent-gold); border-radius: 4px; }}
.badge {{
  display: inline-block; padding: 3px 10px; border-radius: 12px;
  font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px;
}}
.badge-defense {{ background: #1e3a2f; color: #34d399; }}
.badge-energy {{ background: #3b1f1f; color: #f87171; }}
.badge-commodity {{ background: #3b2f1f; color: #fbbf24; }}
.badge-tech {{ background: #1f2d3b; color: #60a5fa; }}
.badge-shipping {{ background: #1f3b3b; color: #2dd4bf; }}
.badge-pharma {{ background: #1f2a3b; color: #93c5fd; }}
.two-col {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-top: 15px; }}
.factor-box {{
  background: var(--bg-secondary); border-radius: 8px; padding: 15px;
  border-left: 3px solid var(--accent-blue);
}}
.factor-box.macro {{ border-left-color: var(--accent-purple); }}
.factor-box.specific {{ border-left-color: var(--accent-green); }}
.factor-box h4 {{ margin-top: 0; }}
.factor-box ul {{ padding-left: 18px; }}
.factor-box li {{ font-size: 13px; margin-bottom: 6px; }}
.metrics-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin: 15px 0; }}
.metric {{
  background: var(--bg-secondary); border-radius: 6px; padding: 10px;
  text-align: center;
}}
.metric .metric-label {{ font-size: 10px; color: var(--text-muted); text-transform: uppercase; }}
.metric .metric-value {{ font-size: 18px; font-weight: 700; margin-top: 3px; }}
.chart-container {{ background: var(--bg-card); border-radius: 8px; padding: 15px; margin: 15px 0; border: 1px solid var(--border-color); min-height: 400px; overflow: visible; }}
.ratings-bar {{
  display: flex; height: 8px; border-radius: 4px; overflow: hidden; margin-top: 8px;
}}
.rb-segment {{ height: 100%; }}
.footer-section {{
  text-align: center; padding: 40px 20px;
  border-top: 1px solid var(--border-color);
  color: var(--text-muted); font-size: 12px;
}}
@media print {{
  #sidebar {{ display: none; }}
  #main {{ margin-left: 0; max-width: 100%; }}
  .stock-card {{ break-inside: avoid; }}
}}
@media (max-width: 1024px) {{
  #sidebar {{ width: 200px; }}
  #main {{ margin-left: 200px; width: calc(100% - 200px); padding: 20px; }}
  .dashboard {{ grid-template-columns: repeat(2, 1fr); }}
}}
@media (max-width: 768px) {{
  #sidebar {{ display: none; }}
  #main {{ margin-left: 0; width: 100%; padding: 15px; }}
  .two-col {{ grid-template-columns: 1fr; }}
  .dashboard {{ grid-template-columns: 1fr 1fr; }}
  .metrics-grid {{ grid-template-columns: repeat(2, 1fr); }}
}}
</style>
</head>
<body>

<!-- SIDEBAR -->
<div id="sidebar">
  <div class="logo">
    <h2>Anka Research</h2>
    <p>AI-Augmented Market Intelligence<br>Bharat Ankaraju | {week_label}</p>
  </div>
  <nav>
    <a href="/">Back to askanka.com</a>
    <a href="#executive-summary">Executive Summary</a>
    <a href="#global-indices">Global Indices</a>
    <a href="#commodities">Commodities & Energy</a>
    <a href="#fx-impact">FX Impact</a>
    <a href="#sector-performance">Sector Performance</a>
    <a href="#top-movers" class="section-head">Top Movers</a>
    <a href="#winners">Winners</a>
    <a href="#losers">Losers</a>
    <a href="#stock-deep-dives" class="section-head">Stock Deep Dives</a>
{stock_nav}
    <a href="#methodology" class="section-head">Methodology</a>
    <a href="#methodology">Sources & Disclaimer</a>
  </nav>
</div>

<!-- MAIN CONTENT -->
<div id="main">

<section id="executive-summary">
<div style="display:flex;align-items:center;gap:15px;margin-bottom:5px;">
  <div style="width:50px;height:50px;background:linear-gradient(135deg,#f59e0b,#d97706);border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:24px;font-weight:900;color:#0a0e1a;">A</div>
  <div>
    <h1 style="margin-bottom:0;">{week_label} — Weekly Market Brief</h1>
    <p style="font-size:12px;color:#6b7280;margin:2px 0 0;">Anka Research | AI-Augmented Market Intelligence</p>
  </div>
</div>
<p class="subtitle">Wartime Market Analysis | {period['start']} to {period['end']}<br>
<span style="font-size:12px;color:#9ca3af;">By Bharat Ankaraju | Published {period['end']} | Weekly Research Brief #{week_num:03d}</span></p>

<div class="dashboard">
  <div class="dash-card">
    <div class="label">Brent Crude</div>
    <div class="value {"positive" if brent_change >= 0 else "negative"}">${brent_price:,.2f}</div>
    <div class="change {"positive" if brent_change >= 0 else "negative"}">{_fmt_pct(brent_change)} WoW</div>
  </div>
  <div class="dash-card">
    <div class="label">Gold</div>
    <div class="value {"positive" if gold_change >= 0 else "negative"}">${gold_price:,.2f}</div>
    <div class="change {"positive" if gold_change >= 0 else "negative"}">{_fmt_pct(gold_change)} WoW</div>
  </div>
  <div class="dash-card">
    <div class="label">VIX</div>
    <div class="value {"positive" if vix_change < 0 else "negative"}">{vix_price:.1f}</div>
    <div class="change {"positive" if vix_change < 0 else "negative"}">{_fmt_pct(vix_change)} WoW</div>
  </div>
  <div class="dash-card">
    <div class="label">Best Index</div>
    <div class="value positive">{best_idx.get('name', 'N/A')}</div>
    <div class="change positive">{_fmt_pct(best_idx.get('wow_pct', 0))}</div>
  </div>
</div>

<div class="dashboard">
  <div class="dash-card">
    <div class="label">Worst Index</div>
    <div class="value negative">{worst_idx.get('name', 'N/A')}</div>
    <div class="change negative">{_fmt_pct(worst_idx.get('wow_pct', 0))}</div>
  </div>
  <div class="dash-card">
    <div class="label">Top Winner</div>
    <div class="value positive">{winners[0]['ticker'] if winners else 'N/A'}</div>
    <div class="change positive">{_fmt_pct(winners[0]['wow_pct']) if winners else ''}</div>
  </div>
  <div class="dash-card">
    <div class="label">Top Loser</div>
    <div class="value negative">{losers[-1]['ticker'] if losers else 'N/A'}</div>
    <div class="change negative">{_fmt_pct(losers[-1]['wow_pct']) if losers else ''}</div>
  </div>
  <div class="dash-card">
    <div class="label">Stocks Tracked</div>
    <div class="value neutral">{len(stocks)}</div>
    <div class="change neutral">across {len(indices)} indices</div>
  </div>
</div>
</section>

<!-- GLOBAL INDICES -->
<section id="global-indices">
<h2>Global Indices Performance</h2>
<div id="chart-indices" class="chart-container"></div>
<table>
  <thead><tr><th>Index</th><th>Close</th><th>Previous</th><th>WoW Change</th></tr></thead>
  <tbody>{idx_table_rows}</tbody>
</table>
</section>

<!-- COMMODITIES -->
<section id="commodities">
<h2>Commodities & Energy</h2>
<div id="chart-commodities" class="chart-container" style="min-height:350px;"></div>
<table>
  <thead><tr><th>Commodity</th><th>Price</th><th>WoW Change</th></tr></thead>
  <tbody>{''.join(f'<tr><td><strong>{n}</strong></td><td>{_fmt_price(c.get("end_price", 0))}</td><td class="{"positive" if c.get("wow_change_pct", 0) >= 0 else "negative"}">{_fmt_pct(c.get("wow_change_pct", 0))}</td></tr>' for n, c in commodities.items())}</tbody>
</table>
</section>

<!-- FX -->
<section id="fx-impact">
<h2>Currency Impact</h2>
<div id="chart-fx" class="chart-container" style="min-height:350px;"></div>
<table>
  <thead><tr><th>Pair</th><th>Rate</th><th>WoW Change</th></tr></thead>
  <tbody>{fx_rows}</tbody>
</table>
</section>

<!-- SECTOR PERFORMANCE -->
<section id="sector-performance">
<h2>Sector Performance (ETFs)</h2>
<div id="chart-sectors" class="chart-container"></div>
<table>
  <thead><tr><th>Sector ETF</th><th>Price</th><th>WoW Change</th></tr></thead>
  <tbody>{etf_table_rows}</tbody>
</table>
</section>

<!-- TOP MOVERS -->
<section id="top-movers">
<h2>Top Movers This Week</h2>

<div id="chart-stocks" class="chart-container"></div>

<h3 id="winners">Top 5 Winners</h3>
<table>
  <thead><tr><th>Ticker</th><th>Sector</th><th>Index</th><th>WoW</th></tr></thead>
  <tbody>{winner_rows}</tbody>
</table>

<h3 id="losers">Top 5 Losers</h3>
<table>
  <thead><tr><th>Ticker</th><th>Sector</th><th>Index</th><th>WoW</th></tr></thead>
  <tbody>{loser_rows}</tbody>
</table>
</section>

<!-- STOCK DEEP DIVES -->
<section id="stock-deep-dives">
<h2>Stock Deep Dives</h2>
<p>Detailed analysis of the top 12 movers this week, including fundamentals, analyst consensus, and ownership data.</p>
{stock_cards_html}
</section>

<!-- METHODOLOGY -->
<section id="methodology">
<h2>Methodology & Sources</h2>
<h3>Data Collection</h3>
<ul>
  <li><strong>Period:</strong> {period['start']} to {period['end']} (Week {week_num})</li>
  <li><strong>Indices:</strong> {len(indices)} global indices (S&P 500, FTSE 100, CAC 40, DAX, Nifty 50, KOSPI, Nikkei 225, CSI 300)</li>
  <li><strong>Stocks:</strong> {len(stocks)} individual stocks across all indices</li>
  <li><strong>Data Sources:</strong> EODHD (primary), Yahoo Finance (supplementary, analyst data, ownership)</li>
  <li><strong>FX Rates:</strong> 6 major pairs from EODHD</li>
  <li><strong>Commodities:</strong> Brent, WTI, Gold, Natural Gas from EODHD</li>
</ul>

<h3>Report Generation</h3>
<p>This report is generated automatically by the Anka Research Pipeline. Daily market data is collected at 4:30 PM IST (Mon-Fri), aggregated into weekly JSON on Saturday mornings, and converted to this HTML report with interactive Plotly charts.</p>

<h3>Limitations</h3>
<ul>
  <li>Week-over-week returns are based on last available closing prices and may not reflect intraday extremes</li>
  <li>Analyst consensus data from Yahoo Finance may have a 1-2 day lag</li>
  <li>Some fundamental data points may be unavailable for non-US stocks</li>
  <li>Conflict ongoing — data and context subject to rapid change</li>
</ul>
</section>

<div class="footer-section">
  <p><strong>Anka Research</strong> | AI-Augmented Market Intelligence</p>
  <p>By Bharat Ankaraju | {week_label} | Published {period['end']}</p>
  <p style="margin-top:12px;font-size:11px;max-width:600px;margin-left:auto;margin-right:auto;">
    This report is for informational purposes only and does not constitute investment advice.
    Past performance is not indicative of future results. All data sourced from public markets.
    AI-assisted analysis with human oversight.
  </p>
  <p style="margin-top:8px;font-size:10px;">Generated by Anka Pipeline on {data.get('generated_at', '')[:19]}</p>
</div>

</div><!-- /main -->

<!-- PLOTLY CHARTS -->
<script>
const C = {{
  green: '#10b981', red: '#ef4444', gold: '#f59e0b', blue: '#3b82f6',
  purple: '#8b5cf6', cyan: '#06b6d4', pink: '#ec4899', orange: '#f97316',
  bg: '#1a2035', grid: '#1f2937', text: '#9ca3af'
}};
const L = {{
  paper_bgcolor: C.bg, plot_bgcolor: C.bg,
  font: {{ color: C.text, family: 'Segoe UI, sans-serif', size: 12 }},
  xaxis: {{ gridcolor: C.grid, zerolinecolor: C.grid }},
  yaxis: {{ gridcolor: C.grid, zerolinecolor: C.grid, title: 'WoW Change (%)' }},
  margin: {{ l: 60, r: 30, t: 50, b: 80 }},
  showlegend: false
}};

// Index Performance Bar Chart
Plotly.newPlot('chart-indices', [{{
  x: {idx_names_json},
  y: {idx_changes_json},
  type: 'bar',
  marker: {{ color: {idx_colors_json}, line: {{ width: 0 }} }},
  text: {idx_changes_json}.map(v => v.toFixed(2) + '%'),
  textposition: 'outside',
  textfont: {{ size: 11, color: C.text }}
}}], {{
  ...L,
  title: {{ text: 'Global Index Performance (WoW %)', font: {{ size: 16, color: C.gold }} }},
  xaxis: {{ ...L.xaxis, tickangle: -30 }}
}}, {{ responsive: true }});

// Commodity Bar Chart
Plotly.newPlot('chart-commodities', [{{
  x: {comm_names_json},
  y: {comm_changes_json},
  type: 'bar',
  marker: {{ color: {comm_colors_json}, line: {{ width: 0 }} }},
  text: {comm_changes_json}.map(v => v.toFixed(2) + '%'),
  textposition: 'outside',
  textfont: {{ size: 11, color: C.text }}
}}], {{
  ...L,
  title: {{ text: 'Commodity Performance (WoW %)', font: {{ size: 16, color: C.gold }} }}
}}, {{ responsive: true }});

// FX Bar Chart
Plotly.newPlot('chart-fx', [{{
  x: {fx_names_json},
  y: {fx_changes_json},
  type: 'bar',
  marker: {{ color: {fx_colors_json}, line: {{ width: 0 }} }},
  text: {fx_changes_json}.map(v => v.toFixed(2) + '%'),
  textposition: 'outside',
  textfont: {{ size: 11, color: C.text }}
}}], {{
  ...L,
  title: {{ text: 'FX Movements (WoW %)', font: {{ size: 16, color: C.gold }} }}
}}, {{ responsive: true }});

// Sector ETF Bar Chart
Plotly.newPlot('chart-sectors', [{{
  x: {etf_names_json},
  y: {etf_changes_json},
  type: 'bar',
  marker: {{ color: {etf_colors_json}, line: {{ width: 0 }} }},
  text: {etf_changes_json}.map(v => v.toFixed(2) + '%'),
  textposition: 'outside',
  textfont: {{ size: 11, color: C.text }}
}}], {{
  ...L,
  title: {{ text: 'Sector ETF Performance (WoW %)', font: {{ size: 16, color: C.gold }} }},
  xaxis: {{ ...L.xaxis, tickangle: -35 }}
}}, {{ responsive: true }});

// Stock Waterfall Chart
Plotly.newPlot('chart-stocks', [{{
  x: {stock_tickers_json},
  y: {stock_changes_json},
  type: 'bar',
  marker: {{ color: {stock_colors_json}, line: {{ width: 0 }} }},
  text: {stock_changes_json}.map(v => v.toFixed(1) + '%'),
  textposition: 'outside',
  textfont: {{ size: 10, color: C.text }}
}}], {{
  ...L,
  title: {{ text: 'All Stocks — WoW Performance (%)', font: {{ size: 16, color: C.gold }} }},
  xaxis: {{ ...L.xaxis, tickangle: -45, tickfont: {{ size: 10 }} }},
  margin: {{ l: 60, r: 30, t: 50, b: 100 }}
}}, {{ responsive: true }});

// Sidebar active link tracking
document.addEventListener('scroll', function() {{
  const sections = document.querySelectorAll('section[id]');
  const links = document.querySelectorAll('#sidebar nav a');
  let current = '';
  sections.forEach(s => {{
    if (window.scrollY >= s.offsetTop - 100) current = s.id;
  }});
  links.forEach(a => {{
    a.classList.remove('active');
    if (a.getAttribute('href') === '#' + current) a.classList.add('active');
  }});
}});
</script>

</body>
</html>"""

    return html


def update_index_html(week_num: int, data: dict) -> None:
    """Update the main index.html to point to the latest report."""
    index_file = SITE_DIR / "index.html"
    if not index_file.exists():
        log.warning("index.html not found, skipping update")
        return

    content = index_file.read_text(encoding="utf-8")
    period = data["period"]
    rankings = data.get("rankings", {})
    best_idx = rankings.get("best_index", {})
    worst_idx = rankings.get("worst_index", {})
    winners = rankings.get("top_5_winners", [])

    # Find and replace the latest report card
    import re

    # Replace the href
    content = re.sub(
        r'href="reports/week-\d+\.html"',
        f'href="reports/week-{week_num:03d}.html"',
        content,
        count=1,
    )

    # Replace the date
    content = re.sub(
        r'(<span class="date">)\d{4}-\d{2}-\d{2}(</span>)',
        f'\\g<1>{period["end"]}\\2',
        content,
        count=1,
    )

    # Replace the title
    top_winner = winners[0]["ticker"] if winners else "N/A"
    title = f"Weekly Brief #{week_num:03d} — {period['start']} to {period['end']}"
    content = re.sub(
        r'(<h3>)Weekly Brief #\d+ .+?(</h3>)',
        f'\\g<1>{title}\\2',
        content,
        count=1,
    )

    index_file.write_text(content, encoding="utf-8")
    log.info(f"Updated index.html to point to week-{week_num:03d}")


def update_library_html(week_num: int, data: dict) -> None:
    """Add the new weekly report to the library page."""
    library_file = REPORTS_DIR / "library.html"
    if not library_file.exists():
        log.warning("library.html not found, skipping update")
        return

    content = library_file.read_text(encoding="utf-8")
    period = data["period"]

    # Check if this week already exists
    week_file = f"week-{week_num:03d}.html"
    if week_file in content:
        log.info(f"Week {week_num:03d} already in library, skipping")
        return

    # Insert new card after the "Weekly Briefs" section label
    new_card = f"""
        <a href="{week_file}" class="report-card">
            <div class="card-top">
                <span class="badge">Week {week_num:03d}</span>
                <span class="date">{period['end']}</span>
            </div>
            <h3>Weekly Brief #{week_num:03d} — {period['start']} to {period['end']}</h3>
            <p class="description">Automated weekly market analysis across 8 global indices, 20 stocks, commodities, and FX.</p>
        </a>
"""

    # Insert after the section-label div for Weekly Briefs
    insert_marker = '<div class="section-label">Weekly Briefs</div>'
    if insert_marker in content:
        content = content.replace(
            insert_marker,
            insert_marker + new_card,
        )
        library_file.write_text(content, encoding="utf-8")
        log.info(f"Added week-{week_num:03d} to library.html")
    else:
        log.warning("Could not find insertion point in library.html")


def validate_weekly_data(data: dict) -> list[str]:
    """Pre-publish guardrail: validate weekly JSON before generating HTML.

    Returns list of FATAL errors. If non-empty, the report MUST NOT be published.
    Logs warnings for non-fatal anomalies.
    """
    errors = []
    warnings = []
    period = data.get("period", {})

    # ── 1. Structure checks ──────────────────────────────────────────────
    required_keys = ["period", "indices", "stocks", "fx", "commodities", "rankings"]
    for k in required_keys:
        if k not in data or not data[k]:
            errors.append(f"Missing or empty required section: '{k}'")

    if not period.get("start") or not period.get("end"):
        errors.append("Period start/end dates missing")

    # ── 2. Minimum data thresholds ───────────────────────────────────────
    indices = data.get("indices", {})
    stocks = data.get("stocks", {})
    fx = data.get("fx", {})
    commodities = data.get("commodities", {})

    if len(indices) < 4:
        errors.append(f"Only {len(indices)} indices (minimum 4 required)")
    if len(stocks) < 10:
        errors.append(f"Only {len(stocks)} stocks (minimum 10 required)")
    if len(fx) < 3:
        errors.append(f"Only {len(fx)} FX pairs (minimum 3 required)")
    if len(commodities) < 2:
        errors.append(f"Only {len(commodities)} commodities (minimum 2 required)")

    # ── 3. Price sanity checks (no zeros, no nulls, no absurd values) ───
    for name, idx in indices.items():
        ep = idx.get("end_price")
        if ep is None or ep == 0:
            errors.append(f"Index '{name}' has zero/null end_price")
        wow = idx.get("wow_change_pct")
        if wow is not None and abs(wow) > 30:
            errors.append(f"Index '{name}' wow_change_pct={wow:.1f}% exceeds ±30% — likely data error")

    for ticker, s in stocks.items():
        ep = s.get("end_price")
        if ep is None or ep == 0:
            errors.append(f"Stock '{ticker}' has zero/null end_price")
        wow = s.get("wow_change_pct")
        if wow is not None and abs(wow) > 50:
            errors.append(f"Stock '{ticker}' wow_change_pct={wow:.1f}% exceeds ±50% — likely data error")
        elif wow is not None and abs(wow) > 25:
            warnings.append(f"Stock '{ticker}' wow_change_pct={wow:.1f}% is unusually large")

    for pair, fd in fx.items():
        rate = fd.get("end_rate", fd.get("end_price"))
        if rate is None or rate == 0:
            errors.append(f"FX '{pair}' has zero/null rate")
        wow = fd.get("wow_change_pct")
        if wow is not None and abs(wow) > 15:
            errors.append(f"FX '{pair}' wow_change_pct={wow:.1f}% exceeds ±15% — likely data error")

    for name, cd in commodities.items():
        ep = cd.get("end_price")
        if ep is None or ep == 0:
            errors.append(f"Commodity '{name}' has zero/null end_price")
        wow = cd.get("wow_change_pct")
        if wow is not None and abs(wow) > 40:
            errors.append(f"Commodity '{name}' wow_change_pct={wow:.1f}% exceeds ±40% — likely data error")

    # ── 4. Rankings consistency ──────────────────────────────────────────
    rankings = data.get("rankings", {})
    top5 = rankings.get("top_5_winners", [])
    bot5 = rankings.get("top_5_losers", [])
    if len(top5) < 3:
        errors.append(f"Only {len(top5)} top winners (need at least 3)")
    if len(bot5) < 3:
        errors.append(f"Only {len(bot5)} top losers (need at least 3)")

    # Verify ranked tickers actually exist in stocks
    all_tickers = set(stocks.keys())
    for entry in top5 + bot5:
        t = entry.get("ticker", "") if isinstance(entry, dict) else ""
        if t and t not in all_tickers:
            warnings.append(f"Ranked ticker '{t}' not found in stocks data")

    # ── 5. Date sanity ───────────────────────────────────────────────────
    try:
        start = datetime.strptime(period.get("start", ""), "%Y-%m-%d")
        end = datetime.strptime(period.get("end", ""), "%Y-%m-%d")
        span = (end - start).days
        if span < 4 or span > 10:
            warnings.append(f"Period spans {span} days (expected 5-7 for a trading week)")
        if end > datetime.now():
            errors.append(f"End date {period['end']} is in the future")
    except ValueError:
        errors.append("Could not parse period dates")

    # ── Log results ──────────────────────────────────────────────────────
    for w in warnings:
        log.warning(f"VALIDATION WARNING: {w}")
    for e in errors:
        log.error(f"VALIDATION FATAL: {e}")

    if not errors:
        log.info(f"VALIDATION PASSED: {len(indices)} indices, {len(stocks)} stocks, "
                 f"{len(fx)} FX pairs, {len(commodities)} commodities")

    return errors


def generate_weekly_report(week_num: int = None, deploy: bool = False) -> Path:
    """Main entry: generate HTML report, update site, optionally deploy."""
    if week_num is None:
        week_num = _find_latest_week()

    log.info(f"Generating report for week {week_num:03d}")

    data = _load_week_data(week_num)

    # ── GUARDRAIL: validate before generating ────────────────────────────
    validation_errors = validate_weekly_data(data)
    if validation_errors:
        log.error(f"REPORT BLOCKED — {len(validation_errors)} validation error(s):")
        for e in validation_errors:
            log.error(f"  • {e}")
        raise ValueError(
            f"Report generation blocked for week {week_num:03d}: "
            f"{len(validation_errors)} fatal validation error(s). "
            f"Fix the data before publishing."
        )

    html = generate_report_html(data)

    # Write report
    report_file = REPORTS_DIR / f"week-{week_num:03d}.html"
    report_file.write_text(html, encoding="utf-8")
    log.info(f"Report written to {report_file}")

    # Append the weekly brief to data/weekly_index.json (single source of truth).
    # The homepage reads this JSON client-side via JS. This script NEVER touches
    # index.html or library.html anymore — that was the regression source that
    # clobbered 934 lines of homepage features on 2026-04-11 (commit 40822e4).
    _append_to_weekly_index(week_num, data)

    # ── GUARDRAIL: verify HTML output before deploy ────────────────────
    html_size = report_file.stat().st_size
    if html_size < 5000:
        log.error(f"Generated HTML is only {html_size} bytes — suspiciously small, aborting deploy")
        raise ValueError(f"HTML output too small ({html_size} bytes), likely broken template")

    # Spot-check: verify key sections exist in the output
    html_check = report_file.read_text(encoding="utf-8")
    required_sections = ["plotly", "Executive Summary", "stock-card", "Methodology"]
    missing = [s for s in required_sections if s.lower() not in html_check.lower()]
    if missing:
        log.error(f"Generated HTML missing sections: {missing}")
        raise ValueError(f"HTML output missing required sections: {missing}")

    log.info(f"HTML guardrail passed: {html_size:,} bytes, all sections present")

    if deploy:
        log.info("Deploying to GitHub Pages...")
        try:
            subprocess.run(
                ["git", "add", "reports/", "data/weekly_index.json"],
                cwd=str(SITE_DIR), check=True,
            )
            subprocess.run(
                ["git", "commit", "-m",
                 f"Weekly report: week-{week_num:03d} ({data['period']['start']} to {data['period']['end']})"],
                cwd=str(SITE_DIR), check=True,
            )
            subprocess.run(
                ["git", "push", "origin", "master"],
                cwd=str(SITE_DIR), check=True,
            )
            log.info("Deployed successfully")
        except subprocess.CalledProcessError as e:
            log.error(f"Deploy failed: {e}")

    return report_file


def _append_to_weekly_index(week_num: int, data: dict) -> None:
    """Append this week's brief to data/weekly_index.json (single source of truth).

    Schema:
    {
      "weekly_briefs": [
        {"week": 7, "filename": "week-007.html",
         "period_start": "2026-04-06", "period_end": "2026-04-11",
         "title": "...", "description": "...",
         "top_winner": {...}, "top_loser": {...}, "published_at": "2026-04-11"}
      ]
    }
    """
    index_json = SITE_DIR / "data" / "weekly_index.json"
    index_json.parent.mkdir(parents=True, exist_ok=True)

    if index_json.exists():
        try:
            store = json.loads(index_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            store = {"weekly_briefs": []}
    else:
        store = {"weekly_briefs": []}

    briefs = store.get("weekly_briefs", [])

    period = data.get("period", {})
    top_winner = data.get("top_winner") or {}
    top_loser = data.get("top_loser") or {}

    entry = {
        "week": week_num,
        "filename": f"week-{week_num:03d}.html",
        "period_start": period.get("start", ""),
        "period_end": period.get("end", ""),
        "title": f"Weekly Brief #{week_num:03d} — {period.get('start','')} to {period.get('end','')}",
        "description": (
            f"Automated weekly market analysis. "
            f"Top winner: {top_winner.get('ticker','?')} {top_winner.get('wow_pct','?')}%. "
            f"Top loser: {top_loser.get('ticker','?')} {top_loser.get('wow_pct','?')}%."
        ),
        "top_winner": top_winner,
        "top_loser": top_loser,
        "published_at": datetime.now().strftime("%Y-%m-%d"),
    }

    # Dedupe on week number
    existing_idx = next((i for i, b in enumerate(briefs) if b.get("week") == week_num), None)
    if existing_idx is not None:
        briefs[existing_idx] = entry
    else:
        briefs.append(entry)

    # Sort newest first
    briefs.sort(key=lambda b: b.get("week", 0), reverse=True)

    index_json.write_text(
        json.dumps({"weekly_briefs": briefs}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    log.info(f"weekly_index.json updated: {len(briefs)} total briefs")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    parser = argparse.ArgumentParser(description="Anka Weekly Report Generator")
    parser.add_argument("--week", type=int, help="Week number (default: latest)")
    parser.add_argument("--deploy", action="store_true", help="Git push after generating")
    args = parser.parse_args()

    result = generate_weekly_report(week_num=args.week, deploy=args.deploy)
    print(f"Report generated: {result}")
