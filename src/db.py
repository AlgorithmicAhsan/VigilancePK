"""Neon Postgres access (ADR-028).

One small connection pool, opened on first use so importing this module
never needs a database. Neon's pooled endpoint runs PgBouncer, which does
not keep server-side prepared statements between transactions, so psycopg's
automatic statement preparation is switched off.
"""
import os
from pathlib import Path
from dotenv import load_dotenv
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

load_dotenv()

SCHEMA_FILE = Path(__file__).with_name("schema.sql")

_pool = None


def pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        url = os.getenv("DATABASE_URL")
        if not url:
            raise RuntimeError("DATABASE_URL is not set.")
        _pool = ConnectionPool(
            url,
            min_size=0,
            max_size=5,
            open=True,
            # Neon sleeps when idle; check=... drops connections that died meanwhile.
            check=ConnectionPool.check_connection,
            kwargs={"prepare_threshold": None, "row_factory": dict_row},
        )
    return _pool


def connection():
    """`with db.connection() as conn:` commits on success, rolls back on error."""
    return pool().connection()


def init_schema():
    """Creates missing tables and indexes. Safe to run on every start."""
    with connection() as conn:
        conn.execute(SCHEMA_FILE.read_text(encoding="utf-8"))
