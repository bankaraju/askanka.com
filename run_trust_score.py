"""
OPUS ANKA — ANKA Trust Score Scorer

Takes collected data from run_research.py and produces:
1. Structured financials analysis (from Screener data)
2. Management narrative extraction (from annual report PDFs via Claude)
3. Promise-vs-Delivery scoring
4. Final ANKA Trust Score score

Usage:
    python run_trust_score.py HAL
    python run_trust_score.py HDFCBANK

Requires: ANTHROPIC_API_KEY in environment or config/.env
"""

import json
import sys
import os
from pathlib import Path
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / "config" / ".env")

IST = timezone(timedelta(hours=5, minutes=30))
ARTIFACTS = Path(__file__).parent / "artifacts"

# ── LLM Provider (Gemini default, Claude optional) ──────────────────
#
# Cost comparison for 213 annual reports:
#   Claude Sonnet 4: ~$230 (too expensive)
#   Claude Haiku 4.5: ~$70
#   Gemini 2.5 Flash (paid): ~$6
#   Gemini 2.5 Flash (FREE TIER): $0 for up to ~50 stocks/day
#
# Set ANKA_LLM_PROVIDER=claude to fall back to Claude.

# Load Gemini key from askanka.com pipeline .env as well
_ASKANKA_ENV = Path("C:/Users/Claude_Anka/Documents/askanka.com/pipeline/.env")
if _ASKANKA_ENV.exists():
    load_dotenv(_ASKANKA_ENV)

LLM_PROVIDER = os.getenv("ANKA_LLM_PROVIDER", "gemini")
EXTRACTION_MODEL = os.getenv("ANKA_EXTRACTION_MODEL", "claude-haiku-4-5-20251001")
SCORING_MODEL = os.getenv("ANKA_SCORING_MODEL", "claude-sonnet-4-20250514")


def check_api_credit() -> bool:
    """Pre-flight check: verify LLM API is reachable before starting batch."""
    if LLM_PROVIDER == "gemini":
        return _check_gemini()
    return _check_claude_credit()


def _check_gemini() -> bool:
    import requests
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        print("ERROR: GEMINI_API_KEY not set")
        return False
    try:
        resp = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={key}",
            json={"contents": [{"parts": [{"text": "hi"}]}], "generationConfig": {"maxOutputTokens": 5}},
            timeout=10,
        )
        return resp.status_code == 200
    except Exception as e:
        print(f"ERROR: Gemini check failed: {e}")
        return False


def _check_claude_credit() -> bool:
    import anthropic
    try:
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=10,
            messages=[{"role": "user", "content": "hi"}],
        )
        return True
    except anthropic.BadRequestError as e:
        if "credit balance" in str(e).lower():
            print("ERROR: Anthropic API credit balance too low")
            return False
        raise
    except Exception as e:
        print(f"ERROR: Claude check failed: {e}")
        return False


def call_llm(prompt: str, max_tokens: int = 4096, role: str = "extraction") -> str:
    """Call the configured LLM. Role: 'extraction' (Haiku/Flash) or 'scoring' (Sonnet/Flash)."""
    if LLM_PROVIDER == "gemini":
        return _call_gemini(prompt, max_tokens)
    return _call_claude(prompt, max_tokens, role)


def _call_gemini(prompt: str, max_tokens: int = 8192) -> str:
    """Call Gemini 2.5 Flash with thinking disabled.

    Gemini 2.5 Flash reserves tokens for 'thinking' by default which eats the output
    budget. We disable it since extraction doesn't need chain-of-thought reasoning —
    we just want it to pattern-match from the example we gave.
    """
    import requests
    import time

    key = os.getenv("GEMINI_API_KEY")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={key}"

    for attempt in range(3):
        try:
            resp = requests.post(
                url,
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "maxOutputTokens": max_tokens,
                        "temperature": 0,
                        "responseMimeType": "application/json",
                        "thinkingConfig": {"thinkingBudget": 0},
                    },
                },
                timeout=180,
            )
            if resp.status_code == 429:
                time.sleep(15 * (attempt + 1))
                continue
            resp.raise_for_status()
            result = resp.json()
            candidates = result.get("candidates", [])
            if not candidates:
                raise ValueError(f"No candidates: {result}")
            parts = candidates[0].get("content", {}).get("parts", [])
            if not parts:
                raise ValueError(f"No parts: {candidates[0]}")
            return parts[0].get("text", "")
        except requests.exceptions.HTTPError:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError("Gemini call failed after 3 attempts")


def _call_claude(prompt: str, max_tokens: int = 4096, role: str = "extraction") -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    model = EXTRACTION_MODEL if role == "extraction" else SCORING_MODEL
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


# Backwards-compatible alias for scoring calls
def call_claude(prompt: str, max_tokens: int = 4096, model: str = None) -> str:
    return call_llm(prompt, max_tokens, role="scoring")


