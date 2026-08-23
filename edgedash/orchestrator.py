"""Orchestrator — reads state, decides what to run, delegates, logs, reports.

The orchestrator never fetches data or scores listings directly.
Swap an agent by changing one line in AGENT_REGISTRY.
"""

from __future__ import annotations

from datetime import datetime, timezone

import edgedash.storage as storage
from edgedash.agents.base import Agent, AgentResult
from edgedash.agents.fetcher import Fetcher
from edgedash.agents.gap_analyzer import GapAnalyzer
from edgedash.agents.verifier import Verifier
from edgedash.agents.mock_fetcher import MockFetcher
from edgedash.agents.scorer import Scorer
from edgedash.config import Config
from edgedash.planning import build_plan
from edgedash.state import read_state


# ---------------------------------------------------------------------------
# Agent registry
# The active fetcher is chosen at runtime from config.use_mock_fetcher.
# Scorer and GapAnalyzer are registered in the cycle order below.
# ---------------------------------------------------------------------------

class _NotImplementedAgent:
    """Placeholder that logs a skip and returns immediately."""

    def __init__(self, agent_name: str) -> None:
        self.name = agent_name

    def run(
        self,
        config: Config,
        db_path: str,
        goal: str,
        stop_conditions: dict[str, int],
    ) -> AgentResult:
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
        GapAnalyzer(),
        Verifier(),
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


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def _print_explanation(state, plan) -> None:
    print("  SYSTEM STATE EXPLANATION")
    print(f"  last_fetch_at={state.last_fetch_at!r} -> Fetcher decision")
    print(f"  hours_since_fetch={state.hours_since_fetch!r} -> {plan.tasks[0].reason}")
    print(f"  unscored_count={state.unscored_count} -> {plan.tasks[1].reason}")
    print(f"  gaps_computed_at={state.gaps_computed_at!r} -> GapAnalyzer decision")
    print(f"  gaps_stale={state.gaps_stale} -> {plan.tasks[2].reason}")
    print(f"  last_cycle_verdict={state.last_cycle_verdict!r}")
    print(f"  last_cycle_at={state.last_cycle_at!r}")
    print()


def _retry_target(verdict, agents: dict[str, Agent]) -> str | None:
    mapping = {
        "score_spread": "Scorer",
        "extraction_sanity": "Scorer",
        "gap_sample_size": "GapAnalyzer",
        "freshness": "Fetcher",
    }
    for check in verdict.failed_checks:
        target = mapping.get(check.name)
        if target in agents:
            return target
    return None


