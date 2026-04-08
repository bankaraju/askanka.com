"""
OPUS ANKA — Pattern Premium Scorer

Takes collected data from run_research.py and produces:
1. Structured financials analysis (from Screener data)
2. Management narrative extraction (from annual report PDFs via Claude)
3. Promise-vs-Delivery scoring
4. Final Pattern Premium score

Usage:
    python run_pattern_premium.py HAL
    python run_pattern_premium.py HDFCBANK

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

# ── Claude API ───────────────────────────────────────────────────────

def call_claude(prompt: str, max_tokens: int = 4096) -> str:
    """Call Claude API and return text response."""
    import anthropic
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


def extract_pdf_text(pdf_path: Path) -> dict[str, str]:
    """Extract text from PDF and split into sections.

    Returns dict of section_name → text for key sections:
    MD&A, Chairman's letter, Directors' report, Risk factors, Financial highlights.
    """
    import pymupdf
    doc = pymupdf.open(str(pdf_path))
    total_pages = len(doc)

    # First pass: extract all text and find section boundaries
    all_text = []
    section_markers = {}
    keywords = {
        "mda": ["management discussion", "management's discussion", "md&a"],
        "chairman": ["chairman's message", "chairman's letter", "chairman's statement", "message from chairman"],
        "directors": ["directors' report", "directors report", "board's report"],
        "risk": ["risk management", "risk factors", "enterprise risk"],
        "overview": ["strategic overview", "business overview", "operational review", "company overview"],
        "financial_highlights": ["financial highlights", "financial performance", "performance highlights"],
        "outlook": ["outlook", "way forward", "future outlook", "looking ahead"],
        "order_book": ["order book", "order position", "orders received"],
    }

    for i, page in enumerate(doc):
        text = page.get_text()
        all_text.append(text)
        text_lower = text.lower()
        for section, kws in keywords.items():
            if section not in section_markers:
                if any(kw in text_lower for kw in kws):
                    section_markers[section] = i

    doc.close()

    # Second pass: extract sections with generous context (20 pages each)
    sections = {}
    for section, start_page in section_markers.items():
        end_page = min(start_page + 20, total_pages)
        section_text = "\n".join(all_text[start_page:end_page])
        sections[section] = section_text

    # Also provide a combined text of ALL key sections
    all_key_pages = set()
    for start_page in section_markers.values():
        for p in range(start_page, min(start_page + 15, total_pages)):
            all_key_pages.add(p)

    # If we found sections, combine them
    if all_key_pages:
        combined = "\n\n--- PAGE BREAK ---\n\n".join(
            all_text[p] for p in sorted(all_key_pages)
        )
    else:
        # Fallback: pages 30-120 (typical Indian AR structure)
        combined = "\n\n--- PAGE BREAK ---\n\n".join(
            all_text[p] for p in range(min(30, total_pages), min(120, total_pages))
        )

    sections["_combined"] = combined
    sections["_total_pages"] = str(total_pages)
    sections["_key_pages"] = str(len(all_key_pages))
    sections["_sections_found"] = list(section_markers.keys())

    return sections


def call_claude_with_ar_text(text: str, prompt: str, max_tokens: int = 8192) -> str:
    """Call Claude API with extracted annual report text."""
    import anthropic
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    # Truncate if still too long (~150K chars ≈ ~40K tokens for text)
    if len(text) > 500000:
        text = text[:500000] + "\n\n[TRUNCATED — remaining pages omitted]"

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=max_tokens,
        messages=[{
            "role": "user",
            "content": f"Here is the text extracted from an annual report:\n\n{text}\n\n---\n\n{prompt}",
        }],
    )
    return response.content[0].text


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
    years = sorted([k for k in sales if k.startswith("Mar ")], key=lambda x: int(x.split()[-1]))
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

NARRATIVE_EXTRACTION_PROMPT = """You are a forensic equity research analyst. Your job is to extract MATERIAL FINANCIAL GUIDANCE from this annual report — the specific numbers and targets management committed to.

ONLY extract guidance that is SPECIFIC and MEASURABLE. Ignore vague aspirational language like "we aim to grow" or "we are optimistic." We need hard numbers.

