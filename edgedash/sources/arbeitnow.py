"""Arbeitnow job-board source.

Uses the free public API (no key, no signup):
    https://www.arbeitnow.com/api/job-board-api?page=N

Filtering rules (steered by config):
1. Keep listings where title or description contains at least one config keyword.
2. Among those, keep listings whose location contains config.target_city.
3. If fewer than 5 results survive the city filter, relax it (keep all keyword
   matches regardless of location) and log that the filter was relaxed.

Rate-limiting: 1 request per second per steering rule 14.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from edgedash.config import Config
from edgedash.sources.base import register
from edgedash.sources.http import SourceError, get_json

_API_URL = "https://www.arbeitnow.com/api/job-board-api"
_MAX_PAGES = 5
_MIN_RESULTS_BEFORE_RELAXING_LOCATION = 5
_REQUEST_INTERVAL = 1.0  # seconds between requests (steering rule 14)


def _matches_keywords(item: dict[str, Any], keywords: list[str]) -> bool:
    """Return True if any keyword appears in title or description (case-insensitive)."""
    haystack = " ".join(
        [
            (item.get("title") or ""),
            (item.get("description") or ""),
        ]
    ).lower()
    return any(kw.lower() in haystack for kw in keywords)


def _matches_city(item: dict[str, Any], city: str) -> bool:
    """Return True if the listing's location contains the target city."""
    location = (item.get("location") or "").lower()
    return city.lower() in location


def _normalise(item: dict[str, Any]) -> dict[str, Any]:
    """Map a raw Arbeitnow record to our canonical normalised schema."""
    raw_posted = item.get("created_at")
    posted_at: str | None = None
    if isinstance(raw_posted, int):
        # Arbeitnow returns UNIX timestamps
        posted_at = datetime.fromtimestamp(raw_posted, tz=timezone.utc).date().isoformat()

    return {
        "source": "arbeitnow",
        "external_id": item["slug"],       # Arbeitnow's stable slug
        "title": item.get("title") or None,
        "company": item.get("company_name") or None,
        "location": item.get("location") or None,
        "url": item.get("url") or None,
        "description": item.get("description") or None,
        "posted_at": posted_at,
        "raw": item,
    }


@register
class ArbeitnowSource:
    name: str = "arbeitnow"

    def fetch(self, config: Config) -> list[dict[str, Any]]:
        """Fetch up to _MAX_PAGES from Arbeitnow and return filtered rows."""
        all_raw: list[dict[str, Any]] = []

        for page in range(1, _MAX_PAGES + 1):
            try:
                data = get_json(_API_URL, params={"page": page})
            except SourceError:
                print(f"  [arbeitnow] page {page} failed, stopping pagination.")
                break

            items: list[dict[str, Any]] = data.get("data", [])
            print(f"  [arbeitnow] page {page}: {len(items)} raw listings")

            if not items:
                break

            # Filter by keywords on each page; stop paging when we get a
            # page with zero keyword matches (the feed is sorted newest-first
            # so relevance drops off quickly).
            keyword_matches = [i for i in items if _matches_keywords(i, config.keywords)]
            all_raw.extend(keyword_matches)

            if not keyword_matches:
                print(f"  [arbeitnow] no keyword matches on page {page}, stopping.")
                break

            if page < _MAX_PAGES:
                time.sleep(_REQUEST_INTERVAL)

        print(
            f"  [arbeitnow] total keyword-matching listings across pages: {len(all_raw)}"
        )

        # City filter
        city_filtered = [i for i in all_raw if _matches_city(i, config.target_city)]
        filter_relaxed = False

        if len(city_filtered) < _MIN_RESULTS_BEFORE_RELAXING_LOCATION:
            filter_relaxed = True
            print(
                f"  [arbeitnow] only {len(city_filtered)} listings match "
                f"'{config.target_city}' — relaxing location filter to avoid "
                f"empty results. Returning all keyword matches."
            )
            final_raw = all_raw
        else:
            final_raw = city_filtered

        print(
            f"  [arbeitnow] {len(final_raw)} listings after filtering "
            f"({'location relaxed' if filter_relaxed else f'city={config.target_city!r}'})"
        )

        return [_normalise(item) for item in final_raw]
