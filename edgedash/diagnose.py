"""Read-only diagnostics for the existing EdgeDash database."""

from __future__ import annotations

import json
from pathlib import Path

import edgedash.storage as storage
from edgedash.config import load_config


def _print_section(title: str) -> None:
    print(f"\n{title}")
    print("-" * len(title))


def _fmt_source_counts(counts: list[dict]) -> str:
    if not counts:
        return "none"
    return ", ".join(f"{row['source']}={row['COUNT(*)']}" for row in counts)


def main() -> None:
    cfg = load_config()
    data = storage.get_listing_diagnostics(cfg.db_path)

    _print_section("Listings")
    print(f"total: {data['total_listings']}")
    print(f"by source: {_fmt_source_counts(data['source_counts'])}")

    _print_section("Probable cross-source duplicates")
    print(data["probable_cross_source_duplicates"])

    _print_section("5 most recent listings")
    if not data["recent"]:
        print("none")
    else:
        for row in data["recent"]:
            print(
                f"{row['source']} | {row['title']} | {row['company']} | "
                f"fetched={row['fetched_at']} | posted={row['posted_at']}"
            )

    _print_section("Data quality issues")
    if not data["data_quality_issues"]:
        print("none")
    else:
        for row in data["data_quality_issues"]:
            print(
                f"{row['source']} | title={row['title']} | company={row['company']} | "
                f"url={row['url']}"
            )


if __name__ == "__main__":
    main()
