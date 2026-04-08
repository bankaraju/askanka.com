"""
NSE India API client — zero cost, no auth required.

Fetches:
- Annual report PDFs (5+ years)
- XBRL financial results (structured XML)
- Board meetings & corporate actions
- Shareholding patterns

Requires session cookie handling (hit homepage first).
"""

import json
import time
import requests
from pathlib import Path

BASE = "https://www.nseindia.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}


class NSEClient:
    """Session-based NSE API client with automatic cookie refresh."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self._init_session()

    def _init_session(self):
        """Hit homepage to get session cookies."""
        try:
            self.session.get(BASE, timeout=10)
            time.sleep(0.5)
        except Exception:
            pass

    def _get(self, endpoint: str, retries: int = 2) -> dict | list | None:
        """GET with automatic session refresh on 401/403."""
        url = f"{BASE}{endpoint}"
        for attempt in range(retries + 1):
            try:
                resp = self.session.get(url, timeout=15)
                if resp.status_code in (401, 403):
                    self._init_session()
                    continue
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                if attempt == retries:
                    print(f"  NSE API failed: {endpoint} — {e}")
                    return None
                time.sleep(1)
                self._init_session()
        return None

    def get_annual_reports(self, symbol: str) -> list[dict]:
        """Fetch annual report PDF download links.

        Returns: [{"year": "2024-2025", "url": "https://...", "source": "NSE"}]
        """
        raw = self._get(f"/api/annual-reports?index=equities&symbol={symbol}")
        if not raw:
            return []
        items = raw.get("data", raw) if isinstance(raw, dict) else raw
        if not isinstance(items, list):
            return []
        reports = []
        for item in items:
            if not isinstance(item, dict):
                continue
            year = f"{item.get('fromYr', '')}-{item.get('toYr', '')}"
            reports.append({
                "year": year,
                "url": item.get("fileName", ""),
                "source": "NSE",
                "format": "PDF",
            })
        return reports

    def get_financial_results(self, symbol: str, period: str = "Annual") -> list[dict]:
        """Fetch XBRL financial results (structured data).

        period: "Annual" or "Quarterly"
        Returns: [{"period": "FY2024", "type": "Consolidated", "xbrl_url": "...", ...}]
        """
        raw = self._get(f"/api/corporates-financial-results?index=equities&period={period}&symbol={symbol}")
        if not raw:
            return []
        items = raw.get("data", raw) if isinstance(raw, dict) else raw
        if not isinstance(items, list):
            return []
        results = []
        for item in items:
            if not isinstance(item, dict):
                continue
            results.append({
                "financial_year": item.get("financialYear", ""),
                "from_date": item.get("fromDate", ""),
                "to_date": item.get("toDate", ""),
                "type": item.get("relatingTo", ""),
                "audited": item.get("audited", ""),
                "xbrl_url": item.get("xbrl", ""),
                "filing_date": item.get("filingDate", ""),
                "is_bank": item.get("bank", "N") == "Y",
                "source": "NSE",
            })
        return results

    def get_shareholding(self, symbol: str) -> list[dict]:
        """Fetch shareholding pattern data."""
        data = self._get(f"/api/corporate-shareholding?index=equities&symbol={symbol}")
        if not data:
            return []
        return data if isinstance(data, list) else [data]

    def get_board_meetings(self, symbol: str) -> list[dict]:
        """Fetch board meeting dates and agendas."""
        data = self._get(f"/api/corporate-board-meetings?index=equities&symbol={symbol}")
        if not data:
            return []
        return data

    def get_corporate_actions(self, symbol: str) -> list[dict]:
        """Fetch corporate actions (dividends, splits, bonuses)."""
        data = self._get(f"/api/corporates-corporateActions?index=equities&symbol={symbol}")
        if not data:
            return []
        return data

    def download_pdf(self, url: str, save_path: Path) -> bool:
        """Download a PDF file from NSE archives.

        Auto-detects and extracts ZIP archives (NSE wraps some PDFs in ZIPs).
        Validates the PDF is readable before returning success.
        """
        try:
            resp = self.session.get(url, timeout=60)
            resp.raise_for_status()
            save_path.parent.mkdir(parents=True, exist_ok=True)

            content = resp.content

            # Check if it's a ZIP (starts with PK magic bytes)
            if content[:2] == b'PK':
                import zipfile
                import io
                with zipfile.ZipFile(io.BytesIO(content)) as zf:
                    pdf_files = [f for f in zf.namelist() if f.lower().endswith('.pdf')]
                    if pdf_files:
                        largest = max(pdf_files, key=lambda f: zf.getinfo(f).file_size)
                        content = zf.read(largest)
                        print(f"    Extracted from ZIP: {largest}")
                    else:
                        print(f"    ZIP contains no PDFs: {zf.namelist()}")
                        return False

            save_path.write_bytes(content)

            # Validate PDF is readable
            try:
                import pymupdf
                doc = pymupdf.open(str(save_path))
                pages = doc.page_count
                doc.close()
                if pages == 0:
                    print(f"    WARNING: PDF has 0 pages")
                    return False
            except ImportError:
                pass  # No pymupdf — skip validation
            except Exception as e:
                print(f"    WARNING: PDF validation failed: {e}")
                save_path.unlink(missing_ok=True)
                return False

            return True
        except Exception as e:
            print(f"  Download failed: {url} — {e}")
            return False
