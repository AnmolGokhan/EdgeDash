"""Deterministic, score-weighted skill-gap analysis."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import time
from uuid import uuid4

import edgedash.storage as storage
from edgedash.agents.base import Agent, AgentResult
from edgedash.config import Config
from edgedash.skills import canonical


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _gap_rows(listings: list[dict], config: Config) -> list[dict]:
    owned = {canonical(skill, config.skill_aliases) for skill in config.skills}
    blocked: dict[str, list[dict]] = defaultdict(list)
    nice_counts: dict[str, int] = defaultdict(int)

    for listing in listings:
        required = {canonical(skill, config.skill_aliases) for skill in listing.get("required_skills", [])}
        nice = {canonical(skill, config.skill_aliases) for skill in listing.get("nice_to_have", [])}
        for skill in nice - owned:
            nice_counts[skill] += 1
        for skill in required - owned:
            blocked[skill].append(listing)

    rows: list[dict] = []
    for skill, matches in blocked.items():
        matches.sort(key=lambda row: (-row["fit_score"], row["id"]))
        scores = [row["fit_score"] for row in matches]
        rows.append(
            {
                "skill": skill,
                "listings_blocked": len(matches),
                "opportunity_cost": sum(score / 100 for score in scores),
                "mean_score": sum(scores) / len(scores),
                "top_score": scores[0],
                "example_ids": [row["id"] for row in matches[:5]],
                "also_nice_to_have": nice_counts[skill],
            }
        )
    return sorted(rows, key=lambda row: (-row["opportunity_cost"], row["skill"]))[:10]


class GapAnalyzer:
    name: str = "GapAnalyzer"

    def run(
        self,
        config: Config,
        db_path: str,
        goal: str,
        stop_conditions: dict[str, int],
    ) -> AgentResult:
        started = time.monotonic()
        listings = storage.get_scored_listings_with_facts(db_path)
        if stop_conditions.get("max_seconds") and time.monotonic() - started >= stop_conditions["max_seconds"]:
            return AgentResult(self.name, "ok", 0, "analysis skipped: max_seconds reached")
        rows = _gap_rows(listings, config)
        computed_at = _now_iso()
        storage.write_skill_gap_snapshot(db_path, str(uuid4()), computed_at, rows)
        top = rows[0] if rows else None
        notes = f"{len(rows)} gaps"
        if top:
            notes += f" · top: {top['skill']} ({top['listings_blocked']} listings, cost {top['opportunity_cost']:.1f})"
        notes += f" · {len(listings)} listings analysed"
        return AgentResult(self.name, "ok", len(listings), notes)