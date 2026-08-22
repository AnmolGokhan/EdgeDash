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
    "target_role": "Data Analyst",
    "target_city": "Bengaluru",
    "target_seniority": "mid",
    "keywords": [],
    "my_skills": [],
    "skills": [],
    "experience_years": 0,
    "db_path": "edgedash.db",
    "min_fit_score": 60,
    "sources": ["arbeitnow"],
    "use_mock_fetcher": False,
    "llm_provider": "gemini",
    "llm_model": "gemini-3.6-flash",
    "llm_requests_per_minute": 15,
    "scoring_batch_size": 25,
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
    experience_years: int
    db_path: str
    min_fit_score: int
    sources: list[str]
    use_mock_fetcher: bool
    llm_provider: str
    llm_model: str
    llm_requests_per_minute: int
    scoring_batch_size: int
    skill_match_weight: float
    seniority_fit_weight: float
    location_fit_weight: float
    recency_weight: float


def load_config(path: Path | None = None) -> Config:
    """Read config.yaml and return a Config instance.

    Raises FileNotFoundError with a clear message if the file is absent.
    Missing individual fields fall back to sensible defaults.
    """
    load_dotenv(_REPO_ROOT / ".env", override=False)

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
        experience_years=int(merged["experience_years"]),
        db_path=str(merged["db_path"]),
        min_fit_score=int(merged["min_fit_score"]),
        sources=list(merged["sources"]),
        use_mock_fetcher=bool(merged["use_mock_fetcher"]),
        llm_provider=str(merged["llm_provider"]),
        llm_model=str(merged["llm_model"]),
        llm_requests_per_minute=int(merged["llm_requests_per_minute"]),
        scoring_batch_size=int(merged["scoring_batch_size"]),
        skill_match_weight=float(merged["skill_match_weight"]),
        seniority_fit_weight=float(merged["seniority_fit_weight"]),
        location_fit_weight=float(merged["location_fit_weight"]),
        recency_weight=float(merged["recency_weight"]),
    )
