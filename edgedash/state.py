"""Cheap, deterministic system-state inspection for orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import edgedash.storage as storage
from edgedash.config import Config


@dataclass(frozen=True)
class SystemState:
    last_fetch_at: str | None
    hours_since_fetch: float | None
    unscored_count: int
    gaps_computed_at: str | None
    gaps_stale: bool
    last_cycle_verdict: str | None
    last_cycle_at: str | None


def _hours_since(timestamp: str | None, now: datetime) -> float | None:
    if timestamp is None:
        return None
    parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    if parsed.tzinfo is None and now.tzinfo is not None:
        parsed = parsed.replace(tzinfo=now.tzinfo)
    return max(0.0, (now - parsed).total_seconds() / 3600)


def read_state(config: Config, now: datetime) -> SystemState:
    metrics = storage.get_state_metrics(config.db_path)
    last_fetch_at = metrics["last_fetch_at"]
    gaps_computed_at = metrics["gaps_computed_at"]
    latest_score_at = metrics["latest_score_at"]
    gaps_stale = gaps_computed_at is None or (
        latest_score_at is not None and latest_score_at > gaps_computed_at
    )
    return SystemState(
        last_fetch_at=last_fetch_at,
        hours_since_fetch=_hours_since(last_fetch_at, now),
        unscored_count=int(metrics["unscored_count"] or 0),
        gaps_computed_at=gaps_computed_at,
        gaps_stale=gaps_stale,
        last_cycle_verdict=metrics["last_cycle_verdict"],
        last_cycle_at=metrics["last_cycle_at"],
    )