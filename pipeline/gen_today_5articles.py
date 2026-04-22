"""Generate 5 articles for today — 3 war + 2 epstein — grounded in YouTube sources."""
import requests, json, os, base64, subprocess
from pathlib import Path
from dotenv import load_dotenv
from daily_articles import build_article_html
from datetime import datetime, timezone, timedelta

load_dotenv(Path(__file__).parent / ".env")
IST = timezone(timedelta(hours=5, minutes=30))
key = os.getenv("ANTHROPIC_API_KEY")
gkey = os.getenv("GEMINI_API_KEY")
GIT_REPO = Path("C:/Users/Claude_Anka/askanka.com")
today = datetime.now(IST).strftime("%Y-%m-%d")
today_display = datetime.now(IST).strftime("%B %d, %Y")

WAR_CONTEXT = """From Bharat's 70 YouTube war channels (181 videos):
1. MILITARY MUTINY: US Generals panicked, wanted out. Army Chief ousted mid-war (Al Jazeera). Hegseth melted down (Young Turks, MeidasTouch). Ceasefire was FORCED (NPR, CNN).
2. TECH HUMILIATION: US radars wiped out (Richard Medhurst). USS Ford on fire (Hindustan Times). Iran Sejjil missiles broke Iron Dome (Global Military Update). F-15 downed (Young Turks).
3. HORMUZ ECONOMIC SUICIDE: Dubai, Abu Dhabi explosions (Times Now). India worst hit (Being Honest, Deshbhakt). Ceasefire = desperate pause.
TODAY: 2-week ceasefire. Crude -15%. Nifty +4.5%. Negotiations Friday Islamabad."""

EPSTEIN_CONTEXT = """From Bharat's 50+ Epstein channels (236 videos):
1. INDIAN NEXUS: Modi, Ambani, Puri in files (Deshbhakt, newslaundry). Priyanka Gandhi Parliament. Opposition demands resignation.
2. SPIRITUAL ICONS: Dalai Lama, Deepak Chopra connections (multiple). Jim Caviezel on kids (Dr G Explains).
3. DOJ COVER-UP: 19 intimate videos hidden. Maxwell-9/11 email (CUFBOYS). NM ranch graves (Katie Phang). Prison guard testimony (MeidasTouch). 47 missing minutes."""

prompts = [
    ("war-ceasefire", "war", "Ceasefire as forced retreat. Generals panicked. Trump backed down. Sources: Al Jazeera, Young Turks, MeidasTouch."),
    ("war-tech", "war", "Iran humiliated US military tech. USS Ford fire, radars wiped, F-15 down. Sources: Global Military Update, Danny Haiphong."),
    ("war-india", "war", "Ceasefire impact on Indian markets. Crude -15%, OMCs rally, defence at risk. Regime change for traders."),
    ("epstein-india", "epstein", "Indian names in files — Modi, Ambani, Puri. Media silence. Sources: Deshbhakt, newslaundry."),
    ("epstein-coverup", "epstein", "DOJ cover-up deepens. Hidden videos, Maxwell-9/11, ranch graves, missing footage. Sources: Katie Phang, MeidasTouch."),
]

articles = []
for slug, segment, angle in prompts:
    ctx = WAR_CONTEXT if segment == "war" else EPSTEIN_CONTEXT
    prompt = f"""Write a provocative article for Anka Research. {today_display}.

GROUNDED SOURCES:
{ctx}

THIS ARTICLE'S ANGLE: {angle}

RULES: 300-500 words. Provocative. Cite channels. No hedging. End with what to watch.
Return ONLY JSON: {{"headline": "...", "body": "..."}}"""

    try:
        resp = requests.post("https://api.anthropic.com/v1/messages",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": "claude-sonnet-4-20250514", "max_tokens": 1500,
                  "messages": [{"role": "user", "content": prompt}]}, timeout=60)
        raw = resp.json()["content"][0]["text"]
        if "```" in raw:
            inner = raw.split("```")[1]
            if inner.startswith("json"): inner = inner[4:]
            article = json.loads(inner.strip())
        else:
            article = json.loads(raw)

        html = build_article_html(segment, article, today_display)
        filepath = GIT_REPO / "articles" / f"{today}-{slug}.html"
        filepath.write_text(html, encoding="utf-8")
        print(f"OK: {slug} — {article['headline'][:60]}")
        articles.append(slug)
    except Exception as e:
        print(f"FAIL: {slug} — {e}")

# Images
for slug in articles:
    segment = "war" if "war" in slug else "epstein"
    img_prompt = ("Dark dramatic: military conflict, warships, fire, gold accents. 16:9. No text."
                  if segment == "war" else
                  "Dark editorial: legal documents, shadows, scales of justice. 16:9. No text.")
    try:
        resp = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-image-preview:generateContent?key={gkey}",
            json={"contents": [{"parts": [{"text": img_prompt}]}],
                  "generationConfig": {"response_modalities": ["IMAGE"],
                                      "image_config": {"aspect_ratio": "16:9", "image_size": "1K"}}},
            timeout=90)
        if resp.status_code == 200:
            for c in resp.json().get("candidates", []):
                for p in c.get("content", {}).get("parts", []):
                    if "inlineData" in p:
                        (GIT_REPO / "articles" / f"img-{today}-{slug}.jpg").write_bytes(
                            base64.b64decode(p["inlineData"]["data"]))
                        print(f"IMG: {slug}")
    except Exception:
        pass

subprocess.run(["git", "add", "articles/"], cwd=str(GIT_REPO), check=True)
subprocess.run(["git", "commit", "-m", f"daily: {today} — 5 grounded articles from YouTube sources"],
               cwd=str(GIT_REPO), check=True)
subprocess.run(["git", "push"], cwd=str(GIT_REPO), check=True)
print(f"\nDeployed {len(articles)} articles to askanka.com!")