def extract_pdf_text(pdf_path: Path) -> dict[str, str]:
    """Extract text from PDF and split into sections.

    Returns dict of section_name → text for key sections:
    MD&A, Chairman's letter, Directors' report, Risk factors, Financial highlights.
    """
    import pymupdf
    sections = {"_combined": "", "_total_pages": "0", "_key_pages": "0", "_sections_found": []}
    try:
        doc = pymupdf.open(str(pdf_path))
    except Exception as e:
        print(f"      PDF open failed: {e}")
        return sections

    total_pages = len(doc)
    if total_pages == 0:
        doc.close()
        print(f"      PDF has 0 pages (corrupted)")
        return sections

    # First pass: extract all text and find section boundaries
    # Uses multiple detection strategies — explicit section titles AND content keywords
    all_text = []
    section_markers = {}
    keywords = {
        "mda": [
            "management discussion", "management's discussion", "md&a",
            "management discussion and analysis",
        ],
        "chairman": [
            "chairman's message", "chairman's letter", "chairman's statement",
            "message from chairman", "chairman's statement to", "chairman & managing director",
            "dear shareholders", "dear members",  # Common opening
        ],
        "directors": [
            "directors' report", "directors report", "board's report",
            "report of the directors", "to the members of",
        ],
        "risk": [
            "risk management", "risk factors", "enterprise risk",
            "key risks", "risk assessment", "principal risks",
        ],
        "overview": [
            "strategic overview", "business overview", "operational review",
            "company overview", "business segments", "business performance",
            "segment performance", "review of operations",
        ],
        "financial_highlights": [
            "financial highlights", "financial performance", "performance highlights",
            "financial review", "key financial indicators", "summary of financials",
        ],
        "outlook": [
            "outlook", "way forward", "future outlook", "looking ahead",
            "future prospects", "forward looking", "strategic priorities",
        ],
        "order_book": [
            "order book", "order position", "orders received",
            "order inflow", "order intake", "contract pipeline",
        ],
        "guidance": [
            "we expect", "we target", "we aim", "we plan to",
            "our guidance", "targeted growth", "will deliver",
            "will achieve", "to achieve by",
        ],
        "strategy": [
            "strategic initiatives", "key initiatives", "growth strategy",
            "strategic focus", "strategic pillars", "growth pillars",
        ],
    }

    # Track ALL pages where each section appears (not just first hit)
    section_hits = {k: [] for k in keywords.keys()}
    for i, page in enumerate(doc):
        text = page.get_text()
        all_text.append(text)
        text_lower = text.lower()
        for section, kws in keywords.items():
            if any(kw in text_lower for kw in kws):
                section_hits[section].append(i)

    # section_markers: first hit for each section (for backwards compat)
    section_markers = {k: v[0] for k, v in section_hits.items() if v}

    doc.close()

    # Second pass: extract sections with generous context
    sections = {}
    for section, start_page in section_markers.items():
        end_page = min(start_page + 20, total_pages)
        section_text = "\n".join(all_text[start_page:end_page])
        sections[section] = section_text

    # Collect ALL pages where any section keyword was found, plus N pages of context
    all_key_pages = set()
    CONTEXT_RADIUS = 5  # Pages of context after each hit
    for hits in section_hits.values():
        for hit_page in hits:
            for p in range(hit_page, min(hit_page + CONTEXT_RADIUS, total_pages)):
                all_key_pages.add(p)

    # Build the page set smartly:
    # 1. Always include pages 1-15 (chairman letter, highlights — start of AR)
    # 2. Include FIRST hit of each section + 3 pages context (not all hits)
    # 3. Cap at 80 pages to keep context window manageable
    priority_pages = set(range(0, min(15, total_pages)))  # Early sections

    # For each section, use first hit + next 3 pages (not all recurrences)
    for section, start_page in section_markers.items():
        for p in range(start_page, min(start_page + 4, total_pages)):
            priority_pages.add(p)

    # If still low, add some fallback coverage
    if len(priority_pages) < 40:
        fallback = set(range(min(15, total_pages), min(60, total_pages)))
        priority_pages.update(fallback)

    # Cap at 80 pages to prevent massive inputs
    priority_pages = set(sorted(priority_pages)[:80])
    all_key_pages = priority_pages

    if all_key_pages:
        combined = "\n\n--- PAGE BREAK ---\n\n".join(
            all_text[p] for p in sorted(all_key_pages) if p < len(all_text)
        )
    else:
        combined = "\n\n--- PAGE BREAK ---\n\n".join(
            all_text[p] for p in range(min(15, total_pages), min(60, total_pages))
        )

    sections["_combined"] = combined
    sections["_total_pages"] = str(total_pages)
    sections["_key_pages"] = str(len(all_key_pages))
    sections["_sections_found"] = list(section_markers.keys())

    return sections


def call_claude_with_ar_text(text: str, prompt: str, max_tokens: int = 16384) -> str:
    """Call the LLM with extracted annual report text.

    Gemini 2.5 Flash is free on free tier, so we send full text (up to 200K chars)
    and request large output tokens. No penalty for being generous.
    """
    # Only truncate if truly excessive (Gemini handles 1M+ context)
    MAX_CHARS = 200_000
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS] + "\n\n[TRUNCATED]"

    full_prompt = f"Annual report text:\n\n{text}\n\n---\n\n{prompt}"
    return call_llm(full_prompt, max_tokens=max_tokens, role="extraction")


# ── Step 1: Financial Analysis from Screener Data ────────────────────

def analyse_financials(symbol: str) -> dict:
    """Analyse Screener financial data and compute key metrics."""
    data_path = ARTIFACTS / symbol / "screener_financials.json"
    if not data_path.exists():
        return {"error": "No Screener data found. Run run_research.py first."}

    data = json.loads(data_path.read_text(encoding="utf-8"))
    pl = data.get("profit_loss", [])
    bs = data.get("balance_sheet", [])
    cf = data.get("cash_flow", [])
    about = data.get("about", {})

    # Parse numeric values from Screener format ("1,234" → 1234)
    def parse_num(s: str) -> float | None:
        if not s or s == "":
            return None
        try:
            return float(s.replace(",", "").replace("%", ""))
        except (ValueError, AttributeError):
            return None

    # Extract time series for key metrics
    metrics = {}
    for row in pl:
        label = row.get("", "").strip()
        if not label:
            continue
        values = {}
        for k, v in row.items():
            if k and k.startswith("Mar ") or k == "TTM":
                values[k] = parse_num(v)
        if values:
            metrics[label] = values

    # Compute forensic signals
    forensic = {}

    # Revenue growth trend
    sales = metrics.get("Sales+", metrics.get("Sales", {}))
    years = sorted([k for k in sales if k.startswith("Mar ") and k.split()[-1].isdigit()], key=lambda x: int(x.split()[-1]))
    if len(years) >= 2:
        recent = sales.get(years[-1])
        prev = sales.get(years[-2])
        if recent and prev and prev > 0:
            forensic["revenue_growth_latest"] = round((recent - prev) / prev * 100, 1)

    # Operating margin trend
    op_profit = metrics.get("Operating Profit", {})
    if sales and op_profit:
        margins = {}
        for yr in years:
            s = sales.get(yr)
            o = op_profit.get(yr)
            if s and o and s > 0:
                margins[yr] = round(o / s * 100, 1)
        forensic["operating_margins"] = margins

    # Net profit trend
    net_profit = metrics.get("Net Profit+", metrics.get("Net Profit", {}))
    if net_profit:
        forensic["net_profit_series"] = {k: v for k, v in net_profit.items() if v is not None}

    # Key ratios from about section
    forensic["current_pe"] = parse_num(about.get("Stock P/E", ""))
    forensic["current_roce"] = parse_num(about.get("ROCE", ""))
    forensic["current_roe"] = parse_num(about.get("ROE", ""))
    forensic["book_value"] = parse_num(about.get("Book Value", ""))
    forensic["dividend_yield"] = parse_num(about.get("Dividend Yield", ""))
    forensic["market_cap"] = about.get("Market Cap", "")

    return {
        "metrics": metrics,
        "forensic": forensic,
        "years_of_data": len(years),
        "about": about,
    }


# ── Step 2: Extract Management Narratives from Annual Reports ────────

