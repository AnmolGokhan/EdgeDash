from datetime import datetime, timezone
from types import SimpleNamespace

from edgedash.planning import build_plan
from edgedash.state import SystemState


CONFIG = SimpleNamespace(
    fetch_interval_hours=6, max_pages=5, max_listings=500,
    scoring_batch_size=25, score_max_seconds=300, analyse_max_seconds=60,
)
NOW = datetime(2026, 8, 22, 12, tzinfo=timezone.utc)


def state(**changes):
    values = dict(last_fetch_at="2026-08-22T00:00:00+00:00", hours_since_fetch=12,
                  unscored_count=3, gaps_computed_at="2026-08-21T00:00:00+00:00",
                  gaps_stale=True, last_cycle_verdict="ok", last_cycle_at=None)
    values.update(changes)
    return SystemState(**values)


def statuses(plan):
    return [task.skipped for task in plan.tasks]


def test_everything_stale_runs_all():
    assert statuses(build_plan(state(), CONFIG)) == [False, False, False, False]


def test_nothing_to_do_skips_all():
    plan = build_plan(state(hours_since_fetch=1, unscored_count=0, gaps_stale=False), CONFIG)
    assert statuses(plan) == [True, True, True, True]
    assert "skipped: unscored_count=0" in plan.render()


def test_only_unscored_runs_score():
    plan = build_plan(state(hours_since_fetch=1, unscored_count=2, gaps_stale=False), CONFIG)
    assert statuses(plan) == [True, False, True, False]


def test_stale_gaps_runs_analysis_without_unscored():
    plan = build_plan(state(hours_since_fetch=1, unscored_count=0, gaps_stale=True), CONFIG)
    assert statuses(plan) == [True, True, False, False]


def test_force_overlay_only_unskips_named_agent():
    plan = build_plan(state(hours_since_fetch=1, unscored_count=0, gaps_stale=False), CONFIG)

    forced = plan.with_forced_agents(["Scorer"])

    assert statuses(forced) == [True, False, True, True]
    assert forced.tasks[1].reason == "forced by operator"
    assert statuses(plan) == [True, True, True, True]