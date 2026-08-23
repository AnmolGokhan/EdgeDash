"""Base contract for all EdgeDash agents."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from edgedash.config import Config


@dataclass
class AgentResult:
    agent: str
    status: str          # "ok" | "failed"
    records_touched: int
    notes: str | None = None
    verdict: object | None = None


@runtime_checkable
class Agent(Protocol):
    """Every agent must expose a name and a run method.

    run() receives the loaded Config and the db_path string so it can call
    storage functions directly without coupling to a connection object.
    """

    name: str

    def run(
        self,
        config: Config,
        db_path: str,
        goal: str,
        stop_conditions: dict[str, int],
    ) -> AgentResult:
        ...
