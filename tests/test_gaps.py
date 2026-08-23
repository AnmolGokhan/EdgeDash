from edgedash.gaps import _print_trend


def _snapshot(run_id, computed_at, rows):
    return {"run_id": run_id, "computed_at": computed_at, "rows": rows}


def _row(skill, cost):
    return {
        "skill": skill,
        "opportunity_cost": cost,
        "listings_blocked": 1,
        "mean_score": 50,
        "top_score": 50,
        "example_ids": [f"{skill}-id"],
        "also_nice_to_have": 0,
    }


def test_trend_refuses_to_invent_history(capsys):
    _print_trend([_snapshot("one", "2026-08-22T00:00:00+00:00", [_row("python", 1.0)])])

    assert capsys.readouterr().out == (
        "Only one snapshot so far; 1 more day of runs is needed to show a trend.\n"
    )


def test_trend_reports_changes_new_and_dropped(capsys):
    _print_trend(
        [
            _snapshot("one", "2026-08-20T00:00:00+00:00", [_row("python", 1.0), _row("spark", 2.0)]),
            _snapshot("two", "2026-08-22T00:00:00+00:00", [_row("python", 1.5), _row("kubernetes", 3.0)]),
        ]
    )
    output = capsys.readouterr().out

    assert "2026-08-20T00:00:00+00:00 -> 2026-08-22T00:00:00+00:00" in output
    assert "python" in output and "+50.0%" in output
    assert "kubernetes" in output and "NEW" in output
    assert "spark  DROPPED OUT" in output