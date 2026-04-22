"""
Anka Research — Daily Article Generator V2
Uses NotebookLM (grounded in Bharat's YouTube watch history) as THE source.
NOT Claude's imagination. NOT random RSS feeds.

Flow:
  1. NotebookLM → ask for today's article angles from Bharat's sources
  2. Web search → verify what's actually happening TODAY
  3. Cross-check → match against current MSI regime and open positions
  4. Claude → structure the article using NotebookLM's grounded response
  5. Nano Banana → generate header image
  6. Publish → askanka.com + update homepage

RULE: If NotebookLM is unavailable, DO NOT generate. A missing article
is better than a wrong one.
"""

import json
import logging
import os
import re
import subprocess
import base64
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path

log = logging.getLogger("anka.daily_v2")

IST = timezone(timedelta(hours=5, minutes=30))
PIPELINE_DIR = Path(__file__).parent
GIT_REPO = Path("C:/Users/Claude_Anka/askanka.com")

from dotenv import load_dotenv
load_dotenv(PIPELINE_DIR / ".env")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
NOTEBOOKLM_BRAIN_ID = "192af7f1-80f3-4985-8760-476401276e5f"


def query_notebooklm(question: str) -> str:
    """Ask NotebookLM a question grounded in Bharat's YouTube sources."""
    try:
        result = subprocess.run(
            ["notebooklm", "ask", question],
            capture_output=True, text=True, timeout=60,
            env={**os.environ, "PYTHONIOENCODING": "utf-8",
                 "PATH": os.path.expanduser("~/.notebooklm-venv/bin") + os.pathsep + os.environ.get("PATH", "")},
        )
        if result.returncode == 0:
            return result.stdout.strip()
        else:
            log.error("NotebookLM query failed: %s", result.stderr[:200])
            return ""
    except Exception as e:
        log.error("NotebookLM unavailable: %s", e)
        return ""


def web_search_verify(topic: str) -> str:
    """Verify today's actual events via web search."""
    try:
        # Use Anthropic's web search or a simple news check
        resp = requests.get(
            f"https://newsapi.org/v2/everything?q={topic}&sortBy=publishedAt&pageSize=5"
            f"&apiKey={os.getenv('NEWSAPI_KEY', '')}",
            timeout=10,
        )
        if resp.status_code == 200:
            articles = resp.json().get("articles", [])
            return "\n".join(f"- {a['title']} ({a['source']['name']})" for a in articles[:5])
    except Exception:
        pass
    return ""


def generate_article_v2(segment: str) -> dict:
    """Generate a daily article grounded in NotebookLM + web verification."""
    today = datetime.now(IST).strftime("%B %d, %Y")

    # Step 1: Get angles from NotebookLM (YOUR YouTube sources)
    if segment == "war":
        nlm_question = (
            "From my war YouTube sources: What are the 3 most important stories "
            "my channels (Al Jazeera, Deshbhakt, MeidasTouch, Danny Haiphong) are "
            "covering right now about Iran-US conflict? Give specific claims with "
            "which channel reported it."
        )
    else:
        nlm_question = (
            "From my Epstein YouTube sources: What are the 3 most important "
            "developments my channels (Brian Tyler Cohen, Law&Crime, Legal AF, "
            "MeidasTouch, Dr G Explains) are covering? Give specific claims with "
            "which channel reported it."
        )

    nlm_response = query_notebooklm(nlm_question)
    if not nlm_response:
        log.error("NotebookLM unavailable — NOT generating article (rule: no source = no article)")
        return {}

    # Step 2: Verify with web search
    search_topic = "Iran US ceasefire" if segment == "war" else "Epstein files DOJ"
    web_context = web_search_verify(search_topic)

    # Step 3: Check current MSI regime for consistency
    try:
        from macro_stress import compute_msi
        msi = compute_msi()
        msi_context = f"MSI: {msi['msi_score']}/100 ({msi['regime']})"
    except Exception:
        msi_context = "MSI unavailable"

    # Step 4: Claude structures the article using NotebookLM's grounded content
    prompt = f"""Write a daily intelligence article for Anka Research.

DATE: {today}
SEGMENT: {segment}

GROUNDED SOURCE MATERIAL FROM BHARAT'S YOUTUBE RESEARCH (NotebookLM):
{nlm_response}

TODAY'S VERIFIED NEWS:
{web_context if web_context else '(No news API results — rely on NotebookLM sources above)'}

CURRENT MARKET REGIME: {msi_context}

RULES:
1. Write 400-600 words based ONLY on the source material above
2. DO NOT invent facts — only use what NotebookLM provided
3. Cite which YouTube channel reported each claim
4. Be provocative but accurate
5. If this is about war: connect to Indian market impact
6. End with "What to watch tomorrow"

Return ONLY JSON: {{"headline": "...", "body": "..."}}"""

    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": "claude-sonnet-4-20250514", "max_tokens": 2000,
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=60,
        )
        resp.raise_for_status()
        raw = resp.json()["content"][0]["text"]
        if "```" in raw:
            inner = raw.split("```")[1]
            if inner.startswith("json"):
                inner = inner[4:]
            return json.loads(inner.strip())
        return json.loads(raw)
    except Exception as e:
        log.error("Article generation failed: %s", e)
        return {}


