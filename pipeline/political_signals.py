"""
Anka Research Pipeline -- Political Signal Engine
Real-time political event detection and signal generation.
Scans RSS feeds, classifies events, and generates spread trade signals.
"""

import json
import logging
import os
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import requests
from bs4 import BeautifulSoup

from config import (
    EVENT_TAXONOMY,
    INDIA_SIGNAL_STOCKS,
    INDIA_SPREAD_PAIRS,
    NEWS_KEYWORDS,
    NEWS_RSS_FEEDS,
    SIGNAL_CONFIDENCE_THRESHOLD,
    SIGNAL_HIT_RATE_THRESHOLD,
    SIGNAL_MIN_PRECEDENTS,
    SIGNAL_STOP_LOSS_PCT,
    TIER_SIGNAL,
    TIER_EXPLORING,
    TIER_NO_DATA,
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logger = logging.getLogger("anka.political_signals")
logger.setLevel(logging.DEBUG)
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter(
        "%(asctime)s | %(name)s | %(levelname)s | %(message)s"
    ))
    logger.addHandler(_handler)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
DATA_DIR = Path(__file__).parent / "data"
SIGNALS_DIR = DATA_DIR / "signals"
SEEN_FILE = DATA_DIR / "seen_events.json"

DATA_DIR.mkdir(parents=True, exist_ok=True)
SIGNALS_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Optional API keys
# ---------------------------------------------------------------------------
ANTHROPIC_API_KEY: Optional[str] = os.environ.get("ANTHROPIC_API_KEY")
GEMINI_API_KEY: Optional[str] = os.environ.get("GEMINI_API_KEY")
NEWSAPI_KEY: Optional[str] = os.environ.get("NEWSAPI_KEY")

