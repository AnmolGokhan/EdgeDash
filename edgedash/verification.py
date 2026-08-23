"""Deterministic plausibility checks for pipeline output."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from statistics import stdev
from typing import Any


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    observed: Any
    threshold: Any
    message: str


@dataclass(frozen=True)
class Verdict:
    passed: bool
    failed_checks: list[CheckResult]
    summary: str


def _threshold(config: Any, name: str, default: Any) -> Any:
    return getattr(config, name, default)


def check_score_spread(scores: list[float], config: Any) -> CheckResult:
    if len(scores) < 5:
        return CheckResult("score_spread", True, len(scores), 5, "passed trivially: fewer than 5 scores")
    spread = max(scores) - min(scores)
    deviation = stdev(scores)
    spread_limit = _threshold(config, "min_score_spread", 10)
    stdev_limit = _threshold(config, "min_score_stdev", 5)
    passed = spread >= spread_limit and deviation >= stdev_limit
    return CheckResult(
        "score_spread", passed, {"spread": spread, "stdev": deviation},
        {"min_spread": spread_limit, "min_stdev": stdev_limit},
        f"spread={spread:.2f}, stdev={deviation:.2f}"
        + ("" if passed else " below configured plausibility threshold"),
    )


def check_extraction_sanity(facts_list: list[dict[str, Any]], config: Any) -> CheckResult:
    total = len(facts_list)
    empty = sum(not (facts.get("required_skills") or []) for facts in facts_list)
    empty_pct = empty / total if total else 0.0
    max_empty = _threshold(config, "max_empty_extraction_pct", 0.20)
    max_skills = _threshold(config, "max_skills_per_listing", 20)
    oversized = max((len(facts.get("required_skills") or []) for facts in facts_list), default=0)
    passed = empty_pct <= max_empty and oversized <= max_skills
    return CheckResult(
        "extraction_sanity", passed,
        {"empty_pct": empty_pct, "max_required_skills": oversized},
        {"max_empty_pct": max_empty, "max_skills": max_skills},
        f"empty={empty_pct:.1%}, max_required_skills={oversized}"
        + ("" if passed else " violates configured plausibility threshold"),
    )


def check_gap_sample_size(gaps: list[dict[str, Any]], config: Any) -> CheckResult:
    minimum = _threshold(config, "min_gap_sample", 3)
    sample = gaps[0].get("listings_blocked", 0) if gaps else 0
    passed = not gaps or sample >= minimum
    return CheckResult("gap_sample_size", passed, sample, minimum, f"top gap sample={sample}")


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def check_freshness(latest_fetch_at: str | None, config: Any, now: datetime) -> CheckResult:
    maximum = _threshold(config, "max_data_age_days", 3)
    if latest_fetch_at is None:
        return CheckResult("freshness", False, None, maximum, "no listing fetch timestamp available")
    age_days = max(0.0, (now - _parse_timestamp(latest_fetch_at)).total_seconds() / 86400)
    return CheckResult("freshness", age_days <= maximum, age_days, maximum, f"data age={age_days:.2f} days")


def run_all_checks(
    scores: list[float],
    facts_list: list[dict[str, Any]],
    gaps: list[dict[str, Any]],
    latest_fetch_at: str | None,
    config: Any,
    now: datetime,
) -> Verdict:
    checks = [
        check_score_spread(scores, config),
        check_extraction_sanity(facts_list, config),
        check_gap_sample_size(gaps, config),
        check_freshness(latest_fetch_at, config, now),
    ]
    failed = [check for check in checks if not check.passed]
    summary = "all plausibility checks passed" if not failed else "; ".join(
        f"{check.name}: {check.message}" for check in failed
    )
    return Verdict(not failed, failed, summary)