## What to extract (MATERIAL GUIDANCE ONLY):

### Financial Guidance
- Revenue target/guidance (e.g., "Revenue expected to reach Rs 35,000 Cr in FY26")
- Profit margin guidance (e.g., "Operating margin to be maintained at 25%+")
- EPS or PAT guidance
- Dividend policy (e.g., "Minimum 30% payout ratio")
- Revenue/profit CAGR targets

### Order Book & Pipeline
- Order book size targets (e.g., "Order book of Rs 1.5 lakh Cr by FY26")
- New orders expected (specific contracts, programs)
- Order execution timelines

### Capex & Capacity
- Capital expenditure plans with amounts (e.g., "Rs 3,000 Cr capex in FY25")
- New facility timelines (e.g., "Helicopter factory operational by Q2 FY26")
- Production rate targets (e.g., "16 LCA per year by FY27")
- Capacity utilization targets

### Export & Diversification
- Export revenue targets (e.g., "Exports to reach 15% of revenue")
- New market entry plans with timelines
- New product/program delivery dates

### Operational KPIs
- Employee productivity targets
- R&D spend as % of revenue
- Working capital / cash conversion targets

## For each guidance item, provide:
1. **exact_quote**: The verbatim text from the report
2. **category**: revenue_guidance | profit_guidance | order_book | capex | capacity | export | new_program | dividend | working_capital | other
3. **metric**: What specifically (e.g., "total revenue", "EBITDA margin", "order book value")
4. **target_value**: The specific number (e.g., "Rs 35,000 Cr", "25%", "16 aircraft/year")
5. **target_year**: When (e.g., "FY26", "by March 2027", "next 3 years")
6. **section_found**: Where in the report (MD&A, Chairman Letter, Directors Report, Financial Highlights)
7. **confidence**: How firm is this commitment? "hard_commitment" (board approved), "guidance" (management expects), "aspiration" (would like to)

## Also extract:
- **risks_disclosed**: Specific risks management acknowledges (not boilerplate)
- **actual_numbers_this_year**: Key actuals reported (revenue, profit, order book, capex spent, exports) — these are needed to cross-reference LAST year's guidance

Return ONLY valid JSON, no markdown fences:
{
  "guidance": [
    {
      "exact_quote": "...",
      "category": "...",
      "metric": "...",
      "target_value": "...",
      "target_year": "...",
      "section_found": "...",
      "confidence": "hard_commitment|guidance|aspiration"
    }
  ],
  "actuals_reported": {
    "revenue": "Rs X Cr",
    "operating_profit": "Rs X Cr",
    "net_profit": "Rs X Cr",
    "order_book": "Rs X Cr",
    "capex_spent": "Rs X Cr",
    "export_revenue": "Rs X Cr",
    "dividend_per_share": "Rs X",
    "employees": "X",
    "other_key_numbers": {}
  },
  "risks_disclosed": ["specific risk 1", "specific risk 2"],
  "overall_tone": "confident|cautious|defensive|promotional"
}

