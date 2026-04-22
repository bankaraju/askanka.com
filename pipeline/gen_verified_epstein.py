"""Generate Epstein articles with VERIFIED current facts."""
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

# WEB-VERIFIED FACTS as of April 8, 2026:
VERIFIED_CONTEXT = """
VERIFIED FACTS (web-searched April 8, 2026):

1. Pam Bondi was FIRED as Attorney General on April 2, 2026 (CNN, Fox, WashPost, Al Jazeera)
2. Todd Blanche is now ACTING Attorney General (CBS News)
3. Trump fired Bondi partly because she wasn't aggressive enough on Epstein files (NBC)
4. Trump also wanted her to prosecute his political enemies more aggressively (WashPost)
5. Lee Zeldin (EPA head) is being considered as permanent replacement (CNBC)
6. DOJ published 3.5 MILLION responsive pages in the Epstein Library (DOJ.gov — verified)
7. Epstein Files Transparency Act Section 3 Report released (DOJ.gov — verified)
8. PBS published full list of powerful people named in files
9. No new criminal charges have been filed despite the document releases
10. Democratic lawmakers wrote to Bondi (before firing) demanding victim advocacy (House Oversight)
11. Survivors continue to ask: where is accountability? (Iowa Public Radio)

FROM BHARAT'S YOUTUBE CHANNELS:
- Deshbhakt: Indian names in files (Modi, Ambani, Puri connections)
- newslaundry: Anil Ambani investigation
- MeidasTouch: Bondi deposition coverage (pre-firing)
- Katie Phang: NM ranch investigation, new evidence
- Dr G Explains: Forensic analysis of prison surveillance gaps
- Brian Tyler Cohen: DOJ oversight analysis
- Legal AF: Legal implications of document releases
"""

prompts = [
    ("epstein-bondi-fired",
     "Write about Trump FIRING Bondi partly over Epstein handling. What does this mean? "
     "Todd Blanche is now acting AG. Will he be tougher or just another cover? "
     "The real question: if Trump was unhappy with Bondi's Epstein approach, "
     "what is HIS agenda with the files? Sources: CNN, Al Jazeera, NBC, WashPost."),

    ("epstein-3point5million",
     "Write about DOJ dropping 3.5 MILLION pages but filing ZERO new charges. "
     "Todd Blanche (not Bondi — she was fired April 2) now oversees this. "
     "PBS published the names. Survivors demand accountability. "
     "The biggest document dump in US legal history and still no handcuffs. Why? "
     "Sources: DOJ.gov, PBS, Iowa Public Radio, House Oversight."),
]

articles = []
for slug, angle in prompts:
    prompt = f"""Write a provocative investigative article for Anka Research. {today_display}.

CRITICAL VERIFIED FACTS:
{VERIFIED_CONTEXT}

THIS ARTICLE: {angle}

RULES:
1. 400-500 words. Every claim must cite the verified source.
2. BONDI WAS FIRED APRIL 2. Todd Blanche is acting AG. Get this right.
3. Provocative but factually accurate — every statement must be traceable to a source above.
4. Connect to Indian angle where relevant (names in files).
5. End with "What to watch"
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

        html = build_article_html("epstein", article, today_display)
        filepath = GIT_REPO / "articles" / f"{today}-{slug}.html"
        filepath.write_text(html, encoding="utf-8")
        print(f"OK: {slug} — {article['headline'][:70]}")
        articles.append(slug)
    except Exception as e:
        print(f"FAIL: {slug} — {e}")

# Images
for slug in articles:
    try:
        resp = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-image-preview:generateContent?key={gkey}",
            json={"contents": [{"parts": [{"text": "Dark editorial: fired attorney general, legal chaos, scattered documents, gavel. 16:9. No text."}]}],
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
                   f"daily: {today} — VERIFIED Epstein articles (Bondi fired, Blanche acting AG)"],
                  cwd=str(GIT_REPO), check=True)
    subprocess.run(["git", "push"], cwd=str(GIT_REPO), check=True)
    print(f"\nDeployed {len(articles)} verified Epstein articles!")
