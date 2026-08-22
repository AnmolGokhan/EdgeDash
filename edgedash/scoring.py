"""Deterministic, model-free scoring for job listings."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any


SENIORITY_ORDER = ["junior", "mid", "senior", "lead"]


def _clean_skill(value: Any) -> str:
    return str(value).strip().lower()


def _skill_set(items: Any) -> set[str]:
    if not isinstance(items, list):
        return set()
    return {_clean_skill(item) for item in items if str(item).strip()}


def _config_skills(config: Any) -> list[str]:
    if hasattr(config, "skills"):
        return [str(skill).strip().lower() for skill in getattr(config, "skills") if str(skill).strip()]
    if hasattr(config, "my_skills"):
        return [str(skill).strip().lower() for skill in getattr(config, "my_skills") if str(skill).strip()]
    return []


def _normalise_float(value: float, digits: int = 3) -> float:
    return round(float(value), digits)


def _skill_match_component(facts: dict[str, Any], config: Any) -> float:
    required = [
        _clean_skill(skill) for skill in (facts.get("required_skills") or []) if str(skill).strip()
    ]
    nice = [
        _clean_skill(skill) for skill in (facts.get("nice_to_have") or []) if str(skill).strip()
    ]
    profile = set(_config_skills(config))

    if not required:
        return 1.0

    required_count = len(required)
    required_matches = sum(1 for skill in required if skill in profile)
    required_fraction = required_matches / required_count

    if not nice:
        return required_fraction

    nice_count = len(nice)
    nice_matches = sum(1 for skill in nice if skill in profile)
    nice_fraction = nice_matches / nice_count
    return min(1.0, required_fraction + (nice_fraction * 0.3333333333))


def _seniority_fit_component(facts: dict[str, Any], config: Any) -> float:
    target_name = getattr(config, "target_seniority", "mid") or "mid"
    fact_name = (facts.get("seniority") or "unknown").strip().lower()

    if fact_name == "unknown":
        return 0.5

    if target_name not in SENIORITY_ORDER:
        target_name = "mid"
    if fact_name not in SENIORITY_ORDER:
        return 0.5

    target_index = SENIORITY_ORDER.index(target_name)
    fact_index = SENIORITY_ORDER.index(fact_name)
    delta = abs(target_index - fact_index)

    if delta == 0:
        return 1.0
    if delta == 1:
        return 0.6
    if delta == 2:
        return 0.25
    return 0.0


def _location_fit_component(listing: dict[str, Any], facts: dict[str, Any], config: Any) -> float:
    if bool(facts.get("remote_ok")):
        return 1.0

    target_city = str(getattr(config, "target_city", "") or "").strip().lower()
    listing_location = str(listing.get("location") or "").strip().lower()

    if not listing_location:
        return 0.5

    if target_city and (listing_location == target_city or target_city in listing_location or listing_location in target_city):
        return 1.0

    if listing_location in {"remote", "hybrid", "remote ok", "remote-friendly"}:
        return 1.0

    return 0.1


def _recency_component(listing: dict[str, Any]) -> float:
    posted_at = listing.get("posted_at")
    if posted_at is None or posted_at == "":
        return 0.5

    try:
        if isinstance(posted_at, str):
            if posted_at.endswith("Z"):
                posted_at = posted_at[:-1] + "+00:00"
            posted_dt = datetime.fromisoformat(posted_at)
        else:
            posted_dt = datetime.fromisoformat(str(posted_at))
    except ValueError:
        return 0.5

    if posted_dt.tzinfo is None:
        posted_dt = posted_dt.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    age_days = max(0.0, (now - posted_dt).total_seconds() / 86400.0)
    if age_days <= 0:
        return 1.0
    if age_days >= 30:
        return 0.0
    return max(0.0, min(1.0, 1.0 - (age_days / 30.0)))


def _weighted_score(components: dict[str, float], config: Any) -> int:
    weights = {
        "skill_match": float(getattr(config, "skill_match_weight", 0.45) or 0.45),
        "seniority_fit": float(getattr(config, "seniority_fit_weight", 0.25) or 0.25),
        "location_fit": float(getattr(config, "location_fit_weight", 0.15) or 0.15),
        "recency": float(getattr(config, "recency_weight", 0.15) or 0.15),
    }
    total = (
        components["skill_match"] * weights["skill_match"]
        + components["seniority_fit"] * weights["seniority_fit"]
        + components["location_fit"] * weights["location_fit"]
        + components["recency"] * weights["recency"]
    )
    return max(0, min(100, int(round(total * 100))))


def _days_ago_text(posted_at: Any) -> str:
    if posted_at is None or posted_at == "":
        return "posted unknown"

    try:
        if isinstance(posted_at, str):
            if posted_at.endswith("Z"):
                posted_at = posted_at[:-1] + "+00:00"
            posted_dt = datetime.fromisoformat(posted_at)
        else:
            posted_dt = datetime.fromisoformat(str(posted_at))
    except ValueError:
        return "posted unknown"

    if posted_dt.tzinfo is None:
        posted_dt = posted_dt.replace(tzinfo=timezone.utc)

    age_days = max(0.0, (datetime.now(timezone.utc) - posted_dt).total_seconds() / 86400.0)
    rounded = max(0, int(round(age_days)))
    return f"posted {rounded}d ago"


def build_reason(components: dict[str, float], facts: dict[str, Any], config: Any) -> str:
    required = [str(skill).strip().lower() for skill in (facts.get("required_skills") or []) if str(skill).strip()]
    profile = set(_config_skills(config))
    matched_required = sum(1 for skill in required if skill in profile)

    required_part = f"{matched_required}/{len(required)} required skills" if required else "0/0 required skills"

    seniority_text = "seniority fits" if components["seniority_fit"] >= 0.6 else "seniority mismatch"

    location_text = "remote" if bool(facts.get("remote_ok")) else "location fit" if components["location_fit"] >= 0.9 else "location mismatch"

    recency_text = _days_ago_text((facts.get("posted_at") if isinstance(facts, dict) else None))
    if not isinstance(facts, dict):
        recency_text = "posted unknown"

    missing = [skill for skill in required if skill not in profile]
    pieces = [required_part, seniority_text, location_text, recency_text]
    if missing:
        pieces.append(f"gap: {', '.join(missing[:5])}")
    return " · ".join(pieces)


def score_listing(listing: dict[str, Any], facts: dict[str, Any], config: Any) -> dict[str, Any]:
    """Compute a deterministic score and reason from extracted listing facts."""
    components = {
        "skill_match": _skill_match_component(facts, config),
        "seniority_fit": _seniority_fit_component(facts, config),
        "location_fit": _location_fit_component(listing, facts, config),
        "recency": _recency_component(listing),
    }
    components = {key: _normalise_float(value) for key, value in components.items()}
    score = _weighted_score(components, config)
    reason = build_reason(components, facts, config)
    return {"score": score, "reason": reason, "components": components}
