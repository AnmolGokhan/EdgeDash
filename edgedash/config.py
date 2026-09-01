"""Load project configuration from config.yaml at the repo root."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# PyYAML is the only practical YAML parser in the Python ecosystem;
# stdlib has no YAML support.
try:
    import yaml
except ImportError as exc:
    raise ImportError(
        "PyYAML is required: pip install pyyaml"
    ) from exc

try:
    from dotenv import load_dotenv
except ImportError as exc:
    raise ImportError(
        "python-dotenv is required: pip install python-dotenv"
    ) from exc

_REPO_ROOT = Path(__file__).parent.parent
_CONFIG_PATH = _REPO_ROOT / "config.yaml"

_DEFAULTS: dict[str, Any] = {
    "target_role": "AI Engineer",
    "target_city": "Bengaluru",
    "target_seniority": "fresher",
    "keywords": [],
    "my_skills": [],
    "skills": [],
    "skill_aliases": {},
    "experience_years": 0,
    "db_path": "edgedash.db",
    "min_fit_score": 60,
    "sources": ["arbeitnow"],
    "use_mock_fetcher": False,
    "llm_provider": "gemini",
    "llm_model": "gemini-3.6-flash",
    "llm_requests_per_minute": 15,
    "scoring_batch_size": 25,
    "fetch_interval_hours": 6,
    "max_pages": 5,
    "max_listings": 500,
    "score_max_seconds": 300,
    "analyse_max_seconds": 60,
    "verify_max_seconds": 60,
    "min_score_spread": 10,
    "min_score_stdev": 5,
    "max_empty_extraction_pct": 0.20,
    "max_skills_per_listing": 20,
    "min_gap_sample": 3,
    "max_data_age_days": 3,
    "skill_match_weight": 0.45,
    "seniority_fit_weight": 0.25,
    "location_fit_weight": 0.15,
    "recency_weight": 0.15,
}


@dataclass
class Config:
    target_role: str
    target_city: str
    target_seniority: str
    keywords: list[str]
    my_skills: list[str]
    skills: list[str]
    skill_aliases: dict[str, str]
    experience_years: int
    db_path: str
    min_fit_score: int
    sources: list[str]
    use_mock_fetcher: bool
    llm_provider: str
    llm_model: str
    llm_requests_per_minute: int
    scoring_batch_size: int
    fetch_interval_hours: int
    max_pages: int
    max_listings: int
    score_max_seconds: int
    analyse_max_seconds: int
    verify_max_seconds: int
    min_score_spread: int
    min_score_stdev: float
    max_empty_extraction_pct: float
    max_skills_per_listing: int
    min_gap_sample: int
    max_data_age_days: int
    skill_match_weight: float
    seniority_fit_weight: float
    location_fit_weight: float
    recency_weight: float


def load_config(path: Path | None = None) -> Config:
    """Read config.yaml and return a Config instance.

    Raises FileNotFoundError with a clear message if the file is absent.
    Missing individual fields fall back to sensible defaults.
    """
    load_dotenv(_REPO_ROOT / "edgedash" / ".env", override=False)

    config_path = path or _CONFIG_PATH

    if not config_path.exists():
        raise FileNotFoundError(
            f"config.yaml not found at '{config_path}'. "
            "Copy config.yaml.example to config.yaml and fill in your details."
        )

    with config_path.open("r", encoding="utf-8") as fh:
        raw: dict[str, Any] = yaml.safe_load(fh) or {}

    merged = {**_DEFAULTS, **raw}

    profile_skills = list(merged.get("skills") or merged.get("my_skills") or [])

    return Config(
        target_role=str(merged["target_role"]),
        target_city=str(merged["target_city"]),
        target_seniority=str(merged.get("target_seniority", "mid")),
        keywords=list(merged["keywords"]),
        my_skills=list(merged["my_skills"]),
        skills=profile_skills,
        skill_aliases={str(key): str(value) for key, value in merged["skill_aliases"].items()},
        experience_years=int(merged["experience_years"]),
        db_path=str(merged["db_path"]),
        min_fit_score=int(merged["min_fit_score"]),
        sources=list(merged["sources"]),
        use_mock_fetcher=bool(merged["use_mock_fetcher"]),
        llm_provider=str(merged["llm_provider"]),
        llm_model=str(merged["llm_model"]),
        llm_requests_per_minute=int(merged["llm_requests_per_minute"]),
        scoring_batch_size=int(merged["scoring_batch_size"]),
        fetch_interval_hours=int(merged["fetch_interval_hours"]),
        max_pages=int(merged["max_pages"]),
        max_listings=int(merged["max_listings"]),
        score_max_seconds=int(merged["score_max_seconds"]),
        analyse_max_seconds=int(merged["analyse_max_seconds"]),
        verify_max_seconds=int(merged["verify_max_seconds"]),
        min_score_spread=int(merged["min_score_spread"]),
        min_score_stdev=float(merged["min_score_stdev"]),
        max_empty_extraction_pct=float(merged["max_empty_extraction_pct"]),
        max_skills_per_listing=int(merged["max_skills_per_listing"]),
        min_gap_sample=int(merged["min_gap_sample"]),
        max_data_age_days=int(merged["max_data_age_days"]),
        skill_match_weight=float(merged["skill_match_weight"]),
        seniority_fit_weight=float(merged["seniority_fit_weight"]),
        location_fit_weight=float(merged["location_fit_weight"]),
        recency_weight=float(merged["recency_weight"]),
    )
