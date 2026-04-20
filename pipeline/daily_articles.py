"""
Anka Research — Daily Article Generator
Scrapes YouTube sources, generates provocative daily analysis articles,
and publishes to askanka.com. Runs after market close.

Two daily articles:
  1. War/Geopolitics — Iran-US, Hormuz, oil, defence spending
  2. Epstein Files — DOJ releases, legal proceedings, cover-up

Sources: 40+ YouTube channels from Bharat's research (video_pipeline.py)
Style: Provocative, investigative, sourced. Not neutral — we have a view.

Articles go to /articles/YYYY-MM-DD-war.html and /articles/YYYY-MM-DD-epstein.html
Homepage shows today's articles; old ones move to Library.
"""

import json
import logging
import os
import re
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

from article_grounding import (
    load_market_context, load_prior_context, build_topic_panel,
    verify_narrative, render_panel_html, MarketDataMissing, TOPIC_SCHEMAS,
)

log = logging.getLogger("anka.daily_articles")

IST = timezone(timedelta(hours=5, minutes=30))
PIPELINE_DIR = Path(__file__).parent
GIT_REPO = Path("C:/Users/Claude_Anka/askanka.com")

from dotenv import load_dotenv
load_dotenv(PIPELINE_DIR / ".env")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")


def _load_yesterday_example(segment: str) -> dict | None:
    """Load yesterday's article as a style reference for Gemini.

    Finds the most recent previously-published article for the same segment,
    extracts headline + first few paragraphs, and returns as example.
    """
    try:
        from datetime import datetime, timedelta
        articles_dir = GIT_REPO / "articles"
        if not articles_dir.exists():
            return None

        today = datetime.now(IST).date()
        # Look back up to 5 days for a recent example
        for days_back in range(1, 6):
            check_date = (today - timedelta(days=days_back)).strftime("%Y-%m-%d")
            candidate = articles_dir / f"{check_date}-{segment}.html"
            if candidate.exists():
                html = candidate.read_text(encoding="utf-8")
                # Extract headline from <h1>
                h1_match = re.search(r'<h1>(.*?)</h1>', html, re.DOTALL)
                headline = h1_match.group(1).strip() if h1_match else ""

                # Extract first 3 paragraphs from body
                body_match = re.search(r'<div class="body">(.*?)</div>', html, re.DOTALL)
                if body_match:
                    paras = re.findall(r'<p>(.*?)</p>', body_match.group(1), re.DOTALL)
                    # Strip HTML from paragraphs
                    clean_paras = [re.sub(r'<.*?>', '', p).strip() for p in paras[:3]]
                    body_excerpt = "\n\n".join(clean_paras)
                    return {"headline": headline, "body_excerpt": body_excerpt}
    except Exception as e:
        log.warning(f"Could not load yesterday's example: {e}")
    return None


def _load_recent_articles(segment: str, max_days: int = 5) -> list[dict]:
    """Return [{date, headline, opening, themes}, ...] for recent articles."""
    articles_dir = GIT_REPO / "articles"
    if not articles_dir.exists():
        return []
    today = datetime.now(IST).date()
    results = []
    for days_back in range(1, max_days + 1):
        check_date = (today - timedelta(days=days_back)).strftime("%Y-%m-%d")
        candidate = articles_dir / f"{check_date}-{segment}.html"
        if candidate.exists():
            try:
                html = candidate.read_text(encoding="utf-8")
                h1 = re.search(r"<h1>(.*?)</h1>", html, re.DOTALL)
                body = re.search(r'<div class="body">(.*?)</div>', html, re.DOTALL)
                opening = ""
                if body:
                    paras = re.findall(r"<p>(.*?)</p>", body.group(1), re.DOTALL)
                    if paras:
                        opening = re.sub(r"<[^>]+>", "", paras[0]).strip()[:300]
                results.append({
                    "date": check_date,
                    "headline": h1.group(1).strip() if h1 else "",
                    "opening": opening,
                })
            except Exception:
                continue
    return results


def scrape_today_sources(segment: str, days_back: int = 1) -> list:
    """Get today's relevant YouTube videos for a segment."""
    from video_pipeline import scrape_weekly_sources
    return scrape_weekly_sources(segment, days_back=days_back)