Be EXHAUSTIVE. Every number that represents a forward-looking target or guidance must be captured. Minimum 15 guidance items expected from a defence company annual report."""


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
            # Step 1: Extract text from PDF sections
            sections = extract_pdf_text(pdf_path)
            combined_text = sections["_combined"]
            found = sections.get("_sections_found", [])
            key_pages = sections.get("_key_pages", "?")
            total = sections.get("_total_pages", "?")
            print(f"      {key_pages} key pages from {total} total | Sections: {found}")
            print(f"      Text length: {len(combined_text):,} chars")

            # Save extracted text for reference
            (ARTIFACTS / symbol / f"ar_text_{year}.txt").write_text(
                combined_text, encoding="utf-8")

            # Step 2: Send to Claude for narrative extraction
            response = call_claude_with_ar_text(combined_text, NARRATIVE_EXTRACTION_PROMPT, max_tokens=8192)

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
            parsed["pages_extracted"] = int(key_pages) if key_pages != "?" else 0
            all_narratives.append(parsed)
            print(f"    → {len(parsed.get('claims', []))} claims, tone: {parsed.get('overall_tone', '?')}")

        except json.JSONDecodeError as e:
            print(f"    → JSON parse error: {e}")
            (ARTIFACTS / symbol / f"narrative_raw_{year}.txt").write_text(
                response, encoding="utf-8")
        except Exception as e:
            print(f"    → Error: {e}")

    return all_narratives


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

Return ONLY valid JSON, no markdown fences:
{{
  "scorecard": [
    {{
      "guidance_year": "FY23",
      "category": "revenue_guidance",
      "guidance_quote": "exact management quote",
      "target_metric": "total revenue",
      "target_value": "Rs 30,000 Cr",
      "target_year": "FY24",
      "actual_value": "Rs 30,381 Cr (from Screener Mar 2024)",
      "variance_pct": 1.3,
      "status": "DELIVERED",
      "source_of_actual": "Screener P&L Mar 2024 / FY24 Annual Report"
    }}
  ],
  "summary": {{
    "total_guidance_items": 0,
    "delivered": 0,
    "exceeded": 0,
    "partially_delivered": 0,
    "missed": 0,
    "quietly_dropped": 0,
    "too_early": 0,
    "unverifiable": 0,
    "delivery_rate_pct": 0.0,
    "beat_rate_pct": 0.0
  }},
  "dropped_themes": [
    {{
      "theme": "description of what was dropped",
      "last_mentioned_year": "FY23",
      "significance": "high|medium|low"
    }}
  ],
  "guidance_accuracy_by_category": {{
    "revenue_guidance": {{"total": 0, "delivered": 0, "rate_pct": 0}},
    "order_book": {{"total": 0, "delivered": 0, "rate_pct": 0}},
    "capex": {{"total": 0, "delivered": 0, "rate_pct": 0}},
    "other": {{"total": 0, "delivered": 0, "rate_pct": 0}}
  }},
  "credibility_trajectory": "improving|stable|deteriorating",
  "management_pattern": "2-3 sentences on management's overall credibility pattern — do they sandbag (guide low, beat high), guide accurately, or over-promise?",
  "biggest_red_flag": "the single most concerning finding with specific numbers",
  "biggest_strength": "the single most impressive delivery with specific numbers",
  "what_street_is_missing": "what this cross-referencing reveals that consensus analyst reports don't capture"
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
        response = call_claude(prompt, max_tokens=8192)
        text = response.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            if text.endswith("```"):
                text = text[:-3]
        return json.loads(text)
    except json.JSONDecodeError as e:
        print(f"    → JSON parse error: {e}")
        (ARTIFACTS / symbol / "scoring_raw.txt").write_text(response, encoding="utf-8")
        return {"error": f"JSON parse failed: {e}", "raw": response[:500]}
    except Exception as e:
        return {"error": str(e)}


# ── Step 4: Pattern Premium Calculation ──────────────────────────────

def calculate_pattern_premium(scoring: dict, financials: dict) -> dict:
    """Calculate the final Pattern Premium from the guidance scorecard.

    Components:
    - Execution Score (50%): delivery + beat rate from cross-referenced guidance
    - Guidance Accuracy (15%): how close actuals are to targets (sandbagging vs accurate vs over-promising)
    - Dropped Theme Penalty (25%): -3% per quietly dropped narrative (high significance)
    - Credibility Trajectory (10%): improving gets bonus, deteriorating gets penalty
    """
    summary = scoring.get("summary", scoring.get("delivery_summary", {}))
    total = summary.get("total_guidance_items", summary.get("total_scoreable", 0))
    delivered = summary.get("delivered", 0) + summary.get("exceeded", 0)
    scoreable = total - summary.get("too_early", 0) - summary.get("unverifiable", 0)

    if scoreable == 0:
        return {
            "pattern_premium_pct": 0.0,
            "verdict": "INSUFFICIENT_DATA",
            "detail": "Not enough scoreable guidance items to calculate premium",
        }

    delivery_rate = summary.get("delivery_rate_pct", (delivered / scoreable * 100) if scoreable > 0 else 0)
    beat_rate = summary.get("beat_rate_pct", 0)

    # Execution score: -10 to +10
    execution = (delivery_rate / 100 * 20) - 10

    # Guidance accuracy bonus: companies that beat guidance get extra credit
    accuracy_bonus = min(beat_rate / 100 * 5, 5.0) if beat_rate else 0.0

    # Dropped theme penalty: -3% for high significance, -1.5% for medium
    dropped_themes = scoring.get("dropped_themes", [])
    if isinstance(dropped_themes, list) and dropped_themes and isinstance(dropped_themes[0], dict):
        drop_penalty = sum(
            -3.0 if d.get("significance") == "high" else -1.5
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

    verdict = "PREMIUM" if premium > 2 else "DISCOUNT" if premium < -2 else "FAIR"

    return {
        "pattern_premium_pct": round(premium, 1),
        "components": {
            "execution_score": round(execution, 1),
            "accuracy_bonus": round(accuracy_bonus, 1),
            "dropped_penalty": round(drop_penalty, 1),
            "trajectory_bonus": round(traj_score, 1),
        },
        "verdict": verdict,
        "delivery_rate": round(delivery_rate, 1),
        "beat_rate": round(beat_rate, 1),
        "guidance_scored": scoreable,
        "guidance_delivered": delivered,
        "guidance_missed": summary.get("missed", 0),
        "themes_dropped": len(dropped_themes),
        "dropped_theme_details": dropped_themes,
        "category_breakdown": cat_analysis,
        "credibility_trajectory": trajectory,
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
    "what_street_is_missing": "the key insight from Pattern Premium analysis that street doesn't capture"
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
    """Run full Pattern Premium analysis."""
    out_dir = ARTIFACTS / symbol
    if not out_dir.exists():
        print(f"ERROR: No data found for {symbol}. Run 'python run_research.py {symbol}' first.")
        return

    print(f"{'='*70}")
    print(f"  OPUS ANKA — Pattern Premium Analysis: {symbol}")
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
    total_claims = sum(len(n.get("claims", [])) for n in narratives)
    print(f"         {len(narratives)} reports processed, {total_claims} claims extracted")

    # Step 3: Guidance vs Actual cross-referencing
    print(f"\n  [3/5] Cross-referencing guidance vs actuals...")
    scoring = score_promises(symbol, financials, narratives)
    (out_dir / "guidance_scorecard.json").write_text(
        json.dumps(scoring, indent=2, ensure_ascii=False), encoding="utf-8")
    ds = scoring.get("summary", scoring.get("delivery_summary", {}))
    print(f"         Delivery rate: {ds.get('delivery_rate_pct', '?')}% | Dropped themes: {len(scoring.get('dropped_themes', []))}")
    print(f"         Delivered: {ds.get('delivered', 0)} | Exceeded: {ds.get('exceeded', 0)} | Missed: {ds.get('missed', 0)} | Too Early: {ds.get('too_early', 0)}")

    # Step 4: Pattern Premium calculation
    print(f"\n  [4/5] Calculating Pattern Premium...")
    premium = calculate_pattern_premium(scoring, financials)
    (out_dir / "pattern_premium.json").write_text(
        json.dumps(premium, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"         Premium: {premium.get('pattern_premium_pct', 0):+.1f}% | Verdict: {premium.get('verdict')}")

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
        "pattern_premium": premium,
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
            cat = item.get("category", "")[:15]
            target = item.get("target_value", "?")[:25]
            actual = item.get("actual_value", "?")[:30]
            yr = item.get("guidance_year", "?")
            print(f"  [{s:>2}] {yr} {cat:<16} Target: {target:<26} Actual: {actual}")

    print(f"\n{'='*70}")
    print(f"  PATTERN PREMIUM: {premium.get('pattern_premium_pct', 0):+.1f}% ({premium.get('verdict')})")
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

    return report


if __name__ == "__main__":
    symbol = sys.argv[1] if len(sys.argv) > 1 else "HAL"
    # Resolve if needed
    from run_research import resolve_symbol
    nse_symbol, _ = resolve_symbol(symbol)
    run(nse_symbol)
