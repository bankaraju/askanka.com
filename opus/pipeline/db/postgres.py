"""PostgreSQL connection manager for OPUS ANKA.

V2 Forensics: Port 5000
V3 Trading: Port 9001
"""

import os
from contextlib import contextmanager

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    HAS_PG = True
except ImportError:
    HAS_PG = False


def get_v2_connection():
    """Connect to V2 Forensics database (Port 5000)."""
    if not HAS_PG:
        raise ImportError("psycopg2 not installed: pip install psycopg2-binary")
    return psycopg2.connect(
        host=os.getenv("PG_HOST", "localhost"),
        port=int(os.getenv("PG_V2_PORT", "5000")),
        database=os.getenv("PG_V2_DB", "opus_anka_forensics"),
        user=os.getenv("PG_USER", "postgres"),
        password=os.getenv("PG_PASSWORD", ""),
    )


def get_v3_connection():
    """Connect to V3 Trading database (Port 9001)."""
    if not HAS_PG:
        raise ImportError("psycopg2 not installed: pip install psycopg2-binary")
    return psycopg2.connect(
        host=os.getenv("PG_HOST", "localhost"),
        port=int(os.getenv("PG_V3_PORT", "9001")),
        database=os.getenv("PG_V3_DB", "opus_anka_trading"),
        user=os.getenv("PG_USER", "postgres"),
        password=os.getenv("PG_PASSWORD", ""),
    )


@contextmanager
def v2_cursor():
    """Context manager for V2 forensics queries."""
    conn = get_v2_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            yield cur
        conn.commit()
    finally:
        conn.close()


@contextmanager
def v3_cursor():
    """Context manager for V3 trading queries."""
    conn = get_v3_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            yield cur
        conn.commit()
    finally:
        conn.close()


def init_schemas():
    """Initialize database schemas from SQL file."""
    from pathlib import Path
    sql = (Path(__file__).parent / "schemas.sql").read_text(encoding="utf-8")

    for get_conn in [get_v2_connection, get_v3_connection]:
        try:
            conn = get_conn()
            with conn.cursor() as cur:
                cur.execute(sql)
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Schema init warning: {e}")
