"""
Anka Research — AI Avatar Video Pipeline
Generates weekly video segments using HeyGen API with AI avatar presenter.

Two segments per week:
  1. Geopolitical/War analysis (Iran/US, Middle East, oil impact on India)
  2. Epstein Files updates (DOJ releases, legal proceedings, connections)

Pipeline flow:
  1. Load weekly themes + source URLs from video_themes.json
  2. Generate narration scripts via Claude API (fact-checked, sourced)
  3. Submit to HeyGen API for avatar video generation
  4. Poll for completion, download MP4
  5. Deploy to askanka.com/videos/ and push to GitHub Pages

Usage:
    python video_pipeline.py                     # generate both segments for current week
    python video_pipeline.py --segment war       # generate war segment only
    python video_pipeline.py --segment epstein   # generate epstein segment only
    python video_pipeline.py --week 7            # generate for specific week
    python video_pipeline.py --script-only       # generate scripts without video
    python video_pipeline.py --deploy            # generate + git push
"""

import argparse
import json
import logging
import os
import re
import sys
import time
import requests
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

log = logging.getLogger("anka.video")

PIPELINE_DIR = Path(__file__).parent
DATA_DIR = PIPELINE_DIR / "data" / "video"
SCRIPTS_DIR = DATA_DIR / "scripts"
OUTPUT_DIR = PIPELINE_DIR.parent / "videos"
THEMES_FILE = DATA_DIR / "video_themes.json"
LOG_DIR = PIPELINE_DIR / "logs"

