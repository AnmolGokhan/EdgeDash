"""Deterministic, parameterised query-tool registry. Never generates SQL."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Callable

import edgedash.storage as storage
from edgedash.config import load_config
from edgedash.skills import canonical

TOOLS: dict[str, dict[str, Any]] = {}


def tool(name: str, description: str, parameters: dict[str, Any]) -> Callable:
    """Register a fixed query function and its router-facing metadata."""
    def decorator(function: Callable) -> Callable:
        TOOLS[name] = {"name": name, "description": description, "parameters": parameters, "function": function}
        return function
    return decorator


def _clamp(value: Any, low: int, high: int) -> int:
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return low


def _context() -> tuple[str, dict[str, str]] | None:
    config = load_config()
    snapshot = storage.get_query_snapshot(config.db_path)
    return (config.db_path, config.skill_aliases) if snapshot else None


@tool("companies_hiring", "Count companies with listings posted in the last N days.", {"days": {"type": "integer", "minimum": 1, "maximum": 90}})
def companies_hiring(days: int = 7) -> dict[str, Any]:
    context = _context()
    days = _clamp(days, 1, 90)
    if context is None:
        return {"rows": [], "summary": "0 listings from the last day"}
    path, _ = context
    cutoff = storage.get_query_snapshot(path)["finished_at"]
    since = (datetime.fromisoformat(cutoff.replace("Z", "+00:00")) - timedelta(days=days)).date().isoformat()
    rows = storage.query_companies_hiring(path, cutoff, since)
    return {"rows": rows, "summary": f"{sum(row['count'] for row in rows)} listings from the last {days} days"}


@tool("best_matches", "Return the highest-scoring verified listings.", {"n": {"type": "integer", "minimum": 1, "maximum": 25}})
def best_matches(n: int = 10) -> dict[str, Any]:
    n = _clamp(n, 1, 25); context = _context()
    if context is None: return {"rows": [], "summary": "0 verified listings"}
    path, _ = context; cutoff = storage.get_query_snapshot(path)["finished_at"]
    rows = storage.query_best_matches(path, cutoff, n)
    return {"rows": rows, "summary": f"{len(rows)} verified scored listings"}


@tool("top_gaps", "Return top skill gaps ranked by opportunity cost.", {"n": {"type": "integer", "minimum": 1, "maximum": 25}})
def top_gaps(n: int = 5) -> dict[str, Any]:
    n = _clamp(n, 1, 25); context = _context()
    if context is None: return {"rows": [], "summary": "0 verified skill gaps"}
    path, _ = context; snapshot = storage.get_query_snapshot(path); rows = storage.query_top_gaps(path, snapshot["gap_run_id"], n)
    return {"rows": rows, "summary": f"{len(rows)} verified skill gaps"}


@tool("gap_detail", "List verified scored listings blocked by one canonical skill.", {"skill": {"type": "string"}})
def gap_detail(skill: str) -> dict[str, Any]:
    context = _context(); skill = canonical(str(skill), context[1] if context else {})
    if context is None: return {"rows": [], "summary": "0 verified listings"}
    path, aliases = context; cutoff = storage.get_query_snapshot(path)["finished_at"]
    if not storage.query_skill_exists(path, cutoff, skill, aliases):
        return {"rows": [], "summary": f"skill {skill} was not found in verified data"}
    rows = storage.query_gap_detail(path, cutoff, skill, aliases)
    return {"rows": rows, "summary": f"{len(rows)} verified listings blocked by {skill}"}


@tool("trend", "Show opportunity-cost changes across recent gap snapshots.", {"weeks": {"type": "integer", "minimum": 1, "maximum": 12}})
def trend(weeks: int = 3) -> dict[str, Any]:
    weeks = _clamp(weeks, 1, 12); context = _context()
    if context is None: return {"rows": [], "summary": "0 verified snapshots"}
    path, _ = context; cutoff = storage.get_query_snapshot(path)["finished_at"]
    cutoff_dt = datetime.fromisoformat(cutoff.replace("Z", "+00:00"))
    since = (cutoff_dt - timedelta(weeks=weeks)).isoformat()
    rows = storage.query_trend(path, cutoff, since)
    return {"rows": rows, "summary": f"{len(rows)} gap rows across the last {weeks} weeks"}


@tool("listing_count", "Return verified listing, scored, unscored, and newest-date totals.", {})
def listing_count() -> dict[str, Any]:
    context = _context()
    if context is None: return {"rows": [], "summary": "0 verified listings"}
    path, _ = context; rows = storage.query_listing_count(path, storage.get_query_snapshot(path)["finished_at"])
    return {"rows": rows, "summary": f"{rows[0]['listings']} verified listings"}


@tool("skill_demand", "Count verified required and nice-to-have appearances for one canonical skill.", {"skill": {"type": "string"}})
def skill_demand(skill: str) -> dict[str, Any]:
    context = _context(); skill = canonical(str(skill), context[1] if context else {})
    if context is None: return {"rows": [], "summary": "0 verified listings"}
    path, aliases = context
    cutoff = storage.get_query_snapshot(path)["finished_at"]
    if not storage.query_skill_exists(path, cutoff, skill, aliases):
        return {"rows": [], "summary": f"skill {skill} was not found in verified data"}
    rows = storage.query_skill_demand(path, cutoff, skill, aliases)
    return {"rows": rows, "summary": f"demand checked across verified listings for {skill}"}