NARRATIVE_EXTRACTION_PROMPT = """You are a forensic equity research analyst extracting management guidance from an Indian listed company's annual report.

## TASK
Extract ONLY management's forward-looking financial and operational commitments that a future year's actuals can be checked against.

## WHAT TO EXTRACT (must be ALL of these):
1. **Forward-looking** — about future periods, not describing what already happened
2. **Management-committed** — stated by the company about THEIR own plans (not macro forecasts, not industry views)
3. **Quantifiable** — has a specific number or measurable target
4. **Verifiable next year** — something you can check in next year's annual report

## THE TEST: Could you check next year whether this was delivered?
If the answer isn't "yes with a specific number", DO NOT extract it.

## EXAMPLES OF WHAT TO EXTRACT (specific + measurable + testable):
- "Revenue to grow 15% in FY26" (specific number, specific year)
- "Operating margin will stay above 20%" (specific threshold)
- "Loan book to grow 17-18% in FY26" (specific range)
- "Commissioning 500MW solar plant by Q3 FY26" (specific capacity, specific date)
- "Capex of Rs 3,000 Cr in FY26" (specific amount)
- "30 new stores to open by end of FY26" (specific count)
- "Order book to cross Rs 1.5 lakh Cr by FY27" (specific target)
- "R&D spend will be 8% of revenue in FY26" (specific ratio)
- "Net debt to reduce by Rs 2,000 Cr in FY26" (specific reduction)
- "Maintain CASA above 40%" (specific threshold)
- "Keep GNPA below 2% in FY26" (specific ceiling)

## EXAMPLES OF WHAT NOT TO EXTRACT — these are FILLER, not guidance:

BAD: "higher growth rate" — Higher than what? No number. SKIP.
BAD: "faster than industry average" — What industry rate? SKIP.
BAD: "well placed to deliver" — Generic confidence, no target. SKIP.
BAD: "strive to achieve leadership" — No metric, no date. SKIP.
BAD: "continue to focus on growth" — That's just saying "we will keep trying". SKIP.
BAD: "aims to utilise digital assets" — No measurable outcome. SKIP.
BAD: "create value for stakeholders" — Pure corporate-speak. SKIP.
BAD: "positive outlook for FY26" — Not a target. SKIP.
BAD: "India GDP will grow at 6.5%" — RBI forecast, not company guidance. SKIP.
BAD: "Global pharma market will reach $500B by 2030" — Industry forecast. SKIP.
BAD: "PAT grew 10.7% in FY25" — Past result, not forward-looking. SKIP.
BAD: "Audit fees of Rs 9.9 Cr" — Not strategic guidance. SKIP.
BAD: "carbon neutral by 2032" — Keep only if stated as a specific measurable milestone with progress tracking. Single entry, not multiple variations.

If management doesn't give specific numerical guidance, EXTRACT FEWER ITEMS. An empty list of 0 items is better than 20 items of filler. The absence of hard guidance is itself a data point about management credibility — we capture that by extracting NOTHING rather than making up items.

## SECTOR HINTS (types of guidance to look for):
- Banks: Loan growth %, NIM target, GNPA target, CASA %, ROA target, credit cost target, capital adequacy target
- IT: Revenue CC growth, margin band, headcount additions, deal wins guidance
- Pharma: New product launches (number), R&D spend %, FDA filings, US market share target
- FMCG: Volume growth %, distribution expansion, new product launches, margin target
- Auto: Volume target, new model launches, EV mix %, export %
- Metals/Energy: Production volume target, capex plan, debt reduction, capacity addition
- Defence: Order book target, production units/year, export target
- Real Estate: Pre-sales target, deliveries target, net debt target, new launches
- Infra/Power: Order book, capacity MW additions, PLF target, capex

## EXAMPLE OUTPUT (from Dr Reddy's FY25 annual report)

Here is the exact format and quality level expected:

```json
{
  "guidance": [
    {
      "exact_quote": "By 2030, serve 1.5 billion patients",
      "category": "other",
      "metric": "patients reached",
      "target_value": "1.5 billion patients",
      "target_year": "2030",
      "section_found": "Our ESG aspiration and progress",
      "page_reference": "Page 30-31, ESG Goals",
      "confidence": "hard_commitment",
      "materiality": "critical"
    },
    {
      "exact_quote": "By 2027, 25% new launches to be first to market",
      "category": "other",
      "metric": "first-to-market product launches",
      "target_value": "25%",
      "target_year": "2027",
      "section_found": "Our ESG aspiration and progress",
      "page_reference": "Page 30-31, ESG Goals",
      "confidence": "hard_commitment",
      "materiality": "significant"
    }
  ],
  "actuals_reported": {
    "revenue": "Rs 24,588 Cr",
    "operating_profit": "Rs 7,308 Cr EBITDA",
    "net_profit": "Rs 4,507 Cr",
    "order_book": "Not applicable for pharma",
    "capex_spent": "Rs 4,752 Cr in last 5 years",
    "export_revenue": "Not separately disclosed",
    "dividend_per_share": "Rs 40",
    "employees": "24,832 globally",
    "other_key_numbers": {
      "R&D_spend": "Rs 1,938 Cr",
      "EBITDA_margin": "29.7%",
      "RoCE": "34.6%",
      "manufacturing_facilities": "22"
    }
  },
  "risks_disclosed": [
    "Regulatory compliance risks across multiple jurisdictions",
    "Patent expiry and generic competition risks"
  ],
  "overall_tone": "confident"
}
```

## YOUR OUTPUT

Return the same JSON structure. Required fields:
- `guidance`: array of guidance items. QUALITY > QUANTITY. Extract 0-5 items if that's all the company specifically committed to. Do NOT pad with vague items to reach a quota. An empty list is fine if management gives no measurable forward-looking targets.
- `actuals_reported`: actual numbers for the current year
- `risks_disclosed`: specific risks acknowledged
- `overall_tone`: confident | cautious | defensive | promotional

Each guidance item needs: exact_quote, category, metric, target_value, target_year, section_found, page_reference, confidence (hard_commitment/guidance/aspiration), materiality (critical/significant/routine).

Return ONLY valid JSON, no markdown fences, no preamble."""


