"""Extract structured facts from a job description without scoring or guessing."""

from __future__ import annotations

import hashlib
from typing import Any

import edgedash.storage as storage
from edgedash.config import load_config
from edgedash.llm import LLMError, complete_json

EXTRACTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "required_skills": {"type": "array", "items": {"type": "string"}},
        "nice_to_have": {"type": "array", "items": {"type": "string"}},
        "seniority": {
            "type": "string",
            "enum": ["junior", "mid", "senior", "lead", "unknown"],
        },
        "years_required": {"type": ["integer", "null"]},
        "remote_ok": {"type": ["boolean", "null"]},
    },
    "required": [
        "required_skills",
        "nice_to_have",
        "seniority",
        "years_required",
        "remote_ok",
    ],
    "additionalProperties": False,
}

EXTRACTION_PROMPT = """Read the job description below and extract only the facts explicitly stated in the listing.

Return a JSON object with exactly these keys:
required_skills, nice_to_have, seniority, years_required, remote_ok

Rules:
- Use only information directly stated in the listing.
- Do not infer, do not guess, do not evaluate the candidate.
- If the listing does not state a field, return [] for list fields, \"unknown\" for seniority, and null for years_required and remote_ok.
- Do not include any other keys.
- Do not consider any candidate profile, skills, experience, or scoring.
- This is a document-reading task only.
- Output JSON only, no prose, no markdown fences.

Job description:
"""

_VALID_SENIORITY = {"junior", "mid", "senior", "lead", "unknown"}
_REQUIRED_KEYS = list(EXTRACTION_SCHEMA["required"])


def _description_hash(description: str | None) -> str:
    """Return a stable SHA-256 digest for the listing text."""
    text = (description or "").strip()
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _normalise_skill_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []

    cleaned: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            continue
        skill = item.strip().lower()
        if not skill or skill in seen:
            continue
        seen.add(skill)
        cleaned.append(skill)
    return cleaned


def _normalise_extraction(raw: dict[str, Any]) -> dict[str, Any]:
    seniority = raw.get("seniority")
    if not isinstance(seniority, str):
        seniority_name = "unknown"
    else:
        seniority_name = seniority.strip().lower()
        if seniority_name not in _VALID_SENIORITY:
            seniority_name = "unknown"

    years_required = raw.get("years_required")
    if not isinstance(years_required, int) or isinstance(years_required, bool):
        years_required = None

    remote_ok = raw.get("remote_ok")
    if not isinstance(remote_ok, bool):
        remote_ok = None

    result = {
        "required_skills": _normalise_skill_list(raw.get("required_skills")),
        "nice_to_have": _normalise_skill_list(raw.get("nice_to_have")),
        "seniority": seniority_name,
        "years_required": years_required,
        "remote_ok": remote_ok,
    }
    return {key: result[key] for key in _REQUIRED_KEYS}


def extract(listing: dict) -> dict:
    """Extract structured facts from a listing, using the cache before the model."""
    description = listing.get("description") or ""
    description_hash = _description_hash(description)

    config = load_config()
    storage.init_db(config.db_path)

    cached = storage.get_extraction_cache(config.db_path, description_hash)
    if cached is not None:
        return _normalise_extraction(cached)

    prompt = f"{EXTRACTION_PROMPT}\n{description}"
    data = complete_json(prompt, EXTRACTION_SCHEMA, max_retries=1)

    if set(data.keys()) - set(_REQUIRED_KEYS):
        raise ValueError("Extraction response included unexpected keys")

    result = _normalise_extraction(data)
    storage.set_extraction_cache(config.db_path, description_hash, result)
    return result
