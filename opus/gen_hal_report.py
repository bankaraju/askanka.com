"""Generate HAL research report HTML from all collected artifacts."""
import json, os
from dotenv import load_dotenv
from pathlib import Path
import anthropic

load_dotenv(Path("config/.env"))
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

tmp = Path(os.environ.get("TEMP", "/tmp")) / "hal_all_data.json"
all_data = json.loads(tmp.read_text(encoding="utf-8"))
data_str = json.dumps(all_data, indent=1, default=str)[:120000]

prompt = (
    "You are writing a professional equity research report for OPUS ANKA Research.\n\n"
    "Using ALL the data below, write a comprehensive research report on HAL "
    "(Hindustan Aeronautics Limited) in HTML format. This is a premium "
    "institutional-grade report — not retail cheerleading.\n\n"
    "## DATA:\n" + data_str + "\n\n"
    "## REPORT STRUCTURE:\n\n"
    "Write a complete HTML page with dark theme (background #0a0e1a, text #e5e7eb, "
    "gold accent #d4a855, green #10b981, red #ef4444) using DM Serif Display for "
    "headings and Inter for body text, JetBrains Mono for numbers. Include Google Fonts link.\n\n"
    "Include these sections:\n\n"
    "1. **Nav bar**: OPUS ANKA Research branding with gold accent\n"
    "2. **Header**: Company name HAL, date April 2026, ANKA Trust Score score as a colored badge, one-line verdict\n"
    "3. **Executive Summary**: 3-4 sentences — the single most important finding. What makes this different from street research.\n"
    "4. **Financial Snapshot**: Clean table — Market Cap, PE, ROCE, ROE, Revenue (8 year series), Net Profit, OPM trend\n"
    "5. **Guidance Scorecard**: THE KEY TABLE. Every guidance item from the scorecard data with columns: Year, Category, What Management Said, Target, Actual, Status. Color code: green=DELIVERED, bright green=EXCEEDED, amber=PARTIAL, red=MISSED, dark red with strikethrough=QUIETLY DROPPED, gray=TOO EARLY\n"
    "6. **The Production Paradox**: Revenue grew 67% while production dropped 46%. Explain the PoC accounting mechanism. Show the year-by-year data.\n"
    "7. **Defence Forensic Ratios**: Table with Ratio Name, Value, Benchmark, Flag (colored), What It Reveals. Use traffic light colors.\n"
    "8. **Order Book Reality**: The math — show order book series from 61K to 189K Cr. OB CAGR 17.5% vs Revenue CAGR 7.6%. Executable vs unexecutable split.\n"
    "9. **Export Credibility Check**: 8-year export revenue series. Show it is flat at 1% of revenue. Management recycles same promise annually.\n"
    "10. **Realistic Valuation**: Show the math — realistic growth 8%, fair PE 9.6x, current PE 29.4x, overvaluation 225%. Make clear this is forensic-based, not a price target.\n"
    "11. **Street Consensus vs Our View**: What 65% buy-rated analysts see vs what forensics reveal.\n"
    "12. **Management Credibility Assessment**: Overall pattern — do they deliver? The 81% delivery rate with specific examples.\n"
    "13. **What Street Is Missing**: The one insight — order book growth 223% with declining production capacity creates permanent disappointment cycle OR massive execution upside if capacity investment materializes.\n"
    "14. **Risk to Our Thesis**: What could prove us wrong — government capex push, new facilities coming online, Tejas production ramp.\n"
    "15. **ANKA Trust Score Verdict**: Score +2.8%, components breakdown in a visual box. BUT with the caveat that valuation forensics suggest the market is ahead of execution.\n"
    "16. **Methodology**: Brief note on OPUS ANKA approach — 8 annual reports, 36 guidance items extracted, 15 sector forensic ratios, cross-referenced against Screener.in verified data.\n"
    "17. **Disclaimer**: This is research, not investment advice. OPUS ANKA Research — askanka.com\n\n"
    "Style notes:\n"
    "- Make tables with subtle borders (rgba(255,255,255,0.05))\n"
    "- Use callout boxes (gold left border) for key findings\n"
    "- Monospace font for all numbers\n"
    "- Stat boxes at top for key metrics (like the askanka.com research page)\n"
    "- Make it look like a Goldman Sachs initiation report but more honest\n"
    "- Total length: comprehensive, not abbreviated\n\n"
    "Return ONLY the complete HTML document starting with <!DOCTYPE html>. No markdown fences."
)

response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=16000,
    messages=[{"role": "user", "content": prompt}],
)

html = response.content[0].text
if "<!DOCTYPE" in html and not html.strip().startswith("<!DOCTYPE"):
    html = html[html.index("<!DOCTYPE"):]

Path("artifacts/HAL/HAL_RESEARCH_REPORT.html").write_text(html, encoding="utf-8")
print(f"Report saved: {len(html):,} chars")
print("artifacts/HAL/HAL_RESEARCH_REPORT.html")