def extract_narratives(symbol: str) -> list[dict]:
    """Extract management narratives from annual report PDFs using Claude.

    Uses text extraction (not PDF-as-image) to capture the FULL content
    of MD&A, Chairman's letter, Directors' report, Risk sections, and more.
    """
    pdf_dir = ARTIFACTS / symbol / "pdfs"
    if not pdf_dir.exists():
        return []

    all_narratives = []
    for pdf_path in sorted(pdf_dir.glob("annual_report_*.pdf")):
        year = pdf_path.stem.replace("annual_report_", "")
        print(f"    Extracting narratives from {year}...")

        try:
            # Step 1: Extract text from PDF sections (with caching)
            cache_file = ARTIFACTS / symbol / f"ar_text_{year}.txt"
            if cache_file.exists() and cache_file.stat().st_size > 10000:
                combined_text = cache_file.read_text(encoding="utf-8")
                found = ["cached"]
                key_pages = "cached"
                total = "cached"
                print(f"      Using cached text: {len(combined_text):,} chars")
            else:
                sections = extract_pdf_text(pdf_path)
                combined_text = sections["_combined"]
                found = sections.get("_sections_found", [])
                key_pages = sections.get("_key_pages", "?")
                total = sections.get("_total_pages", "?")
                print(f"      {key_pages} key pages from {total} total | Sections: {found}")
                print(f"      Text length: {len(combined_text):,} chars")

                # Skip if PDF extraction failed (corrupted or 0 pages)
                if len(combined_text) < 5000:
                    print(f"      SKIP: PDF extraction produced too little text (likely corrupted)")
                    continue

                # Save extracted text for cache
                cache_file.write_text(combined_text, encoding="utf-8")

            # Step 2: Send to Claude (Haiku) for narrative extraction
            response = call_claude_with_ar_text(combined_text, NARRATIVE_EXTRACTION_PROMPT, max_tokens=4096)

            # Parse JSON
            text = response.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1]
                if text.endswith("```"):
                    text = text[:-3]
            parsed = json.loads(text)
            parsed["source_year"] = year
            parsed["source_file"] = pdf_path.name
            parsed["sections_analysed"] = found
            parsed["pages_extracted"] = int(key_pages) if str(key_pages).isdigit() else 0

            # POST-EXTRACTION QUALITY FILTER
            # Drop items where target_value is clearly vague (no number, no measurable outcome)
            items = parsed.get("guidance", parsed.get("claims", []))
            filtered = _filter_vague_guidance(items)
            parsed["guidance"] = filtered
            if len(filtered) < len(items):
                print(f"    → Filtered {len(items) - len(filtered)} vague items")

            item_count = len(filtered)
            if item_count == 0:
                print(f"    → WARNING: 0 specific items extracted from {year}")
                (ARTIFACTS / symbol / f"narrative_raw_{year}.txt").write_text(
                    response[:2000], encoding="utf-8")
            else:
                all_narratives.append(parsed)
                print(f"    → {item_count} specific items, tone: {parsed.get('overall_tone', '?')}")

        except json.JSONDecodeError as e:
            print(f"    → JSON parse error: {e}")
            (ARTIFACTS / symbol / f"narrative_raw_{year}.txt").write_text(
                response, encoding="utf-8")
        except Exception as e:
            print(f"    → Error: {e}")

    return all_narratives


def _filter_vague_guidance(items: list) -> list:
    """Drop guidance items that are vague, unmeasurable, or backward-looking.

    Rules:
    - target_value must contain a number OR a specific deliverable (e.g., "App live")
    - Reject pure hedging language: "higher", "faster", "continue", "focus on", "at scale"
    - Reject ESG aspirations longer than one entry per category
    - Reject macro/industry forecasts (not company guidance)
    """
    import re

    # Vague phrases that indicate non-specific guidance
    VAGUE_PATTERNS = [
        r"^higher\b",
        r"^faster\b",
        r"^continue\b",
        r"^focus\b",
        r"^strive\b",
        r"^aim\b",
        r"^hope\b",
        r"^well placed\b",
        r"^positive\b",
        r"^at scale\b",
        r"^drive\b",
        r"^create\b",
        r"^enhance\b",
        r"^strengthen\b",
        r"^leverage\b",
        r"industry average",
        r"stakeholders",
        r"value.accretive",
    ]

    # Vague quote patterns (the exact_quote itself is aspirational)
    VAGUE_QUOTE_PATTERNS = [
        r"our mission is",
        r"our vision is",
        r"our aspiration",
        r"our commitment is to",
        r"we are committed to",
        r"we believe",
        r"we remain confident",
        r"we are well positioned",
        r"our goal is to",
        r"we will continue to",
        r"we will focus",
        r"consent of the",  # board resolution language
        r"remuneration of",  # compensation details
        r"as part of our",
    ]

    # Macro/industry forecast keywords
    MACRO_WORDS = {"gdp", "inflation", "industry outlook", "market outlook",
                   "global economy", "rbi", "fed ", "geopolitical", "commodity prices",
                   "sector outlook", "market will reach", "industry will grow"}

    filtered = []
    seen_esg_carbon = False

    for item in items:
        target = str(item.get("target_value", "")).lower().strip()
        quote = str(item.get("exact_quote", "")).lower()
        category = str(item.get("category", "")).lower()
        metric = str(item.get("metric", "")).lower()

        # Reject empty targets
        if not target or target in ("?", "n/a", "none", "null"):
            continue

        # Reject macro/industry forecasts
        if any(word in quote for word in MACRO_WORDS):
            continue

        # Reject vague quote patterns (aspirational language)
        if any(re.search(p, quote) for p in VAGUE_QUOTE_PATTERNS):
            continue

        # Reject vague targets (no number and no specific deliverable)
        has_number = bool(re.search(r'\d', target))
        is_specific_deliverable = any(kw in target for kw in
                                      ["live", "launch", "operational", "complete", "commission",
                                       "integrat", "rollout", "deploy", "open", "build"])

        if not has_number and not is_specific_deliverable:
            # Check if target starts with vague phrase
            if any(re.match(pattern, target) for pattern in VAGUE_PATTERNS):
                continue
            # Short targets without numbers are usually vague
            if len(target) < 30:
                continue

        # Dedupe carbon-neutral aspirations
        if "carbon" in quote or "net zero" in quote or "net-zero" in quote:
            if seen_esg_carbon:
                continue
            seen_esg_carbon = True

        filtered.append(item)

    return filtered


# ── Step 3: Promise vs Delivery Scoring ──────────────────────────────

