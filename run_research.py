"""
OPUS ANKA — Run ANKA Trust Score Research for any Indian listed company.

Usage:
    python run_research.py HAL
    python run_research.py HDFCBANK
    python run_research.py "Hindustan Aeronautics"

Everything is automatic. Output goes to artifacts/<symbol>/ as JSON files.
No database required.
"""

import json
import sys
import time
from pathlib import Path
from datetime import datetime, timezone, timedelta

from pipeline.retrieval.nse_client import NSEClient
from pipeline.retrieval.bse_client import BSEClient
from pipeline.retrieval.screener_client import ScreenerClient

IST = timezone(timedelta(hours=5, minutes=30))
ARTIFACTS = Path(__file__).parent / "artifacts"

# ── Symbol lookup for common names ──────────────────────────────────
KNOWN_COMPANIES = {
    "hindustan aeronautics": ("HAL", "541154"),
    "hal": ("HAL", "541154"),
    "hdfc bank": ("HDFCBANK", "500180"),
    "hdfcbank": ("HDFCBANK", "500180"),
    "tcs": ("TCS", "532540"),
    "infosys": ("INFY", "500209"),
    "infy": ("INFY", "500209"),
    "reliance": ("RELIANCE", "500325"),
    "icici bank": ("ICICIBANK", "532174"),
    "icicibank": ("ICICIBANK", "532174"),
    "sbi": ("SBIN", "500112"),
    "sbin": ("SBIN", "500112"),
    "bajaj finance": ("BAJFINANCE", "500034"),
    "bajfinance": ("BAJFINANCE", "500034"),
    "sun pharma": ("SUNPHARMA", "524715"),
    "sunpharma": ("SUNPHARMA", "524715"),
    "wipro": ("WIPRO", "507685"),
    "hcl tech": ("HCLTECH", "532281"),
    "hcltech": ("HCLTECH", "532281"),
    "bel": ("BEL", "500049"),
    "bharat electronics": ("BEL", "500049"),
    "ongc": ("ONGC", "500312"),
    "coal india": ("COALINDIA", "533278"),
    "coalindia": ("COALINDIA", "533278"),
    "tatamotors": ("TATAMOTORS", "500570"),
    "tata motors": ("TATAMOTORS", "500570"),
    "maruti": ("MARUTI", "532500"),
    "itc": ("ITC", "500875"),
    "larsen": ("LT", "500510"),
    "lt": ("LT", "500510"),
    "axis bank": ("AXISBANK", "532215"),
    "axisbank": ("AXISBANK", "532215"),
    "kotak": ("KOTAKBANK", "500247"),
    "kotakbank": ("KOTAKBANK", "500247"),
}


def resolve_symbol(name: str) -> tuple[str, str]:
    """Resolve company name/symbol to (NSE symbol, BSE scrip code)."""
    key = name.strip().lower()
    if key in KNOWN_COMPANIES:
        return KNOWN_COMPANIES[key]
    # If it looks like an NSE symbol already (all caps, no spaces)
    if name.isupper() and " " not in name:
        return (name, "")
    print(f"  WARNING: '{name}' not in known companies. Trying as NSE symbol.")
    return (name.upper().replace(" ", ""), "")


