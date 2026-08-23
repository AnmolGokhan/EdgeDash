"""Shared HTTP helper — the only place in the project that makes HTTP requests.

All network calls go through get_json(). It enforces:
- 10 s timeout
- 2 retries for timeouts and 429 responses with exponential backoff (1 s, then 2 s)
- A real User-Agent header
- Raises SourceError (never swallows failures silently)
"""

from __future__ import annotations

import time
from typing import Any

try:
    import requests
except ImportError as exc:
    raise ImportError(
        "requests is required: pip install requests"
    ) from exc

_USER_AGENT = (
    "EdgeDash/0.1 (+https://github.com/edgedash; job-board-crawler) "
    "Python-requests"
)
_TIMEOUT_SECONDS = 10
_MAX_RETRIES = 2
_BACKOFF_BASE = 1.0  # seconds; doubled on each retry


class SourceError(Exception):
    """Raised when a source fails to fetch data."""


def get_json(
    url: str,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> Any:
    """Fetch a URL and return the parsed JSON body.

    Retries up to _MAX_RETRIES times with exponential backoff.
    Raises SourceError on any persistent failure.
    """
    merged_headers = {"User-Agent": _USER_AGENT}
    if headers:
        merged_headers.update(headers)

    last_error: Exception | None = None

    for attempt in range(_MAX_RETRIES + 1):
        if attempt > 0:
            sleep_for = _BACKOFF_BASE * (2 ** (attempt - 1))
            time.sleep(sleep_for)

        try:
            response = requests.get(
                url,
                params=params,
                headers=merged_headers,
                timeout=_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            return response.json()

        except requests.exceptions.Timeout as exc:
            last_error = exc
        except requests.exceptions.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "?"
            if status == 429:
                last_error = exc
                continue
            # Other 4xx errors are not transient and should fail immediately.
            raise SourceError(
                f"HTTP {status} from {url}: {exc}"
            ) from exc
        except requests.exceptions.RequestException as exc:
            last_error = exc

    raise SourceError(
        f"Failed to fetch {url} after {_MAX_RETRIES + 1} attempts: {last_error}"
    ) from last_error
