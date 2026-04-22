"""Generate the 3 remaining articles that failed — adjusted prompts."""
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

prompts = [
    ("war-tech", "war",
     f"""Write an analytical article for Anka Research dated {today_display}.

TOPIC: The military technology story of the Iran-US conflict.
GROUNDED FACTS FROM YOUTUBE CHANNELS:
- Al Jazeera reported US military equipment failures during Iran operations
- Global Military Update covered Iran's missile capabilities including Sejjil systems
- Danny Haiphong and Glenn Diesen analyzed the shifting military balance
- Hindustan Times covered damage to US naval assets
- Young Turks reported on aircraft incidents over Iran

Write 400 words analyzing what the military technology balance reveals about the conflict's outcome and why the ceasefire was necessary. Cite channels. Be analytical.
Return ONLY JSON: {{"headline": "...", "body": "..."}}"""),

    ("epstein-india", "epstein",
     f"""Write an investigative article for Anka Research dated {today_display}.

TOPIC: Indian connections revealed in Epstein-related legal proceedings.
GROUNDED FACTS FROM YOUTUBE CHANNELS:
- The Deshbhakt (Akash Banerjee) investigated Indian business names appearing in documents
- newslaundry examined the Anil Ambani and Hardeep Singh Puri connections
- Priyanka Gandhi raised questions in Indian Parliament about the files
- Opposition parties demanding accountability from the government
- Firstpost covered why PM Modi's name appeared in certain contexts

Write 400 words examining what the Indian connections mean for domestic politics and business accountability. Cite channels. Focus on documented evidence.
Return ONLY JSON: {{"headline": "...", "body": "..."}}"""),

    ("epstein-coverup", "epstein",
     f"""Write an investigative article for Anka Research dated {today_display}.

TOPIC: Questions about the DOJ's handling of the Epstein case.
GROUNDED FACTS FROM YOUTUBE CHANNELS:
- Katie Phang reported on the New Mexico ranch investigation developments
- MeidasTouch covered testimony from corrections officers
- Brian Tyler Cohen analyzed DOJ document releases and redactions
- Legal AF examined the legal implications of sealed vs unsealed documents
- Dr G Explains provided forensic analysis of evidence gaps

Write 400 words examining the accountability questions around institutional handling of this case. Cite channels. Focus on legal proceedings and documented evidence.
Return ONLY JSON: {{"headline": "...", "body": "..."}}"""),
]

articles = []
for slug, segment, prompt in prompts:
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
    img_prompt = ("Dark analytical: radar screens, missile trajectories, military tech. 16:9. No text."
                  if "tech" in slug else
                  "Dark editorial: legal investigation, courthouse, documents under spotlight. 16:9. No text.")
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

if articles:
    subprocess.run(["git", "add", "articles/"], cwd=str(GIT_REPO), check=True)
    subprocess.run(["git", "commit", "-m", f"daily: {today} — remaining articles"],
                   cwd=str(GIT_REPO), check=True)
    subprocess.run(["git", "push"], cwd=str(GIT_REPO), check=True)
    print(f"\nDeployed {len(articles)} more articles!")
