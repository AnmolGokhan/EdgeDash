"""Single storage module — the only place sqlite3 is imported.

Swapping to Postgres in week 4 means replacing this file only.
Every other module calls these functions; none import a DB driver directly.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Generator, Sequence


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def _connect(path: str) -> Generator[sqlite3.Connection, None, None]:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_DDL = """
CREATE TABLE IF NOT EXISTS listings (
    id          TEXT PRIMARY KEY,
    title       TEXT,
    company     TEXT,
    location    TEXT,
    url         TEXT,
    description TEXT,
    source      TEXT,
    posted_at   TEXT,
    fetched_at  TEXT,
    fit_score   INTEGER,
    fit_reason  TEXT,
    scored_at   TEXT,
    components  TEXT
);

CREATE TABLE IF NOT EXISTS skill_gaps (
    skill       TEXT PRIMARY KEY,
    frequency   INTEGER NOT NULL DEFAULT 0,
    last_seen   TEXT
);

CREATE TABLE IF NOT EXISTS extraction_cache (
    description_hash TEXT PRIMARY KEY,
    payload          TEXT NOT NULL,
    created_at       TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS cycle_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    agent           TEXT    NOT NULL,
    started_at      TEXT    NOT NULL,
    finished_at     TEXT,
    records_touched INTEGER NOT NULL DEFAULT 0,
    status          TEXT    NOT NULL,
    notes           TEXT
);
"""


def _migrate_extraction_cache(conn: sqlite3.Connection) -> None:
    """Safely add the extraction cache table/columns on older SQLite databases."""
    table_exists = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='extraction_cache'"
    ).fetchone()
    if table_exists is None:
        conn.execute(
            """
            CREATE TABLE extraction_cache (
                description_hash TEXT PRIMARY KEY,
                payload          TEXT NOT NULL,
                created_at       TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        return

    columns = {
        row[1] for row in conn.execute("PRAGMA table_info(extraction_cache)").fetchall()
    }
    if "payload" not in columns:
        conn.execute(
            "ALTER TABLE extraction_cache ADD COLUMN payload TEXT NOT NULL DEFAULT '{}'"
        )
    if "created_at" not in columns:
        conn.execute(
            "ALTER TABLE extraction_cache ADD COLUMN created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP"
        )


def init_db(path: str) -> None:
    """Create all tables if they do not already exist."""
    with _connect(path) as conn:
        conn.executescript(_DDL)
        _migrate_extraction_cache(conn)


# ---------------------------------------------------------------------------
# Listing ID
# ---------------------------------------------------------------------------

def make_listing_id(source: str, url: str) -> str:
    """Return a stable SHA-256 hex digest for a (source, url) pair."""
    payload = f"{source}|{url}".encode()
    return hashlib.sha256(payload).hexdigest()


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def upsert_listings(path: str, rows: Sequence[dict[str, Any]]) -> int:
    """Insert listings, skipping duplicates by primary key.

    Returns the count of genuinely new rows inserted.
    Each row dict must contain at minimum: source, url, title, company,
    location, description, posted_at. The id and fetched_at are set here.
    """
    fetched_at = _now_iso()
    inserted = 0

    with _connect(path) as conn:
        for row in rows:
            listing_id = make_listing_id(row["source"], row["url"])
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO listings
                    (id, title, company, location, url,
                     description, source, posted_at, fetched_at,
                     fit_score, fit_reason)
                VALUES
                    (:id, :title, :company, :location, :url,
                     :description, :source, :posted_at, :fetched_at,
                     :fit_score, :fit_reason)
                """,
                {
                    "id": listing_id,
                    "title": row.get("title"),
                    "company": row.get("company"),
                    "location": row.get("location"),
                    "url": row["url"],
                    "description": row.get("description"),
                    "source": row["source"],
                    "posted_at": row.get("posted_at"),
                    "fetched_at": fetched_at,
                    "fit_score": row.get("fit_score"),
                    "fit_reason": row.get("fit_reason"),
                },
            )
            inserted += cursor.rowcount

    return inserted


def get_extraction_cache(path: str, description_hash: str) -> dict[str, Any] | None:
    """Return a cached extraction payload for a description hash, if present."""
    with _connect(path) as conn:
        row = conn.execute(
            "SELECT payload FROM extraction_cache WHERE description_hash = ?",
            (description_hash,),
        ).fetchone()

    if row is None:
        return None
    return json.loads(row["payload"])


def set_extraction_cache(path: str, description_hash: str, payload: dict[str, Any]) -> None:
    """Persist a normalized extraction result keyed by the job description hash."""
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    with _connect(path) as conn:
        conn.execute(
            """
            INSERT INTO extraction_cache (description_hash, payload, created_at)
            VALUES (:description_hash, :payload, :created_at)
            ON CONFLICT(description_hash)
            DO UPDATE SET payload = excluded.payload,
                          created_at = excluded.created_at
            """,
            {
                "description_hash": description_hash,
                "payload": encoded,
                "created_at": _now_iso(),
            },
        )


def get_unscored_listings(path: str, limit: int = 25) -> list[dict[str, Any]]:
    """Return unscored listings, oldest-first or insertion order for scoring."""
    with _connect(path) as conn:
        rows = conn.execute(
            "SELECT * FROM listings WHERE fit_score IS NULL ORDER BY fetched_at ASC, id ASC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def update_listing_score(
    path: str,
    listing_id: str,
    score: int,
    reason: str,
    components: dict[str, Any],
    scored_at: str,
) -> None:
    """Store score, reason, and component breakdown for one listing."""
    payload = json.dumps(components, ensure_ascii=False, sort_keys=True)
    with _connect(path) as conn:
        conn.execute(
            """
            UPDATE listings
            SET fit_score = :fit_score,
                fit_reason = :fit_reason,
                scored_at = :scored_at,
                components = :components
            WHERE id = :id
            """,
            {
                "fit_score": score,
                "fit_reason": reason,
                "scored_at": scored_at,
                "components": payload,
                "id": listing_id,
            },
        )


def count_unscored(path: str) -> int:
    """Return the number of listings that have not yet been scored."""
    with _connect(path) as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM listings WHERE fit_score IS NULL"
        ).fetchone()
    return int(row[0])


def last_fetch_time(path: str) -> str | None:
    """Return the most recent fetched_at timestamp, or None if no rows exist."""
    with _connect(path) as conn:
        row = conn.execute(
            "SELECT MAX(fetched_at) FROM listings"
        ).fetchone()
    return row[0]


def log_cycle(
    path: str,
    agent: str,
    started_at: str,
    finished_at: str,
    records_touched: int,
    status: str,
    notes: str | None = None,
) -> None:
    """Write one row to cycle_log for observability and auditing."""
    with _connect(path) as conn:
        conn.execute(
            """
            INSERT INTO cycle_log
                (agent, started_at, finished_at, records_touched, status, notes)
            VALUES
                (:agent, :started_at, :finished_at, :records_touched, :status, :notes)
            """,
            {
                "agent": agent,
                "started_at": started_at,
                "finished_at": finished_at,
                "records_touched": records_touched,
                "status": status,
                "notes": notes,
            },
        )


def get_listings(
    path: str,
    limit: int = 100,
    min_score: int | None = None,
) -> list[dict[str, Any]]:
    """Return listings ordered by fit_score descending.

    Filters to min_score when provided; includes unscored rows when omitted.
    """
    query = "SELECT * FROM listings"
    params: list[Any] = []

    if min_score is not None:
        query += " WHERE fit_score >= ?"
        params.append(min_score)

    query += " ORDER BY fit_score DESC NULLS LAST LIMIT ?"
    params.append(limit)

    with _connect(path) as conn:
        rows = conn.execute(query, params).fetchall()

    return [dict(row) for row in rows]