SCORING_PROMPT_TEMPLATE = """You are a forensic equity research analyst. Your job is to CROSS-REFERENCE management guidance against actual results.

## VERIFIED FINANCIAL DATA (from Screener.in):
{financials_json}

## MANAGEMENT GUIDANCE EXTRACTED FROM ANNUAL REPORTS (multiple years):
{claims_json}

## YOUR TASK: Build a GUIDANCE vs ACTUAL scorecard

For EVERY guidance item, find the ACTUAL result and score it:

### Scoring Rules:
- **DELIVERED**: Actual meets or exceeds the target (within 5% tolerance)
- **PARTIALLY_DELIVERED**: Actual is within 5-20% of target
- **MISSED**: Actual is more than 20% below target
- **EXCEEDED**: Actual significantly exceeds target (>10% above)
- **QUIETLY_DROPPED**: This guidance/theme disappeared from subsequent annual reports without explanation or update
- **TOO_EARLY**: Target year hasn't arrived yet — cannot score
- **UNVERIFIABLE**: Cannot find actual data to verify

### Cross-referencing method:
1. Take guidance from FY(N) annual report
2. Check actuals reported in FY(N+1) annual report AND Screener financial data
3. Example: FY23 AR says "Revenue target Rs 30,000 Cr by FY24" → Check FY24 actual revenue from Screener data

### For QUIETLY DROPPED detection:
- If FY22 and FY23 both mention "export target of 15%" but FY24 and FY25 stop mentioning exports entirely → QUIETLY_DROPPED
- If a major program or initiative is mentioned in 2+ years then vanishes → flag it

### MATERIALITY WEIGHTING (critical for ANKA Trust Score):
When scoring, weight items by materiality:
- **critical** items (revenue, profit, production targets): These DEFINE the investment thesis. A MISS here is 3x more damaging than a routine MISS.
- **significant** items (capex, capacity, order book): Important but secondary.
- **routine** items (CSR, compliance, policy): Delivery on these is expected and proves little. Missing on these is concerning only if systematic.

### TEMPORAL WEIGHTING:
Recent guidance matters more. Apply these weights:
- Last 2 years (FY24-FY25): Full weight (1.0x)
- 3-4 years ago (FY22-FY23): 0.7x weight
- 5+ years ago (FY18-FY21): 0.4x weight
A production target MISS in FY23 should matter MORE than a CSR delivery in FY19.

### DIVERGENCE LOGIC:
If your scoring leads to a conclusion that CONTRADICTS street consensus (e.g., street says 12-15% growth, our analysis suggests 8%), you MUST explicitly explain:
1. What specific evidence supports the street view
2. What specific evidence supports our view
3. Why our evidence is stronger (with page references and numbers)

## CRITICAL JSON RULES
- Return ONLY valid JSON, no markdown fences, no preamble
- All numeric fields must be COMPUTED numbers (e.g., -9.67), NOT expressions like (5.51 - 6.1) / 6.1 * 100
- Use null for unknown numeric values, never NaN or Infinity
- variance_pct must be a single number like -9.67 or 2.13

Example JSON structure:
{{
  "scorecard": [
    {{
      "guidance_year": "FY23",
      "category": "revenue_guidance",
      "materiality": "critical",
      "guidance_quote": "exact management quote",
      "page_reference": "Page X, MD&A Section Y",
      "target_metric": "total revenue",
      "target_value": "Rs 30,000 Cr",
      "target_year": "FY24",
      "actual_value": "Rs 30,381 Cr (from Screener Mar 2024)",
      "variance_pct": 1.3,
      "status": "DELIVERED",
      "source_of_actual": "Screener P&L Mar 2024 / FY24 Annual Report",
      "temporal_weight": 0.7
    }}
  ],
  "summary": {{
    "total_guidance_items": 0,
    "critical_items": 0,
    "critical_delivery_rate_pct": 0.0,
    "significant_items": 0,
    "significant_delivery_rate_pct": 0.0,
    "routine_items": 0,
    "routine_delivery_rate_pct": 0.0,
    "delivered": 0,
    "exceeded": 0,
    "partially_delivered": 0,
    "missed": 0,
    "quietly_dropped": 0,
    "too_early": 0,
    "unverifiable": 0,
    "delivery_rate_pct": 0.0,
    "weighted_delivery_rate_pct": 0.0,
    "beat_rate_pct": 0.0
  }},
  "dropped_themes": [
    {{
      "theme": "description of what was dropped",
      "last_mentioned_year": "FY23",
      "significance": "high|medium|low",
      "page_last_seen": "Page X of FY23 AR"
    }}
  ],
  "guidance_accuracy_by_category": {{
    "revenue_guidance": {{"total": 0, "delivered": 0, "rate_pct": 0}},
    "capacity_production": {{"total": 0, "delivered": 0, "rate_pct": 0}},
    "order_book": {{"total": 0, "delivered": 0, "rate_pct": 0}},
    "capex": {{"total": 0, "delivered": 0, "rate_pct": 0}},
    "export": {{"total": 0, "delivered": 0, "rate_pct": 0}},
    "routine": {{"total": 0, "delivered": 0, "rate_pct": 0}}
  }},
  "divergence_from_street": {{
    "street_view": "what consensus analysts believe (e.g., 12-15% revenue CAGR)",
    "our_view": "what our forensic cross-referencing shows (e.g., 8% capped by production)",
    "evidence_supporting_street": ["specific point with numbers"],
    "evidence_supporting_us": ["specific point with numbers and page references"],
    "why_our_evidence_is_stronger": "1-2 sentences explaining why forensic cross-referencing trumps forward guidance"
  }},
  "credibility_trajectory": "improving|stable|deteriorating",
  "management_pattern": "2-3 sentences — do they sandbag, guide accurately, or over-promise? Distinguish between CRITICAL and ROUTINE delivery patterns.",
  "biggest_red_flag": "most concerning finding with specific numbers and page reference",
  "biggest_strength": "most impressive delivery with specific numbers and page reference",
  "what_street_is_missing": "the key insight consensus doesn't capture"
}}"""


