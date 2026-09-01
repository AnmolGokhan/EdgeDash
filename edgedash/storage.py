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
from pathlib import Path
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


@contextmanager
def _connect_readonly(path: str) -> Generator[sqlite3.Connection, None, None]:
    """Open SQLite without allowing a read-only diagnostic to write."""
    uri = f"file:{Path(path).resolve().as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
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
    run_id              TEXT NOT NULL,
    computed_at         TEXT NOT NULL,
    skill               TEXT NOT NULL,
    listings_blocked    INTEGER NOT NULL,
    opportunity_cost    REAL NOT NULL,
    mean_score          REAL NOT NULL,
    top_score           INTEGER NOT NULL,
    example_ids         TEXT NOT NULL,
    also_nice_to_have   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (run_id, skill)
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

CREATE TABLE IF NOT EXISTS query_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    question        TEXT NOT NULL,
    tool_chosen     TEXT,
    params          TEXT NOT NULL,
    answerable      INTEGER NOT NULL,
    duration        REAL NOT NULL,
    created_at      TEXT NOT NULL
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


def _migrate_listing_scores(conn: sqlite3.Connection) -> None:
    """Add score columns to databases created before component scoring."""
    columns = {
        row[1] for row in conn.execute("PRAGMA table_info(listings)").fetchall()
    }
    for name, definition in (
        ("scored_at", "TEXT"),
        ("components", "TEXT"),
    ):
        if name not in columns:
            conn.execute(f"ALTER TABLE listings ADD COLUMN {name} {definition}")


