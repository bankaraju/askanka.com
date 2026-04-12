"""
Step 6: News Archive Ingestion
Pull 5-year news archive, filter for material events.

Material events: contract wins, expansions, regulatory actions,
management changes, M&A, restructuring.
"""


def fetch_news_archive(company_name: str, nse_symbol: str, years: int = 5) -> list:
    """Fetch and filter material news events.

    Returns list of dicts: [{"date": "...", "headline": "...", "source": "...", "material": bool}]
    """
    # TODO: Implement news archive with materiality filter
    return []
