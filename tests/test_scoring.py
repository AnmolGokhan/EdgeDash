from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from edgedash.scoring import score_listing


def _config(**overrides):
    base = {
        "skills": ["python", "sql", "postgres", "kubernetes", "spark"],
        "target_city": "Bengaluru",
        "target_seniority": "mid",
        "skill_match_weight": 0.45,
        "seniority_fit_weight": 0.25,
        "location_fit_weight": 0.15,
        "recency_weight": 0.15,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_score_listing_perfect_match():
    listing = {
        "location": "Bengaluru",
        "remote_ok": True,
        "posted_at": datetime.now(timezone.utc).isoformat(),
    }
    facts = {
        "required_skills": ["python", "sql"],
        "nice_to_have": ["postgres"],
        "seniority": "mid",
        "years_required": 3,
        "remote_ok": True,
    }

    result = score_listing(listing, facts, _config())

    assert result["score"] == 100
    assert result["components"]["skill_match"] >= 0.9
    assert result["components"]["seniority_fit"] == 1.0
    assert result["components"]["location_fit"] == 1.0
    assert result["components"]["recency"] == 1.0


def test_score_listing_zero_match():
    listing = {
        "location": "Paris",
        "remote_ok": False,
        "posted_at": (datetime.now(timezone.utc) - timedelta(days=45)).isoformat(),
    }
    facts = {
        "required_skills": ["kubernetes", "spark"],
        "nice_to_have": [],
        "seniority": "junior",
        "years_required": None,
        "remote_ok": False,
    }

    result = score_listing(listing, facts, _config(skills=[]))

    assert result["score"] < 25
    assert result["components"]["skill_match"] == 0.0
    assert result["components"]["location_fit"] == 0.1


def test_score_listing_empty_required_skills():
    listing = {
        "location": "Bengaluru",
        "remote_ok": True,
        "posted_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
    }
    facts = {
        "required_skills": [],
        "nice_to_have": [],
        "seniority": "mid",
        "years_required": None,
        "remote_ok": True,
    }

    result = score_listing(listing, facts, _config())

    assert result["components"]["skill_match"] == 1.0
    assert result["score"] == 100


def test_score_listing_null_posted_at():
    listing = {
        "location": "Bengaluru",
        "remote_ok": False,
        "posted_at": None,
    }
    facts = {
        "required_skills": ["python"],
        "nice_to_have": [],
        "seniority": "mid",
        "years_required": None,
        "remote_ok": False,
    }

    result = score_listing(listing, facts, _config())

    assert result["components"]["recency"] == 0.5
    assert 85 <= result["score"] <= 100


def test_score_listing_null_remote_ok():
    listing = {
        "location": "Bengaluru",
        "remote_ok": None,
        "posted_at": (datetime.now(timezone.utc) - timedelta(days=3)).isoformat(),
    }
    facts = {
        "required_skills": ["python"],
        "nice_to_have": [],
        "seniority": "mid",
        "years_required": None,
        "remote_ok": None,
    }

    result = score_listing(listing, facts, _config())

    assert result["components"]["location_fit"] == 1.0
    assert result["score"] >= 80


def test_score_listing_seniority_three_bands_off():
    listing = {
        "location": "Bengaluru",
        "remote_ok": False,
        "posted_at": (datetime.now(timezone.utc) - timedelta(days=5)).isoformat(),
    }
    facts = {
        "required_skills": ["python"],
        "nice_to_have": [],
        "seniority": "junior",
        "years_required": None,
        "remote_ok": False,
    }

    result = score_listing(listing, facts, _config(target_seniority="senior"))

    assert result["components"]["seniority_fit"] == 0.25
    assert result["score"] < 90
