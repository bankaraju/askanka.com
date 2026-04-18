"""Generate per-stock research report HTML from all available artifacts.

Usage: python gen_stock_report.py <SYMBOL> [--provider gemini|claude]

Reads all JSON artifacts under artifacts/<SYMBOL>/ and generates a standalone
HTML scorecard at artifacts/<SYMBOL>/<SYMBOL>_RESEARCH_REPORT.html.
"""
import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / "config" / ".env")
load_dotenv(ROOT.parent / "pipeline" / ".env")

ARTIFACTS = ROOT / "artifacts"


def _call_gemini(prompt: str, max_tokens: int = 16000) -> str:
    import requests
    import time

    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY not set")
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
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError("Gemini call failed after 3 attempts")


def _call_claude(prompt: str, max_tokens: int = 16000) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    chunks = []
    with client.messages.stream(
        model="claude-haiku-4-5-20251001",
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        for text in stream.text_stream:
            chunks.append(text)
    return "".join(chunks)


def build_prompt(symbol: str, data: dict) -> str:
    data_str = json.dumps(data, indent=1, default=str)[:120000]

    final = data.get("FINAL_REPORT", data)
    trust = final.get("trust_score", data.get("trust_score", {}))
    if isinstance(trust, dict):
        score_pct = trust.get("trust_score_pct", trust.get("verdict", "?"))
        grade = trust.get("trust_score_grade", "?")
        verdict = trust.get("verdict", "?")
    else:
        score_pct = grade = verdict = "?"

    guidance = final.get("guidance_scorecard", data.get("guidance_scorecard", []))
    if isinstance(guidance, dict):
        guidance = guidance.get("items", guidance.get("scorecard", []))
    if not isinstance(guidance, list):
        guidance = []
    n_items = len(guidance)
    categories = set()
    for g in guidance:
        if isinstance(g, dict):
            categories.add(g.get("category", ""))

    financial = final.get("financial_snapshot", data.get("screener_financials", {}))
    street = final.get("street_consensus", data.get("street_consensus", {}))

    return (
        "You are writing a professional equity research report for OPUS ANKA Research.\n\n"
        f"Using ALL the data below, write a comprehensive research report on {symbol} "
        "in HTML format. This is a premium institutional-grade report.\n\n"
        f"## KEY FACTS:\n"
        f"- Symbol: {symbol}\n"
        f"- ANKA Trust Score: {score_pct} (Grade: {grade})\n"
        f"- Verdict: {verdict}\n"
        f"- Guidance items tracked: {n_items} across {len(categories)} categories\n"
        f"- Financial snapshot keys: {list(financial.keys())[:10]}\n"
        f"- Street consensus: {json.dumps(street, default=str)[:500]}\n\n"
        f"## FULL DATA:\n{data_str}\n\n"
        "## REPORT STRUCTURE:\n\n"
        "Write a complete HTML page with dark theme (background #0a0e1a, text #e5e7eb, "
        "gold accent #d4a855, green #10b981, red #ef4444) using DM Serif Display for "
        "headings and Inter for body text, JetBrains Mono for numbers. Include Google Fonts link.\n\n"
        "Include these sections:\n\n"
        "1. **Nav bar**: OPUS ANKA Research branding with gold accent\n"
        f"2. **Header**: Company name {symbol}, date April 2026, ANKA Trust Score as a colored badge, one-line verdict\n"
        "3. **Executive Summary**: 3-4 sentences — the single most important finding\n"
        "4. **Financial Snapshot**: Clean table with all available financial metrics from the data\n"
        "5. **Guidance Scorecard**: THE KEY TABLE. Every guidance item with columns: Year, Category, "
        "What Management Said, Target, Actual, Status. Color code: green=DELIVERED, bright green=EXCEEDED, "
        "amber=PARTIAL, red=MISSED, dark red with strikethrough=QUIETLY DROPPED, gray=TOO EARLY, "
        "muted=UNVERIFIABLE\n"
        "6. **Management Credibility Assessment**: Pattern analysis from the data\n"
        "7. **What Street Is Missing**: The differentiated view from the data\n"
        "8. **Street Consensus vs Our View**: Contrast if street data is available\n"
        "9. **Risk to Our Thesis**: What could prove the analysis wrong\n"
        "10. **ANKA Trust Score Verdict**: Score components breakdown in a visual box\n"
        "11. **Methodology**: Brief note — annual reports analyzed, guidance items extracted, "
        "cross-referenced against verified financial data\n"
        "12. **Disclaimer**: This is research, not investment advice. OPUS ANKA Research — askanka.com\n\n"
        "Style notes:\n"
        "- Make tables with subtle borders (rgba(255,255,255,0.05))\n"
        "- Use callout boxes (gold left border) for key findings\n"
        "- Monospace font for all numbers\n"
        "- Stat boxes at top for key metrics\n"
        "- Professional, honest, institutional tone\n"
        "- Total length: comprehensive, not abbreviated\n\n"
        "Return ONLY the complete HTML document starting with <!DOCTYPE html>. No markdown fences."
    )


def load_all_artifacts(symbol: str) -> dict:
    sym_dir = ARTIFACTS / symbol
    if not sym_dir.exists():
        print(f"ERROR: {sym_dir} not found")
        sys.exit(1)

    all_data = {"symbol": symbol}
    for f in sorted(sym_dir.glob("*.json")):
        if f.name.endswith("_RESEARCH_REPORT.json"):
            continue
        key = f.stem
        try:
            all_data[key] = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass

    for f in sorted(sym_dir.glob("ar_text_*.txt")):
        try:
            text = f.read_text(encoding="utf-8", errors="replace")[:20000]
            all_data.setdefault("annual_report_excerpts", {})[f.stem] = text
        except Exception:
            pass

    return all_data


def generate_report(symbol: str, provider: str = "gemini") -> Path:
    sym_dir = ARTIFACTS / symbol
    data = load_all_artifacts(symbol)

    if "FINAL_REPORT" not in data and "trust_score" not in data:
        print(f"ERROR: No FINAL_REPORT.json or trust_score.json for {symbol}")
        sys.exit(1)

    prompt = build_prompt(symbol, data)

    print(f"Generating report for {symbol} via {provider}...")
    if provider == "gemini":
        html = _call_gemini(prompt)
    else:
        html = _call_claude(prompt)

    if "<!DOCTYPE" in html and not html.strip().startswith("<!DOCTYPE"):
        html = html[html.index("<!DOCTYPE"):]

    out_path = sym_dir / f"{symbol}_RESEARCH_REPORT.html"
    out_path.write_text(html, encoding="utf-8")
    print(f"Report saved: {len(html):,} chars → {out_path}")
    return out_path


def main():
    parser = argparse.ArgumentParser(description="Generate OPUS ANKA stock research report")
    parser.add_argument("symbol", help="Stock symbol (e.g. RELIANCE, MARUTI)")
    parser.add_argument("--provider", choices=["gemini", "claude"], default="gemini",
                        help="LLM provider (default: gemini)")
    args = parser.parse_args()
    generate_report(args.symbol.upper(), args.provider)


if __name__ == "__main__":
    main()
