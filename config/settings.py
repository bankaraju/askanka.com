"""OPUS ANKA configuration."""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
ARTIFACTS_DIR = PROJECT_ROOT / "artifacts"
FILINGS_DIR = ARTIFACTS_DIR / "filings"
REPORTS_DIR = ARTIFACTS_DIR / "reports"

# PostgreSQL
PG_HOST = os.getenv("PG_HOST", "localhost")
PG_V2_PORT = int(os.getenv("PG_V2_PORT", "5000"))
PG_V3_PORT = int(os.getenv("PG_V3_PORT", "9001"))
PG_USER = os.getenv("PG_USER", "postgres")
PG_PASSWORD = os.getenv("PG_PASSWORD", "")

# Neo4j
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")

# Azure OCR
AZURE_OCR_ENDPOINT = os.getenv("AZURE_OCR_ENDPOINT", "")
AZURE_OCR_KEY = os.getenv("AZURE_OCR_KEY", "")

# Claude API (for narrative extraction)
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