# ---------------------------------------------------------------------------
# Keyword classification rules
# ---------------------------------------------------------------------------
KEYWORD_RULES: dict[str, dict[str, Any]] = {
    # ── ESCALATION ─────────────────────────────────────────────
    # Broadest category: military action from ANY actor
    "escalation": {
        "must_contain": [
            # Military actions
            "strike", "attack", "bomb", "missile", "shell",
            "assault", "offensive", "retaliat", "escalat", "war",
            "invade", "invasion", "troops deploy", "military operation",
            "air raid", "naval clash", "drone strike", "ground offensive",
            "carpet bomb", "bunker buster", "intercept",
            # Houthi / proxy actions
            "houthi attack", "houthi missile", "houthi drone",
            "houthi target", "red sea attack", "bab al-mandab",
            "ansar allah", "yemen strike",
            # Hezbollah / Lebanon
            "hezbollah rocket", "hezbollah attack", "hezbollah strike",
            "lebanon front", "nasrallah",
            # Iran direct
            "irgc attack", "irgc strike", "iran retali",
            "iran launches", "iran fires", "ballistic missile",
            "hypersonic", "iran nuclear",
            # Israel actions
            "idf strike", "israel bomb", "israel attack", "mossad",
            "iron dome", "israel retali", "netanyahu warn",
            "netanyahu threat", "gallant", "katz warn",
            # Iraqi / Syrian militia
            "militia attack", "pmf", "kata'ib", "islamic resistance",
            "iraq militia", "syria strike",
            # Broader conflict markers
            "civilian casualt", "infrastructure destroy",
            "damage irreversible", "point of no return",
            "total war", "all-out war", "wider war", "regional war",
        ],
        "boost_words": [
            "iran", "israel", "hezbollah", "houthi", "idf",
            "irgc", "pentagon", "casualties", "killed",
            "destroyed", "intercepted", "launched", "netanyahu",
            "khamenei", "raisi", "nasrallah", "abdulmalik",
            "yemen", "lebanon", "syria", "iraq", "gulf",
        ],
        "exclude": ["ceasefire", "peace", "de-escalat", "truce", "deal signed"],
    },

    # ── DE-ESCALATION ──────────────────────────────────────────
    "de_escalation": {
        "must_contain": [
            "de-escalat", "deescalat", "tensions eas", "pull back",
            "withdraw", "stand down", "cooling", "calm",
            "restraint", "back channel", "reduce tensions",
            "step back", "pause operation", "halt strikes",
            # Leadership signals
            "khamenei restrain", "netanyahu pause", "trump willing",
            "xi calls for calm", "putin urge", "erdogan mediat",
            "mbs peace", "modi call", "macron restrain",
        ],
        "boost_words": [
            "diplomat", "talks", "negotiat", "un envoy", "mediator",
            "backchannel", "hotline", "confidence build",
            "both sides", "mutual", "goodwill",
        ],
        "exclude": ["escalat", "strike", "attack", "bomb", "reject"],
    },

    # ── CEASEFIRE ──────────────────────────────────────────────
    "ceasefire": {
        "must_contain": [
            "ceasefire", "cease-fire", "truce", "armistice",
            "peace deal", "peace agreement", "halt fire",
            "cessation of hostilities", "lay down arms",
            "ceasefire proposal", "un ceasefire", "humanitarian pause",
            "72-hour", "48-hour", "temporary halt",
        ],
        "boost_words": [
            "signed", "agreed", "accepted", "permanent",
            "humanitarian", "un resolution", "security council",
            "both parties", "verified", "monitor",
        ],
        "exclude": ["reject ceasefire", "violat", "broke ceasefire", "collapsed", "ceasefire fails"],
    },

    # ── OIL POSITIVE (price up) ────────────────────────────────
    "oil_positive": {
        "must_contain": [
            "oil price rise", "oil surge", "crude surge", "crude jump",
            "brent above", "opec cut", "supply cut", "output cut",
            "oil rally", "energy price spike", "oil supply risk",
            "production cut", "oil above", "oil soar", "crude soar",
            "oil hits", "brent hits", "crude hits",
            # Supply disruption triggers
            "oil supply disrupt", "refinery shut", "pipeline attack",
            "tanker attack", "shipping disrupt", "port closure",
            "export halt", "opec emergency",
            # Geopolitical oil movers
            "saudi cut", "russia cut", "opec+ cut",
            "oil weapon", "energy weapon",
        ],
        "boost_words": [
            "barrel", "$100", "$110", "$120", "$130", "$140", "$150",
            "shortage", "disruption", "strait", "tanker",
            "record high", "highest since", "all-time",
            "hormuz", "red sea", "supply shock",
        ],
        "exclude": ["oil price drop", "oil falls", "crude drop", "oil slump"],
    },

    # ── OIL NEGATIVE (price down) ──────────────────────────────
    "oil_negative": {
        "must_contain": [
            "oil price drop", "oil falls", "crude drop", "crude slide",
            "brent below", "opec increase", "output increase",
            "oil demand weak", "oil surplus", "inventory build",
            "oil slump", "crude slump", "oil crash", "oil tumble",
            "demand destruction", "recession fear",
            # Supply increase
            "spr release", "strategic reserve", "us shale boom",
            "opec+ increase", "production ramp", "saudi increase",
        ],
        "boost_words": [
            "recession", "demand destruction", "oversupply",
            "us shale", "spr release", "glut", "weakest since",
        ],
        "exclude": ["oil surge", "oil rally", "crude jump", "oil soar"],
    },

    # ── SANCTIONS ──────────────────────────────────────────────
    "sanctions": {
        "must_contain": [
            "sanction", "embargo", "ban export", "trade restrict",
            "blacklist", "asset freeze", "financial penalty",
            "ofac", "treasury designat", "secondary sanction",
            # Broader sanctions actors
            "eu sanction", "un sanction", "us sanction",
            "china sanction", "swift ban", "bank restrict",
            "oil embargo", "arms embargo", "tech export ban",
            "entity list", "trade war", "economic warfare",
        ],
        "boost_words": [
            "iran", "russia", "china", "north korea",
            "oil sanction", "secondary sanction", "waiver",
            "exemption", "enforcement", "violat",
            "india buy", "china buy", "bypass",
        ],
        "exclude": ["lift sanction", "ease sanction", "waive sanction", "suspend sanction"],
    },

    # ── HORMUZ / SHIPPING CHOKEPOINTS ──────────────────────────
    "hormuz": {
        "must_contain": [
            "hormuz", "strait of hormuz", "persian gulf block",
            "hormuz closure", "gulf shipping", "tanker seiz",
            "naval blockade", "mine hormuz", "hormuz patrol",
            # Broader shipping/chokepoint
            "bab al-mandab", "bab el-mandeb", "red sea shipping",
            "suez disrupt", "shipping lane block", "maritime security",
            "tanker seized", "tanker hijack", "oil tanker attack",
            "shipping insurance", "war risk premium",
            # Houthi shipping attacks (major oil flow impact)
            "houthi ship", "houthi tanker", "houthi cargo",
            "houthi red sea", "houthi shipping", "houthi maritime",
            "shipping reroute", "cape of good hope reroute",
        ],
        "boost_words": [
            "iran", "irgc navy", "tanker", "shipping lane",
            "oil flow", "choke point", "houthi", "yemen",
            "us navy", "escort", "mine", "blockade",
            "insurance cost", "freight rate",
        ],
        "exclude": [],
    },

    # ── DEFENSE SPENDING ───────────────────────────────────────
    "defense_spend": {
        "must_contain": [
            "defense budget", "defence budget", "military spend",
            "defense procurement", "arms deal", "weapons order",
            "defense contract", "defense allocat",
            "military moderniz", "rearm", "arms race",
            # Specific country defense moves
            "india defense", "india defence", "nato spend",
            "european rearm", "germany defense", "japan defense",
            "south korea defense", "australia defense",
            "saudi arms", "uae arms", "gulf arms",
            # Specific platforms / deals
            "fighter jet order", "missile defense order",
            "submarine deal", "tank order", "drone order",
            "hal order", "tejas order", "rafale deal",
            "f-35 deal", "s-400", "patriot missile",
        ],
        "boost_words": [
            "india", "nato", "billion", "increase", "boost",
            "record", "approve", "parliament", "gdp",
            "2%", "3%", "unprecedented", "emergency",
        ],
        "exclude": ["cut defense", "reduce military", "peace dividend"],
    },

    # ── LEADER THREATS (expanded from trump_threat) ────────────
    # Covers ALL key leaders whose statements move markets
    "trump_threat": {
        "must_contain": [
            # Trump / US
            "trump iran", "trump threat", "trump warn",
            "trump sanction", "trump tariff", "trump oil",
            "trump military", "trump strike", "trump order",
            "trump ultimatum", "trump demand", "trump deploy",
            "trump 48 hour", "trump deadline", "white house warn",
            "pentagon warn", "us ultimatum",
            # Netanyahu / Israel leadership
            "netanyahu threat", "netanyahu warn", "netanyahu vow",
            "netanyahu destroy", "netanyahu iron fist",
            "gallant warn", "gallant threat", "katz ultimatum",
            "israel vow", "israel threat", "israel promise",
            # Khamenei / Iran leadership
            "khamenei threat", "khamenei warn", "khamenei vow",
            "khamenei death", "khamenei destroy", "khamenei revenge",
            "iran supreme leader", "iran vow", "iran promise revenge",
            "irgc commander", "irgc threat", "irgc warn",
            # Houthi leadership
            "houthi leader", "houthi threat", "houthi warn",
            "houthi vow", "abdulmalik", "ansar allah leader",
            "houthi escalat", "houthi expand",
            # Putin / Russia
            "putin iran", "putin warn", "putin threat",
            "putin oil", "russia warn", "russia threat",
            "russia deploy", "lavrov warn", "lavrov threat",
            # Xi / China
            "xi warn", "xi iran", "china warn", "china threat",
            "china deploy", "china navy", "china red line",
            "wang yi warn", "beijing warn",
            # Erdogan / Turkey
            "erdogan warn", "erdogan threat", "turkey warn",
            "erdogan nato", "turkey escalat",
            # MBS / Saudi
            "mbs warn", "saudi warn", "saudi threat",
            "saudi oil weapon", "saudi cut", "saudi red line",
            "opec weapon",
            # Regional leaders
            "modi warn", "india warn", "macron warn",
            "un warn", "guterres warn",
            # Generic leader threat patterns
            "irreversible damage", "irreversible", "point of no return",
            "nuclear option", "last warning", "final warning",
            "cross red line", "consequences", "unacceptable",
            "will not tolerate", "unprecedented response",
            "will not stop", "no mercy", "total destruction",
            "wipe out", "eliminate", "obliterate",
        ],
        "boost_words": [
            "executive order", "white house", "maximum pressure",
            "tweet", "truth social", "pentagon", "kremlin",
            "state media", "press conference", "un address",
            "emergency session", "security council",
            "nuclear", "existential", "annihilat",
        ],
        "exclude": ["trump peace", "trump deal sign", "netanyahu peace", "khamenei accept"],
    },

    # ── DIPLOMACY ──────────────────────────────────────────────
    "diplomacy": {
        "must_contain": [
            "diplomacy", "diplomatic", "talks", "negotiat",
            "peace talk", "summit", "un resolution",
            "mediator", "envoy", "bilateral",
            # Specific diplomatic actors
            "un security council", "un general assembly",
            "swiss mediat", "oman channel", "qatar mediat",
            "turkey mediat", "china mediat", "india mediat",
            "back channel", "secret talks", "indirect talks",
            # Leadership diplomatic signals
            "xi call", "putin call", "modi call",
            "macron call", "erdogan propos", "mbs propos",
            "guterres appeal", "pope appeal",
            "willing to talk", "open to negotiat",
            "preconditions met", "framework agreed",
        ],
        "boost_words": [
            "breakthrough", "progress", "agree", "framework",
            "roadmap", "confidence building", "historic",
            "first time", "direct contact", "phone call",
            "visit", "handshake", "constructive",
        ],
        "exclude": ["talks fail", "collapse", "walk out", "stalled", "reject"],
    },

    # ── DOMESTIC REGULATORY / POLICY ───────────────────────────
    "rbi_policy": {
        "must_contain": [
            "rbi policy", "rbi rate", "rbi norm", "rbi circular",
            "rbi guideline", "rbi regulation", "rbi directive",
            "repo rate", "reverse repo", "crr cut", "crr hike",
            "slr change", "monetary policy", "mpc meeting",
            "rbi governor", "das announce", "rbi liquidity",
            "rbi macro-prudential", "rbi npa", "rbi capital",
            "priority sector lending", "rbi digital",
        ],
        "boost_words": [
            "rbi", "reserve bank", "monetary", "interest rate",
            "liquidity", "credit growth", "banking sector",
            "nbfc", "microfinance", "housing finance",
        ],
        "exclude": [],
    },

    "nbfc_reform": {
        "must_contain": [
            "nbfc regulation", "nbfc reform", "nbfc norm",
            "nbfc guideline", "nbfc capital", "nbfc npa",
            "housing finance regulation", "microfinance norm",
            "psu nbfc", "nbfc lending", "nbfc liquidity",
            "mudra loan", "nbfc license", "nbfc merger",
            "gold loan norm", "nbfc stress test",
        ],
        "boost_words": [
            "nbfc", "hudco", "pfc", "rec", "ireda", "lic housing",
            "bajaj finance", "manappuram", "muthoot", "shriram",
        ],
        "exclude": [],
    },

    "ev_policy": {
        "must_contain": [
            "ev policy", "ev subsid", "electric vehicle norm",
            "ev incentive", "fame scheme", "fame subsid",
            "ev mandate", "battery swap", "charging infrastructure",
            "ev adoption", "emission norm", "bharat stage",
            "green hydrogen", "ev manufacturing", "pli auto",
            "pli battery", "acc battery", "ev tax",
        ],
        "boost_words": [
            "electric vehicle", "ev", "tata motors", "maruti ev",
            "mahindra ev", "ola electric", "ather", "bajaj auto",
            "hero electric", "lithium", "battery",
        ],
        "exclude": [],
    },

    "tax_reform": {
        "must_contain": [
            "gst change", "gst rate", "gst reform", "gst council",
            "income tax", "corporate tax", "tax cut", "tax hike",
            "tax relief", "tax exemption", "customs duty",
            "import duty", "export duty", "budget announce",
            "fiscal deficit", "disinvestment", "privatisation",
            "windfall tax", "capital gains tax", "stt change",
            "securities transaction tax", "stamp duty",
        ],
        "boost_words": [
            "budget", "finance minister", "sitharaman", "gst",
            "tax", "fiscal", "revenue", "deficit",
        ],
        "exclude": [],
    },

    "infra_capex": {
        "must_contain": [
            "infra spend", "capital expenditure", "capex push",
            "highway project", "rail project", "metro project",
            "smart city", "sagarmala", "bharatmala",
            "national infrastructure pipeline", "nip",
            "government capex", "public invest", "pli scheme",
            "semiconductor fab", "defence corridor",
            "industrial corridor", "logistics park",
        ],
        "boost_words": [
            "infrastructure", "capex", "government spend",
            "l&t", "ntpc", "nhpc", "ircon", "rvnl",
            "cement", "steel", "construction",
        ],
        "exclude": [],
    },

    "sebi_regulation": {
        "must_contain": [
            "sebi regulation", "sebi norm", "sebi circular",
            "sebi guideline", "sebi mandate", "sebi reform",
            "sebi penalty", "sebi ban", "insider trading sebi",
            "fpi regulation", "dii regulation", "mutual fund norm",
            "market structure", "t+0 settlement", "sebi chairperson",
            "sebi board meeting",
        ],
        "boost_words": [
            "sebi", "market regulator", "capital market",
            "mutual fund", "fpi", "promoter holding",
        ],
        "exclude": [],
    },
}

