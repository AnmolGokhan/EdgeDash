"""Pure orchestration planning from state and configuration."""

from __future__ import annotations

from dataclasses import dataclass

from edgedash.config import Config
from edgedash.state import SystemState


@dataclass(frozen=True)
class Task:
    agent_name: str
    goal: str
    stop_conditions: dict[str, int]
    reason: str
    skipped: bool = False


@dataclass(frozen=True)
class Plan:
    tasks: list[Task]

    def with_forced_agents(self, agent_names: list[str]) -> "Plan":
        forced = set(agent_names)
        return Plan(
            [
                Task(task.agent_name, task.goal, task.stop_conditions, "forced by operator", False)
                if task.agent_name in forced and task.skipped
                else task
                for task in self.tasks
            ]
        )

    def render(self) -> str:
        lines = []
        for task in self.tasks:
            status = "SKIP" if task.skipped else "RUN"
            limits = ", ".join(f"{key}={value}" for key, value in task.stop_conditions.items())
            lines.append(f"{status} {task.agent_name}: {task.goal} [{limits}] | {task.reason}")
        return "\n".join(lines)


def build_plan(state: SystemState, config: Config) -> Plan:
    fetch_due = state.hours_since_fetch is None or state.hours_since_fetch >= config.fetch_interval_hours
    score_due = state.unscored_count > 0
    analyse_due = state.gaps_stale or state.gaps_computed_at is None
    tasks = [
        Task("Fetcher", "fetch new listings", {"max_pages": config.max_pages, "max_listings": config.max_listings},
             f"hours_since_fetch={state.hours_since_fetch}" if fetch_due else f"skipped: hours_since_fetch={state.hours_since_fetch}", not fetch_due),
        Task("Scorer", "score unscored listings", {"max_items": config.scoring_batch_size, "max_seconds": config.score_max_seconds},
             f"unscored_count={state.unscored_count}" if score_due else "skipped: unscored_count=0", not score_due),
        Task("GapAnalyzer", "analyse scored skill gaps", {"max_seconds": config.analyse_max_seconds},
             "gaps_stale=True" if analyse_due and state.gaps_stale else "gaps_computed_at=None" if analyse_due else "skipped: gaps_stale=False",
             not analyse_due),
            Task("Verifier", "verify current cycle output", {"max_seconds": getattr(config, "verify_max_seconds", 60)},
                 "verify after planned work" if (fetch_due or score_due or analyse_due) else "skipped: no planned work",
                 not (fetch_due or score_due or analyse_due)),
    ]
    return Plan(tasks)