for d in [DATA_DIR, SCRIPTS_DIR, OUTPUT_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# Load env
from dotenv import load_dotenv
load_dotenv(PIPELINE_DIR / ".env")

HEYGEN_API_KEY = os.getenv("HEYGEN_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
HEYGEN_BASE = "https://api.heygen.com"

# Avatar config — customise after creating your HeyGen avatar
AVATAR_ID = os.getenv("HEYGEN_AVATAR_ID", "")       # Set after account setup
VOICE_ID = os.getenv("HEYGEN_VOICE_ID", "")          # Set after account setup
AVATAR_STYLE = "normal"                                # normal, circle, closeup

# ── YouTube Source Channels (from Bharat's research watch history) ────────────
# YouTube RSS feeds: https://www.youtube.com/feeds/videos.xml?channel_id=XXXX
# These are the channels Bharat regularly watches for each research track.

YOUTUBE_SOURCES = {
    # === WAR / GEOPOLITICAL CHANNELS ===
    # Sourced from Bharat's YouTube watch history (1300+ videos, Feb-Apr 2026)
    "war": {
        # Tier 1 — Heavy watch (20+ videos each)
        "Al Jazeera English": {"channel_id": "UCNye-wNBqNL5ZzHSJj3l8Bg",     # 32 war videos
                               "keywords": ["iran", "war", "gulf", "hormuz", "trump", "middle east",
                                            "oil", "sanctions", "hegseth", "pentagon", "strike", "missile"]},
        "The Deshbhakt": {"channel_id": "UCmTM_hPCeckqN3cPWtYZZcg",          # 20 war videos
                          "keywords": ["iran", "war", "india", "oil", "crude", "modi", "defense",
                                       "geopolitical", "pakistan", "trump", "invasion"]},
        "MeidasTouch": {"channel_id": "UC9r9HYFxEQOBXSopFS61ZWg",            # 19 war videos
                        "keywords": ["iran", "war", "trump", "hegseth", "pentagon", "military",
                                     "strike", "bomb", "gulf", "bases"]},
        # Tier 2 — Regular watch (5-15 videos each)
        "The Young Turks": {"channel_id": "UC1yBKRuGpC1tSM73A0ZjYjQ",        # 8 war videos
                            "keywords": ["iran", "war", "trump", "hegseth", "towel", "military"]},
        "Being Honest": {"channel_id": "UCbrgKz68f3NvLr7p3Oiw9nA",           # 8 war videos
                         "keywords": ["iran", "modi", "petrol", "oil", "trump", "war"]},
        "MS NOW": {"channel_id": "UCaXkIU1QidjPwiAYu6GcHjg",                 # 7 war videos
                   "keywords": ["iran", "war", "hegseth", "negotiate", "trump", "military"]},
        "Brian Tyler Cohen": {"channel_id": "UCQANb2YPwAtK-IQJrLaaUFw",      # 7 war videos
                              "keywords": ["iran", "war", "hegseth", "trump", "raskin", "bomb"]},
        "Danny Haiphong": {"channel_id": "UCOxLhz6B_elvLflntSEfnzA",         # 6 war videos
                           "keywords": ["iran", "war", "hormuz", "kharg", "invasion", "pepe", "escobar",
                                        "missile", "gulf"]},
        "Times Of India": {"channel_id": "UCckHqySbfy5FcPP6MD_S-Yg",         # 6 war videos
                           "keywords": ["iran", "war", "irgc", "missile", "strike", "israel", "gulf"]},
        "Hook Global": {"channel_id": "UCyri-PL3l4Dn9IooWXQAqfA",            # 5 war videos
                        "keywords": ["iran", "war", "trump", "congress", "military"]},
        "Times Now": {"channel_id": "UC6RJ7-PaXg6TIH2BzZfTV7w",             # 5 war videos
                      "keywords": ["iran", "war", "middle east", "dubai", "explosion", "gulf", "alert"]},
        # Tier 3 — Occasional but credible (2-4 videos each)
        "Glenn Diesen": {"channel_id": "UCZFCDIHTe9HGxtIuVDpBz7g",           # 4 geopolitical analysis
                         "keywords": ["iran", "war", "narrative", "collapse", "ceasefire", "status quo"]},
        "Dhruv Rathee": {"channel_id": "UC-CSyyi47VX1lD9zyeABW3w",           # 2 war videos
                         "keywords": ["iran", "war", "oil", "crisis", "india", "danger", "middle east"]},
        "WION": {"channel_id": "UC_gUM8rL-Lrg6O3adPW9K1g",                   # 1 war (but high quality)
                 "keywords": ["iran", "war", "gulf", "hormuz", "oil", "india", "crude",
                              "defense", "trump", "middle east", "missile", "drone"]},
        "moneycontrol": {"channel_id": "UChftTVI0QJmyXkajQYt2tiQ",           # 3 war/oil videos
                         "keywords": ["iran", "war", "oil", "kharg", "crude", "strike", "israel"]},
        "ET Now World": {"channel_id": "UCJ04m06GHw3DUDQG6chCAUA",           # 3 war videos
                         "keywords": ["iran", "war", "trump", "conflict", "breaking"]},
        "Breaking Points": {"channel_id": "UCDRIjKy6eZOvKtOELtTdeUA",        # 2 (prison + war)
                            "keywords": ["iran", "war", "trump", "military", "coverup"]},
        "BBC News": {"channel_id": "UC16niRr50-MSBwiO3YDb3RA",               # 1 war
                     "keywords": ["iran", "war", "marines", "assault", "ship"]},
        "CNN": {"channel_id": "UCupvZG-5ko_eiXAupbDfxWw",                    # 1 war
                "keywords": ["iran", "war", "epstein", "maga"]},
        "Basant Maheshwari": {"channel_id": "UCqvuLvdIkUjAtSFrKw5LhXg",      # 1 — India market angle
                              "keywords": ["iran", "war", "stock market", "dubai", "oil"]},
    },
    # === EPSTEIN FILES CHANNELS ===
    # Sourced from Bharat's watch history — 140+ Epstein-related videos
    "epstein": {
        # Tier 1 — Heavy watch (10+ videos each)
        "Brian Tyler Cohen": {"channel_id": "UCQANb2YPwAtK-IQJrLaaUFw",      # 16 Epstein videos
                              "keywords": ["epstein", "files", "bondi", "trump", "coverup",
                                           "prosecutor", "doj", "bomb"]},
        "Law&Crime Network": {"channel_id": "UCz8K1occVvDTYDfFo7N5EZw",      # 15 Epstein videos
                              "keywords": ["epstein", "maxwell", "prince andrew", "trial", "trafficking",
                                           "documents", "files", "arrest", "depo", "photos", "secrets",
                                           "names", "300"]},
        "MS NOW": {"channel_id": "UCaXkIU1QidjPwiAYu6GcHjg",                 # 14 Epstein videos
                   "keywords": ["epstein", "files", "stink bomb", "shredded", "jail", "door",
                                "story", "broke"]},
        "MeidasTouch": {"channel_id": "UC9r9HYFxEQOBXSopFS61ZWg",            # 10 Epstein videos
                        "keywords": ["epstein", "files", "trump", "bondi", "deposition", "prison",
                                     "guard", "shutting down", "secrets"]},
        # Tier 2 — Regular watch (5-9 videos each)
        "Legal AF": {"channel_id": "UCJgZJZZbnLFPr5GJdCuIwpA",               # 8 Epstein videos
                     "keywords": ["epstein", "inner circle", "money trail", "trump", "panics",
                                  "bombshell", "revealed"]},
        "Dr. G Explains": {"channel_id": "UCOmjR-JVOshlZbUoQYOCxWg",         # 7 Epstein videos
                           "keywords": ["epstein", "prison", "cover up", "forensic", "expert",
                                        "inner circle", "exposed", "evidence"]},
        "CNN": {"channel_id": "UCupvZG-5ko_eiXAupbDfxWw",                    # 7 Epstein videos
                "keywords": ["epstein", "trump", "allegations", "perjury", "testimony",
                              "bondi", "briefing", "files"]},
        "The Young Turks": {"channel_id": "UC1yBKRuGpC1tSM73A0ZjYjQ",        # 7 Epstein videos
                            "keywords": ["epstein", "media", "cover", "story", "massie",
                                         "names", "himself"]},
        "Trap More Ross": {"channel_id": "UCfHv8HOlha7XMDtQSdOtlUA",         # 6 Epstein videos
                           "keywords": ["epstein", "home videos", "bill gates", "apology",
                                        "disturbing", "affairs"]},
        "Katie Phang": {"channel_id": "UCZl9z2UMvN9mwpUoU9-E9bA",            # 5 Epstein videos
                        "keywords": ["epstein", "ranch", "searched", "investigation", "doj",
                                     "files", "naming", "trump", "deep ties"]},
        # Tier 3 — Occasional but relevant (2-4 videos each)
        "ET Now World": {"channel_id": "UCJ04m06GHw3DUDQG6chCAUA",           # 4 Epstein videos
                         "keywords": ["epstein", "kash patel", "fbi", "pam bondi", "list"]},
        "Ari Melber": {"channel_id": "UCFovbwWXUHkHsRT9eX2KQUQ",             # 4 Epstein videos
                       "keywords": ["epstein", "docs", "shredded", "jail", "death", "elite",
                                    "finance", "expose"]},
        "Times Of India": {"channel_id": "UCckHqySbfy5FcPP6MD_S-Yg",         # 4 Epstein videos
                           "keywords": ["epstein", "elon musk", "kash patel", "wexner",
                                        "les wexner", "deposition"]},
        "60 Minutes Australia": {"channel_id": "UC0L1suV8pVgO4pCAIBNGx5w",   # 4 Epstein videos
                                 "keywords": ["epstein", "files", "rich", "famous", "reckoning",
                                              "trafficking"]},
        "Dr. Subramanian Swamy": {"channel_id": "UCDnCzWI3cKSExdlDfuB3Zeg",  # 4 Epstein videos (India angle)
                                  "keywords": ["epstein", "files", "modi", "inaction", "fallout"]},
        "Glenn Kirschner": {"channel_id": "UCrWmonkmTk5NbvmVnc7f70w",        # 3 Epstein videos
                            "keywords": ["epstein", "coverup", "doj", "evidence", "revelations",
                                         "staggering"]},
        "Forbes Breaking News": {"channel_id": "UCg40OxZ1GYh3u3jBntB6DLg",   # 3 Epstein videos
                                 "keywords": ["epstein", "indyke", "lawyer", "testifies", "oversight",
                                              "prince andrew", "bill gates"]},
        "ABC News In-depth": {"channel_id": "UCxcrzzhQDj5zKJbXfIscCtg",      # 3 Epstein videos
                              "keywords": ["epstein", "money", "shadow", "chaos", "uk", "silence"]},
        "The Deshbhakt": {"channel_id": "UCmTM_hPCeckqN3cPWtYZZcg",          # 3 Epstein videos (India)
                          "keywords": ["epstein", "india", "puri", "hardeep", "opposition",
                                       "minister", "question", "files", "israel", "trump"]},
        "BBC News": {"channel_id": "UC16niRr50-MSBwiO3YDb3RA",               # 3 Epstein videos
                     "keywords": ["epstein", "hillary", "clinton", "cover-up", "congress",
                                  "victims", "justice"]},
        "Dhruv Rathee": {"channel_id": "UC-CSyyi47VX1lD9zyeABW3w",           # 2 Epstein videos (India)
                         "keywords": ["epstein", "dark secrets", "scandal", "ambani", "modi",
                                      "evidence"]},
        "Breaking Points": {"channel_id": "UCDRIjKy6eZOvKtOELtTdeUA",        # 2 Epstein videos
                            "keywords": ["epstein", "prison", "inmate", "coverup", "surveillance",
                                         "israeli"]},
        "Channel 4 News": {"channel_id": "UCTrQ7HXWRRxr7OsOtodr2_w",         # 2 Epstein videos
                           "keywords": ["epstein", "files", "unreleased", "incompetence", "coverup",
                                        "spycams", "unredacted"]},
        "newslaundry": {"channel_id": "UCustbySVJGb659WDpdkeATg",             # 1 but India-specific
                        "keywords": ["epstein", "anil ambani", "hardeep singh puri", "india"]},
        "Zeteo": {"channel_id": "UCVG72F2Q5yCmLQfctNK6M2A",                  # 2 Epstein videos
                  "keywords": ["epstein", "achilles heel", "trump", "mehdi", "conspiracies",
                               "elite circle"]},
    },
}

# Segment definitions
SEGMENTS = {
    "war": {
        "title": "Iran-US War & Geopolitical Impact",
        "slug": "war-geopolitical",
        "themes": [
            "Iran US military conflict", "Strait of Hormuz oil shipping",
            "Gulf state impact on India", "crude oil price impact",
            "defense spending escalation", "sanctions and trade",
            "Trump Iran policy", "Middle East ceasefire negotiations",
        ],
        "tone": "Analytical and measured. Present facts from credible sources. "
                "Connect geopolitical events to market impact on Indian equities. "
                "No speculation — only cite what has been reported. "
                "Mention oil price movements, defense sector implications, "
                "and FII flow sensitivity.",
        "sources_priority": [
            "Al Jazeera", "Reuters", "Firstpost", "WION", "The Deshbhakt",
            "Danny Haiphong", "MeidasTouch", "AP News", "BBC", "The Hindu",
            "Economic Times",
        ],
    },
    "epstein": {
        "title": "Epstein Files & Legal Developments",
        "slug": "epstein-files",
        "themes": [
            "Epstein DOJ file releases", "Jeffrey Epstein associates",
            "Prince Andrew legal developments", "Ghislaine Maxwell",
            "Epstein island visitor logs", "intelligence connections",
            "Indian names in Epstein files", "legal proceedings updates",
        ],
        "tone": "Investigative journalism style. Stick strictly to documented facts "
                "from DOJ releases, court filings, and credible investigative journalism. "
                "No conspiracy theories — only cite verifiable sources. "
                "Use cautious language: 'according to court documents', 'as reported by'. "
                "Fact-check every claim against primary sources.",
        "sources_priority": [
            "DOJ.gov", "Court filings (PACER)", "Legal AF", "Law&Crime",
            "MeidasTouch", "Brian Tyler Cohen", "Dr. G Explains",
            "The Deshbhakt",
        ],
    },
}

# Target durations (constrained by HeyGen 5000 char/scene limit)
MIN_DURATION_SECS = 240   # 4 minutes
MAX_DURATION_SECS = 330   # 5.5 minutes (5000 chars ≈ 720 words ≈ 4.8 min)
WORDS_PER_MINUTE = 150    # Average speaking pace for avatar


def _current_week_num() -> int:
    """Get current Anka week number (Week 001 started 2026-02-24)."""
    epoch = datetime(2026, 2, 24)
    delta = datetime.now() - epoch
    return max(1, delta.days // 7 + 1)


def load_themes(week_num: int) -> dict:
    """Load or create weekly video themes file."""
    if THEMES_FILE.exists():
        all_themes = json.loads(THEMES_FILE.read_text(encoding="utf-8"))
    else:
        all_themes = {}

    week_key = f"week-{week_num:03d}"
    if week_key not in all_themes:
        # Auto-generate theme skeleton for this week
        all_themes[week_key] = {
            "week_number": week_num,
            "created": datetime.now().isoformat(),
            "segments": {
                name: {
                    "title": seg["title"],
                    "key_events": [],       # Fill manually or via news API
                    "source_urls": [],      # URLs to cite
                    "script": None,         # Generated script
                    "video_id": None,       # HeyGen video ID
                    "video_url": None,      # Downloaded MP4 path
                    "status": "pending",
                }
                for name, seg in SEGMENTS.items()
            },
        }
        THEMES_FILE.write_text(
            json.dumps(all_themes, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        log.info(f"Created theme skeleton for {week_key}")

    return all_themes[week_key]


def save_themes(week_num: int, week_data: dict):
    """Save updated theme data back to file."""
    if THEMES_FILE.exists():
        all_themes = json.loads(THEMES_FILE.read_text(encoding="utf-8"))
    else:
        all_themes = {}
    all_themes[f"week-{week_num:03d}"] = week_data
    THEMES_FILE.write_text(
        json.dumps(all_themes, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


# ── YouTube Channel Scraper (yt-dlp) ─────────────────────────────────────────

_YT_CACHE_DIR = PIPELINE_DIR / "data" / "yt_cache"


def fetch_youtube_feed(channel_id: str, max_entries: int = 15) -> list[dict]:
    """Fetch recent videos from a YouTube channel via yt-dlp.

    Results are cached on disk for 6 hours to avoid hammering YouTube
    when multiple article segments run back-to-back.
    """
    _YT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = _YT_CACHE_DIR / f"{channel_id}.json"
    if cache_file.exists():
        try:
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
            age_s = (datetime.now() - datetime.fromisoformat(cached["ts"])).total_seconds()
            if age_s < 6 * 3600:
                return cached["entries"][:max_entries]
        except Exception:
            pass

    try:
        import yt_dlp
    except ImportError:
        log.warning("yt-dlp not installed — cannot fetch videos for %s", channel_id)
        return []

    url = f"https://www.youtube.com/channel/{channel_id}/videos"
    opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": "in_playlist",
        "playlist_items": f"1-{max_entries}",
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        if not info or "entries" not in info:
            log.warning("No entries from yt-dlp for %s", channel_id)
            return []

        entries = []
        for e in list(info["entries"])[:max_entries]:
            if e is None:
                continue
            entries.append({
                "title": e.get("title", ""),
                "url": f"https://www.youtube.com/watch?v={e['id']}" if e.get("id") else "",
                "published": "",
                "description": (e.get("description") or "")[:500],
            })

        cache_file.write_text(json.dumps({
            "ts": datetime.now().isoformat(),
            "channel_id": channel_id,
            "entries": entries,
        }), encoding="utf-8")
        return entries
    except Exception as e:
        log.warning("yt-dlp fetch failed for %s: %s", channel_id, e)
        return []


def scrape_weekly_sources(segment_name: str, days_back: int = 7) -> list[dict]:
    """Scrape YouTube RSS feeds for a segment, filter by keywords and recency."""
    channels = YOUTUBE_SOURCES.get(segment_name, {})
    cutoff = datetime.now() - timedelta(days=days_back)
    relevant = []

    for channel_name, cfg in channels.items():
        entries = fetch_youtube_feed(cfg["channel_id"])
        keywords = [k.lower() for k in cfg["keywords"]]

        for entry in entries:
            # Check recency
            try:
                pub_date = datetime.fromisoformat(entry["published"].replace("Z", "+00:00"))
                if pub_date.replace(tzinfo=None) < cutoff:
                    continue
            except (ValueError, TypeError):
                pass  # If we can't parse date, include it

            # Check keyword relevance
            text = (entry["title"] + " " + entry["description"]).lower()
            matched = [k for k in keywords if k in text]
            if matched:
                relevant.append({
                    "channel": channel_name,
                    "title": entry["title"],
                    "url": entry["url"],
                    "published": entry["published"],
                    "matched_keywords": matched,
                    "relevance_score": len(matched),
                })

    # Sort by relevance (most keyword matches first)
    relevant.sort(key=lambda x: x["relevance_score"], reverse=True)
    log.info(f"Scraped {len(relevant)} relevant videos for '{segment_name}' "
             f"from {len(channels)} channels")
    return relevant


def auto_populate_themes(week_num: int):
    """Auto-populate weekly themes from YouTube RSS feeds."""
    week_data = load_themes(week_num)

    for seg_name in SEGMENTS:
        seg_data = week_data["segments"][seg_name]
        if seg_data.get("key_events") and seg_data["key_events"]:
            log.info(f"  {seg_name}: already has {len(seg_data['key_events'])} events, skipping")
            continue

        videos = scrape_weekly_sources(seg_name)
        if videos:
            # Top 10 most relevant video titles become key events
            seg_data["key_events"] = [v["title"] for v in videos[:10]]
            # All URLs become source URLs
            seg_data["source_urls"] = [v["url"] for v in videos[:15]]
            log.info(f"  {seg_name}: populated {len(seg_data['key_events'])} events "
                     f"from {len(videos)} relevant videos")

    save_themes(week_num, week_data)
    return week_data


# ── Script Generation (Claude API) ───────────────────────────────────────────

def generate_script(segment_name: str, week_data: dict, week_num: int) -> str:
    """Generate a narration script for a video segment using Claude API."""
    seg_config = SEGMENTS[segment_name]
    seg_data = week_data["segments"][segment_name]

    # Build context from key events and sources
    events_text = "\n".join(f"- {e}" for e in seg_data.get("key_events", []))
    sources_text = "\n".join(f"- {u}" for u in seg_data.get("source_urls", []))

    # HeyGen API has 5000 char limit per video (~700 words clean)
    target_words = 650   # ~4.5 min at 150 wpm, leaves room for SOURCE tags
    max_words = 720      # Hard ceiling to stay under 5000 chars after tag removal

    prompt = f"""You are a script writer for Anka Research (askanka.com), an Indian equity
spread trading signal platform. Write a narration script for an AI avatar video segment.

SEGMENT: {seg_config['title']}
WEEK: {week_num} of the Anka Research weekly video series
DATE: {datetime.now().strftime('%B %d, %Y')}

TONE: {seg_config['tone']}

KEY EVENTS THIS WEEK:
{events_text if events_text else '(No specific events provided — use general themes below)'}

THEMES TO COVER:
{chr(10).join('- ' + t for t in seg_config['themes'])}

SOURCE URLS PROVIDED:
{sources_text if sources_text else '(No specific URLs — cite from priority sources)'}

PRIORITY SOURCES (cite these when possible):
{chr(10).join('- ' + s for s in seg_config['sources_priority'])}

REQUIREMENTS:
1. Write {target_words}-{max_words} words (5-10 minutes at 150 wpm)
2. Start with a brief hook/intro: "Welcome to Anka Research Week {week_num}..."
3. Present 3-5 key developments with source attribution
4. For each development, briefly explain the market/India impact
5. End with a summary and forward-looking statement
6. Include [SOURCE: ...] tags inline for fact-checking
7. Do NOT include stage directions, camera notes, or visual cues
8. Write in first person as the Anka Research presenter
9. Use measured, analytical language — no sensationalism
10. Every factual claim must have a [SOURCE: ...] tag

OUTPUT FORMAT:
Return ONLY the narration script text. No headers, no metadata."""

    if not GEMINI_API_KEY:
        log.warning("No GEMINI_API_KEY — returning placeholder script")
        return f"[PLACEHOLDER] Script for {seg_config['title']} — Week {week_num}. Set GEMINI_API_KEY to generate."

    # Use Gemini 2.5 Flash (free tier) during shadow period
    resp = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}",
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "maxOutputTokens": 8192,
                "temperature": 0.7,
                "thinkingConfig": {"thinkingBudget": 0},
            },
        },
        timeout=180,
    )
    resp.raise_for_status()
    result = resp.json()
    candidates = result.get("candidates", [])
    if not candidates:
        raise ValueError(f"Gemini returned no candidates: {result}")
    parts = candidates[0].get("content", {}).get("parts", [])
    script = parts[0].get("text", "") if parts else ""

    # Save script to file
    script_file = SCRIPTS_DIR / f"week-{week_num:03d}-{seg_config['slug']}.txt"
    script_file.write_text(script, encoding="utf-8")
    log.info(f"Script saved: {script_file} ({len(script.split())} words)")

    return script


# ── Fact-Check Layer ────────���─────────────────────────────────────────────────

def extract_source_tags(script: str) -> list[dict]:
    """Extract all [SOURCE: ...] tags from a script for verification."""
    pattern = r'\[SOURCE:\s*([^\]]+)\]'
    matches = re.findall(pattern, script)
    return [{"source": m.strip(), "verified": False} for m in matches]


def fact_check_script(script: str, segment_name: str) -> dict:
    """Run fact-check pass on generated script. Returns check report."""
    sources = extract_source_tags(script)
    word_count = len(script.split())
    duration_est = word_count / WORDS_PER_MINUTE

    report = {
        "word_count": word_count,
        "estimated_duration_min": round(duration_est, 1),
        "source_count": len(sources),
        "sources": sources,
        "in_range": MIN_DURATION_SECS / 60 <= duration_est <= MAX_DURATION_SECS / 60,
        "warnings": [],
    }

    if duration_est < MIN_DURATION_SECS / 60:
        report["warnings"].append(f"Script too short: {duration_est:.1f} min (min 5)")
    if duration_est > MAX_DURATION_SECS / 60:
        report["warnings"].append(f"Script too long: {duration_est:.1f} min (max 10)")
    if len(sources) < 3:
        report["warnings"].append(f"Only {len(sources)} sources cited — aim for 5+")

    # Check for speculation language
    spec_phrases = ["it is believed", "rumor has it", "some say", "conspiracy",
                    "allegedly" , "unconfirmed reports"]
    for phrase in spec_phrases:
        if phrase.lower() in script.lower():
            report["warnings"].append(f"Speculation language detected: '{phrase}'")

    return report


# ── HeyGen Video Generation ───────────────���──────────────────────────────────

def _heygen_headers() -> dict:
    return {
        "X-Api-Key": HEYGEN_API_KEY,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _split_script_to_scenes(text: str, max_chars: int = 4800) -> list[str]:
    """Split a long script into chunks that fit HeyGen's per-scene char limit.
    Splits on paragraph breaks first, then sentence boundaries."""
    if len(text) <= max_chars:
        return [text]

    # Try splitting on double-newlines (paragraphs) first
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks = []
    current = ""
    for para in paragraphs:
        if len(current) + len(para) + 2 <= max_chars:
            current = current + "\n\n" + para if current else para
        else:
            if current:
                chunks.append(current.strip())
            # If single paragraph exceeds limit, split on sentences
            if len(para) > max_chars:
                sentences = re.split(r'(?<=[.!?])\s+', para)
                current = ""
                for sent in sentences:
                    if len(current) + len(sent) + 1 <= max_chars:
                        current = current + " " + sent if current else sent
                    else:
                        if current:
                            chunks.append(current.strip())
                        current = sent
            else:
                current = para
    if current:
        chunks.append(current.strip())
    return chunks


def create_heygen_video(script: str, segment_name: str, week_num: int) -> str:
    """Submit script to HeyGen API (v2/videos) for avatar video generation.
    Uses the new flat API format. Returns the video_id for polling."""
    if not HEYGEN_API_KEY:
        log.error("No HEYGEN_API_KEY set")
        return ""
    if not AVATAR_ID or not VOICE_ID:
        log.error("HEYGEN_AVATAR_ID and HEYGEN_VOICE_ID must be set in .env")
        return ""

    seg_config = SEGMENTS[segment_name]

    # Strip [SOURCE: ...] tags from narration (keep for script file only)
    clean_script = re.sub(r'\[SOURCE:\s*[^\]]+\]', '', script).strip()
    # Collapse multiple spaces
    clean_script = re.sub(r'  +', ' ', clean_script)

    # Talking photo avatars have a ~2500 char effective limit
    # Split into chunks and generate separate videos, then concatenate
    CHUNK_LIMIT = 2000
    chunks = _split_script_to_scenes(clean_script, CHUNK_LIMIT)
    log.info(f"Script: {len(clean_script)} chars -> {len(chunks)} part(s) (avatar: {AVATAR_ID[:12]}...)")

    if len(chunks) == 1:
        # Single video
        return _submit_heygen_single(chunks[0], seg_config, week_num)
    else:
        # Multiple parts — submit all, return first ID (track all in themes)
        video_ids = []
        for i, chunk in enumerate(chunks):
            title = f"Anka Research Week {week_num} - {seg_config['title']} (Part {i+1}/{len(chunks)})"
            vid = _submit_heygen_single(chunk, seg_config, week_num, title=title)
            if vid:
                video_ids.append(vid)
            else:
                log.error(f"Failed to submit part {i+1}")
                return ""
        log.info(f"Submitted {len(video_ids)} parts: {video_ids}")
        # Store all IDs comma-separated so we can poll/download all
        return ",".join(video_ids)


def _submit_heygen_single(script_text: str, seg_config: dict, week_num: int,
                          title: str = None) -> str:
    """Submit a single video to HeyGen v2/videos API."""
    payload = {
        "avatar_id": AVATAR_ID,
        "script": script_text,
        "voice_id": VOICE_ID,
        "title": title or f"Anka Research Week {week_num} - {seg_config['title']}",
        "resolution": "1080p",
        "aspect_ratio": "16:9",
        "expressiveness": "medium",
    }

    resp = requests.post(
        f"{HEYGEN_BASE}/v2/videos",
        headers=_heygen_headers(),
        json=payload,
        timeout=60,
    )

    if resp.status_code != 200:
        log.error(f"HeyGen API error: {resp.status_code} — {resp.text[:500]}")
        return ""

    data = resp.json()
    video_id = (data.get("data", {}).get("video_id", "")
                or data.get("video_id", ""))
    if video_id:
        log.info(f"HeyGen video submitted: {video_id}")
    else:
        log.error(f"HeyGen response missing video_id: {data}")

    return video_id


def poll_heygen_video(video_id: str, max_wait: int = 1800) -> dict:
    """Poll HeyGen API until video is ready. Returns video info dict."""
    start = time.time()
    while time.time() - start < max_wait:
        resp = requests.get(
            f"{HEYGEN_BASE}/v2/videos/{video_id}",
            headers=_heygen_headers(),
            timeout=30,
        )
        if resp.status_code != 200:
            # Fallback to legacy endpoint
            resp = requests.get(
                f"{HEYGEN_BASE}/v1/video_status.get",
                headers=_heygen_headers(),
                params={"video_id": video_id},
                timeout=30,
            )
        resp.raise_for_status()
        data = resp.json().get("data", {})
        status = data.get("status", "")

        if status == "completed":
            log.info(f"Video {video_id} completed!")
            return data
        elif status == "failed":
            log.error(f"Video {video_id} failed: {data.get('error', 'unknown')}")
            return data
        else:
            elapsed = int(time.time() - start)
            log.info(f"Video {video_id} status: {status} ({elapsed}s elapsed)")
            time.sleep(30)

    log.error(f"Video {video_id} timed out after {max_wait}s")
    return {"status": "timeout"}


def download_heygen_video(video_url: str, week_num: int, segment_name: str) -> Path:
    """Download completed video MP4 to output directory."""
    seg_slug = SEGMENTS[segment_name]["slug"]
    filename = f"week-{week_num:03d}-{seg_slug}.mp4"
    output_path = OUTPUT_DIR / filename

    resp = requests.get(video_url, stream=True, timeout=300)
    resp.raise_for_status()

    with open(output_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)

    size_mb = output_path.stat().st_size / (1024 * 1024)
    log.info(f"Downloaded: {output_path} ({size_mb:.1f} MB)")
    return output_path


# ── HTML Video Page Generator ────────���────────────────────────────────────────

def generate_video_page(week_num: int, segments_data: dict) -> Path:
    """Generate HTML page for the week's video segments."""
    cards = []
    for seg_name, seg_data in segments_data.items():
        if seg_data.get("video_url"):
            seg_config = SEGMENTS.get(seg_name, {})
            video_file = Path(seg_data["video_url"]).name
            cards.append(f"""
    <div class="video-card">
      <h3>{seg_config.get('title', seg_name)}</h3>
      <video controls width="100%" poster="">
        <source src="/videos/{video_file}" type="video/mp4">
      </video>
      <p class="video-sources">Sources: {', '.join(seg_config.get('sources_priority', [])[:4])}</p>
    </div>""")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Anka Research — Week {week_num:03d} Video Briefing</title>
<style>
:root {{ --bg: #0a0a0a; --card-bg: #141414; --text: #e5e7eb; --accent: #d4a855; --border: #2a2a2a; }}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ background: var(--bg); color: var(--text); font-family: 'Inter', -apple-system, sans-serif; }}
.container {{ max-width: 960px; margin: 0 auto; padding: 40px 20px; }}
h1 {{ color: var(--accent); font-size: 28px; margin-bottom: 8px; }}
.subtitle {{ color: #6b7280; margin-bottom: 30px; }}
.video-card {{ background: var(--card-bg); border: 1px solid var(--border); border-radius: 12px; padding: 24px; margin-bottom: 24px; }}
.video-card h3 {{ color: var(--accent); margin-bottom: 16px; font-size: 20px; }}
.video-card video {{ border-radius: 8px; background: #000; }}
.video-sources {{ font-size: 12px; color: #6b7280; margin-top: 12px; }}
.back-link {{ color: var(--accent); text-decoration: none; display: inline-block; margin-top: 20px; }}
</style>
</head>
<body>
<div class="container">
  <h1>Week {week_num:03d} Video Briefing</h1>
  <p class="subtitle">Anka Research — {datetime.now().strftime('%B %d, %Y')}</p>
  {''.join(cards) if cards else '<p>Videos are being generated. Check back soon.</p>'}
  <a href="/" class="back-link">&larr; Back to Dashboard</a>
</div>
</body>
</html>"""

    page_path = OUTPUT_DIR / f"week-{week_num:03d}.html"
    page_path.write_text(html, encoding="utf-8")
    log.info(f"Video page generated: {page_path}")
    return page_path


# ── Main Pipeline ───────��─────────────────────────────────────────────────────

def run_segment(segment_name: str, week_num: int, script_only: bool = False) -> dict:
    """Run full pipeline for one segment."""
    log.info(f"=== {SEGMENTS[segment_name]['title']} — Week {week_num} ===")

    week_data = load_themes(week_num)
    seg_data = week_data["segments"][segment_name]

    # Step 1: Generate script
    if not seg_data.get("script"):
        log.info("Generating script...")
        script = generate_script(segment_name, week_data, week_num)
        seg_data["script"] = script
        seg_data["status"] = "script_ready"
        save_themes(week_num, week_data)
    else:
        script = seg_data["script"]
        log.info(f"Using existing script ({len(script.split())} words)")

    # Step 2: Fact-check
    check = fact_check_script(script, segment_name)
    log.info(f"Fact-check: {check['word_count']} words, {check['estimated_duration_min']} min, "
             f"{check['source_count']} sources")
    for w in check["warnings"]:
        log.warning(f"  WARNING: {w}")

    # Save fact-check report
    check_file = SCRIPTS_DIR / f"week-{week_num:03d}-{SEGMENTS[segment_name]['slug']}-check.json"
    check_file.write_text(json.dumps(check, indent=2), encoding="utf-8")

    if script_only:
        log.info("Script-only mode — stopping before video generation")
        return {"script": script, "check": check, "status": "script_ready"}

    # Step 3: Generate video via HeyGen
    if not seg_data.get("video_id"):
        video_id = create_heygen_video(script, segment_name, week_num)
        if not video_id:
            return {"script": script, "check": check, "status": "heygen_error"}
        seg_data["video_id"] = video_id
        seg_data["status"] = "generating"
        save_themes(week_num, week_data)
    else:
        video_id = seg_data["video_id"]
        log.info(f"Using existing video_id: {video_id}")

    # Step 4: Poll for completion (handle multi-part videos)
    all_video_ids = video_id.split(",")
    all_paths = []
    for i, vid in enumerate(all_video_ids):
        log.info(f"Polling part {i+1}/{len(all_video_ids)}: {vid}")
        result = poll_heygen_video(vid)
        if result.get("status") != "completed":
            seg_data["status"] = f"failed: {result.get('status', 'unknown')}"
            save_themes(week_num, week_data)
            return {"script": script, "check": check, "status": seg_data["status"]}

        # Step 5: Download each part
        video_url = result.get("video_url", "")
        if video_url:
            suffix = f"-part{i+1}" if len(all_video_ids) > 1 else ""
            seg_slug = SEGMENTS[segment_name]["slug"]
            filename = f"week-{week_num:03d}-{seg_slug}{suffix}.mp4"
            output_path = OUTPUT_DIR / filename
            resp = requests.get(video_url, stream=True, timeout=300)
            resp.raise_for_status()
            with open(output_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            size_mb = output_path.stat().st_size / (1024 * 1024)
            log.info(f"Downloaded part {i+1}: {output_path} ({size_mb:.1f} MB)")
            all_paths.append(str(output_path))

    if all_paths:
        seg_data["video_url"] = all_paths[0] if len(all_paths) == 1 else ",".join(all_paths)
        seg_data["status"] = "complete"
        save_themes(week_num, week_data)
        log.info(f"Segment complete: {len(all_paths)} file(s)")
    else:
        seg_data["status"] = "no_download_url"
        save_themes(week_num, week_data)

    return {"script": script, "check": check, "status": seg_data["status"]}


def run_pipeline(week_num: int = None, segment: str = None,
                 script_only: bool = False, deploy: bool = False):
    """Run the full video pipeline."""
    if week_num is None:
        week_num = _current_week_num()

    segments_to_run = [segment] if segment else list(SEGMENTS.keys())

    log.info(f"Video pipeline — Week {week_num}, segments: {segments_to_run}")

    # Auto-populate themes from YouTube RSS feeds
    log.info("Scraping YouTube source channels for this week's content...")
    auto_populate_themes(week_num)

    results = {}
    for seg_name in segments_to_run:
        results[seg_name] = run_segment(seg_name, week_num, script_only=script_only)

    # Generate video page
    week_data = load_themes(week_num)
    generate_video_page(week_num, week_data["segments"])

    # Deploy if requested
    if deploy:
        _deploy_to_github(week_num)

    return results


def _deploy_to_github(week_num: int):
    """Git add, commit, push video files to askanka.com repo."""
    import subprocess
    site_dir = PIPELINE_DIR.parent
    try:
        subprocess.run(["git", "add", "videos/"], cwd=str(site_dir), check=True)
        subprocess.run(
            ["git", "commit", "-m",
             f"video: Week {week_num:03d} video briefing"],
            cwd=str(site_dir), check=True,
        )
        subprocess.run(["git", "push"], cwd=str(site_dir), check=True)
        log.info("Deployed to GitHub Pages")
    except subprocess.CalledProcessError as e:
        log.error(f"Git deploy failed: {e}")


# ── CLI ─────────────────���─────────────────────────────────────────────────────

def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(LOG_DIR / "video_pipeline.log", delay=True, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )

    parser = argparse.ArgumentParser(description="Anka Research Video Pipeline")
    parser.add_argument("--week", type=int, default=None, help="Week number")
    parser.add_argument("--segment", choices=list(SEGMENTS.keys()),
                        help="Generate specific segment only")
    parser.add_argument("--script-only", action="store_true",
                        help="Generate scripts without video")
    parser.add_argument("--deploy", action="store_true",
                        help="Git push after generation")
    args = parser.parse_args()

    run_pipeline(
        week_num=args.week,
        segment=args.segment,
        script_only=args.script_only,
        deploy=args.deploy,
    )


if __name__ == "__main__":
    main()
