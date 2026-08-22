"""Base contract for all EdgeDash job-board sources."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from edgedash.config import Config

# Registry: maps source name -> class.
# Add a source by decorating it with @register; nothing else needs to change.
SOURCES: dict[str, type[Source]] = {}


def register(cls: type) -> type:
    """Class decorator that registers a Source implementation by name."""
    SOURCES[cls.name] = cls
    return cls


@runtime_checkable
class Source(Protocol):
    """Uniform interface every source must implement.

    fetch() returns a list of normalised dicts.  Missing values must be None,
    never empty string, never "N/A".

    Required keys per row:
        source        str   – source identifier, e.g. "arbeitnow"
        external_id   str   – the source's own stable slug / id
        title         str | None
        company       str | None
        location      str | None
        url           str   – canonical job URL
        description   str | None
        posted_at     str | None  – ISO-8601 date string or None
        raw           dict  – the original response object, unmodified
    """

    name: str

    def fetch(self, config: Config) -> list[dict[str, Any]]:
        ...