def score_promises(symbol: str, financials: dict, narratives: list) -> dict:
    """Score management claims against actual financial results."""
    if not narratives:
        return {"error": "No narratives to score"}

    # Flatten all guidance + actuals across years
    all_claims = []
    for narr in narratives:
        year = narr.get("source_year", "")
        # Support both old format (claims) and new format (guidance)
        items = narr.get("guidance", narr.get("claims", []))
        actuals = narr.get("actuals_reported", {})
        for claim in items:
            claim["source_year"] = year
            claim["actuals_this_year"] = actuals
            all_claims.append(claim)

    if not all_claims:
        return {"error": "No guidance items extracted"}

    # Prepare financial data for scoring
    fin_summary = {
        "about": financials.get("about", {}),
        "forensic": financials.get("forensic", {}),
        "key_metrics": {}
    }
    # Include key P&L metrics
    for label in ["Sales+", "Sales", "Operating Profit", "Net Profit+", "Net Profit", "OPM %", "EPS in Rs"]:
        if label in financials.get("metrics", {}):
            fin_summary["key_metrics"][label] = financials["metrics"][label]

    prompt = SCORING_PROMPT_TEMPLATE.format(
        symbol=symbol,
        financials_json=json.dumps(fin_summary, indent=2, default=str),
        claims_json=json.dumps(all_claims, indent=2, default=str),
    )

    print(f"    Scoring {len(all_claims)} claims against financials...")
    try:
        response = call_llm(prompt, max_tokens=32768, role="scoring")
        text = response.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            if text.endswith("```"):
                text = text[:-3]

        # Clean up Gemini quirks: sometimes returns math expressions instead of numbers
        text = _clean_json_expressions(text)

        return json.loads(text)
    except json.JSONDecodeError as e:
        print(f"    → JSON parse error: {e}")
        (ARTIFACTS / symbol / "scoring_raw.txt").write_text(response, encoding="utf-8")
        return {"error": f"JSON parse failed: {e}", "raw": response[:500]}
    except Exception as e:
        return {"error": str(e)}


def _clean_json_expressions(text: str) -> str:
    """Replace math expressions in JSON values with computed results.

    Gemini sometimes returns: "variance_pct": (5.51 - 6.1) / 6.1 * 100
    This breaks JSON parsing. We compute the expression and substitute.
    """
    import re

    # Match patterns like: "key": (expression) or "key": value / value * value
    # Look for numeric field values that contain math operators
    def replace_expr(match):
        key = match.group(1)
        expr = match.group(2).strip()
        # Try to eval the expression safely (only numbers and basic math)
        try:
            # Safe eval — only allow digits, operators, parens, decimal, minus
            allowed = set("0123456789.+-*/() ")
            if all(c in allowed for c in expr):
                result = eval(expr, {"__builtins__": {}}, {})
                return f'"{key}": {round(result, 2)}'
        except Exception:
            pass
        return f'"{key}": null'

    # Pattern: "field_name": (expression containing math)
    pattern = r'"(variance_pct|pct|percentage|ratio|score|value)":\s*(\([^)]+\)(?:\s*[*/+-]\s*[\d.]+)*|[\d.]+\s*[*/+-]\s*[\d.()+-/*]+)'
    text = re.sub(pattern, replace_expr, text)

    # Also catch unquoted NaN and Infinity
    text = text.replace(": NaN,", ": null,").replace(": Infinity,", ": null,").replace(": -Infinity,", ": null,")

    return text


# ── Step 4: ANKA Trust Score Calculation ──────────────────────────────

def calculate_trust_score(scoring: dict, financials: dict) -> dict:
    """Calculate the final ANKA Trust Score from the guidance scorecard.

    Uses materiality weighting and temporal decay:
    - Critical guidance (revenue/profit/production) counts 3x vs routine (CSR/policy)
    - Recent failures (FY24-25) count 1.0x, old ones (FY18-21) count 0.4x
    - Dropped themes penalised by significance level
    - Explicit divergence from street captured
    """
    summary = scoring.get("summary", scoring.get("delivery_summary", {}))
    total = summary.get("total_guidance_items", summary.get("total_scoreable", 0))
    scoreable = total - summary.get("too_early", 0) - summary.get("unverifiable", 0)

    # Need minimum 5 scoreable items for a reliable grade
    MIN_SCOREABLE = 5
    if scoreable < MIN_SCOREABLE:
        return {
            "trust_score_pct": 0.0,
            "trust_score_grade": "?",
            "verdict": "INSUFFICIENT_DATA",
            "detail": f"Only {scoreable} scoreable items ({total} total, {summary.get('too_early', 0)} too early, {summary.get('unverifiable', 0)} unverifiable). Need minimum {MIN_SCOREABLE} for reliable grade.",
            "guidance_scored": scoreable,
            "total_guidance_items": total,
        }

    # Use weighted delivery rate if available, else fall back to simple
    weighted_rate = summary.get("weighted_delivery_rate_pct")
    simple_rate = summary.get("delivery_rate_pct", 0)
    critical_rate = summary.get("critical_delivery_rate_pct", simple_rate)

    # The execution score is driven primarily by CRITICAL delivery rate
    # Critical items define the investment thesis — CSR delivery is noise
    if critical_rate is not None and summary.get("critical_items", 0) > 0:
        # 70% weight on critical, 30% on overall
        effective_rate = critical_rate * 0.70 + simple_rate * 0.30
    else:
        effective_rate = weighted_rate if weighted_rate else simple_rate

    delivery_rate = round(effective_rate, 1)
    beat_rate = summary.get("beat_rate_pct", 0)

    # Execution score: -10 to +10
    execution = (delivery_rate / 100 * 20) - 10

    # Beat bonus: companies that exceed guidance get extra credit
    accuracy_bonus = min(beat_rate / 100 * 5, 5.0) if beat_rate else 0.0

    # Dropped theme penalty: -4% for high significance, -2% for medium, -0.5% for low
    dropped_themes = scoring.get("dropped_themes", [])
    if isinstance(dropped_themes, list) and dropped_themes and isinstance(dropped_themes[0], dict):
        drop_penalty = sum(
            -4.0 if d.get("significance") == "high" else
            -2.0 if d.get("significance") == "medium" else -0.5
            for d in dropped_themes
        )
    else:
        drop_penalty = -3.0 * len(dropped_themes)

    # Credibility trajectory
    trajectory = scoring.get("credibility_trajectory", "stable")
    traj_score = {"improving": 3.0, "stable": 0.0, "deteriorating": -5.0}.get(trajectory, 0.0)

    # Category-level analysis
    cat_analysis = scoring.get("guidance_accuracy_by_category", {})

    # Weighted composite
    premium = (
        execution * 0.50 +
        accuracy_bonus * 0.15 +
        drop_penalty * 0.25 +
        traj_score * 0.10
    )

    # Letter grade based on effective delivery rate
    def _grade(rate):
        if rate >= 90: return "A+"
        if rate >= 80: return "A"
        if rate >= 70: return "B+"
        if rate >= 60: return "B"
        if rate >= 40: return "C"
        if rate >= 20: return "D"
        return "F"

    grade = _grade(delivery_rate)
    verdict = f"{grade} ({delivery_rate:.0f}%)"

    # Divergence from street
    divergence = scoring.get("divergence_from_street", {})

    return {
        "trust_score_pct": round(delivery_rate, 1),
        "trust_score_grade": grade,
        "premium_adjustment_pct": round(premium, 1),
        "components": {
            "execution_score": round(execution, 1),
            "accuracy_bonus": round(accuracy_bonus, 1),
            "dropped_penalty": round(drop_penalty, 1),
            "trajectory_bonus": round(traj_score, 1),
        },
        "scoring_methodology": {
            "effective_delivery_rate": delivery_rate,
            "critical_delivery_rate": critical_rate,
            "overall_delivery_rate": simple_rate,
            "note": "Effective rate = 70% critical items + 30% overall. Production MISSes weigh more than CSR deliveries.",
        },
        "verdict": verdict,
        "delivery_rate": delivery_rate,
        "beat_rate": round(beat_rate, 1),
        "guidance_scored": scoreable,
        "guidance_delivered": summary.get("delivered", 0) + summary.get("exceeded", 0),
        "guidance_missed": summary.get("missed", 0),
        "themes_dropped": len(dropped_themes),
        "dropped_theme_details": dropped_themes,
        "category_breakdown": cat_analysis,
        "credibility_trajectory": trajectory,
        "divergence_from_street": divergence,
        "management_pattern": scoring.get("management_pattern", ""),
        "biggest_red_flag": scoring.get("biggest_red_flag", ""),
        "biggest_strength": scoring.get("biggest_strength", ""),
        "what_street_is_missing": scoring.get("what_street_is_missing", ""),
    }