def generate_article(segment: str, sources: list, date: str) -> str:
    """Generate a provocative daily article from source headlines."""
    if not ANTHROPIC_API_KEY:
        return ""

    # Market-number grounding only applies to market-anchored topics.
    # Political/investigative topics (e.g. epstein) recontextualize YouTube
    # watch history and do not cite market data, so we skip the panel and
    # the verification gate for them.
    market_grounded = segment in TOPIC_SCHEMAS
    panel = {}
    panel_lines = ""
    if market_grounded:
        try:
            ctx = load_market_context(date)
        except MarketDataMissing as e:
            log.error(f"Cannot generate {segment} article — market data missing: {e}")
            return ""
        prior_ctx = load_prior_context(date)
        panel = build_topic_panel(segment, ctx, prior_context=prior_ctx)
        panel_lines = "\n".join(
            f"  - {k}: {v}" for k, v in panel.items()
            if k not in ("_raw", "_deltas")
        )

    template_path = GIT_REPO / "articles" / "_template" / "regime-engine-defining.html"
    template_excerpt = ""
    if template_path.exists():
        try:
            tpl_html = template_path.read_text(encoding="utf-8")
            h1 = re.search(r"<h1>(.*?)</h1>", tpl_html, re.DOTALL)
            body_match = re.search(r'<div class="body">(.*?)</div>', tpl_html, re.DOTALL)
            if body_match:
                paras = re.findall(r"<p>(.*?)</p>", body_match.group(1), re.DOTALL)
                clean = [re.sub(r"<.*?>", "", p).strip() for p in paras[:3]]
                template_excerpt = (
                    f"\n# REFERENCE STYLE — match this voice, structure, and "
                    f"panel-anchored discipline:\n"
                    f"Headline: {h1.group(1).strip() if h1 else ''}\n"
                    f"Opening paragraphs:\n" + "\n\n".join(clean) + "\n"
                )
        except Exception as e:
            log.warning(f"Could not load defining-article template: {e}")
    else:
        log.info(f"No defining-article template at {template_path}; using fallback style")

    if market_grounded:
        grounding_block = f"""
# GROUNDING — DO NOT VIOLATE
The following panel will be displayed to the reader at the top of the article:
{panel_lines}

Rules:
1. Every market number you cite (oil, gold, indices, currencies, yields) must match
   the panel within ±2%.
2. If a number you want to cite is NOT in the panel, OMIT it. Do not invent.
3. Non-market figures (population %, retail prices ₹/liter) are allowed
   but should not contradict the panel direction.
4. DO NOT make quantitative forecasts. Never write "could fall 5-10%", "may rise
   by 8%", "outperforming by 3-5%", "potentially gaining 12%", or any range/point
   prediction. Use qualitative language for predictions: "could weaken further",
   "likely to underperform", "downside risk", "upside skew". Numbers are only for
   what HAS happened (per the panel), never for what MIGHT happen.
5. Articles whose numbers contradict the panel — or that contain quantitative
   forecasts — are REJECTED and not published.
"""
    else:
        grounding_block = ""

    # ── ETF regime ground truth block (market-grounded topics only) ───────
    regime_block = ""
    if market_grounded:
        try:
            regime_path = GIT_REPO / "data" / "global_regime.json"
            today_regime_path = PIPELINE_DIR / "data" / "today_regime.json"
            if regime_path.exists():
                rg = json.loads(regime_path.read_text(encoding="utf-8"))
                comp = rg.get("components", {})
                # Augment panel["_raw"] with regime driver magnitudes so the
                # verifier treats them as approved panel values (the extractor
                # emits unsigned pct_bps, so store abs()).
                for name, c in comp.items():
                    raw_val = c.get("raw")
                    if isinstance(raw_val, (int, float)):
                        panel.setdefault("_raw", {})[f"regime_{name}"] = abs(raw_val)
                driver_lines = []
                for name, c in comp.items():
                    raw = c.get("raw")
                    if raw is None:
                        continue
                    label = {
                        "inst_flow": "FII/DII flow",
                        "india_vix": "India VIX",
                        "usdinr": "USD/INR 5d move",
                        "nifty_30d": "Nifty 30d return",
                        "crude_5d": "Brent 5d return",
                    }.get(name, name)
                    suffix = "%" if name in ("usdinr", "nifty_30d", "crude_5d") else ""
                    driver_lines.append(f"  - {label}: {raw}{suffix}")
                drivers_txt = "\n".join(driver_lines) if driver_lines else "  (no driver data)"
                eligible = []
                if today_regime_path.exists():
                    tr = json.loads(today_regime_path.read_text(encoding="utf-8"))
                    # Augment _raw with every win-rate surfaced so the LLM can
                    # cite them verbatim without tripping the verifier.
                    for sp_name, s in tr.get("eligible_spreads", {}).items():
                        for k in ("1d_win", "3d_win", "5d_win", "best_win"):
                            wv = s.get(k)
                            if isinstance(wv, (int, float)):
                                panel.setdefault("_raw", {})[f"win_{sp_name}_{k}"] = abs(wv)
                    for name, s in sorted(
                        tr.get("eligible_spreads", {}).items(),
                        key=lambda kv: -(kv[1].get("best_win") or 0),
                    )[:3]:
                        eligible.append(f"  - {name}: best win {s.get('best_win')}% over {s.get('best_period')}d")
                eligible_txt = "\n".join(eligible) if eligible else "  (none)"
                regime_block = f"""
# ETF REGIME GROUND TRUTH — align your thesis with this
Current zone: {rg.get('zone')} (score {rg.get('score')})
Top drivers: {', '.join(rg.get('top_drivers') or [])}
Component reads:
{drivers_txt}
Highest-edge spreads under this regime:
{eligible_txt}

If the ETF engine says crude is DOWN 5d, you cannot describe oil as "surging"
or "jumping". If VIX is falling, you cannot describe fear as rising. Your
narrative MUST be consistent with these component reads. Contradictions are
article failures.
"""
        except Exception as e:
            log.warning(f"Could not load ETF regime context: {e}")
            regime_block = ""

    seg_config = {
        "war": {
            "title_style": "provocative geopolitical analysis",
            "tone": "Investigative. Direct. Not neutral — we have a view. "
                    "Connect events to Indian market impact. Name names. "
                    "Quote specific sources. Ask hard questions the mainstream won't.",
            "framing": "Let today's sources drive your angle. Find the FRESHEST "
                      "development — a new escalation, a diplomatic shift, a supply "
                      "chain disruption, a policy reversal — and build the thesis "
                      "around THAT. Connect to Indian markets via the panel numbers.",
        },
        "epstein": {
            "title_style": "investigative journalism",
            "tone": "Forensic. Relentless. Connect dots across documents. "
                    "This is a cover-up and we say so. Name the players. "
                    "Quote court filings. Ask why the mainstream is silent.",
            "framing": "Let today's sources drive your angle. Find the FRESHEST "
                      "revelation — a new document release, a witness development, "
                      "a political reaction — and build the thesis around THAT.",
        },
    }

    cfg = seg_config.get(segment, seg_config["war"])

    # Diversify sources: max 2 per channel, prefer videos near top of each
    # channel's list (most recent, since yt-dlp returns newest-first).
    seen_channels: dict[str, int] = {}
    diverse_sources = []
    for s in sources:
        ch = s["channel"]
        if seen_channels.get(ch, 0) >= 2:
            continue
        seen_channels[ch] = seen_channels.get(ch, 0) + 1
        diverse_sources.append(s)
        if len(diverse_sources) >= 15:
            break
    source_text = "\n".join(
        f"- [{s['channel']}] {s['title']} ({s['url']})"
        for s in diverse_sources
    )

    # Load recent articles so the LLM can avoid repeating content.
    recent_articles = _load_recent_articles(segment, max_days=5)
    novelty_block = ""
    if recent_articles:
        prior_lines = []
        for a in recent_articles:
            prior_lines.append(f"  DATE: {a['date']}")
            prior_lines.append(f"  HEADLINE: {a['headline']}")
            if a["opening"]:
                prior_lines.append(f"  OPENING: {a['opening']}")
            prior_lines.append("")
        prior_text = "\n".join(prior_lines)
        novelty_block = f"""
# MANDATORY NOVELTY — HARD CONSTRAINT
We have been writing the SAME article for days. This MUST stop.

Here are our recent articles — read them carefully:
{prior_text}

RULES (violation = article rejected):
1. Your opening paragraph MUST NOT mention {recent_articles[0]['headline'].split(':')[0] if recent_articles else 'the same topic'}.
   Find a DIFFERENT entry point — a specific person, a specific event, a specific
   number that changed.
2. Your article structure MUST differ. If recent articles went
   "big picture → India impact → military → diplomacy → what to watch",
   try: "specific incident → who benefits → who loses → historical parallel → prediction".
3. Pick ONE specific source video from today's list and build the article
   around its SPECIFIC claim or revelation — not a general overview.
4. Do NOT use phrases that appeared in recent headlines above.
5. If you cannot find genuinely new content, write about WHY nothing has
   changed and what that stagnation itself means for markets.
"""

    # Load yesterday's article as a style reference for non-market topics.
    yesterday_example = None if market_grounded else _load_yesterday_example(segment)
    example_section = ""
    if yesterday_example:
        example_section = f"""
## STYLE REFERENCE — yesterday's {segment} article (match this quality):

Headline: "{yesterday_example['headline']}"

Body excerpt:
{yesterday_example['body_excerpt']}

Match this tone: direct, opinionated, sourced inline, connects global events to Indian markets, no hedging language. Your article should be AT LEAST this deep.
"""

    prompt = f"""Write a daily intelligence article for Anka Research (askanka.com).

DATE: {date}
SEGMENT: {segment}
STYLE: {cfg['title_style']}
TONE: {cfg['tone']}
FRAMING: {cfg['framing']}

TODAY'S SOURCES FROM OUR CHANNEL NETWORK:
{source_text if source_text else '(No fresh sources today — use general knowledge of current events)'}
{example_section}
REQUIREMENTS:
1. Write 500-700 words (longer is better if substantive)
2. Start with a punchy headline (no "Week X" numbering, no clickbait)
3. Open with a SPECIFIC development from today's sources — not a sweeping overview.
   Name a person, quote a claim, cite a number. Drop the reader into a scene.
4. At least 2 paragraphs must connect to Indian markets or positioning, but NOT every
   paragraph. Some paragraphs should develop the story on its own terms.
5. End with 3-5 concrete, specific things to watch — not generic categories.
   Bad: "Oil price movements". Good: "Whether Iran reopens the eastern Hormuz lane by Monday."
6. Attribute claims with [Source: channel name] — place AT THE END of the sentence.
   Post-processed into footnotes. Keep compact, no repeated attributions per paragraph.
7. Be opinionated — this is analysis, not news
8. NO disclaimers, NO "alleged", NO "reportedly" — state your view clearly
9. Include at least ONE specific number or data point per paragraph
10. Reference specific stocks or sectors where actionable
11. VARY your article structure. Try: Q&A format, timeline, "winners and losers",
    "what the market is missing", character profile, or contrarian take.
    Do NOT default to "overview → India impact → military → diplomacy → watch list".

{template_excerpt}
{novelty_block}
{regime_block}
{grounding_block}
OUTPUT FORMAT:
Return ONLY a JSON object:
{{"headline": "...", "body": "full article with \\n\\n between paragraphs", "sources": ["channel1", "channel2"]}}
"""

    # Use Gemini 2.5 Flash (free tier) instead of Claude (Anthropic credit exhausted)
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

    for attempt in range(3):
        try:
            resp = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}",
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "maxOutputTokens": 4096,
                        "temperature": 0.7,
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
                raise ValueError(f"No candidates in response")
            parts = candidates[0].get("content", {}).get("parts", [])
            if not parts:
                raise ValueError(f"No parts in candidate")
            raw = parts[0].get("text", "")

            # Parse JSON from response
            if "```" in raw:
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            article = json.loads(raw.strip())

            # ── Publish gate: verify narrative against panel ───────────────
            # Skipped for non-market-grounded topics (e.g. epstein).
            narrative = article.get("body", "")
            violations = verify_narrative(narrative, panel) if market_grounded else []
            if violations:
                failed_dir = GIT_REPO / "articles" / "_failed"
                failed_dir.mkdir(parents=True, exist_ok=True)
                failed_path = failed_dir / f"{date}-{segment}.html"
                failed_path.write_text(narrative, encoding="utf-8")
                log.error(f"REJECTED {segment} article — {len(violations)} violations:")
                for v in violations:
                    log.error(f"  {v.pattern_kind}={v.number} (closest panel: {v.closest_panel_value}) — '{v.text_excerpt[:80]}'")
                # Append to violations log
                viol_log = PIPELINE_DIR / "logs" / "article_violations.log"
                viol_log.parent.mkdir(parents=True, exist_ok=True)
                with viol_log.open("a", encoding="utf-8") as f:
                    f.write(f"\n=== {date} {segment} — {len(violations)} violations ===\n")
                    for v in violations:
                        f.write(f"  {v.pattern_kind}={v.number} closest={v.closest_panel_value} text='{v.text_excerpt[:120]}'\n")
                # Best-effort telegram alert
                try:
                    from telegram_bot import send_message
                    send_message(f"⚠️ {segment} article rejected ({len(violations)} violations). Drafted to articles/_failed/")
                except Exception:
                    pass
                return ""

            # 0 violations: attach panel HTML (market-grounded topics only)
            if market_grounded:
                try:
                    panel_date_display = datetime.strptime(date, "%Y-%m-%d").strftime("%B %d, %Y")
                except ValueError:
                    panel_date_display = date
                article["panel_html"] = render_panel_html(panel, date_str=panel_date_display)
            return article

        except requests.exceptions.Timeout:
            log.warning("Attempt %d timed out, retrying...", attempt + 1)
            import time
            time.sleep(5)
        except Exception as e:
            log.error("Article generation failed (attempt %d): %s", attempt + 1, e)
            if attempt < 2:
                import time
                time.sleep(5)

    return {"headline": "", "body": "", "sources": []}


