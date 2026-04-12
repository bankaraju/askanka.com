"""Forensic deep-dive: HAL production vs revenue discrepancy."""
import json, os
from dotenv import load_dotenv
from pathlib import Path
import anthropic

load_dotenv(Path("config/.env"))
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

prompt = """You are a forensic equity analyst. Investigate a CRITICAL discrepancy in HAL (Hindustan Aeronautics Limited).

## THE DISCREPANCY:

PRODUCTION CAPACITY:
- FY19 guidance: 41 aircraft/helicopters + 110 engines per year
- FY23 actual: Only 22 aircraft/helicopters + 51 engines
- That is a 46% DROP in production capacity

BUT:
- Revenue grew EVERY year: 18,520 -> 20,008 -> 21,445 -> 22,882 -> 24,620 -> 26,927 -> 30,381 -> 30,981 Cr
- Order book EXPLODED: 61,123 -> 58,588 -> 52,965 -> 80,639 -> 82,154 -> 81,784 -> 94,129 -> 1,89,302 Cr
- Operating margin IMPROVED: 19% -> 23% -> 23% -> 23% -> 22% -> 25% -> 32% -> 31%
- Employees DECLINED: 29,035 -> 28,345 -> 27,384 -> 26,432 -> 25,412 -> 24,457 -> 23,766 -> 23,999

## INVESTIGATE:

1. HOW is revenue growing 67% (18,520 to 30,981) while production capacity DROPPED 46%?
   - Is HAL using percentage-of-completion accounting (booking revenue before delivery)?
   - Is the revenue mix shifting from production to MRO/repair (service revenue)?
   - Are they recognizing advance payments from government as revenue?

2. The order book went from 61K to 1,89K Cr (210% growth). But if they cant produce 41 units/year:
   - How many YEARS of backlog is that at current production rates?
   - Is this order book real or are these LOIs (Letters of Intent) that may never convert?
   - Is this the classic government defence contractor game - book massive orders, delay delivery, keep getting cost escalations?

3. Employees dropped 17% (29,035 to 23,999) while revenue grew 67%.
   - Is this genuine productivity improvement or are they outsourcing production?
   - Does less employees = less production capacity = cant execute the order book?

4. Operating margin went from 19% to 31%.
   - Is this genuine efficiency or is it accounting (percentage-of-completion inflating margins)?
   - For a government defence monopoly with cost-plus contracts, how can margins expand this much?

5. THE AGENCY PROBLEM:
   - HAL is a government company. Management has no skin in the game.
   - Are they optimizing for order book headlines (looks good in Parliament) while under-investing in production capacity?
   - Is the declining workforce + declining production + growing order book a HOODWINKING pattern?

6. EXPORT REALITY:
   - Exports: 314 -> 405 -> 212 -> 240 -> 168 -> 294 -> 311 -> 400 Cr
   - Exports are FLAT over 8 years at ~Rs 300 Cr on Rs 30,000 Cr revenue (1%)
   - Management keeps talking about export targets. Is this a QUIETLY DROPPED theme that they keep recycling?

Give me a BRUTALLY HONEST forensic assessment. Not retail cheerleading.

Return ONLY valid JSON, no markdown:
{
  "revenue_accounting_analysis": "how is revenue growing without production growth",
  "order_book_reality": "is the 1.89L Cr order book real or aspirational? years of backlog",
  "production_bottleneck": "why capacity dropped and what it means",
  "margin_forensics": "is 31% OPM genuine or accounting artifact",
  "agency_problem_score": "1-10 severity",
  "agency_problem_evidence": ["evidence1", "evidence2"],
  "export_credibility": "credible or recycled aspiration",
  "hoodwinking_indicators": ["indicator1", "indicator2"],
  "what_management_doesnt_want_you_to_know": "biggest thing buried in the numbers",
  "revised_trust_score_recommendation": "premium/discount given findings",
  "investment_implication": "what this means for buying HAL"
}"""

response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=4096,
    messages=[{"role": "user", "content": prompt}],
)
result = response.content[0].text
print(result)
Path("artifacts/HAL/forensic_deep_dive.json").write_text(result, encoding="utf-8")
