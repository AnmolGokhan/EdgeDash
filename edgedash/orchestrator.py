"""Orchestrator — reads state, decides what to run, delegates, logs, reports.

The orchestrator never fetches data or scores listings directly.
Swap an agent by changing one line in AGENT_REGISTRY.
"""

from __future__ import annotations

from datetime import datetime, timezone

import edgedash.storage as storage
from edgedash.agents.base import Agent, AgentResult
from edgedash.agents.fetcher import Fetcher
from edgedash.agents.mock_fetcher import MockFetcher
from edgedash.agents.scorer import Scorer
from edgedash.config import Config


# ---------------------------------------------------------------------------
# Agent registry
# The active fetcher is chosen at runtime from config.use_mock_fetcher.
# Scorer and GapAnalyzer are registered as stubs until implemented.
# ---------------------------------------------------------------------------

class _NotImplementedAgent:
    """Placeholder that logs a skip and returns immediately."""

    def __init__(self, agent_name: str) -> None:
        self.name = agent_name

    def run(self, config: Config, db_path: str) -> AgentResult:
        return AgentResult(
            agent=self.name,
            status="ok",
            records_touched=0,
            notes="not implemented yet — skipped",
        )


def _build_registry(config: Config) -> list[Agent]:
    fetcher: Agent = MockFetcher() if config.use_mock_fetcher else Fetcher()
    return [
        fetcher,
        Scorer(),
        _NotImplementedAgent("GapAnalyzer"), # week 3: swap to GapAnalyzer()
    ]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fmt_time(iso: str | None) -> str:
    if iso is None:
        return "never"
    # Trim microseconds for readability
    return iso[:19].replace("T", " ") + " UTC"


def _print_rule(char: str = "─", width: int = 62) -> None:
    print(char * width)


def _print_header(title: str) -> None:
    _print_rule("═")
    print(f"  {title}")
    _print_rule("═")


def _run_agent(agent: Agent, config: Config, db_path: str) -> tuple[AgentResult, str, str]:
    """Run one agent, return (result, started_at, finished_at)."""
    started_at = _now_iso()
    result = agent.run(config, db_path)
    finished_at = _now_iso()
    return result, started_at, finished_at


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_cycle(config: Config) -> None:
    """Execute one full orchestration cycle."""

    _print_header("EdgeDash  ·  Cycle Starting")
    print(f"  Role   : {config.target_role}")
    print(f"  City   : {config.target_city}")
    print(f"  DB     : {config.db_path}")
    print()

    # --- 1. Init DB ---------------------------------------------------------
    storage.init_db(config.db_path)

    # --- 2. Read state ------------------------------------------------------
    last_fetch = storage.last_fetch_time(config.db_path)
    unscored   = storage.count_unscored(config.db_path)

    _print_rule()
    print("  STATE READ")
    _print_rule()
    print(f"  Last fetch   : {_fmt_time(last_fetch)}")
    print(f"  Unscored rows: {unscored}")
    print()

    # --- 3. Build registry (respects use_mock_fetcher flag) -----------------
    agent_registry = _build_registry(config)

    # --- 4. Print plan ------------------------------------------------------
    _print_rule()
    print("  PLAN")
    _print_rule()
    if last_fetch is None:
        print("  → No data yet. Running full pipeline from scratch.")
    else:
        print(f"  → Data exists (last fetched {_fmt_time(last_fetch)}).")
        print(f"    {unscored} listing(s) still awaiting a score.")
        print("  → Re-fetching to catch new postings; running all agents.")
    print()

    for agent in agent_registry:
        marker = "  ✓" if not isinstance(agent, _NotImplementedAgent) else "  ·"
        note = "" if not isinstance(agent, _NotImplementedAgent) else " (stub)"
        print(f"{marker} {agent.name}{note}")
    print()

    # --- 5 & 6. Run agents + log each one -----------------------------------
    results: list[AgentResult] = []

    for agent in agent_registry:
        print(f"  Running {agent.name} ...", end=" ", flush=True)
        result, started_at, finished_at = _run_agent(agent, config, config.db_path)

        storage.log_cycle(
            path=config.db_path,
            agent=result.agent,
            started_at=started_at,
            finished_at=finished_at,
            records_touched=result.records_touched,
            status=result.status,
            notes=result.notes,
        )

        status_icon = "✓" if result.status == "ok" else "✗"
        print(f"{status_icon}")
        if result.notes:
            print(f"    {result.notes}")

        results.append(result)

    # --- 6. Summary table ---------------------------------------------------
    print()
    _print_rule()
    print("  CYCLE SUMMARY")
    _print_rule()
    col = 18
    print(f"  {'Agent':<{col}} {'Status':<8} {'New records':>12}  Notes")
    _print_rule("─")
    for r in results:
        notes_preview = (r.notes or "")[:40]
        print(f"  {r.agent:<{col}} {r.status:<8} {r.records_touched:>12}  {notes_preview}")
    _print_rule()

    total_new = sum(r.records_touched for r in results)
    all_ok    = all(r.status == "ok" for r in results)
    overall   = "ALL OK" if all_ok else "SOME FAILURES — check cycle_log"
    print(f"  Total new records: {total_new}   |   Overall: {overall}")
    _print_rule("═")
    print()