# ---------------------------------------------------------------------------
# RSS fetching
# ---------------------------------------------------------------------------
RSS_TIMEOUT = 15  # seconds


def fetch_rss_news(
    feeds: list[str] = NEWS_RSS_FEEDS,
    keywords: list[str] = NEWS_KEYWORDS,
) -> list[dict[str, Any]]:
    """Fetch latest items from RSS feeds matching any keyword.

    Returns list of dicts with keys:
        title, summary, source, published_at, url, raw_text
    Only items published within the last 6 hours are returned.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=6)
    results: list[dict[str, Any]] = []

    for feed_url in feeds:
        try:
            resp = requests.get(feed_url, timeout=RSS_TIMEOUT)
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.warning("RSS fetch failed for %s: %s", feed_url, exc)
            continue

        items = _parse_rss_items(resp.text, feed_url)
        for item in items:
            # Recency filter
            if item.get("published_at") and item["published_at"] < cutoff:
                continue

            raw = f"{item.get('title', '')} {item.get('summary', '')}".lower()
            if any(kw.lower() in raw for kw in keywords):
                item["raw_text"] = raw
                results.append(item)

    logger.info("RSS scan: %d matching items from %d feeds", len(results), len(feeds))
    return results


def _parse_rss_items(xml_text: str, source_url: str) -> list[dict[str, Any]]:
    """Parse RSS XML into list of item dicts."""
    items: list[dict[str, Any]] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        # Fallback to BeautifulSoup for malformed XML
        return _parse_rss_bs4(xml_text, source_url)

    # Standard RSS 2.0
    for item_el in root.iter("item"):
        items.append(_extract_rss_item(item_el, source_url))

    # Atom feeds
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    for entry in root.iter("{http://www.w3.org/2005/Atom}entry"):
        title = _text(entry, "atom:title", ns) or _text(entry, "{http://www.w3.org/2005/Atom}title")
        summary = _text(entry, "atom:summary", ns) or _text(entry, "{http://www.w3.org/2005/Atom}summary") or ""
        link_el = entry.find("{http://www.w3.org/2005/Atom}link")
        url = link_el.get("href", "") if link_el is not None else ""
        published = _text(entry, "{http://www.w3.org/2005/Atom}published") or _text(entry, "{http://www.w3.org/2005/Atom}updated") or ""
        items.append({
            "title": title or "",
            "summary": summary,
            "source": source_url,
            "published_at": _parse_date(published),
            "url": url,
        })

    return items


def _extract_rss_item(item_el: ET.Element, source_url: str) -> dict[str, Any]:
    title = _text(item_el, "title") or ""
    summary = _text(item_el, "description") or ""
    # Strip HTML from description
    if "<" in summary:
        summary = BeautifulSoup(summary, "html.parser").get_text(separator=" ", strip=True)
    link = _text(item_el, "link") or ""
    pub_date = _text(item_el, "pubDate") or ""
    return {
        "title": title,
        "summary": summary,
        "source": source_url,
        "published_at": _parse_date(pub_date),
        "url": link,
    }


def _parse_rss_bs4(xml_text: str, source_url: str) -> list[dict[str, Any]]:
    """Fallback parser using BeautifulSoup for malformed XML."""
    soup = BeautifulSoup(xml_text, "html.parser")
    items: list[dict[str, Any]] = []
    for item_tag in soup.find_all("item"):
        title = item_tag.find("title")
        desc = item_tag.find("description")
        link = item_tag.find("link")
        pub = item_tag.find("pubdate") or item_tag.find("pubDate")
        items.append({
            "title": title.get_text(strip=True) if title else "",
            "summary": desc.get_text(strip=True) if desc else "",
            "source": source_url,
            "published_at": _parse_date(pub.get_text(strip=True) if pub else ""),
            "url": link.get_text(strip=True) if link else "",
        })
    return items


def _text(el: ET.Element, tag: str, ns: dict | None = None) -> str | None:
    child = el.find(tag, ns) if ns else el.find(tag)
    if child is not None and child.text:
        return child.text.strip()
    return None


def _parse_date(date_str: str) -> Optional[datetime]:
    """Best-effort date parsing for RSS date strings."""
    if not date_str:
        return None
    from email.utils import parsedate_to_datetime
    try:
        return parsedate_to_datetime(date_str)
    except Exception:
        pass
    for fmt in (
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%d %H:%M:%S",
    ):
        try:
            return datetime.strptime(date_str, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    logger.debug("Could not parse date: %s", date_str)
    return None


# ---------------------------------------------------------------------------
# Google News RSS fallback
# ---------------------------------------------------------------------------

def fetch_google_news_rss(query: str = "iran war oil") -> list[dict[str, Any]]:
    """Fetch from Google News RSS as a fallback source.

    URL format:
        https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en
    """
    encoded_query = requests.utils.quote(query)
    url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-US&gl=US&ceid=US:en"
    try:
        resp = requests.get(url, timeout=RSS_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("Google News RSS fetch failed: %s", exc)
        return []

    items = _parse_rss_items(resp.text, "google_news")
    cutoff = datetime.now(timezone.utc) - timedelta(hours=6)
    recent = [i for i in items if not i.get("published_at") or i["published_at"] >= cutoff]
    logger.info("Google News RSS: %d recent items for query '%s'", len(recent), query)
    return recent


# ---------------------------------------------------------------------------
# NewsAPI (optional)
# ---------------------------------------------------------------------------

def fetch_newsapi(
    query: str,
    api_key: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Fetch headlines from newsapi.org (free tier: 100 req/day).

    Returns list of dicts matching the standard item schema.
    """
    key = api_key or NEWSAPI_KEY
    if not key:
        logger.debug("NEWSAPI_KEY not set -- skipping NewsAPI fetch")
        return []

    url = "https://newsapi.org/v2/everything"
    params = {
        "q": query,
        "sortBy": "publishedAt",
        "pageSize": 20,
        "apiKey": key,
    }
    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        logger.warning("NewsAPI fetch failed: %s", exc)
        return []

    results: list[dict[str, Any]] = []
    for article in data.get("articles", []):
        results.append({
            "title": article.get("title", ""),
            "summary": article.get("description", "") or "",
            "source": article.get("source", {}).get("name", "newsapi"),
            "published_at": _parse_date(article.get("publishedAt", "")),
            "url": article.get("url", ""),
            "raw_text": f"{article.get('title', '')} {article.get('description', '')}".lower(),
        })
    logger.info("NewsAPI: %d articles for query '%s'", len(results), query)
    return results


