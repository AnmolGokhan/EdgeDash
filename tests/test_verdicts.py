from edgedash.verdicts import _print_history


def test_history_marks_failures_and_summarizes(capsys):
    rows = [
        {"finished_at": "2026-08-23T10:00:00+00:00", "status": "complete", "notes": "ran=['Scorer'] | skipped=[] | durations={} | failed_checks=[] | retry_count=0 | outcome=complete"},
        {"finished_at": "2026-08-23T11:00:00+00:00", "status": "degraded", "notes": "ran=['Scorer', 'Verifier'] | skipped=[] | durations={} | failed_checks=[CheckResult(name='score_spread', passed=False, observed=6, threshold=10, message='bad')] | retry_count=1 | outcome=degraded"},
    ]

    _print_history(rows)
    output = capsys.readouterr().out

    assert "pass" in output
    assert "!!" in output
    assert "score_spread" in output
    assert "Pass rate: 1/2 (50.0%)" in output
    assert "Most frequent failing check: score_spread" in output


def test_history_check_filter(capsys):
    rows = [
        {"finished_at": "one", "status": "failed", "notes": "ran=[] | failed_checks=[CheckResult(name='freshness', passed=False, observed=4, threshold=3)] | retry_count=1"},
        {"finished_at": "two", "status": "complete", "notes": "ran=[] | failed_checks=[] | retry_count=0"},
    ]

    _print_history(rows, "freshness")
    output = capsys.readouterr().out

    assert "one" in output
    assert "two" not in output