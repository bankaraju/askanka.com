"""
BSE India API client — zero cost, no auth required.

Fetches:
- Annual report PDFs
- Financial results (quarterly + annual)
- Corporate actions
"""

import time
import requests
from pathlib import Path

BASE = "https://api.bseindia.com/BseIndiaAPI/api"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Referer": "https://www.bseindia.com/",
}


class BSEClient:
    """BSE India API client."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def _get(self, endpoint: str) -> dict | list | str | None:
        """GET request to BSE API."""
        url = f"{BASE}/{endpoint}"
        try:
            resp = self.session.get(url, timeout=15)
            resp.raise_for_status()
            try:
                return resp.json()
            except Exception:
                return resp.text
        except Exception as e:
            print(f"  BSE API failed: {endpoint} — {e}")
            return None

    def get_annual_reports(self, scrip_code: str) -> list[dict]:
        """Fetch annual report PDF links.

        Returns: [{"year": "2024", "url": "https://...", "source": "BSE"}]
        """
        data = self._get(f"AnnualReport/w?scripcode={scrip_code}&flag=New")
        if not data or not isinstance(data, list):
            return []
        reports = []
        for item in data:
            url = item.get("FilePath", "")
            if url and not url.startswith("http"):
                url = f"https://www.bseindia.com{url}"
            reports.append({
                "year": item.get("Year", ""),
                "url": url,
                "source": "BSE",
                "format": "PDF",
            })
        return reports

    def get_financial_results(self, scrip_code: str) -> list[dict]:
        """Fetch financial result filing links."""
        data = self._get(f"FinancialResult/w?scripcode={scrip_code}&flag=New")
        if not data:
            return []
        return data if isinstance(data, list) else []

    def get_corporate_actions(self, scrip_code: str) -> list[dict]:
        """Fetch corporate actions."""
        data = self._get(f"CorporateAction/w?scripcode={scrip_code}")
        if not data:
            return []
        return data if isinstance(data, list) else []

    def download_pdf(self, url: str, save_path: Path) -> bool:
        """Download a PDF file from BSE archives."""
        try:
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
            save_path.parent.mkdir(parents=True, exist_ok=True)
            save_path.write_bytes(resp.content)
            return True
        except Exception as e:
            print(f"  Download failed: {url} — {e}")
            return False
