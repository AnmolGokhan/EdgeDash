"""Apify job-board source."""

from __future__ import annotations

import os
from typing import Any

from edgedash.config import Config
from edgedash.sources.base import register
from edgedash.sources.http import SourceError, get_json

_ACTOR_URL = "https://api.apify.com/v2/acts/apify/google-jobs-scraper/run-sync-get-dataset-items"
_MAX_RESULTS = 100


def _pick(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _normalise(item: dict[str, Any]) -> dict[str, Any]:
    """Map a raw Apify record to the repo's canonical listing schema."""
    raw_url = _pick(item.get("url"), item.get("applyUrl"), item.get("link"))
    posted_at = _pick(item.get("publishedAt"), item.get("postedAt"), item.get("date"))

    return {
        "source": "apify",
        "external_id": str(_pick(item.get("id"), item.get("externalId"), raw_url, item.get("title"), "apify-item")),
        "title": _pick(item.get("title"), item.get("jobTitle"), item.get("position")),
        "company": _pick(item.get("company"), item.get("companyName"), item.get("employer")),
        "location": _pick(item.get("location"), item.get("city"), item.get("place")),
        "url": raw_url,
        "description": _pick(item.get("description"), item.get("text"), item.get("snippet")),
        "posted_at": posted_at,
        "raw": item,
    }


@register
class ApifySource:
    name: str = "apify"

    def fetch(self, config: Config) -> list[dict[str, Any]]:
        token = os.getenv("APIFY_TOKEN")
        if not token:
            print("  [apify] no APIFY_TOKEN, skipping")
            return []

        params = {
            "token": token,
            "search": config.target_role,
            "location": config.target_city,
            "maxItems": _MAX_RESULTS,
        }

        data = get_json(_ACTOR_URL, params=params)
        if isinstance(data, dict):
            items = data.get("items") or data.get("data") or data.get("results") or []
        elif isinstance(data, list):
            items = data
        else:
            items = []

        if not isinstance(items, list):
            items = []

        return [_normalise(item) for item in items[:_MAX_RESULTS]]
