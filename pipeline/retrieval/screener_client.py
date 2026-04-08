"""
Screener.in scraper — 11 years of clean financial data, no auth needed.

Fetches:
- P&L, Balance Sheet, Cash Flow tables (10+ years)
- Key financial ratios
- Earnings call transcript PDF links
- Peer comparison data
"""

import re
import requests
from bs4 import BeautifulSoup

BASE = "https://www.screener.in"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html",
}


class ScreenerClient:
    """Screener.in HTML scraper for Indian equity data."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def get_financials(self, symbol: str, consolidated: bool = True) -> dict:
        """Scrape full financial data for a company.

        Returns: {
            "profit_loss": [...],
            "balance_sheet": [...],
            "cash_flow": [...],
            "ratios": [...],
            "quarterly": [...],
            "documents": [...],  # transcript/AR PDF links
            "peers": [...],
            "about": {...},
        }
        """
        suffix = "consolidated/" if consolidated else ""
        url = f"{BASE}/company/{symbol}/{suffix}"
        try:
            resp = self.session.get(url, timeout=15)
            resp.raise_for_status()
        except Exception as e:
            print(f"  Screener failed for {symbol}: {e}")
            return {}

        soup = BeautifulSoup(resp.text, "html.parser")
        return {
            "about": self._parse_about(soup),
            "profit_loss": self._parse_table(soup, "profit-loss"),
            "balance_sheet": self._parse_table(soup, "balance-sheet"),
            "cash_flow": self._parse_table(soup, "cash-flow"),
            "ratios": self._parse_table(soup, "ratios"),
            "quarterly": self._parse_table(soup, "quarters"),
            "documents": self._parse_documents(soup),
            "peers": self._parse_peers(soup),
        }

    def _parse_about(self, soup: BeautifulSoup) -> dict:
        """Extract company description and key stats."""
        about = {}
        desc = soup.find("div", class_="about")
        if desc:
            about["description"] = desc.get_text(strip=True)

        # Key stats from top section
        for li in soup.select(".company-ratios li"):
            name_el = li.find("span", class_="name")
            val_el = li.find("span", class_="number")
            if name_el and val_el:
                about[name_el.get_text(strip=True)] = val_el.get_text(strip=True)

        return about

    def _parse_table(self, soup: BeautifulSoup, section_id: str) -> list[dict]:
        """Parse a Screener financial table into list of dicts."""
        section = soup.find("section", id=section_id)
        if not section:
            return []

        table = section.find("table")
        if not table:
            return []

        # Headers = date columns
        headers = []
        thead = table.find("thead")
        if thead:
            for th in thead.find_all("th"):
                headers.append(th.get_text(strip=True))

        # Rows
        rows = []
        tbody = table.find("tbody")
        if not tbody:
            return []

        for tr in tbody.find_all("tr"):
            cells = tr.find_all("td")
            if not cells:
                continue
            row = {}
            for i, td in enumerate(cells):
                key = headers[i] if i < len(headers) else f"col_{i}"
                row[key] = td.get_text(strip=True)
            rows.append(row)

        return rows

    def _parse_documents(self, soup: BeautifulSoup) -> list[dict]:
        """Extract document links (transcripts, annual reports, presentations)."""
        docs = []
        doc_section = soup.find("section", id="documents")
        if not doc_section:
            return []

        for li in doc_section.find_all("li"):
            link = li.find("a")
            if not link:
                continue
            href = link.get("href", "")
            text = link.get_text(strip=True)

            doc_type = "other"
            if "transcript" in text.lower() or "concall" in text.lower():
                doc_type = "transcript"
            elif "annual" in text.lower():
                doc_type = "annual_report"
            elif "investor" in text.lower() or "presentation" in text.lower():
                doc_type = "investor_presentation"

            docs.append({
                "title": text,
                "url": href,
                "type": doc_type,
            })

        return docs

    def _parse_peers(self, soup: BeautifulSoup) -> list[dict]:
        """Extract peer comparison data."""
        peers = []
        peer_section = soup.find("section", id="peers")
        if not peer_section:
            return []

        table = peer_section.find("table")
        if not table:
            return []

        headers = [th.get_text(strip=True) for th in table.find_all("th")]
        for tr in table.find("tbody", recursive=False).find_all("tr") if table.find("tbody") else []:
            cells = tr.find_all("td")
            peer = {}
            for i, td in enumerate(cells):
                key = headers[i] if i < len(headers) else f"col_{i}"
                peer[key] = td.get_text(strip=True)
            if peer:
                peers.append(peer)

        return peers

    def get_transcript_urls(self, symbol: str) -> list[dict]:
        """Get just the transcript PDF links."""
        data = self.get_financials(symbol)
        return [d for d in data.get("documents", []) if d["type"] == "transcript"]