def run_cycle(
    config: Config,
    *,
    dry_run: bool = False,
    force: list[str] | None = None,
    explain: bool = False,
) -> None:
    """Execute one full orchestration cycle."""

    _print_header("EdgeDash  ·  Cycle Starting")
    print(f"  Role   : {config.target_role}")
    print(f"  City   : {config.target_city}")
    print(f"  DB     : {config.db_path}")
    print()

    # --- 1. Init DB ---------------------------------------------------------
    if not dry_run:
        storage.init_db(config.db_path)

    # --- 2. Read state ------------------------------------------------------
    state = read_state(config, datetime.now(timezone.utc))

    _print_rule()
    print("  STATE READ")
    _print_rule()
    print(f"  Last fetch   : {_fmt_time(state.last_fetch_at)}")
    print(f"  Unscored rows: {state.unscored_count}")
    print()

    # --- 3. Build registry (respects use_mock_fetcher flag) -----------------
    agent_registry = _build_registry(config)

    plan = build_plan(state, config)
    forced = force or []
    known_agents = {task.agent_name for task in plan.tasks}
    unknown_forced = sorted(set(forced) - known_agents)
    if unknown_forced:
        raise ValueError(f"Unknown agent(s) for --force: {', '.join(unknown_forced)}")
    if forced:
        plan = plan.with_forced_agents(forced)
        print("  WARNING: plan manually overridden by operator (--force)")

    # --- 4. Print plan ------------------------------------------------------
    _print_rule()
    print("  PLAN")
    _print_rule()
    print(plan.render())
    print()

    if explain:
        _print_explanation(state, plan)

    if dry_run:
        print("Dry run: no agents executed and no writes made.")
        return

    # --- 5 & 6. Run agents + log each one -----------------------------------
    results: list[AgentResult] = []
    durations: dict[str, float] = {}
    skipped = [f"{task.agent_name}: {task.reason}" for task in plan.tasks if task.skipped]
    ran: list[str] = []
    failed = False
    retry_count = 0
    outcome_override: str | None = None

    agents = {agent.name: agent for agent in agent_registry}
    for task_index, task in enumerate(plan.tasks):
        if task.skipped:
            continue
        agent = agents[task.agent_name]
        ran.append(agent.name)
        print(f"  Running {agent.name} ...", end=" ", flush=True)
        started_at = _now_iso()
        started_clock = datetime.now(timezone.utc)
        try:
            result = agent.run(config, config.db_path, task.goal, task.stop_conditions)
        except Exception as exc:
            failed = True
            result = AgentResult(
                agent=agent.name,
                status="failed",
                records_touched=0,
                notes=f"{type(exc).__name__}: {exc}",
            )
        finished_at = _now_iso()
        durations[agent.name] = (datetime.now(timezone.utc) - started_clock).total_seconds()

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
        failed = failed or result.status == "failed"

        if agent.name != "Verifier" or result.status == "failed":
            continue

        verdict = result.verdict
        if verdict is None or verdict.passed:
            continue
        if retry_count >= 1:
            outcome_override = "degraded"
            break

        retry_agent_name = _retry_target(verdict, agents)
        if retry_agent_name is None:
            outcome_override = "degraded"
            break
        retry_count += 1
        retry_conditions = next(
            planned.stop_conditions for planned in plan.tasks
            if planned.agent_name == retry_agent_name
        ).copy()
        retry_conditions["rescore"] = retry_agent_name == "Scorer"
        retry_conditions["strict_distribution"] = any(
            check.name == "score_spread" for check in verdict.failed_checks
        )
        retry_task = next(planned for planned in plan.tasks if planned.agent_name == retry_agent_name)
        print(f"  Retrying {retry_agent_name} once after verification failure ...", end=" ", flush=True)
        retry_started = _now_iso()
        retry_clock = datetime.now(timezone.utc)
        try:
            retry_result = agents[retry_agent_name].run(
                config, config.db_path, retry_task.goal, retry_conditions
            )
        except Exception as exc:
            retry_result = AgentResult(
                retry_agent_name, "failed", 0, f"{type(exc).__name__}: {exc}"
            )
        retry_finished = _now_iso()
        durations[f"{retry_agent_name} (retry)"] = (
            datetime.now(timezone.utc) - retry_clock
        ).total_seconds()
        storage.log_cycle(
            config.db_path,
            f"{retry_agent_name}/retry",
            retry_started,
            retry_finished,
            retry_result.records_touched,
            retry_result.status,
            retry_result.notes,
        )
        print("✓" if retry_result.status == "ok" else "✗")
        results.append(retry_result)
        if retry_result.status == "failed":
            outcome_override = "degraded"
            break

        verifier_task = plan.tasks[task_index]
        print("  Re-verifying ...", end=" ", flush=True)
        verify_started = _now_iso()
        verify_clock = datetime.now(timezone.utc)
        try:
            verify_result = agents["Verifier"].run(
                config, config.db_path, verifier_task.goal, verifier_task.stop_conditions
            )
        except Exception as exc:
            verify_result = AgentResult("Verifier", "failed", 0, f"{type(exc).__name__}: {exc}")
        verify_finished = _now_iso()
        durations["Verifier (retry)"] = (
            datetime.now(timezone.utc) - verify_clock
        ).total_seconds()
        storage.log_cycle(
            config.db_path,
            "Verifier/retry",
            verify_started,
            verify_finished,
            verify_result.records_touched,
            verify_result.status,
            verify_result.notes,
        )
        print("✓" if verify_result.status == "ok" else "✗")
        results.append(verify_result)
        if verify_result.status == "failed" or not verify_result.verdict or not verify_result.verdict.passed:
            outcome_override = "degraded"
            break

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
    outcome = outcome_override or ("nothing_to_do" if not results else "partial" if failed else "complete")
    print(f"  Total new records: {total_new}   |   Outcome: {outcome}")
    summary = (
        f"plan={plan.render()} | forced={forced} | ran={ran} | skipped={skipped} | "
        f"durations={durations} | verdict={getattr(results[-1], 'verdict', None) if results else None} | "
        f"failed_checks={getattr(getattr(results[-1], 'verdict', None), 'failed_checks', []) if results else []} | "
        f"retry_count={retry_count} | outcome={outcome}"
    )
    storage.log_cycle(
        path=config.db_path,
        agent="Orchestrator/Summary",
        started_at=_now_iso(),
        finished_at=_now_iso(),
        records_touched=total_new,
        status=outcome,
        notes=summary,
    )
    _print_rule("═")
    print()
