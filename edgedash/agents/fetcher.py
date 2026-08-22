"""Real Fetcher agent.

Iterates over every source named in config.sources, calls fetch(), handles
per-source failures per steering rule 12 (one dead source never kills the
cycle), then writes all rows via storage.upsert_listings.

The listing id is computed by storage.make_listing_id — exactly the same
function storage.py already uses, imported directly so there is only one
implementation.
"""

from __future__ import annotations

from datetime import datetime, timezone

import edgedash.storage as storage
from edgedash.agents.base import Agent, AgentResult
from edgedash.config import Config
from edgedash.sources.base import SOURCES

# Side-effect import: registers all @register-decorated source classes.
import edgedash.sources.apify  # noqa: F401
import edgedash.sources.arbeitnow  # noqa: F401


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Fetcher:
    name: str = "Fetcher"

    def run(self, config: Config, db_path: str) -> AgentResult:
        source_summaries: list[str] = []
        all_rows: list[dict] = []

        for source_name in config.sources:
            if source_name not in SOURCES:
                msg = f"unknown source '{source_name}' — not in registry"
                print(f"  ⚠  [Fetcher] {msg}")
                source_summaries.append(f"{source_name}: FAILED ({msg})")
                storage.log_cycle(
                    path=db_path,
                    agent=f"Fetcher/{source_name}",
                    started_at=_now_iso(),
                    finished_at=_now_iso(),
                    records_touched=0,
                    status="failed",
                    notes=msg,
                )
                continue

            source = SOURCES[source_name]()
            started_at = _now_iso()

            try:
                rows = source.fetch(config)
            except Exception as exc:  # steering rule 12: never kill the cycle
                finished_at = _now_iso()
                short = type(exc).__name__
                msg = f"{short}: {exc}"
                print(f"  ⚠  [Fetcher] source '{source_name}' failed — {msg}")
                source_summaries.append(f"{source_name}: FAILED ({short})")
                storage.log_cycle(
                    path=db_path,
                    agent=f"Fetcher/{source_name}",
                    started_at=started_at,
                    finished_at=finished_at,
                    records_touched=0,
                    status="failed",
                    notes=msg,
                )
                continue

            finished_at = _now_iso()

            # Normalise rows to the shape storage.upsert_listings expects.
            # Sources return {source, external_id, title, company, location,
            # url, description, posted_at, raw}.  upsert_listings wants
            # {source, url, title, company, location, description, posted_at}.
            # Drop 'external_id' and 'raw'; they are not stored in listings.
            storage_rows = [
                {
                    "source": r["source"],
                    "url": r["url"],
                    "title": r.get("title"),
                    "company": r.get("company"),
                    "location": r.get("location"),
                    "description": r.get("description"),
                    "posted_at": r.get("posted_at"),
                }
                for r in rows
            ]
            all_rows.extend(storage_rows)

            storage.log_cycle(
                path=db_path,
                agent=f"Fetcher/{source_name}",
                started_at=started_at,
                finished_at=finished_at,
                records_touched=len(rows),
                status="ok",
                notes=f"{len(rows)} rows fetched from {source_name}",
            )

            # Partial new-count per source logged in the summary below.
            source_summaries.append(f"{source_name}:{len(rows)}_fetched")

        # Write everything in one upsert pass so we count only genuinely new rows.
        total_new = storage.upsert_listings(db_path, all_rows) if all_rows else 0

        # Rebuild summary now that we know total_new.
        # Re-attribute new rows proportionally per source (best-effort: the
        # true per-source new count would need separate upsert calls, which
        # would defeat batch efficiency; the total is what matters for the log).
        notes = _build_notes(config.sources, source_summaries, total_new)

        return AgentResult(
            agent=self.name,
            status="ok",
            records_touched=total_new,
            notes=notes,
        )


def _build_notes(
    sources: list[str],
    summaries: list[str],
    total_new: int,
) -> str:
    """Format the per-source summary line shown in the cycle report."""
    parts: list[str] = []
    for entry in summaries:
        if "FAILED" in entry:
            parts.append(entry)
        else:
            # entry looks like "arbeitnow:47_fetched"
            name, rest = entry.split(":", 1)
            fetched = rest.replace("_fetched", "")
            parts.append(f"{name}: {fetched} rows ({total_new} new total)")
    return " | ".join(parts) if parts else f"{total_new} new rows"