def run(company_input: str):
    """Run full ANKA Trust Score research pipeline."""
    nse_symbol, bse_scrip = resolve_symbol(company_input)
    out_dir = ARTIFACTS / nse_symbol
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"{'='*70}")
    print(f"  OPUS ANKA — ANKA Trust Score Research")
    print(f"  Company: {company_input} → NSE:{nse_symbol} BSE:{bse_scrip}")
    print(f"  Output:  {out_dir}")
    print(f"{'='*70}")

    nse = NSEClient()
    bse = BSEClient()
    screener = ScreenerClient()

    # ── Step 1: Fetch Screener financials (richest single source) ────
    print(f"\n  [1/6] Fetching Screener financials...")
    screener_data = screener.get_financials(nse_symbol)
    if screener_data:
        (out_dir / "screener_financials.json").write_text(
            json.dumps(screener_data, indent=2, ensure_ascii=False), encoding="utf-8")
        pl_rows = len(screener_data.get("profit_loss", []))
        bs_rows = len(screener_data.get("balance_sheet", []))
        docs = len(screener_data.get("documents", []))
        print(f"         P&L: {pl_rows} rows | BS: {bs_rows} rows | Docs: {docs}")
    else:
        print(f"         FAILED — will rely on NSE/BSE")
    time.sleep(1)

    # ── Step 2: Fetch NSE annual reports ─────────────────────────────
    print(f"\n  [2/6] Fetching NSE annual reports...")
    nse_reports = nse.get_annual_reports(nse_symbol)
    if nse_reports:
        (out_dir / "nse_annual_reports.json").write_text(
            json.dumps(nse_reports, indent=2), encoding="utf-8")
        print(f"         {len(nse_reports)} annual reports found")

        # Download the PDFs (latest 3 for MD&A extraction)
        pdf_dir = out_dir / "pdfs"
        pdf_dir.mkdir(exist_ok=True)
        for report in nse_reports[:3]:
            url = report.get("url", "")
            if url:
                year = report.get("year", "unknown")
                pdf_path = pdf_dir / f"annual_report_{year}.pdf"
                if not pdf_path.exists():
                    print(f"         Downloading {year}...")
                    nse.download_pdf(url, pdf_path)
                    time.sleep(0.5)
    else:
        print(f"         No reports from NSE")
    time.sleep(1)

    # ── Step 3: Fetch NSE XBRL financial results ────────────────────
    print(f"\n  [3/6] Fetching NSE XBRL financials...")
    xbrl_annual = nse.get_financial_results(nse_symbol, "Annual")
    xbrl_quarterly = nse.get_financial_results(nse_symbol, "Quarterly")
    if xbrl_annual or xbrl_quarterly:
        (out_dir / "nse_xbrl_results.json").write_text(
            json.dumps({"annual": xbrl_annual, "quarterly": xbrl_quarterly}, indent=2),
            encoding="utf-8")
        print(f"         Annual: {len(xbrl_annual)} | Quarterly: {len(xbrl_quarterly)}")
    else:
        print(f"         No XBRL data")
    time.sleep(1)

    # ── Step 4: Fetch BSE annual reports (fill gaps) ─────────────────
    print(f"\n  [4/6] Fetching BSE annual reports...")
    if bse_scrip:
        bse_reports = bse.get_annual_reports(bse_scrip)
        if bse_reports:
            (out_dir / "bse_annual_reports.json").write_text(
                json.dumps(bse_reports, indent=2), encoding="utf-8")
            print(f"         {len(bse_reports)} annual reports found")
        else:
            print(f"         No reports from BSE")
    else:
        print(f"         Skipped (no BSE scrip code)")
    time.sleep(1)

    # ── Step 5: Fetch transcript links ───────────────────────────────
    print(f"\n  [5/6] Collecting transcript links...")
    transcripts = [d for d in screener_data.get("documents", []) if d["type"] == "transcript"]
    all_docs = screener_data.get("documents", [])
    if transcripts:
        (out_dir / "transcripts.json").write_text(
            json.dumps(transcripts, indent=2), encoding="utf-8")
        print(f"         {len(transcripts)} transcripts found")

        # Download transcript PDFs
        pdf_dir = out_dir / "pdfs"
        for t in transcripts[:8]:
            url = t.get("url", "")
            if url:
                slug = t.get("title", "transcript")[:50].replace(" ", "_").replace("/", "-")
                pdf_path = pdf_dir / f"transcript_{slug}.pdf"
                if not pdf_path.exists():
                    print(f"         Downloading: {t['title'][:60]}...")
                    nse.download_pdf(url, pdf_path)
                    time.sleep(0.5)
    else:
        print(f"         No transcripts found")

    # ── Step 6: Fetch shareholding + corporate actions ───────────────
    print(f"\n  [6/6] Fetching shareholding & corporate actions...")
    shareholding = nse.get_shareholding(nse_symbol)
    corp_actions = nse.get_corporate_actions(nse_symbol)
    board_meetings = nse.get_board_meetings(nse_symbol)

    (out_dir / "shareholding.json").write_text(
        json.dumps(shareholding, indent=2, default=str), encoding="utf-8")
    (out_dir / "corporate_actions.json").write_text(
        json.dumps(corp_actions, indent=2, default=str), encoding="utf-8")
    (out_dir / "board_meetings.json").write_text(
        json.dumps(board_meetings, indent=2, default=str), encoding="utf-8")
    print(f"         Shareholding: {len(shareholding)} records")
    print(f"         Corp actions: {len(corp_actions)} records")
    print(f"         Board meetings: {len(board_meetings)} records")

    # ── Summary ──────────────────────────────────────────────────────
    manifest = {
        "company": company_input,
        "nse_symbol": nse_symbol,
        "bse_scrip": bse_scrip,
        "generated_at": datetime.now(IST).isoformat(),
        "data_collected": {
            "screener_pl_rows": len(screener_data.get("profit_loss", [])),
            "screener_bs_rows": len(screener_data.get("balance_sheet", [])),
            "screener_cf_rows": len(screener_data.get("cash_flow", [])),
            "screener_docs": len(all_docs),
            "nse_annual_reports": len(nse_reports),
            "nse_xbrl_annual": len(xbrl_annual),
            "nse_xbrl_quarterly": len(xbrl_quarterly),
            "bse_annual_reports": len(bse_reports) if bse_scrip else 0,
            "transcripts": len(transcripts),
            "shareholding_records": len(shareholding),
            "corporate_actions": len(corp_actions),
        },
        "files": [str(p.relative_to(out_dir)) for p in out_dir.rglob("*") if p.is_file()],
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"\n{'='*70}")
    print(f"  DATA COLLECTION COMPLETE")
    print(f"  Output: {out_dir}")
    print(f"  Files:  {len(manifest['files'])}")
    print(f"{'='*70}")
    print(f"\n  Next: Run narrative extraction on downloaded PDFs")
    print(f"        python -m pipeline.narrative.extract_from_pdfs {nse_symbol}")

    return manifest


if __name__ == "__main__":
    company = sys.argv[1] if len(sys.argv) > 1 else "HAL"
    run(company)
