"""Print the latest persisted skill-gap snapshot."""

from __future__ import annotations

import argparse

import edgedash.storage as storage
from edgedash.config import load_config


def _print_latest(rows: list[dict]) -> None:
    print("Rank  Skill                         Blocked  Cost   Mean  Confidence  Opportunity")
    print("----  ----------------------------  -------  -----  ----------  -----------")
    if not rows:
        print("No gap snapshot available.")
        return
    maximum = max(row["opportunity_cost"] for row in rows) or 1
    for rank, row in enumerate(rows, 1):
        bar = "#" * max(1, round(row["opportunity_cost"] / maximum * 24))
        confidence = "low" if row["listings_blocked"] < 3 else "ok"
        print(
            f"{rank:>4}  {row['skill']:<28}  {row['listings_blocked']:>7}  "
            f"{row['opportunity_cost']:>5.1f}  {row['mean_score']:>4.1f}  "
            f"{confidence:<10}  {bar}"
        )


def _print_trend(snapshots: list[dict]) -> None:
    if not snapshots:
        print("No gap snapshots available; run the cycle to create one.")
        return
    if len(snapshots) < 2:
        print("Only one snapshot so far; 1 more day of runs is needed to show a trend.")
        return

    earliest = snapshots[0]
    latest = snapshots[-1]
    earliest_rows = {row["skill"]: row for row in earliest["rows"]}
    latest_rows = {row["skill"]: row for row in latest["rows"]}
    print(f"Trend window: {earliest['computed_at']} -> {latest['computed_at']}")
    print("Rank  Skill                         Earliest  Latest  Change   Change %")
    print("----  ----------------------------  --------  ------  -------  --------")
    for rank, (skill, row) in enumerate(latest_rows.items(), 1):
        old = earliest_rows.get(skill)
        latest_cost = row["opportunity_cost"]
        if old is None:
            print(f"{rank:>4}  {skill:<28}  {'NEW':>8}  {latest_cost:>6.1f}  {'NEW':>7}  {'NEW':>8}")
            continue
        earliest_cost = old["opportunity_cost"]
        change = latest_cost - earliest_cost
        percent = "n/a" if earliest_cost == 0 else f"{change / earliest_cost * 100:+.1f}%"
        print(
            f"{rank:>4}  {skill:<28}  {earliest_cost:>8.1f}  {latest_cost:>6.1f}  "
            f"{change:>+7.1f}  {percent:>8}"
        )

    dropped = sorted(set(earliest_rows) - set(latest_rows))
    print("\nDropped out of latest top 10")
    print("---------------------------")
    print("none" if not dropped else "\n".join(f"{skill}  DROPPED OUT" for skill in dropped))


def main() -> None:
    parser = argparse.ArgumentParser(description="View persisted skill-gap snapshots.")
    parser.add_argument("--trend", action="store_true", help="compare earliest and latest snapshots")
    args = parser.parse_args()
    config = load_config()
    storage.init_db(config.db_path)
    if args.trend:
        _print_trend(storage.get_skill_gap_snapshots(config.db_path))
    else:
        _print_latest(storage.get_latest_skill_gap_snapshot(config.db_path))


if __name__ == "__main__":
    main()