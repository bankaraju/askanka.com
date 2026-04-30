"""Generate articles from NotebookLM's FRESH sources — today's actual news."""
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

# FRESH from NotebookLM (queried minutes ago from live Al Jazeera + MeidasTouch)
FRESH_WAR = """VERIFIED TODAY from Al Jazeera + MeidasTouch (April 8, 2026):

1. CEASEFIRE AGREED but Netanyahu says it "does not include Israel" — Al Jazeera
2. Iran says talks will begin in Pakistan's Islamabad — Al Jazeera
3. Trump PANICKED — Iran rejected his earlier ultimatum — MeidasTouch
4. Iran views US ceasefire overtures as a "ruse" to prepare ground invasion — Al Jazeera
5. US Army Chief ousted MID-WAR as Trump tried to ramp up strikes — Al Jazeera
6. US Generals "want out of the war" — military "fully abandoned" Trump — MeidasTouch
7. Trump went "MIA" during war, health "crashing", 25th Amendment demands — MeidasTouch
8. Trump postponed strikes on Iranian power plants — Al Jazeera
9. Trump "abandoning bases" as war effort collapses — MeidasTouch
10. Oil price shock from Iran war hitting global economy — Al Jazeera
"""

FRESH_EPSTEIN = """VERIFIED TODAY from DOJ.gov + PBS + CBS + Guardian (April 2026):

1. DOJ published 3.5 MILLION responsive pages in Epstein Library — DOJ.gov
2. Epstein Files Transparency Act Section 3 Report released — DOJ.gov
3. Powerful men named in files — but why have there been no new charges? — PBS
4. Massive trove of files released — CBS News live updates
5. Pam Bondi under pressure from both Democrats and MAGA — Guardian
6. Democratic lawmakers wrote to Bondi demanding victim advocacy — House Oversight
7. After file release, survivors asking: where is the accountability? — Iowa Public Radio
8. Full list of powerful people named, with evidence status — PBS
"""

prompts = [
    ("war-ceasefire-fresh", "war",
     f"Write about the ceasefire being a FORCED retreat. Sources: Al Jazeera reports Army Chief ousted mid-war, MeidasTouch reports generals want out, Trump went MIA. Iran views it as a ruse. Netanyahu says it doesn't include Israel. Crude crashed 15%."),
    ("war-collapse-fresh", "war",
     f"Write about the US military and political collapse driving the ceasefire. 25th Amendment demands, Trump health crashing, bases abandoned, generals in mutiny. Sources: MeidasTouch, Al Jazeera."),
    ("epstein-doj-fresh", "epstein",
     f"Write about DOJ releasing 3.5 MILLION pages in the Epstein Library. Why no new charges despite the evidence? Pam Bondi under pressure from all sides. Survivors demanding accountability. Sources: DOJ.gov, PBS, Guardian, CBS."),
    ("epstein-names-fresh", "epstein",
     f"Write about the powerful people named in the files and the accountability gap. Full list published by PBS. Democratic lawmakers demanding action. After the largest document release in history, who will face consequences? Sources: PBS, House Oversight, Iowa Public Radio."),
]

articles = []
for slug, segment, angle in prompts:
    ctx = FRESH_WAR if segment == "war" else FRESH_EPSTEIN
    prompt = f"""Write a provocative daily intelligence article for Anka Research. {today_display}.

FRESH VERIFIED SOURCES (from today):
{ctx}

THIS ARTICLE: {angle}

RULES:
1. 400-500 words. Every claim must cite the source channel/outlet.
2. Provocative — state our view. This is analysis, not neutral reporting.
3. Connect to what it means for readers/subscribers.
4. End with "What to watch tomorrow"
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
        print(f"OK: {slug} — {article['headline'][:70]}")
        articles.append(slug)
    except Exception as e:
        print(f"FAIL: {slug} — {e}")

for slug in articles:
    segment = "war" if "war" in slug else "epstein"
    img_prompt = ("Dark dramatic: ceasefire tension, military retreat, diplomatic crisis. Gold accents. 16:9. No text."
                  if segment == "war" else
                  "Dark editorial: massive document dump, legal files stacked high, spotlight. 16:9. No text.")
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
    subprocess.run(["git", "commit", "-m",
                   f"daily: {today} — FRESH articles from today's Al Jazeera + MeidasTouch + DOJ"],
                  cwd=str(GIT_REPO), check=True)
    subprocess.run(["git", "push"], cwd=str(GIT_REPO), check=True)
    print(f"\nDeployed {len(articles)} FRESH articles!")
