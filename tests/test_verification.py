from datetime import datetime, timezone, timedelta
from types import SimpleNamespace

from edgedash.verification import (
    check_extraction_sanity,
    check_freshness,
    check_gap_sample_size,
    check_score_spread,
    run_all_checks,
)


CONFIG = SimpleNamespace(
    min_score_spread=10,
    min_score_stdev=5,
    max_empty_extraction_pct=0.20,
    max_skills_per_listing=20,
    min_gap_sample=3,
    max_data_age_days=3,
)
NOW = datetime(2026, 8, 22, tzinfo=timezone.utc)


def test_score_spread_passes():
    assert check_score_spread([10, 20, 30, 40, 50], CONFIG).passed


def test_score_spread_fails():
    assert not check_score_spread([40, 41, 42, 43, 44], CONFIG).passed


def test_score_spread_fewer_than_five_passes_trivially():
    result = check_score_spread([1, 1], CONFIG)
    assert result.passed and "fewer than 5" in result.message


def test_extraction_sanity_passes():
    facts = [{"required_skills": ["python"]}] * 5
    assert check_extraction_sanity(facts, CONFIG).passed


def test_extraction_sanity_fails_for_empty_or_oversized():
    facts = [{"required_skills": []}] + [{"required_skills": ["x"] * 21}]
    assert not check_extraction_sanity(facts, CONFIG).passed


def test_gap_sample_size_passes_and_fails():
    assert check_gap_sample_size([{"listings_blocked": 3}], CONFIG).passed
    assert not check_gap_sample_size([{"listings_blocked": 2}], CONFIG).passed


def test_freshness_passes_and_fails():
    fresh = (NOW - timedelta(days=1)).isoformat()
    old = (NOW - timedelta(days=4)).isoformat()
    assert check_freshness(fresh, CONFIG, NOW).passed
    assert not check_freshness(old, CONFIG, NOW).passed


def test_run_all_checks_collects_failures():
    verdict = run_all_checks([40, 41, 42, 43, 44], [], [{"listings_blocked": 1}], None, CONFIG, NOW)
    assert not verdict.passed
    assert {check.name for check in verdict.failed_checks} == {
        "score_spread", "gap_sample_size", "freshness"
    }