def build_article_html(segment: str, article: dict, date: str) -> str:
    """Build article HTML page."""
    headline = article.get("headline", "")
    body = article.get("body", "")
    sources = article.get("sources", [])
    panel_html = article.get("panel_html", "")

    if not headline or not body:
        return ""

    badge_color = "#ef4444" if segment == "war" else "#d4a855"
    badge_label = "GEOPOLITICAL ANALYSIS" if segment == "war" else "INVESTIGATION"

    # Convert body paragraphs to HTML
    paragraphs = body.split("\n\n")
    body_html = "\n".join(f"<p>{p.strip()}</p>" for p in paragraphs if p.strip())

    # Convert [Source: X] markers into numbered footnotes.
    # Each unique channel gets one number assigned in first-seen order; all
    # subsequent references reuse that number. A <section class="sources">
    # list is appended at the end of body_html with anchor targets.
    channel_order: list[str] = []
    channel_num: dict[str, int] = {}

    def _footnote_ref(match: re.Match) -> str:
        channel = match.group(1).strip()
        if channel not in channel_num:
            channel_order.append(channel)
            channel_num[channel] = len(channel_order)
        n = channel_num[channel]
        return f'<sup class="fn-ref"><a href="#fn-{n}">[{n}]</a></sup>'

    body_html = re.sub(r'\[Source:\s*([^\]]+)\]', _footnote_ref, body_html)

    if channel_order:
        items = " ".join(
            f'<span class="src-item" id="fn-{channel_num[c]}">[{channel_num[c]}] {c}</span>'
            for c in channel_order
        )
        body_html += (
            '\n<section class="sources">'
            '<div class="sources-title">Sources</div>'
            f'<div class="sources-inline">{items}</div>'
            '</section>'
        )

    # Prepend the grounding panel (if any) so readers see anchor numbers up top.
    if panel_html:
        body_html = panel_html + "\n" + body_html

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{headline} | Anka Research</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display:wght@400&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
<style>
:root {{ --bg: #0a0e1a; --card: #111827; --border: #1e293b; --text: #e5e7eb; --text2: #9ca3af; --gold: #d4a855; }}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ background: var(--bg); color: var(--text); font-family: 'Inter', sans-serif; line-height: 1.8; }}
.hero {{ padding: 80px 20px 48px; text-align: center; background: linear-gradient(160deg, #0a0e1a, #1a1530, #0f0d1a); border-bottom: 1px solid rgba(212,168,85,0.15); position: relative; }}
.hero::after {{ content: ''; position: absolute; bottom: 0; left: 0; right: 0; height: 1px; background: linear-gradient(90deg, transparent, rgba(212,168,85,0.3), transparent); }}
.hero .badge {{ display: inline-block; background: rgba({','.join(str(int(badge_color[i:i+2], 16)) for i in (1,3,5))},0.15); color: {badge_color}; font-size: 11px; font-weight: 700; letter-spacing: 1.5px; text-transform: uppercase; padding: 5px 14px; border-radius: 4px; margin-bottom: 16px; }}
.hero h1 {{ font-family: 'DM Serif Display', Georgia, serif; font-size: 36px; font-weight: 400; max-width: 800px; margin: 0 auto 16px; background: linear-gradient(135deg, #f5f0e8, #d4a855); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }}
.hero .meta {{ font-size: 14px; color: var(--text2); }}
.hero .meta span {{ color: var(--gold); }}
.container {{ max-width: 720px; margin: 0 auto; padding: 48px 24px 80px; }}
.body p {{ margin-bottom: 20px; font-size: 16px; color: #d1d5db; }}
.body p:first-child::first-letter {{ font-size: 3.2em; float: left; line-height: 0.8; margin: 4px 12px 0 0; font-weight: 800; color: var(--gold); }}
.nav-bar {{ display: flex; justify-content: space-between; align-items: center; padding: 16px 24px; border-bottom: 1px solid var(--border); }}
.nav-bar a {{ color: var(--gold); text-decoration: none; font-size: 14px; font-weight: 500; }}
.nav-bar .brand {{ font-weight: 800; font-size: 16px; }}
.market-anchor {{ background:#161616; border:1px solid #2a2a2a; border-radius:8px; padding:14px 18px; margin:18px 0 24px; }}
.anchor-title {{ font-family:'Inter',sans-serif; font-size:13px; text-transform:uppercase; letter-spacing:0.08em; color:#d4a855; margin-bottom:10px; }}
.anchor-date {{ color:#9c9c9c; font-size:11px; margin-left:8px; text-transform:none; letter-spacing:0; }}
.anchor-grid {{ display:grid; grid-template-columns:repeat(4,1fr); gap:8px 16px; font-family:'JetBrains Mono',monospace; font-size:13px; }}
@media (max-width:600px){{.anchor-grid{{grid-template-columns:repeat(2,1fr);}}}}
.anchor-grid .lbl {{ color:#9c9c9c; font-size:11px; display:block; }}
.anchor-grid .val {{ color:#f3f3f3; font-size:14px; font-weight:600; }}
.anchor-source {{ color:#6e6e6e; font-size:10px; margin-top:10px; font-style:italic; }}
.fn-ref {{ font-size:10px; vertical-align:super; line-height:0; }}
.fn-ref a {{ color:#d4a855; text-decoration:none; padding:0 1px; }}
.fn-ref a:hover {{ text-decoration:underline; }}
.sources {{ margin-top:40px; padding-top:16px; border-top:1px solid #2a2a2a; }}
.sources-title {{ font-family:'Inter',sans-serif; font-size:10px; text-transform:uppercase; letter-spacing:0.12em; color:#6e6e6e; margin-bottom:8px; font-weight:600; }}
.sources-inline {{ display:flex; flex-wrap:wrap; gap:4px 12px; }}
.src-item {{ color:#9c9c9c; font-size:11px; white-space:nowrap; }}
.src-item:target {{ color:#d4a855; }}
</style>
</head>
<body>
<nav class="nav-bar"><a href="/" class="brand">Anka Research</a><a href="/">&larr; Dashboard</a></nav>
<header class="hero">
    <div class="badge">{badge_label}</div>
    <h1>{headline}</h1>
    <p class="meta"><span>Anka Research</span> &mdash; {date} &mdash; Daily Intelligence</p>
</header>
<article class="container"><div class="body">
{body_html}
</div></article>
</body></html>"""

    return html


def generate_and_publish(segments=None):
    """Generate daily articles and publish to askanka.com."""
    if segments is None:
        segments = ["war", "epstein"]

    today = datetime.now(IST).strftime("%Y-%m-%d")
    today_display = datetime.now(IST).strftime("%B %d, %Y")
    articles_dir = GIT_REPO / "articles"
    articles_dir.mkdir(exist_ok=True)

    published = []

    for segment in segments:
        log.info("Generating %s article for %s...", segment, today)

        # Scrape sources
        sources = scrape_today_sources(segment, days_back=2)
        log.info("  Sources: %d videos", len(sources))

        # Generate article
        article = generate_article(segment, sources, today)
        if not article or not article.get("headline"):
            log.warning("  No article generated for %s", segment)
            continue

        # Build HTML
        html = build_article_html(segment, article, today_display)
        if not html:
            continue

        # Save
        filename = f"{today}-{segment}.html"
        filepath = articles_dir / filename
        filepath.write_text(html, encoding="utf-8")
        log.info("  Published: %s — %s", filename, article["headline"])

        published.append({
            "segment": segment,
            "filename": filename,
            "headline": article["headline"],
            "date": today,
        })

    # Append articles to the single source of truth: data/articles_index.json
    # Homepage + Library & Archive sections are rendered client-side by JS reading
    # this JSON. daily_articles.py does NOT touch index.html anymore (that was the
    # regression that clobbered 934 lines of features on 2026-04-11).
    if published:
        try:
            _append_to_articles_index(published, today_display)
        except Exception as e:
            log.error("articles_index.json update failed: %s", e)

    # Git push — only the new article files and the JSON index. NEVER index.html.
    if published:
        try:
            subprocess.run(
                ["git", "add", "articles/", "data/articles_index.json"],
                cwd=str(GIT_REPO), check=True,
            )
            headlines = " + ".join(a["headline"][:40] for a in published)
            subprocess.run(
                ["git", "commit", "-m", f"daily: {today} — {headlines}"],
                cwd=str(GIT_REPO), check=True,
            )
            subprocess.run(["git", "push"], cwd=str(GIT_REPO), check=True)
            log.info("Deployed %d articles to askanka.com", len(published))
        except subprocess.CalledProcessError as e:
            log.error("Git deploy failed: %s", e)

    return published


def _append_to_articles_index(published: list, date_display: str) -> None:
    """Append new articles to data/articles_index.json (single source of truth).

    Schema:
    {
      "articles": [
        {"date": "2026-04-11", "segment": "war", "filename": "2026-04-11-war.html",
         "headline": "...", "category": "GEOPOLITICAL ANALYSIS", "color": "#ef4444"}
      ]
    }
    """
    index_json = GIT_REPO / "data" / "articles_index.json"
    index_json.parent.mkdir(parents=True, exist_ok=True)

    if index_json.exists():
        try:
            data = json.loads(index_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {"articles": []}
    else:
        data = {"articles": []}

    articles = data.get("articles", [])

    # Category + color per segment (keeps homepage styling consistent)
    segment_meta = {
        "war":     {"category": "GEOPOLITICAL ANALYSIS", "color": "#ef4444"},
        "epstein": {"category": "INVESTIGATION",         "color": "#d4a855"},
    }

    # Dedupe on (date, segment) — if today's article was already published, replace
    existing_keys = {(a["date"], a["segment"]): i for i, a in enumerate(articles)}
    for p in published:
        key = (p["date"], p["segment"])
        meta = segment_meta.get(p["segment"], {"category": "ANALYSIS", "color": "#d4a855"})
        entry = {
            "date": p["date"],
            "segment": p["segment"],
            "filename": p["filename"],
            "headline": p["headline"],
            "category": meta["category"],
            "color": meta["color"],
            "published_at": date_display,
        }
        if key in existing_keys:
            articles[existing_keys[key]] = entry
        else:
            articles.append(entry)

    # Sort newest first
    articles.sort(key=lambda a: (a["date"], a["segment"]), reverse=True)

    index_json.write_text(
        json.dumps({"articles": articles}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    log.info("articles_index.json updated: %d total articles", len(articles))


def _update_homepage(published: list, date_display: str):
    """Update index.html: new articles to Today's Intelligence, old ones move to Library."""
    index_path = GIT_REPO / "index.html"
    if not index_path.exists():
        log.warning("index.html not found, skipping homepage update")
        return

    html = index_path.read_text(encoding="utf-8")

    # ── Step 1: Extract old article cards from Today's Intelligence ──
    today_marker = '<div class="reports-grid">'
    today_end = '</div>\n    </section>\n\n    <hr class="section-divider">'

    today_start_idx = html.find(today_marker, html.find("Today's Intelligence"))
    if today_start_idx == -1:
        log.warning("Could not find Today's Intelligence section")
        return

    today_end_idx = html.find(today_end, today_start_idx)
    if today_end_idx == -1:
        log.warning("Could not find end of Today's Intelligence grid")
        return

    old_today_section = html[today_start_idx + len(today_marker):today_end_idx]

    # Extract old article cards (href="articles/") — these move to library
    old_article_cards = []
    for match in re.finditer(r'(<a href="articles/.*?</a>)', old_today_section, re.DOTALL):
        card_html = match.group(1).strip()
        old_article_cards.append(card_html)

    # Extract research cards (href="research/") — these stay
    research_cards = []
    for match in re.finditer(r'(<a href="research/.*?</a>)', old_today_section, re.DOTALL):
        research_cards.append(match.group(1).strip())

    # ── Step 2: Build new article cards ──────────────────────────────
    new_cards = []
    for article in published:
        seg = article["segment"]
        filename = article["filename"]
        headline = article["headline"]
        badge_color = "#ef4444" if seg == "war" else "#d4a855"
        badge_label = "Geopolitical Analysis" if seg == "war" else "Investigation"

        art_path = GIT_REPO / "articles" / filename
        lead = ""
        if art_path.exists():
            art_html = art_path.read_text(encoding="utf-8")
            p_match = re.search(r'<div class="body">\s*<p>(.*?)</p>', art_html, re.DOTALL)
            if p_match:
                lead = re.sub(r'<.*?>', '', p_match.group(1))[:140]

        new_cards.append(
            f'            <a href="articles/{filename}" class="report-card" style="border-top: 2px solid {badge_color};">\n'
            f'                <div style="font-size:11px; text-transform:uppercase; letter-spacing:1.5px; color:{badge_color}; font-weight:700; margin-bottom:10px;">{badge_label.upper()}</div>\n'
            f'                <h3>{headline}</h3>\n'
            f'                <p>{lead}</p>\n'
            f'                <div class="report-date mono">{date_display}</div>\n'
            f'            </a>'
        )

    # ── Step 3: Replace Today's Intelligence with new cards ──────────
    new_today = today_marker + '\n' + '\n'.join(new_cards)
    if research_cards:
        new_today += '\n' + '\n'.join(f'            {c}' for c in research_cards)
    new_today += '\n        '

    html = html[:today_start_idx] + new_today + html[today_end_idx:]

    # ── Step 4: Prepend old article cards to Library section ─────────
    if old_article_cards:
        library_marker = '<div class="reports-grid" id="library-grid" style="display:none;">'
        lib_idx = html.find(library_marker)
        if lib_idx != -1:
            insert_point = lib_idx + len(library_marker)
            old_cards_html = '\n' + '\n'.join(f'            {c}' for c in old_article_cards)
            html = html[:insert_point] + old_cards_html + html[insert_point:]
            log.info("Moved %d old articles to Library", len(old_article_cards))

    index_path.write_text(html, encoding="utf-8")
    log.info("Updated homepage: %d new articles, %d moved to library", len(new_cards), len(old_article_cards))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    articles = generate_and_publish()
    for a in articles:
        print(f"  {a['segment']}: {a['headline']}")
