from types import SimpleNamespace

from edgedash.query import tools


SNAPSHOT = {"finished_at": "2026-08-27T00:00:00+00:00", "gap_run_id": "run-1"}


def setup_tools(monkeypatch, rows=None):
    monkeypatch.setattr(tools, "_context", lambda: ("db", {"k8s": "kubernetes"}))
    monkeypatch.setattr(tools.storage, "get_query_snapshot", lambda path: SNAPSHOT)
    monkeypatch.setattr(tools.storage, "query_companies_hiring", lambda *args: rows or [])
    monkeypatch.setattr(tools.storage, "query_best_matches", lambda *args: rows or [])
    monkeypatch.setattr(tools.storage, "query_top_gaps", lambda *args: rows or [])
    monkeypatch.setattr(tools.storage, "query_gap_detail", lambda *args: rows or [])
    monkeypatch.setattr(tools.storage, "query_trend", lambda *args: rows or [])
    monkeypatch.setattr(tools.storage, "query_listing_count", lambda *args: [{"listings": 0, "scored": 0, "unscored": 0}])
    monkeypatch.setattr(tools.storage, "query_skill_demand", lambda *args: rows or [{"skill": "unknown", "required": 0, "nice_to_have": 0}])
    monkeypatch.setattr(tools.storage, "query_skill_exists", lambda *args: bool(rows))


def test_all_tools_are_registered_with_router_metadata():
    assert set(tools.TOOLS) == {
        "companies_hiring", "best_matches", "top_gaps", "gap_detail",
        "trend", "listing_count", "skill_demand",
    }
    assert all(item["description"] and "parameters" in item for item in tools.TOOLS.values())


def test_integer_parameters_clamp_at_both_bounds(monkeypatch):
    values = []
    monkeypatch.setattr(tools, "_context", lambda: ("db", {}))
    monkeypatch.setattr(tools.storage, "get_query_snapshot", lambda path: SNAPSHOT)
    monkeypatch.setattr(tools.storage, "query_companies_hiring", lambda path, cutoff, since: values.append(since) or [])
    tools.companies_hiring(-100)
    tools.companies_hiring(1000)
    assert values == ["2026-08-26", "2026-05-29"]
    assert tools._clamp(-1, 1, 25) == 1
    assert tools._clamp(999, 1, 25) == 25


def test_each_tool_returns_rows_and_summary(monkeypatch):
    setup_tools(monkeypatch, [{"skill": "python", "count": 1}])
    calls = [
        tools.companies_hiring(), tools.best_matches(), tools.top_gaps(),
        tools.gap_detail("python"), tools.trend(), tools.listing_count(),
        tools.skill_demand("python"),
    ]
    assert all(set(result) == {"rows", "summary"} for result in calls)
    assert all(isinstance(result["rows"], list) and isinstance(result["summary"], str) for result in calls)


def test_unknown_skill_returns_empty(monkeypatch):
    setup_tools(monkeypatch, [])
    assert tools.gap_detail("not-in-database")["rows"] == []
    assert tools.skill_demand("not-in-database")["rows"] == []