# ── Step 5: Street Consensus Comparison ──────────────────────────────

CONSENSUS_PROMPT_TEMPLATE = """Based on your knowledge of {symbol} ({company_description}), provide the current street consensus view.

Current financials:
- Market Cap: {market_cap}
- P/E: {pe}
- ROCE: {roce}%
- ROE: {roe}%
- Latest Revenue Growth: {rev_growth}%

Return ONLY valid JSON:
{{
  "street_consensus": {{
    "rating_distribution": "what % of analysts are buy/hold/sell (approximate)",
    "target_price_range": "Rs X to Rs Y",
    "key_bull_case": "1-2 sentences",
    "key_bear_case": "1-2 sentences",
    "consensus_revenue_growth": "expected growth % for next 2 years",
    "consensus_margin_view": "expanding/stable/contracting"
  }},
  "our_differentiated_view": {{
    "agrees_with_street": ["point1", "point2"],
    "disagrees_with_street": ["point1", "point2"],
    "what_street_is_missing": "the key insight from ANKA Trust Score analysis that street doesn't capture"
  }}
}}"""


def get_street_consensus(symbol: str, financials: dict) -> dict:
    """Generate street consensus comparison."""
    forensic = financials.get("forensic", {})
    about = financials.get("about", {})

    prompt = CONSENSUS_PROMPT_TEMPLATE.format(
        symbol=symbol,
        company_description=about.get("description", symbol),
        market_cap=about.get("Market Cap", "?"),
        pe=forensic.get("current_pe", "?"),
        roce=forensic.get("current_roce", "?"),
        roe=forensic.get("current_roe", "?"),
        rev_growth=forensic.get("revenue_growth_latest", "?"),
    )

    try:
        response = call_claude(prompt, max_tokens=2048)
        text = response.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            if text.endswith("```"):
                text = text[:-3]
        return json.loads(text)
    except Exception as e:
        return {"error": str(e)}


# ── Orchestrator ─────────────────────────────────────────────────────