# ---------------------------------------------------------------------------
# Event classification -- Tier 1: keyword rules
# ---------------------------------------------------------------------------

def classify_event_keywords(
    headline: str,
    summary: str,
) -> tuple[Optional[str], float]:
    """Tier 1: Rule-based keyword classification.

    Returns (category, confidence_score).
    The highest-scoring category that passes the must_contain gate wins.
    Score = base (0.5) + 0.1 per boost-word match, capped at 1.0.
    Returns (None, 0.0) if no category matches.
    """
    text = f"{headline} {summary}".lower()
    best_category: Optional[str] = None
    best_score: float = 0.0

    # Priority categories — specific event types should beat generic escalation
    PRIORITY_BONUS = {
        "hormuz": 0.15, "sanctions": 0.10, "ceasefire": 0.10,
        "trump_threat": 0.10, "defense_spend": 0.10,
        "oil_positive": 0.05, "oil_negative": 0.05,
        "rbi_policy": 0.15, "nbfc_reform": 0.10, "ev_policy": 0.10,
        "tax_reform": 0.15, "infra_capex": 0.10, "sebi_regulation": 0.10,
    }

    for category, rules in KEYWORD_RULES.items():
        # Exclusion gate
        if any(excl in text for excl in rules.get("exclude", [])):
            continue

        # Must-contain gate
        if not any(kw in text for kw in rules["must_contain"]):
            continue

        # Score
        base = 0.5
        n_must = sum(1 for kw in rules["must_contain"] if kw in text)
        n_boost = sum(1 for bw in rules.get("boost_words", []) if bw in text)
        priority = PRIORITY_BONUS.get(category, 0.0)
        score = min(base + (n_must - 1) * 0.05 + n_boost * 0.1 + priority, 1.0)

        if score > best_score:
            best_score = score
            best_category = category

    return best_category, best_score


