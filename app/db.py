"""Database access layer.

Deliberately framework-light: plain SQL over ``psycopg2`` with a small pool.
The schema lives here so the prototype is self-contained, but the queries are
vanilla Postgres SQL and will run unchanged against Databricks Lakebase.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Iterator, Optional

import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor

from app.config import get_settings

logger = logging.getLogger(__name__)

# --- Schema -----------------------------------------------------------------
# Created idempotently on startup. Extend this list when you add tables.
SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS tickets (
        id            SERIAL PRIMARY KEY,
        employee_name TEXT         NOT NULL,
        issue_text    TEXT         NOT NULL,
        category      TEXT,
        priority      TEXT,
        suggested_fix TEXT,
        status        TEXT         NOT NULL DEFAULT 'new'
                        CHECK (status IN ('new', 'classified', 'resolved')),
        created_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
        updated_at    TIMESTAMPTZ  NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets (status)
    """,
    # Keeps `updated_at` honest without app-side bookkeeping.
    """
    CREATE OR REPLACE FUNCTION touch_updated_at()
    RETURNS TRIGGER AS $$
    BEGIN
        NEW.updated_at = now();
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql
    """,
    """
    DROP TRIGGER IF EXISTS trg_tickets_touch_updated_at ON tickets
    """,
    """
    CREATE TRIGGER trg_tickets_touch_updated_at
        BEFORE UPDATE ON tickets
        FOR EACH ROW
        EXECUTE FUNCTION touch_updated_at()
    """,
]

# Valid status transitions, enforced in the data layer.
VALID_STATUSES = {"new", "classified", "resolved"}

_connection_pool: Optional[pool.ThreadedConnectionPool] = None


def init_pool(minconn: int = 1, maxconn: int = 10) -> None:
    """Initialise the global connection pool and create the schema."""
    global _connection_pool
    if _connection_pool is not None:
        return

    settings = get_settings()
    logger.info("Initialising Postgres connection pool")
    _connection_pool = pool.ThreadedConnectionPool(
        minconn=minconn,
        maxconn=maxconn,
        dsn=settings.database_url,
    )
    init_schema()


def init_schema() -> None:
    """Create tables/indexes if they don't already exist."""
    with get_cursor() as cur:
        for statement in SCHEMA_STATEMENTS:
            cur.execute(statement)
    logger.info("Schema is ready")


def close_pool() -> None:
    global _connection_pool
    if _connection_pool is not None:
        _connection_pool.closeall()
        _connection_pool = None


@contextmanager
def get_cursor(dict_cursor: bool = True) -> Iterator[Any]:
    """Yield a cursor and commit/rollback automatically.

    Raises a clear error if the pool was never initialised, which makes
    "forgot to call init_pool()" failures obvious instead of mysterious.
    """
    if _connection_pool is None:
        raise RuntimeError(
            "Database pool not initialised. Call init_pool() at startup."
        )

    conn = _connection_pool.getconn()
    try:
        yield conn.cursor(cursor_factory=RealDictCursor if dict_cursor else None)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _connection_pool.putconn(conn)


# --- Ticket operations -------------------------------------------------------

def create_ticket(employee_name: str, issue_text: str) -> dict:
    """Insert a new ticket with status='new' and return the row."""
    sql = """
        INSERT INTO tickets (employee_name, issue_text, status)
        VALUES (%s, %s, 'new')
        RETURNING id, employee_name, issue_text, category, priority,
                  suggested_fix, status, created_at, updated_at
    """
    with get_cursor() as cur:
        cur.execute(sql, (employee_name, issue_text))
        return dict(cur.fetchone())


def get_ticket(ticket_id: int) -> Optional[dict]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT id, employee_name, issue_text, category, priority,
                   suggested_fix, status, created_at, updated_at
            FROM tickets
            WHERE id = %s
            """,
            (ticket_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def list_tickets() -> list[dict]:
    """All tickets, newest first."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT id, employee_name, issue_text, category, priority,
                   suggested_fix, status, created_at, updated_at
            FROM tickets
            ORDER BY id DESC
            """
        )
        return [dict(r) for r in cur.fetchall()]


def get_new_ticket_ids(batch_size: int = 50) -> list[int]:
    """IDs of tickets still awaiting classification."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT id FROM tickets
            WHERE status = 'new'
            ORDER BY id
            LIMIT %s
            """,
            (batch_size,),
        )
        return [r["id"] for r in cur.fetchall()]


def update_ticket_classification(
    ticket_id: int,
    category: str,
    priority: str,
    suggested_fix: str,
) -> None:
    """Persist classification results and move the ticket to 'classified'."""
    sql = """
        UPDATE tickets
        SET category      = %s,
            priority      = %s,
            suggested_fix = %s,
            status        = 'classified'
        WHERE id = %s
    """
    with get_cursor() as cur:
        cur.execute(sql, (category, priority, suggested_fix, ticket_id))


def update_ticket_status(ticket_id: int, status: str) -> None:
    """Set an arbitrary status (used by the 'resolve' action)."""
    if status not in VALID_STATUSES:
        raise ValueError(
            f"Invalid status {status!r}; expected one of {sorted(VALID_STATUSES)}"
        )
    with get_cursor() as cur:
        cur.execute(
            "UPDATE tickets SET status = %s WHERE id = %s",
            (status, ticket_id),
        )
