"""One-shot: generate today's Epstein article using Sonnet."""
import requests, json, os, subprocess
from dotenv import load_dotenv
from pathlib import Path
from datetime import datetime, timezone, timedelta
from daily_articles import build_article_html

IST = timezone(timedelta(hours=5, minutes=30))
load_dotenv(Path(__file__).parent / ".env")
key = os.getenv("ANTHROPIC_API_KEY")

prompt = """Write a daily intelligence article for Anka Research (askanka.com).

DATE: April 7, 2026
SEGMENT: Epstein investigation
STYLE: investigative journalism
TONE: Forensic. Analytical. Connect dots across documented evidence. Reference court filings and official releases.
FRAMING: Legal proceedings, DOJ document releases, accountability questions, implications for Indian business.

REQUIREMENTS:
1. Write 400-600 words
2. Punchy headline
3. Open with the most significant recent legal development
4. Connect to broader patterns of institutional accountability
5. End with "What to watch tomorrow"
6. Focus on documented facts from court filings and official sources

OUTPUT: Return ONLY a JSON object: {"headline": "...", "body": "...", "sources": ["source1"]}"""

resp = requests.post("https://api.anthropic.com/v1/messages",
    headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
    json={"model": "claude-sonnet-4-20250514", "max_tokens": 2000,
          "messages": [{"role": "user", "content": prompt}]},
    timeout=60)

print(f"Status: {resp.status_code}")
raw = resp.json()["content"][0]["text"]

# Parse JSON
try:
    if "```" in raw:
        inner = raw.split("```")[1]
        if inner.startswith("json"):
            inner = inner[4:]
        article = json.loads(inner.strip())
    else:
        article = json.loads(raw)
except Exception as e:
    print(f"Parse error: {e}")
    print(f"Raw: {raw[:500]}")
    exit(1)

print(f"Headline: {article['headline']}")

today = datetime.now(IST).strftime("%Y-%m-%d")
today_display = datetime.now(IST).strftime("%B %d, %Y")
html = build_article_html("epstein", article, today_display)

GIT_REPO = Path("C:/Users/Claude_Anka/askanka.com")
filepath = GIT_REPO / "articles" / f"{today}-epstein.html"
filepath.write_text(html, encoding="utf-8")
print(f"Saved: {filepath}")

subprocess.run(["git", "add", "articles/"], cwd=str(GIT_REPO), check=True)
subprocess.run(["git", "commit", "-m", f"daily: {today} epstein investigation"], cwd=str(GIT_REPO), check=True)
subprocess.run(["git", "push"], cwd=str(GIT_REPO), check=True)
print("Deployed!")