# ---------------------------------------------------------------------------
# Event classification -- Tier 2: Claude API
# ---------------------------------------------------------------------------

def classify_event_claude(
    headline: str,
    summary: str,
    api_key: Optional[str] = None,
) -> tuple[Optional[str], float]:
    """Tier 2: Call Claude API for ambiguous cases (confidence < 0.6).

    Uses a direct POST to the Anthropic messages API.
    Returns (category, confidence_score) or (None, 0.0) on failure.
    """
    # Use Gemini during shadow period (free tier), fall back to Claude if GEMINI not set
    gemini_key = GEMINI_API_KEY
    if not gemini_key:
        logger.warning("GEMINI_API_KEY not set -- cannot use Tier 2 classification")
        return None, 0.0

    categories = ", ".join(EVENT_TAXONOMY.keys())
    prompt = (
        f"You are a geopolitical event classifier for a financial research system.\n"
        f"Classify the following news headline + summary into EXACTLY ONE of these categories:\n"
        f"{categories}\n\n"
        f"Headline: {headline}\n"
        f"Summary: {summary}\n\n"
        f"Respond with ONLY a JSON object: {{\"category\": \"...\", \"confidence\": 0.XX}}\n"
        f"If none fit, use {{\"category\": null, \"confidence\": 0.0}}"
    )

    try:
        resp = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini_key}",
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "maxOutputTokens": 200,
                    "temperature": 0,
                    "responseMimeType": "application/json",
                    "thinkingConfig": {"thinkingBudget": 0},
                },
            },
            timeout=20,
        )
        resp.raise_for_status()
        result = resp.json()
        candidates = result.get("candidates", [])
        if not candidates:
            return None, 0.0
        parts = candidates[0].get("content", {}).get("parts", [])
        content = parts[0].get("text", "").strip() if parts else ""
        parsed = json.loads(content)
        cat = parsed.get("category")
        conf = float(parsed.get("confidence", 0.0))
        if cat and cat in EVENT_TAXONOMY:
            logger.info("Claude classified as '%s' (%.2f)", cat, conf)
            return cat, conf
        return None, 0.0
    except Exception as exc:
        logger.warning("Claude classification failed: %s", exc)
        return None, 0.0


