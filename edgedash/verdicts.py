"""Read-only verification history for recent EdgeDash cycles."""

from __future__ import annotations

import argparse
import ast
import re
from collections import Counter

import edgedash.storage as storage
from edgedash.config import load_config


_FIELD_RE = re.compile(r"(?P<field>ran|skipped|failed_checks|retry_count|durations)=(?P<value>.*?)(?= \| \w+=|$)")
_CHECK_RE = re.compile(r"name='([^']+)'|name=([A-Za-z_]+)")


def _field(notes: str, name: str) -> str:
    match = next((match for match in _FIELD_RE.finditer(notes or "") if match.group("field") == name), None)
    return match.group("value").strip() if match else ""


def _checks(notes: str) -> list[str]:
    value = _field(notes, "failed_checks")
    return [match.group(1) or match.group(2) for match in _CHECK_RE.finditer(value)]


def _agents(notes: str) -> str:
    value = _field(notes, "ran")
    return value.strip("[]") or "none"


def _retry_count(notes: str) -> str:
    return _field(notes, "retry_count") or "0"


def _duration(notes: str) -> str:
    value = _field(notes, "durations")
    try:
        durations = ast.literal_eval(value)
        return f"{sum(float(item) for item in durations.values()):.1f}s"
    except (ValueError, SyntaxError, AttributeError, TypeError):
        return "n/a"


def _verdict(status: str) -> str:
    if status == "complete":
        return "pass"
    if status == "degraded":
        return "degraded"
    return "fail"


def _print_history(rows: list[dict], check_name: str | None = None) -> None:
    filtered = [row for row in rows if not check_name or check_name in _checks(row.get("notes", ""))]
    print("Timestamp                 Agents run                    Verdict    Failed checks       Retries  Duration")
    print("------------------------  -----------------------------  ---------  -------------------  -------  --------")
    counts: Counter[str] = Counter()
    for row in filtered:
        verdict = _verdict(row.get("status", ""))
        failed = _checks(row.get("notes", ""))
        counts.update(failed)
        failed_text = ", ".join(failed) if failed else "none"
        marker = "!!" if verdict != "pass" else "  "
        print(
            f"{marker} {row.get('finished_at') or row.get('started_at', ''):<22}  "
            f"{_agents(row.get('notes', '')):<29}  {verdict:<9}  {failed_text:<19}  "
            f"{_retry_count(row.get('notes', '')):>7}  {_duration(row.get('notes', '')):>8}"
        )

    total = len(filtered)
    passed = sum(_verdict(row.get("status", "")) == "pass" for row in filtered)
    rate = passed / total * 100 if total else 0.0
    common = counts.most_common(1)[0][0] if counts else "none"
    print(f"\nPass rate: {passed}/{total} ({rate:.1f}%) | Most frequent failing check: {common}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Show recent cycle verification history.")
    parser.add_argument("--check", help="show only cycles where this check failed")
    args = parser.parse_args()
    config = load_config()
    rows = storage.get_verification_history(config.db_path, limit=20)
    if not rows:
        print("no cycles yet")
        return
    _print_history(rows, args.check)


if __name__ == "__main__":
    main()