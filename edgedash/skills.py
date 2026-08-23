"""Deterministic skill canonicalisation and extraction-cache auditing."""

from __future__ import annotations

import argparse
import json
import re
import string
from collections import Counter
from typing import Any

import edgedash.storage as storage
from edgedash.config import load_config
from edgedash.llm import LLMError, complete_json


def _normalise(raw: str) -> str:
    value = raw.lower().strip()
    value = re.sub(r"\s*\([^)]*\)", "", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value.strip(string.punctuation + " \t\r\n")


def canonical(raw: str, aliases: dict) -> str:
    """Return the explicit, deterministic canonical form of a skill."""
    value = _normalise(raw)
    normalised_aliases = {
        _normalise(str(key)): _normalise(str(target))
        for key, target in aliases.items()
    }
    return normalised_aliases.get(value, value)


def _print_audit(rows: list[dict], aliases: dict[str, str], limit: int) -> None:
    print(f"Top {limit} raw required skills")
    print("---------------------------")
    for row in rows[:limit]:
        raw = str(row["skill"])
        print(f"{row['count']:>5}  {raw} -> {canonical(raw, aliases)}")

    print("\nRaw skills seen exactly once")
    print("----------------------------")
    singletons = [row for row in rows if row["count"] == 1]
    if not singletons:
        print("none")
    else:
        for row in singletons:
            raw = str(row["skill"])
            print(f"{raw} -> {canonical(raw, aliases)}")


_ALIAS_SUGGESTION_SCHEMA: dict[str, Any] = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "canonical": {"type": "string"},
            "variants": {"type": "array", "items": {"type": "string"}},
            "confidence": {"type": "string", "enum": ["high", "low"]},
        },
        "required": ["canonical", "variants", "confidence"],
        "additionalProperties": False,
    },
}


def _canonical_counts(rows: list[dict], aliases: dict[str, str]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for row in rows:
        counts[canonical(str(row["skill"]), aliases)] += int(row["count"])
    return counts


def _suggest_aliases(rows: list[dict], aliases: dict[str, str]) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    for row in rows:
        counts[canonical(str(row["skill"]), {})] += int(row["count"])
    known_keys = {canonical(str(key), {}) for key in aliases}
    candidates = [
        {"skill": skill, "count": count}
        for skill, count in counts.most_common()
        if skill not in known_keys
    ]
    prompt = (
        "Suggest only possible canonical skill groupings from this observed list. "
        "Do not invent skills or merge distinct skills such as node and javascript. "
        "Return an array of objects with canonical, variants, and confidence. "
        "Variants must come only from the supplied strings.\n\n"
        f"Observed canonical skill strings and counts:\n{json.dumps(candidates, sort_keys=True)}"
    )
    result = complete_json(prompt, _ALIAS_SUGGESTION_SCHEMA, max_retries=0)
    return result if isinstance(result, list) else []


def _conflict(proposal: dict[str, Any], aliases: dict[str, str]) -> bool:
    target = canonical(str(proposal["canonical"]), {})
    for variant in proposal["variants"]:
        key = canonical(str(variant), {})
        if key in aliases and canonical(str(aliases[key]), {}) != target:
            return True
    return False


def _print_suggestions(proposals: list[dict[str, Any]], aliases: dict[str, str]) -> None:
    print("WARNING: These are model suggestions only and require your review.")
    print("Merging distinct skills is worse than leaving them separate.")
    print("\nReady-to-paste config.yaml alias entries:")
    print("skill_aliases:")
    if not proposals:
        print("  # No groupings suggested.")
        return
    for proposal in proposals:
        if _conflict(proposal, aliases):
            print("  # !!! CONFLICT with an existing alias-map choice !!!")
        target = canonical(str(proposal["canonical"]), {})
        for variant in proposal["variants"]:
            print(f"  {json.dumps(canonical(str(variant), {}))}: {json.dumps(target)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit extracted raw skill names.")
    parser.add_argument("--audit", action="store_true", help="audit required skills in the extraction cache")
    parser.add_argument("--suggest-aliases", action="store_true", help="ask the model for alias suggestions")
    parser.add_argument("--limit", type=int, default=40, help="number of common raw skills to print")
    args = parser.parse_args()
    if args.audit == args.suggest_aliases:
        parser.error("pass exactly one of --audit or --suggest-aliases")
    if args.limit < 1:
        parser.error("--limit must be at least 1")

    config = load_config()
    rows = storage.get_extracted_skill_counts(config.db_path)
    if args.suggest_aliases:
        try:
            proposals = _suggest_aliases(rows, config.skill_aliases)
        except LLMError as exc:
            print(f"Alias suggestion failed: {exc}")
            raise SystemExit(1) from exc
        _print_suggestions(proposals, config.skill_aliases)
    else:
        _print_audit(rows, config.skill_aliases, args.limit)


if __name__ == "__main__":
    main()