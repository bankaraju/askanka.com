"""
Step 5: Transcript Retrieval
Fetch earnings call transcripts — minimum 8 quarters.

These feed the narrative engine (Steps 9-10) for claim extraction
and promise-vs-delivery scoring.
"""


def fetch_transcripts(nse_symbol: str, min_quarters: int = 8) -> list:
    """Fetch earnings call transcripts.

    Returns list of dicts: [{"quarter": "Q3FY25", "text": "...", "source": "..."}]
    """
    # TODO: Implement transcript fetching
    # Sources: BSE corporate announcements, company IR pages, aggregators
    return []
