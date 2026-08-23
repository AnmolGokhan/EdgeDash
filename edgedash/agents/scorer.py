"""Score unscored listings using extracted facts and deterministic weights."""

from __future__ import annotations

import statistics
import time
from datetime import datetime, timezone
from typing import Any

import edgedash.storage as storage
from edgedash.agents.base import Agent, AgentResult
from edgedash.agents.extractor import extract
from edgedash.config import Config
from edgedash.scoring import build_reason, score_listing


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Scorer:
    name: str = "Scorer"

    def run(
        self,
        config: Config,
        db_path: str,
        goal: str,
        stop_conditions: dict[str, int],
    ) -> AgentResult:
        started_at = _now_iso()
        as_of = datetime.fromisoformat(started_at)
        failed = 0
        scored_rows: list[int] = []

        max_items = stop_conditions.get("max_items", config.scoring_batch_size)
        deadline = time.monotonic() + stop_conditions.get("max_seconds", 0) if stop_conditions.get("max_seconds") else None
        retry = bool(stop_conditions.get("rescore"))
        rows = storage.get_scored_listings(db_path, limit=max_items) if retry else storage.get_unscored_listings(db_path, limit=max_items)
        strict_distribution = bool(stop_conditions.get("strict_distribution"))
        for row in rows:
            if deadline is not None and time.monotonic() >= deadline:
                break
            try:
                facts = extract(row)
                result = score_listing(row, facts, config, as_of=as_of, strict_distribution=strict_distribution)
                storage.update_listing_score(
                    path=db_path,
                    listing_id=row["id"],
                    score=result["score"],
                    reason=result["reason"],
                    components=result["components"],
                    scored_at=_now_iso(),
                )
                scored_rows.append(result["score"])
            except Exception as exc:  # rule 17: one listing failure never kills the batch
                failed += 1
                storage.log_cycle(
                    path=db_path,
                    agent=f"Scorer/{row.get('id', 'unknown')}",
                    started_at=started_at,
                    finished_at=_now_iso(),
                    records_touched=0,
                    status="failed",
                    notes=f"{type(exc).__name__}: {exc}",
                )
                print(f"  ⚠  [Scorer] failed listing {row.get('id', '<unknown>')} — {type(exc).__name__}: {exc}")

        finished_at = _now_iso()

        if scored_rows:
            spread = max(scored_rows) - min(scored_rows)
            mean = int(round(statistics.mean(scored_rows)))
            notes = (
                f"scored {len(scored_rows)} · range {min(scored_rows)}-{max(scored_rows)} "
                f"· mean {mean} · {failed} failed · spread {'OK' if spread >= 10 else 'SUSPECT'}"
            )
            status = "suspect" if spread < 10 else "ok"
        else:
            spread = 0
            mean = 0
            notes = f"scored 0 · range n/a · mean 0 · {failed} failed · spread OK"
            status = "ok"

        storage.log_cycle(
            path=db_path,
            agent=self.name,
            started_at=started_at,
            finished_at=finished_at,
            records_touched=len(scored_rows),
            status=status,
            notes=(
                f"count={len(scored_rows)} min={min(scored_rows) if scored_rows else 'n/a'} "
                f"max={max(scored_rows) if scored_rows else 'n/a'} mean={mean} spread={spread}"
            ),
        )

        return AgentResult(
            agent=self.name,
            status="ok",
            records_touched=len(scored_rows),
            notes=notes,
        )