def run(symbol: str):
    """Run full ANKA Trust Score analysis."""
    out_dir = ARTIFACTS / symbol
    if not out_dir.exists():
        print(f"ERROR: No data found for {symbol}. Run 'python run_research.py {symbol}' first.")
        return

    print(f"{'='*70}")
    print(f"  OPUS ANKA — ANKA Trust Score Analysis: {symbol}")
    print(f"{'='*70}")

    # Step 1: Financial analysis
    print(f"\n  [1/5] Analysing financials...")
    financials = analyse_financials(symbol)
    (out_dir / "financial_analysis.json").write_text(
        json.dumps(financials, indent=2, default=str), encoding="utf-8")
    print(f"         {financials.get('years_of_data', 0)} years | ROCE: {financials.get('forensic', {}).get('current_roce')}% | ROE: {financials.get('forensic', {}).get('current_roe')}%")

    # Step 2: Narrative extraction from annual reports
    print(f"\n  [2/5] Extracting management narratives from annual reports...")
    narratives = extract_narratives(symbol)
    (out_dir / "narratives.json").write_text(
        json.dumps(narratives, indent=2, ensure_ascii=False), encoding="utf-8")
    # Support both old 'claims' and new 'guidance' keys
    total_claims = sum(len(n.get("guidance", n.get("claims", []))) for n in narratives)
    print(f"         {len(narratives)} reports processed, {total_claims} guidance items extracted")

    # Step 3: Guidance vs Actual cross-referencing
    print(f"\n  [3/5] Cross-referencing guidance vs actuals...")
    scoring = score_promises(symbol, financials, narratives)
    (out_dir / "guidance_scorecard.json").write_text(
        json.dumps(scoring, indent=2, ensure_ascii=False), encoding="utf-8")
    ds = scoring.get("summary", scoring.get("delivery_summary", {}))
    print(f"         Delivery rate: {ds.get('delivery_rate_pct', '?')}% | Dropped themes: {len(scoring.get('dropped_themes', []))}")
    print(f"         Delivered: {ds.get('delivered', 0)} | Exceeded: {ds.get('exceeded', 0)} | Missed: {ds.get('missed', 0)} | Too Early: {ds.get('too_early', 0)}")

    # Step 4: ANKA Trust Score calculation
    print(f"\n  [4/5] Calculating ANKA Trust Score...")
    premium = calculate_trust_score(scoring, financials)
    (out_dir / "trust_score.json").write_text(
        json.dumps(premium, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"         Premium: {premium.get('trust_score_pct', 0):+.1f}% | Verdict: {premium.get('verdict')}")

    # Step 5: Street consensus
    print(f"\n  [5/5] Getting street consensus view...")
    consensus = get_street_consensus(symbol, financials)
    (out_dir / "street_consensus.json").write_text(
        json.dumps(consensus, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"         Done")

    # ── Final Report Summary ─────────────────────────────────────────
    report = {
        "symbol": symbol,
        "generated_at": datetime.now(IST).isoformat(),
        "financial_snapshot": {
            "market_cap": financials.get("about", {}).get("Market Cap"),
            "pe": financials.get("forensic", {}).get("current_pe"),
            "roce": financials.get("forensic", {}).get("current_roce"),
            "roe": financials.get("forensic", {}).get("current_roe"),
            "revenue_growth": financials.get("forensic", {}).get("revenue_growth_latest"),
        },
        "trust_score": premium,
        "guidance_scorecard": scoring.get("scorecard", []),
        "guidance_summary": scoring.get("summary", {}),
        "guidance_by_category": scoring.get("guidance_accuracy_by_category", {}),
        "dropped_themes": scoring.get("dropped_themes", []),
        "management_pattern": scoring.get("management_pattern", ""),
        "biggest_red_flag": scoring.get("biggest_red_flag", ""),
        "biggest_strength": scoring.get("biggest_strength", ""),
        "what_street_is_missing": scoring.get("what_street_is_missing", ""),
        "street_consensus": consensus.get("street_consensus", {}),
        "differentiated_view": consensus.get("our_differentiated_view", {}),
    }
    (out_dir / "FINAL_REPORT.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    # Print scorecard summary
    scorecard = scoring.get("scorecard", [])
    if scorecard:
        print(f"\n  {'─'*70}")
        print(f"  GUIDANCE vs ACTUAL SCORECARD")
        print(f"  {'─'*70}")
        for item in scorecard:
            status = item.get("status", "?")
            icon = {"DELIVERED": "OK", "EXCEEDED": "++", "PARTIALLY_DELIVERED": "~", "MISSED": "XX", "QUIETLY_DROPPED": "!!", "TOO_EARLY": ".."}
            s = icon.get(status, "??")
            cat = str(item.get("category") or "")[:15]
            target = str(item.get("target_value") or "?")[:25]
            actual = str(item.get("actual_value") or "?")[:30]
            yr = str(item.get("guidance_year", "?"))
            print(f"  [{s:>2}] {yr} {cat:<16} Target: {target:<26} Actual: {actual}")

    print(f"\n{'='*70}")
    print(f"  ANKA TRUST SCORE: {premium.get('trust_score_grade', '?')} ({premium.get('trust_score_pct', 0):.0f}%)")
    print(f"  Premium Adjustment: {premium.get('premium_adjustment_pct', 0):+.1f}%")
    print(f"  Delivery Rate:   {premium.get('delivery_rate', '?')}%")
    print(f"  Beat Rate:       {premium.get('beat_rate', '?')}%")
    print(f"  Guidance Scored: {premium.get('guidance_scored', 0)}")
    print(f"  Dropped Themes:  {premium.get('themes_dropped', 0)}")
    print(f"  Red Flag:        {premium.get('biggest_red_flag', 'None')}")
    print(f"  Strength:        {premium.get('biggest_strength', 'None')}")
    print(f"  Trajectory:      {premium.get('credibility_trajectory', '?')}")
    print(f"  Street Missing:  {premium.get('what_street_is_missing', 'N/A')}")
    print(f"{'='*70}")
    print(f"\n  Full report: {out_dir / 'FINAL_REPORT.json'}")

    # ── Save to Obsidian vault for sector comparisons ────────────
    obsidian_dir = Path("C:/Users/Claude_Anka/ObsidianVault/markets/trust-score")
    try:
        obsidian_dir.mkdir(parents=True, exist_ok=True)
        obsidian_path = obsidian_dir / f"{symbol}-trust-score.md"
        _save_obsidian_note(symbol, report, premium, scoring, obsidian_path)
        print(f"  Obsidian: {obsidian_path}")
    except Exception as e:
        print(f"  Obsidian save failed: {e}")

    return report


def _save_obsidian_note(symbol: str, report: dict, premium: dict, scoring: dict, path: Path):
    """Save structured research note to Obsidian vault."""
    snap = report.get("financial_snapshot", {})
    div = premium.get("divergence_from_street", {})
    scorecard = scoring.get("scorecard", [])

    # Build scorecard table
    sc_lines = []
    for item in scorecard:
        status = item.get("status", "?")
        yr = item.get("guidance_year", "?")
        cat = item.get("category", "?")
        target = item.get("target_value", "?")
        actual = item.get("actual_value", "?")
        mat = item.get("materiality", "?")
        sc_lines.append(f"| {yr} | {cat} | {mat} | {target} | {actual} | {status} |")

    sc_table = "\n".join(sc_lines) if sc_lines else "No scorecard data"

    md = f"""---
company: {symbol}
trust_score: {premium.get('trust_score_pct', 0)}%
verdict: {premium.get('verdict', '?')}
delivery_rate: {premium.get('delivery_rate', '?')}%
generated: {report.get('generated_at', '')}
tags: [trust-score, equity-research, {symbol.lower()}]
---

# {symbol} — ANKA Trust Score Analysis

**ANKA Trust Score: {premium.get('trust_score_pct', 0):+.1f}% ({premium.get('verdict', '?')})**

## Financial Snapshot
- Market Cap: {snap.get('market_cap', '?')} Cr
- P/E: {snap.get('pe', '?')}x | ROCE: {snap.get('roce', '?')}% | ROE: {snap.get('roe', '?')}%
- Revenue Growth: {snap.get('revenue_growth', '?')}%

## Management Pattern
{premium.get('management_pattern', 'N/A')}

## Guidance Scorecard
| Year | Category | Materiality | Target | Actual | Status |
|------|----------|-------------|--------|--------|--------|
{sc_table}

## Key Findings
- **Red Flag**: {premium.get('biggest_red_flag', 'None')}
- **Strength**: {premium.get('biggest_strength', 'None')}
- **Trajectory**: {premium.get('credibility_trajectory', '?')}

## Divergence from Street
- **Street View**: {div.get('street_view', 'N/A')}
- **Our View**: {div.get('our_view', 'N/A')}
- **Why Our Evidence Is Stronger**: {div.get('why_our_evidence_is_stronger', 'N/A')}

## What Street Is Missing
{premium.get('what_street_is_missing', 'N/A')}

## Scoring Methodology
- Effective Rate: {premium.get('scoring_methodology', {}).get('effective_delivery_rate', '?')}%
- Critical Delivery Rate: {premium.get('scoring_methodology', {}).get('critical_delivery_rate', '?')}%
- Note: {premium.get('scoring_methodology', {}).get('note', '')}

---
*Generated by OPUS ANKA ANKA Trust Score Engine*
"""
    path.write_text(md, encoding="utf-8")


if __name__ == "__main__":
    symbol = sys.argv[1] if len(sys.argv) > 1 else "HAL"
    # Resolve if needed
    from run_research import resolve_symbol
    nse_symbol, _ = resolve_symbol(symbol)
    run(nse_symbol)