# ---------------------------------------------------------------------------
# Seen-events persistence
# ---------------------------------------------------------------------------

def load_seen_events() -> set[str]:
    """Load set of previously seen event URLs from seen_events.json."""
    if not SEEN_FILE.exists():
        return set()
    try:
        data = json.loads(SEEN_FILE.read_text(encoding="utf-8"))
        return set(data)
    except (json.JSONDecodeError, TypeError):
        logger.warning("Corrupt seen_events.json -- resetting")
        return set()


def save_seen_events(seen: set[str]) -> None:
    """Persist seen event URLs to disk."""
    SEEN_FILE.write_text(json.dumps(sorted(seen), indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Main detection pipeline
# ---------------------------------------------------------------------------

def detect_new_events() -> list[dict[str, Any]]:
    """Main detection pipeline.

    1. Fetch from all RSS feeds + Google News fallback
    2. Filter by keywords (done inside fetch_rss_news)
    3. Deduplicate against seen events
    4. Classify each new event (Tier 1, then Tier 2 if low confidence)
    5. Save to seen events
    6. Return list of classified events with confidence scores
    """
    seen = load_seen_events()

    # Gather items from all sources
    items = fetch_rss_news()
    items.extend(fetch_google_news_rss())

    # Optional NewsAPI
    if NEWSAPI_KEY:
        items.extend(fetch_newsapi("iran israel oil war"))

    classified_events: list[dict[str, Any]] = []

    for item in items:
        url = item.get("url", "")
        if not url or url in seen:
            continue
        seen.add(url)

        headline = item.get("title", "")
        summary = item.get("summary", "")

        # Tier 1 classification
        category, confidence = classify_event_keywords(headline, summary)

        # Tier 2 fallback for low confidence — uses Gemini (free) during shadow period
        if confidence < SIGNAL_CONFIDENCE_THRESHOLD and GEMINI_API_KEY:
            cat2, conf2 = classify_event_claude(headline, summary)
            if conf2 > confidence:
                category, confidence = cat2, conf2

        if category is None:
            logger.debug("Unclassifiable event: %s", headline[:80])
            continue

        classified_events.append({
            "headline": headline,
            "summary": summary,
            "source": item.get("source", ""),
            "url": url,
            "published_at": item.get("published_at", datetime.now(timezone.utc)).isoformat()
            if isinstance(item.get("published_at"), datetime)
            else str(item.get("published_at", "")),
            "category": category,
            "confidence": round(confidence, 3),
        })
        logger.info(
            "New event: [%s] (%.2f) %s", category, confidence, headline[:60]
        )

    save_seen_events(seen)
    logger.info("Detection complete: %d new classified events", len(classified_events))
    return classified_events


# ---------------------------------------------------------------------------
# Pattern lookup (backtest results)
# ---------------------------------------------------------------------------

PATTERN_LOOKUP_FILE = DATA_DIR / "pattern_lookup.json"


def load_pattern_lookup() -> dict[str, Any]:
    """Load pattern_lookup.json produced by the backtester.

    Returns the spread_backtests section which has structure:
    {
        "Upstream vs Downstream": {
            "escalation": {"hit_rate": 0.72, "1d_spread_median": 1.8, "n": 15},
            ...
        },
        ...
    }
    """
    if not PATTERN_LOOKUP_FILE.exists():
        logger.warning("pattern_lookup.json not found -- signals will lack backtest data")
        return {}
    try:
        raw = json.loads(PATTERN_LOOKUP_FILE.read_text(encoding="utf-8"))
        # The backtest output nests data under "spread_backtests" key
        return raw.get("spread_backtests", raw)
    except (json.JSONDecodeError, TypeError) as exc:
        logger.error("Failed to load pattern_lookup.json: %s", exc)
        return {}


# ---------------------------------------------------------------------------
# Price fetching helper
# ---------------------------------------------------------------------------

def _fetch_current_prices(tickers: list[str]) -> dict[str, float]:
    """Fetch current prices for signal generation using yfinance.

    NOTE: This is yfinance-only (used at signal generation time for entry prices).
    For live P&L monitoring, signal_tracker.fetch_current_prices() is used,
    which has EODHD as primary source with yfinance fallback.
    """
    try:
        import yfinance as yf
    except ImportError:
        logger.error("yfinance not installed -- cannot fetch prices")
        return {}

    prices: dict[str, float] = {}
    for ticker in tickers:
        try:
            data = yf.Ticker(ticker).fast_info
            price = data.get("lastPrice") or data.get("previousClose")
            if price:
                prices[ticker] = round(float(price), 2)
        except Exception as exc:
            logger.warning("Price fetch failed for %s: %s", ticker, exc)
    return prices


# ---------------------------------------------------------------------------
# Signal generation
# ---------------------------------------------------------------------------

_signal_counter: int = 0


def generate_signal(
    event: dict[str, Any],
    pattern_lookup: dict[str, Any],
    current_prices: Optional[dict[str, float]] = None,
) -> Optional[dict[str, Any]]:
    """Generate a spread trade signal from a classified event.

    Gating criteria:
    - confidence >= SIGNAL_CONFIDENCE_THRESHOLD
    - historical hit_rate >= SIGNAL_HIT_RATE_THRESHOLD
    - n_precedents >= SIGNAL_MIN_PRECEDENTS

    Returns a signal dict or None if gates fail.
    """
    global _signal_counter

    category = event.get("category")
    confidence = event.get("confidence", 0.0)

    if confidence < SIGNAL_CONFIDENCE_THRESHOLD:
        logger.debug("Signal gated: confidence %.2f < %.2f", confidence, SIGNAL_CONFIDENCE_THRESHOLD)
        return None

    # Find matching spread pairs
    matching_pairs = [
        pair for pair in INDIA_SPREAD_PAIRS
        if category in pair.get("triggers", [])
    ]
    if not matching_pairs:
        logger.debug("No spread pairs triggered by category '%s'", category)
        return None

    # Pick the best pair based on backtest data
    best_pair = None
    best_stats: dict[str, Any] = {}

    for pair in matching_pairs:
        pair_name = pair["name"]
        stats = pattern_lookup.get(pair_name, {}).get(category, {})
        hit_rate = stats.get("hit_rate", 0.0)
        n_events = stats.get("n", stats.get("n_events", 0))

        if hit_rate >= SIGNAL_HIT_RATE_THRESHOLD and n_events >= SIGNAL_MIN_PRECEDENTS:
            if not best_pair or hit_rate > best_stats.get("hit_rate", 0):
                best_pair = pair
                best_stats = stats

    # If no pair passes backtest gates, use the first match and flag it unvalidated.
    # The subscriber sees "EXPLORING" tier — signal is sent but clearly labelled.
    backtest_validated = best_pair is not None
    if not best_pair:
        best_pair = matching_pairs[0]
        pair_name = best_pair["name"]
        best_stats = pattern_lookup.get(pair_name, {}).get(category, {})
        logger.info(
            "No validated pair for '%s' — using '%s' as EXPLORING (hit_rate=%.2f, n=%d)",
            category, pair_name,
            best_stats.get("hit_rate", 0),
            best_stats.get("n", best_stats.get("n_events", 0)),
        )
        # backtest_validated remains False — signal will be tagged EXPLORING

    # Gather tickers for price fetch
    long_names = best_pair["long"]
    short_names = best_pair["short"]
    all_tickers = []
    for name in long_names + short_names:
        stock_info = INDIA_SIGNAL_STOCKS.get(name, {})
        yf_ticker = stock_info.get("yf", "")
        if yf_ticker:
            all_tickers.append(yf_ticker)

    # Fetch prices if not provided
    if current_prices is None:
        current_prices = _fetch_current_prices(all_tickers)

    # Build legs
    def _build_leg(names: list[str]) -> list[dict[str, Any]]:
        leg = []
        weight = round(1.0 / max(len(names), 1), 4)
        for name in names:
            stock_info = INDIA_SIGNAL_STOCKS.get(name, {})
            yf_ticker = stock_info.get("yf", "")
            price = current_prices.get(yf_ticker, 0.0)
            leg.append({
                "ticker": name,
                "yf": yf_ticker,
                "price": price,
                "weight": weight,
            })
        return leg

    long_leg = _build_leg(long_names)
    short_leg = _build_leg(short_names)

    # Stop-loss levels
    stop_pct = SIGNAL_STOP_LOSS_PCT / 100.0
    stop_prices: dict[str, float] = {}
    for entry in long_leg:
        if entry["price"] > 0:
            stop_prices[entry["ticker"]] = round(entry["price"] * (1 - stop_pct), 2)
    for entry in short_leg:
        if entry["price"] > 0:
            stop_prices[entry["ticker"]] = round(entry["price"] * (1 + stop_pct), 2)

    # Signal ID
    _signal_counter += 1
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    signal_id = f"SIG-{today}-{_signal_counter:03d}"

    signal = {
        "signal_id": signal_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": {
            "headline": event.get("headline", ""),
            "category": category,
            "confidence": confidence,
            "source": event.get("source", ""),
            "url": event.get("url", ""),
        },
        "trade": {
            "spread_name": best_pair["name"],
            "long_leg": long_leg,
            "short_leg": short_leg,
            "expected_1d_spread": best_stats.get("1d_spread_median", best_stats.get("avg_1d_return", 0.0)),
            "historical_hit_rate": best_stats.get("hit_rate", 0.0),
            "n_precedents": best_stats.get("n", best_stats.get("n_events", 0)),
            "backtest_validated": backtest_validated,
        },
        "risk": {
            "stop_loss_pct": SIGNAL_STOP_LOSS_PCT,
            "stop_prices": stop_prices,
        },
        "status": "OPEN",
        "framing": "exploring_idea",
    }

    # Persist signal to disk
    signal_file = SIGNALS_DIR / f"{signal_id}.json"
    signal_file.write_text(json.dumps(signal, indent=2), encoding="utf-8")
    logger.info("Signal generated: %s (%s) -> %s", signal_id, category, best_pair["name"])

    return signal


# ---------------------------------------------------------------------------
# Multi-spread signal card (V2)
# ---------------------------------------------------------------------------

def generate_signal_card(
    event: dict[str, Any],
    pattern_lookup: dict[str, Any],
    current_prices: Optional[dict[str, float]] = None,
) -> Optional[dict[str, Any]]:
    """Generate a multi-spread signal card from a classified event.

    Instead of picking only the best spread, this returns ALL matching
    spreads with tier labels:
      - SIGNAL (🟢): hit_rate >= 0.65 AND n >= 3 → trade-worthy
      - EXPLORING (🟡): has backtest data but below gates → tracked for promotion
      - NO_DATA (⚪): no backtest for this category/spread combo

    Returns a signal card dict with all spreads, or None if confidence too low.
    """
    global _signal_counter

    category = event.get("category")
    confidence = event.get("confidence", 0.0)

    if confidence < SIGNAL_CONFIDENCE_THRESHOLD:
        logger.debug("Signal card gated: confidence %.2f < %.2f", confidence, SIGNAL_CONFIDENCE_THRESHOLD)
        return None

    # Find ALL matching spread pairs for this category
    matching_pairs = [
        pair for pair in INDIA_SPREAD_PAIRS
        if category in pair.get("triggers", [])
    ]
    if not matching_pairs:
        logger.debug("No spread pairs triggered by category '%s'", category)
        return None

    # Build legs helper
    def _build_leg(names: list[str], prices: dict[str, float]) -> list[dict[str, Any]]:
        leg = []
        weight = round(1.0 / max(len(names), 1), 4)
        for name in names:
            stock_info = INDIA_SIGNAL_STOCKS.get(name, {})
            yf_ticker = stock_info.get("yf", "")
            price = prices.get(yf_ticker, 0.0)
            leg.append({
                "ticker": name,
                "yf": yf_ticker,
                "price": price,
                "weight": weight,
            })
        return leg

    # Fetch prices if not provided
    if current_prices is None:
        all_tickers = []
        for pair in matching_pairs:
            for name in pair["long"] + pair["short"]:
                yf_ticker = INDIA_SIGNAL_STOCKS.get(name, {}).get("yf", "")
                if yf_ticker:
                    all_tickers.append(yf_ticker)
        current_prices = _fetch_current_prices(list(set(all_tickers)))

    # Build spread entries with tiers
    spread_entries: list[dict[str, Any]] = []
    has_any_signal_tier = False

    for pair in matching_pairs:
        pair_name = pair["name"]
        stats = pattern_lookup.get(pair_name, {}).get(category, {})
        hit_rate = stats.get("hit_rate", 0.0)
        n_events = stats.get("n", stats.get("n_events", 0))
        expected_spread = stats.get("1d_spread_median", stats.get("avg_1d_return", 0.0))

        # Determine tier
        if not stats:
            tier = TIER_NO_DATA
        elif hit_rate >= SIGNAL_HIT_RATE_THRESHOLD and n_events >= SIGNAL_MIN_PRECEDENTS:
            tier = TIER_SIGNAL
            has_any_signal_tier = True
        else:
            tier = TIER_EXPLORING

        long_leg = _build_leg(pair["long"], current_prices)
        short_leg = _build_leg(pair["short"], current_prices)

        # Stop-loss levels
        stop_pct = SIGNAL_STOP_LOSS_PCT / 100.0
        stop_prices: dict[str, float] = {}
        for entry in long_leg:
            if entry["price"] > 0:
                stop_prices[entry["ticker"]] = round(entry["price"] * (1 - stop_pct), 2)
        for entry in short_leg:
            if entry["price"] > 0:
                stop_prices[entry["ticker"]] = round(entry["price"] * (1 + stop_pct), 2)

        spread_entries.append({
            "spread_name": pair_name,
            "tier": tier,
            "long_leg": long_leg,
            "short_leg": short_leg,
            "hit_rate": hit_rate,
            "n_precedents": n_events,
            "expected_1d_spread": expected_spread,
            "stop_prices": stop_prices,
        })

    # Sort by tier priority (SIGNAL first, then EXPLORING, then NO_DATA),
    # then by hit_rate descending
    tier_order = {TIER_SIGNAL: 0, TIER_EXPLORING: 1, TIER_NO_DATA: 2}
    spread_entries.sort(key=lambda s: (tier_order.get(s["tier"], 3), -s["hit_rate"]))

    # Signal ID
    _signal_counter += 1
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    signal_id = f"SIG-{today}-{_signal_counter:03d}"

    signal_card = {
        "signal_id": signal_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": {
            "headline": event.get("headline", ""),
            "category": category,
            "confidence": confidence,
            "source": event.get("source", ""),
            "url": event.get("url", ""),
        },
        "spreads": spread_entries,
        "has_signal_tier": has_any_signal_tier,
        "risk": {
            "stop_loss_pct": SIGNAL_STOP_LOSS_PCT,
        },
        "status": "OPEN",
    }

    # Persist signal card to disk
    signal_file = SIGNALS_DIR / f"{signal_id}.json"
    signal_file.write_text(json.dumps(signal_card, indent=2), encoding="utf-8")
    logger.info(
        "Signal card generated: %s (%s) -> %d spreads (%d SIGNAL, %d EXPLORING)",
        signal_id, category, len(spread_entries),
        sum(1 for s in spread_entries if s["tier"] == TIER_SIGNAL),
        sum(1 for s in spread_entries if s["tier"] == TIER_EXPLORING),
    )

    return signal_card


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_signal_check() -> list[dict[str, Any]]:
    """Main entry: detect events -> generate multi-spread signal cards.

    Intended to be called every 30 minutes during market hours.
    Returns list of signal cards, each containing ALL matching spreads with tiers.
    """
    logger.info("=== Signal check started ===")

    events = detect_new_events()
    if not events:
        logger.info("No new events detected")
        return []

    pattern_lookup = load_pattern_lookup()

    # Pre-fetch all prices in one batch
    all_tickers: set[str] = set()
    for pair in INDIA_SPREAD_PAIRS:
        for name in pair["long"] + pair["short"]:
            yf_ticker = INDIA_SIGNAL_STOCKS.get(name, {}).get("yf", "")
            if yf_ticker:
                all_tickers.add(yf_ticker)

    current_prices = _fetch_current_prices(list(all_tickers))

    signals: list[dict[str, Any]] = []
    for event in events:
        # V2: generate multi-spread signal card instead of single signal
        signal_card = generate_signal_card(event, pattern_lookup, current_prices)
        if signal_card:
            signals.append(signal_card)

    logger.info(
        "=== Signal check complete: %d events -> %d signal cards ===",
        len(events), len(signals),
    )
    return signals


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    signals = run_signal_check()
    for sig in signals:
        print(json.dumps(sig, indent=2))