def _migrate_skill_gaps(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(skill_gaps)").fetchall()}
    if columns and "run_id" not in columns:
        conn.execute("ALTER TABLE skill_gaps RENAME TO skill_gaps_legacy")
        conn.execute(
            """
            CREATE TABLE skill_gaps (
                run_id TEXT NOT NULL, computed_at TEXT NOT NULL, skill TEXT NOT NULL,
                listings_blocked INTEGER NOT NULL, opportunity_cost REAL NOT NULL,
                mean_score REAL NOT NULL, top_score INTEGER NOT NULL,
                example_ids TEXT NOT NULL, also_nice_to_have INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (run_id, skill)
            )
            """
        )


def init_db(path: str) -> None:
    """Create all tables if they do not already exist."""
    with _connect(path) as conn:
        conn.executescript(_DDL)
        _migrate_listing_scores(conn)
        _migrate_skill_gaps(conn)
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


def get_extracted_skill_counts(path: str) -> list[dict[str, Any]]:
    """Return raw required-skill counts from extraction cache payloads."""
    with _connect_readonly(path) as conn:
        rows = conn.execute(
            """
            SELECT json_each.value AS skill, COUNT(*) AS count
            FROM extraction_cache, json_each(extraction_cache.payload, '$.required_skills')
            WHERE json_each.type = 'text'
            GROUP BY json_each.value
            ORDER BY count DESC, skill COLLATE NOCASE
            """
        ).fetchall()
    return [dict(row) for row in rows]


def get_scored_listings_with_facts(path: str) -> list[dict[str, Any]]:
    """Return scored listings joined to their cached extracted facts."""
    with _connect(path) as conn:
        listings = conn.execute(
            "SELECT id, description, fit_score FROM listings WHERE fit_score IS NOT NULL"
        ).fetchall()
        result: list[dict[str, Any]] = []
        for listing in listings:
            digest = hashlib.sha256((listing["description"] or "").strip().encode("utf-8")).hexdigest()
            cached = conn.execute(
                "SELECT payload FROM extraction_cache WHERE description_hash = ?", (digest,)
            ).fetchone()
            if cached is None:
                continue
            facts = json.loads(cached["payload"])
            result.append({"id": listing["id"], "fit_score": listing["fit_score"], **facts})
    return result


def write_skill_gap_snapshot(path: str, run_id: str, computed_at: str, rows: Sequence[dict[str, Any]]) -> None:
    """Append a timestamped skill-gap snapshot without replacing prior runs."""
    with _connect(path) as conn:
        conn.executemany(
            """
            INSERT INTO skill_gaps
                (run_id, computed_at, skill, listings_blocked, opportunity_cost,
                 mean_score, top_score, example_ids, also_nice_to_have)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    run_id, computed_at, row["skill"], row["listings_blocked"],
                    row["opportunity_cost"], row["mean_score"], row["top_score"],
                    json.dumps(row["example_ids"]), row["also_nice_to_have"],
                )
                for row in rows
            ],
        )


def get_latest_skill_gap_snapshot(path: str) -> list[dict[str, Any]]:
    """Return the most recent persisted skill-gap snapshot."""
    with _connect(path) as conn:
        run = conn.execute("SELECT run_id FROM skill_gaps ORDER BY computed_at DESC LIMIT 1").fetchone()
        if run is None:
            return []
        rows = conn.execute(
            "SELECT * FROM skill_gaps WHERE run_id = ? ORDER BY opportunity_cost DESC",
            (run["run_id"],),
        ).fetchall()
    result = [dict(row) for row in rows]
    for row in result:
        row["example_ids"] = json.loads(row["example_ids"])
    return result


def get_skill_gap_snapshots(path: str) -> list[dict[str, Any]]:
    """Return all persisted skill-gap snapshots in chronological order."""
    with _connect(path) as conn:
        rows = conn.execute(
            """
            SELECT * FROM skill_gaps
            ORDER BY computed_at ASC, run_id ASC, opportunity_cost DESC, skill ASC
            """
        ).fetchall()

    snapshots: list[dict[str, Any]] = []
    for row in rows:
        data = dict(row)
        data["example_ids"] = json.loads(data["example_ids"])
        if not snapshots or snapshots[-1]["run_id"] != data["run_id"]:
            snapshots.append(
                {
                    "run_id": data["run_id"],
                    "computed_at": data["computed_at"],
                    "rows": [],
                }
            )
        snapshots[-1]["rows"].append(data)
    return snapshots


def get_unscored_listings(path: str, limit: int = 25) -> list[dict[str, Any]]:
    """Return unscored listings, oldest-first or insertion order for scoring."""
    with _connect(path) as conn:
        rows = conn.execute(
            "SELECT * FROM listings WHERE fit_score IS NULL ORDER BY fetched_at ASC, id ASC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_scored_listings(path: str, limit: int = 25) -> list[dict[str, Any]]:
    """Return scored listings for an explicit operator retry."""
    with _connect(path) as conn:
        rows = conn.execute(
            "SELECT * FROM listings WHERE fit_score IS NOT NULL ORDER BY scored_at ASC, id ASC LIMIT ?",
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


def clear_listing_scores(path: str, listing_id: str | None = None) -> int:
    """Clear score fields without deleting extraction cache or listing data."""
    query = """
        UPDATE listings
        SET fit_score = NULL,
            fit_reason = NULL,
            scored_at = NULL,
            components = NULL
    """
    params: tuple[str, ...] = ()
    if listing_id is not None:
        query += " WHERE id = ?"
        params = (listing_id,)

    with _connect(path) as conn:
        cursor = conn.execute(query, params)
    return int(cursor.rowcount)


def clear_all_data(path: str) -> None:
    """Remove all stored job data while preserving the database schema."""
    with _connect(path) as conn:
        conn.execute("DELETE FROM listings")
        conn.execute("DELETE FROM extraction_cache")
        conn.execute("DELETE FROM skill_gaps")
        conn.execute("DELETE FROM cycle_log")


def get_data_counts(path: str) -> dict[str, int]:
    """Return row counts for stored data tables without loading their contents."""
    with _connect_readonly(path) as conn:
        return {
            table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in ("listings", "extraction_cache", "skill_gaps", "cycle_log")
        }


def log_query(
    path: str,
    question: str,
    tool_chosen: str | None,
    params: dict[str, Any],
    answerable: bool,
    duration: float,
) -> None:
    """Record one natural-language query for operational auditing."""
    with _connect(path) as conn:
        conn.execute(
            """
            INSERT INTO query_log
                (question, tool_chosen, params, answerable, duration, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                question,
                tool_chosen,
                json.dumps(params, sort_keys=True),
                int(answerable),
                duration,
                _now_iso(),
            ),
        )


def get_listing_diagnostics(path: str) -> dict[str, Any]:
    """Return a read-only summary of listings for operational diagnostics."""
    with _connect(path) as conn:
        total = conn.execute("SELECT COUNT(*) FROM listings").fetchone()[0]

        source_counts = conn.execute(
            "SELECT source, COUNT(*) FROM listings GROUP BY source ORDER BY source"
        ).fetchall()

        duplicate_rows = conn.execute(
            """
            SELECT COUNT(*)
            FROM (
                SELECT LOWER(TRIM(COALESCE(title, ''))) AS title_norm,
                       LOWER(TRIM(COALESCE(company, ''))) AS company_norm,
                       COUNT(DISTINCT source) AS source_count,
                       COUNT(*) AS row_count
                FROM listings
                WHERE COALESCE(title, '') <> '' OR COALESCE(company, '') <> ''
                GROUP BY LOWER(TRIM(COALESCE(title, ''))), LOWER(TRIM(COALESCE(company, '')))
                HAVING COUNT(DISTINCT source) > 1
            )
            """
        ).fetchone()[0]

        recent = conn.execute(
            """
            SELECT source, title, company, fetched_at, posted_at
            FROM listings
            ORDER BY COALESCE(fetched_at, '0000-00-00T00:00:00Z') DESC, id DESC
            LIMIT 5
            """
        ).fetchall()

        bad_rows = conn.execute(
            """
            SELECT source, title, company, url
            FROM listings
            WHERE url IS NULL
               OR TRIM(COALESCE(url, '')) = ''
               OR title IS NULL
               OR TRIM(COALESCE(title, '')) = ''
               OR company IS NULL
               OR TRIM(COALESCE(company, '')) = ''
            ORDER BY fetched_at DESC NULLS LAST, id DESC
            """
        ).fetchall()

    return {
        "total_listings": int(total),
        "source_counts": [dict(row) for row in source_counts],
        "probable_cross_source_duplicates": int(duplicate_rows),
        "recent": [dict(row) for row in recent],
        "data_quality_issues": [dict(row) for row in bad_rows],
    }


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


def get_state_metrics(path: str) -> dict[str, Any]:
    """Return aggregate timestamps and counts needed to build system state."""
    with _connect_readonly(path) as conn:
        row = conn.execute(
            """
            SELECT
                (SELECT MAX(fetched_at) FROM listings) AS last_fetch_at,
                (SELECT COUNT(*) FROM listings WHERE fit_score IS NULL) AS unscored_count,
                (SELECT MAX(scored_at) FROM listings WHERE scored_at IS NOT NULL) AS latest_score_at,
                (SELECT MAX(computed_at) FROM skill_gaps) AS gaps_computed_at,
                (SELECT status FROM cycle_log ORDER BY id DESC LIMIT 1) AS last_cycle_verdict,
                (SELECT finished_at FROM cycle_log ORDER BY id DESC LIMIT 1) AS last_cycle_at
            """
        ).fetchone()
    return dict(row)


def get_verification_inputs(path: str) -> dict[str, Any]:
    """Read current scores, cached facts, latest gaps, and fetch timestamp."""
    with _connect_readonly(path) as conn:
        listings = conn.execute(
            "SELECT id, description, fit_score FROM listings WHERE fit_score IS NOT NULL"
        ).fetchall()
        cache_rows = conn.execute(
            "SELECT description_hash, payload FROM extraction_cache"
        ).fetchall()
        latest_gap = conn.execute(
            "SELECT run_id FROM skill_gaps ORDER BY computed_at DESC LIMIT 1"
        ).fetchone()
        gaps = []
        if latest_gap is not None:
            gaps = conn.execute(
                "SELECT skill, listings_blocked, opportunity_cost FROM skill_gaps WHERE run_id = ? ORDER BY opportunity_cost DESC",
                (latest_gap["run_id"],),
            ).fetchall()
        latest_fetch = conn.execute("SELECT MAX(fetched_at) FROM listings").fetchone()[0]

    facts_by_hash = {row["description_hash"]: json.loads(row["payload"]) for row in cache_rows}
    facts_list: list[dict[str, Any]] = []
    scores: list[int] = []
    for listing in listings:
        digest = hashlib.sha256((listing["description"] or "").strip().encode("utf-8")).hexdigest()
        facts = facts_by_hash.get(digest)
        if facts is not None:
            facts_list.append(facts)
        scores.append(int(listing["fit_score"]))
    return {
        "scores": scores,
        "facts_list": facts_list,
        "gaps": [dict(row) for row in gaps],
        "latest_fetch_at": latest_fetch,
    }


def get_latest_passing_cycle(path: str) -> dict[str, Any] | None:
    """Return the latest cycle summary whose verdict passed verification."""
    with _connect_readonly(path) as conn:
        row = conn.execute(
            """
            SELECT * FROM cycle_log
            WHERE agent = 'Orchestrator/Summary' AND status = 'complete'
            ORDER BY id DESC LIMIT 1
            """
        ).fetchone()
    return dict(row) if row is not None else None


def get_query_snapshot(path: str) -> dict[str, Any] | None:
    """Return the latest passing-cycle cutoff and its gap snapshot id."""
    with _connect_readonly(path) as conn:
        cycle = conn.execute(
            """
            SELECT finished_at FROM cycle_log
            WHERE agent = 'Orchestrator/Summary' AND status = 'complete'
            ORDER BY id DESC LIMIT 1
            """
        ).fetchone()
        if cycle is None:
            return None
        gap = conn.execute(
            """
            SELECT run_id, computed_at FROM skill_gaps
            WHERE computed_at <= ?
            ORDER BY computed_at DESC LIMIT 1
            """,
            (cycle["finished_at"],),
        ).fetchone()
    return {
        "finished_at": cycle["finished_at"],
        "gap_run_id": gap["run_id"] if gap else None,
        "gap_computed_at": gap["computed_at"] if gap else None,
    }


def query_companies_hiring(path: str, cutoff: str, since: str) -> list[dict[str, Any]]:
    with _connect_readonly(path) as conn:
        rows = conn.execute(
            """
            SELECT company, COUNT(*) AS count
            FROM listings
            WHERE fetched_at <= ? AND posted_at >= ?
            GROUP BY company ORDER BY count DESC, company
            """,
            (cutoff, since),
        ).fetchall()
    return [dict(row) for row in rows]


def query_best_matches(path: str, cutoff: str, limit: int) -> list[dict[str, Any]]:
    with _connect_readonly(path) as conn:
        rows = conn.execute(
            """
            SELECT title, company, fit_score AS score, fit_reason AS reason
            FROM listings WHERE fit_score IS NOT NULL AND scored_at <= ?
            ORDER BY fit_score DESC, id LIMIT ?
            """,
            (cutoff, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def query_top_gaps(path: str, run_id: str | None, limit: int) -> list[dict[str, Any]]:
    if run_id is None:
        return []
    with _connect_readonly(path) as conn:
        rows = conn.execute(
            """
            SELECT skill, listings_blocked, opportunity_cost
            FROM skill_gaps WHERE run_id = ?
            ORDER BY opportunity_cost DESC, skill LIMIT ?
            """,
            (run_id, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def query_gap_detail(path: str, cutoff: str, skill: str, aliases: dict[str, str]) -> list[dict[str, Any]]:
    with _connect_readonly(path) as conn:
        listings = conn.execute(
            """
            SELECT id, title, company, fit_score, fit_reason, description
            FROM listings WHERE fit_score IS NOT NULL AND scored_at <= ?
            ORDER BY fit_score DESC, id
            """,
            (cutoff,),
        ).fetchall()
        cache = conn.execute("SELECT description_hash, payload FROM extraction_cache").fetchall()
    facts_by_hash = {row["description_hash"]: json.loads(row["payload"]) for row in cache}
    result = []
    for listing in listings:
        digest = hashlib.sha256((listing["description"] or "").strip().encode("utf-8")).hexdigest()
        facts = facts_by_hash.get(digest, {})
        required = facts.get("required_skills", [])
        if any(_canonical_skill(value, aliases) == skill for value in required):
            result.append({key: listing[key] for key in ("id", "title", "company", "fit_score", "fit_reason")})
    return result


def query_trend(path: str, cutoff: str, since: str) -> list[dict[str, Any]]:
    with _connect_readonly(path) as conn:
        rows = conn.execute(
            """
            SELECT computed_at, skill, opportunity_cost
            FROM skill_gaps WHERE computed_at <= ? AND computed_at >= ?
            ORDER BY computed_at ASC, skill
            """,
            (cutoff, since),
        ).fetchall()
    return [dict(row) for row in rows]


def query_listing_count(path: str, cutoff: str) -> list[dict[str, Any]]:
    with _connect_readonly(path) as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS listings,
                   SUM(CASE WHEN fit_score IS NOT NULL AND scored_at <= ? THEN 1 ELSE 0 END) AS scored,
                   SUM(CASE WHEN fit_score IS NULL THEN 1 ELSE 0 END) AS unscored,
                   MAX(posted_at) AS newest_listing_date
            FROM listings WHERE fetched_at <= ?
            """,
            (cutoff, cutoff),
        ).fetchone()
    return [dict(row)]


def query_skill_demand(path: str, cutoff: str, skill: str, aliases: dict[str, str]) -> list[dict[str, Any]]:
    with _connect_readonly(path) as conn:
        listings = conn.execute(
            "SELECT description FROM listings WHERE fetched_at <= ?", (cutoff,)
        ).fetchall()
        cache = conn.execute("SELECT description_hash, payload FROM extraction_cache").fetchall()
    facts_by_hash = {row["description_hash"]: json.loads(row["payload"]) for row in cache}
    required = nice = 0
    for listing in listings:
        digest = hashlib.sha256((listing["description"] or "").strip().encode("utf-8")).hexdigest()
        facts = facts_by_hash.get(digest, {})
        required += any(_canonical_skill(value, aliases) == skill for value in facts.get("required_skills", []))
        nice += any(_canonical_skill(value, aliases) == skill for value in facts.get("nice_to_have", []))
    return [{"skill": skill, "required": required, "nice_to_have": nice}]


def query_skill_exists(path: str, cutoff: str, skill: str, aliases: dict[str, str]) -> bool:
    """Return whether a canonical skill occurs in verified extracted facts."""
    with _connect_readonly(path) as conn:
        listings = conn.execute(
            "SELECT description FROM listings WHERE fetched_at <= ?", (cutoff,)
        ).fetchall()
        cache = conn.execute("SELECT description_hash, payload FROM extraction_cache").fetchall()
    facts_by_hash = {row["description_hash"]: json.loads(row["payload"]) for row in cache}
    for listing in listings:
        digest = hashlib.sha256((listing["description"] or "").strip().encode("utf-8")).hexdigest()
        facts = facts_by_hash.get(digest, {})
        values = facts.get("required_skills", []) + facts.get("nice_to_have", [])
        if any(_canonical_skill(value, aliases) == skill for value in values):
            return True
    return False


def _canonical_skill(value: str, aliases: dict[str, str]) -> str:
    value = value.strip().lower()
    normalised_aliases = {
        key.strip().lower().strip(".,;:!?()[]{}"):
        target.strip().lower().strip(".,;:!?()[]{}")
        for key, target in aliases.items()
    }
    return normalised_aliases.get(value, value)


def get_cycle_activity(path: str, limit: int = 30) -> list[dict[str, Any]]:
    """Return the most recent cycle-log rows for the read-only dashboard."""
    with _connect_readonly(path) as conn:
        rows = conn.execute(
            """
            SELECT * FROM cycle_log
            WHERE agent = 'Orchestrator/Summary'
            ORDER BY id DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_verification_history(path: str, limit: int = 20) -> list[dict[str, Any]]:
    """Return recent orchestrator summaries for the read-only verdict view."""
    with _connect_readonly(path) as conn:
        rows = conn.execute(
            """
            SELECT id, started_at, finished_at, status, notes
            FROM cycle_log
            WHERE agent = 'Orchestrator/Summary'
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_latest_cycle_summary(path: str) -> dict[str, Any] | None:
    """Return the newest orchestrator summary, regardless of its outcome."""
    with _connect_readonly(path) as conn:
        row = conn.execute(
            "SELECT * FROM cycle_log WHERE agent = 'Orchestrator/Summary' ORDER BY id DESC LIMIT 1"
        ).fetchone()
    return dict(row) if row is not None else None


def get_passing_cycle_data(path: str, summary_finished_at: str) -> dict[str, Any]:
    """Return listings and gaps no newer than a passing cycle summary."""
    with _connect_readonly(path) as conn:
        listings = conn.execute(
            """
            SELECT score.id, score.fit_score, score.fit_reason, listing.title, listing.company
            FROM listings AS score
            JOIN listings AS listing ON listing.id = score.id
            WHERE score.fit_score IS NOT NULL AND score.scored_at <= ?
            ORDER BY score.fit_score DESC, score.id
            LIMIT 10
            """,
            (summary_finished_at,),
        ).fetchall()
        gaps = conn.execute(
            """
            SELECT skill, listings_blocked, opportunity_cost, mean_score
            FROM skill_gaps
            WHERE computed_at = (
                SELECT MAX(computed_at) FROM skill_gaps WHERE computed_at <= ?
            )
            ORDER BY opportunity_cost DESC, skill
            LIMIT 10
            """,
            (summary_finished_at,),
        ).fetchall()
        counts = conn.execute(
            """
            SELECT COUNT(*) AS total_listings,
                   SUM(CASE WHEN fit_score IS NOT NULL THEN 1 ELSE 0 END) AS total_scored
            FROM listings
            WHERE fetched_at <= ?
            """,
            (summary_finished_at,),
        ).fetchone()
    return {
        "listings": [dict(row) for row in listings],
        "gaps": [dict(row) for row in gaps],
        "total_listings": int(counts["total_listings"] or 0),
        "total_scored": int(counts["total_scored"] or 0),
    }


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