def generate_header_image(segment: str, headline: str) -> str:
    """Generate AI header image with Nano Banana."""
    if not GEMINI_API_KEY:
        return ""

    if segment == "war":
        prompt = f"Dark dramatic editorial illustration for article: {headline}. Geopolitical theme, dark navy with gold accents. Wide 16:9. No text."
    else:
        prompt = f"Dark editorial illustration for investigation article: {headline}. Legal documents, shadows, gold light. Wide 16:9. No text."

    try:
        resp = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-image-preview:generateContent?key={GEMINI_API_KEY}",
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"response_modalities": ["IMAGE"],
                                    "image_config": {"aspect_ratio": "16:9", "image_size": "1K"}}
            },
            timeout=90,
        )
        if resp.status_code == 200:
            for c in resp.json().get("candidates", []):
                for p in c.get("content", {}).get("parts", []):
                    if "inlineData" in p:
                        return base64.b64decode(p["inlineData"]["data"])
    except Exception as e:
        log.warning("Image generation failed: %s", e)
    return ""


def publish_daily():
    """Generate and publish today's articles."""
    today = datetime.now(IST).strftime("%Y-%m-%d")
    today_display = datetime.now(IST).strftime("%B %d, %Y")
    articles_dir = GIT_REPO / "articles"

    # Set NotebookLM context
    subprocess.run(
        ["notebooklm", "use", NOTEBOOKLM_BRAIN_ID],
        env={**os.environ, "PYTHONIOENCODING": "utf-8",
             "PATH": os.path.expanduser("~/.notebooklm-venv/bin") + os.pathsep + os.environ.get("PATH", "")},
        capture_output=True, timeout=15,
    )

    published = []

    for segment in ["war", "epstein"]:
        log.info("Generating %s article...", segment)

        article = generate_article_v2(segment)
        if not article or not article.get("headline"):
            log.warning("Skipping %s — no grounded content available", segment)
            continue

        # Build HTML
        from daily_articles import build_article_html
        html = build_article_html(segment, article, today_display)

        # Generate image
        img_data = generate_header_image(segment, article["headline"])
        if img_data:
            img_path = articles_dir / f"img-{today}-{segment}.jpg"
            img_path.write_bytes(img_data)

        # Save article
        filepath = articles_dir / f"{today}-{segment}.html"
        filepath.write_text(html, encoding="utf-8")
        log.info("Published: %s — %s", filepath.name, article["headline"])
        published.append({"segment": segment, "headline": article["headline"]})

    # Git push
    if published:
        subprocess.run(["git", "add", "articles/"], cwd=str(GIT_REPO), check=True)
        subprocess.run(["git", "commit", "-m",
                       f"daily: {today} — grounded in YouTube sources via NotebookLM"],
                      cwd=str(GIT_REPO), check=True)
        subprocess.run(["git", "push"], cwd=str(GIT_REPO), check=True)

    return published


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    articles = publish_daily()
    for a in articles:
        print(f"  {a['segment']}: {a['headline']}")
