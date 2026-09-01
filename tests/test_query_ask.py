from types import SimpleNamespace

import pytest

from edgedash.query import ask as ask_module


class FakeStorage:
    def __init__(self):
        self.logged = []

    def init_db(self, path):
        pass

    def log_query(self, *args):
        self.logged.append(args)


def test_ask_routes_executes_and_phrases_once(monkeypatch):
    calls = []
    storage = FakeStorage()
    monkeypatch.setattr(ask_module, "storage", storage)
    monkeypatch.setattr(ask_module, "load_config", lambda: SimpleNamespace(db_path="db"))
    monkeypatch.setattr(
        ask_module,
        "complete_json",
        lambda prompt, schema: calls.append((prompt, schema)) or (
            {"tool": "best_matches", "params": {"n": 2}, "confidence": "high"}
            if len(calls) == 1 else {"text": "Two matches were found."}
        ),
    )
    monkeypatch.setitem(
        ask_module.TOOLS,
        "best_matches",
        {"description": "best", "parameters": {"n": {"type": "integer", "minimum": 1, "maximum": 25}}, "function": lambda n=10: {"rows": [{"score": 80}], "summary": "1 verified listing"}},
    )

    answer = ask_module.ask("show matches")

    assert answer.text == "Two matches were found."
    assert answer.rows == [{"score": 80}]
    assert answer.tool_used == "best_matches"
    assert len(calls) == 2
    assert len(storage.logged) == 1
    assert storage.logged[0][1] == "show matches"
    assert storage.logged[0][2:5] == ("best_matches", {"n": 2}, True)


def test_ask_null_tool_does_not_phrase(monkeypatch):
    calls = []
    storage = FakeStorage()
    monkeypatch.setattr(ask_module, "storage", storage)
    monkeypatch.setattr(ask_module, "load_config", lambda: SimpleNamespace(db_path="db"))
    monkeypatch.setattr(ask_module, "complete_json", lambda *args, **kwargs: calls.append(args) or {"tool": None, "params": {}, "confidence": "high"})

    answer = ask_module.ask("what is the weather?")

    assert answer.tool_used is None
    assert answer.rows == []
    assert len(calls) == 1
    assert "cannot be answered" in answer.text


def test_ask_unknown_tool_is_hard_error(monkeypatch):
    storage = FakeStorage()
    monkeypatch.setattr(ask_module, "storage", storage)
    monkeypatch.setattr(ask_module, "load_config", lambda: SimpleNamespace(db_path="db"))
    monkeypatch.setattr(ask_module, "complete_json", lambda *args, **kwargs: {"tool": "not_a_tool", "params": {}, "confidence": "high"})

    with pytest.raises(ValueError, match="unknown tool"):
        ask_module.ask("do something")
    assert len(storage.logged) == 1
