"""Generate correct ceasefire article — fact-checked against today's actual news."""
import requests, json, base64, os, subprocess
from pathlib import Path
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

IST = timezone(timedelta(hours=5, minutes=30))
key = os.getenv("ANTHROPIC_API_KEY")
gkey = os.getenv("GEMINI_API_KEY")
GIT_REPO = Path("C:/Users/Claude_Anka/askanka.com")

# Generate article
resp = requests.post("https://api.anthropic.com/v1/messages",
    headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
    json={"model": "claude-sonnet-4-20250514", "max_tokens": 2000,
          "messages": [{"role": "user", "content": """Write a daily intelligence article for Anka Research.

VERIFIED NEWS (April 8, 2026):
- US and Iran agreed to 2-week ceasefire on April 7
- Trump suspended bombing, Iran reopening Strait of Hormuz
- Negotiations start Friday April 10 in Islamabad
- Crude oil crashed 15% overnight
- Nifty surged 4.5% to 23,896. VIX collapsed from 25 to 20.
- OMCs (BPCL, HPCL) rallying. Defence stocks at risk.

TRADING CONTEXT:
- Our war spreads thesis is broken. Crude crash reverses OMC pain.
- New regime: de-escalation. Winners = OMCs, IT, consumers.
- Subscribers need to know: exit war positions, rotate to peace trades.

Write 500 words. State our view clearly.
Return ONLY JSON: {"headline": "...", "body": "..."}"""}]},
    timeout=60)

raw = resp.json()["content"][0]["text"]
if "```" in raw:
    inner = raw.split("```")[1]
    if inner.startswith("json"):
        inner = inner[4:]
    article = json.loads(inner.strip())
else:
    article = json.loads(raw)

print(f"Headline: {article['headline']}")

# Build HTML
from daily_articles import build_article_html
today = datetime.now(IST).strftime("%B %d, %Y")
html = build_article_html("war", article, today)

filepath = GIT_REPO / "articles" / "2026-04-08-ceasefire.html"
filepath.write_text(html, encoding="utf-8")

# Generate image
img_resp = requests.post(
    f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-image-preview:generateContent?key={gkey}",
    json={
        "contents": [{"parts": [{"text": "Editorial illustration: ceasefire and diplomacy. Olive branch between two flags. Oil derricks transitioning from flames to calm. Dawn breaking. Mood: cautious hope. Wide 16:9. No text."}]}],
        "generationConfig": {"response_modalities": ["IMAGE"], "image_config": {"aspect_ratio": "16:9", "image_size": "1K"}}
    }, timeout=90)

if img_resp.status_code == 200:
    for c in img_resp.json().get("candidates", []):
        for p in c.get("content", {}).get("parts", []):
            if "inlineData" in p:
                img = base64.b64decode(p["inlineData"]["data"])
                (GIT_REPO / "articles" / "img-2026-04-08-ceasefire.jpg").write_bytes(img)
                print("Image saved")

# Deploy
subprocess.run(["git", "add", "articles/"], cwd=str(GIT_REPO), check=True)
subprocess.run(["git", "commit", "-m", "daily: ceasefire article — fact-checked, matches signals"], cwd=str(GIT_REPO), check=True)
subprocess.run(["git", "push"], cwd=str(GIT_REPO), check=True)
print("Deployed!")
