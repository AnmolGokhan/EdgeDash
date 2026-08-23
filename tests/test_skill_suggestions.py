from edgedash import skills


def test_suggestions_print_yaml_and_flag_existing_choice(monkeypatch, capsys):
    monkeypatch.setattr(
        skills,
        "complete_json",
        lambda prompt, schema, max_retries=1: [
            {"canonical": "javascript", "variants": ["node", "js"], "confidence": "low"}
        ],
    )

    skills._print_suggestions(
        skills._suggest_aliases(
            [{"skill": "node", "count": 2}, {"skill": "js", "count": 1}],
            {"node": "node", "js": "javascript"},
        ),
        {"node": "node", "js": "javascript"},
    )
    output = capsys.readouterr().out

    assert "WARNING" in output
    assert "CONFLICT" in output
    assert '"node": "javascript"' in output


def test_suggestion_command_does_not_write_config(monkeypatch):
    calls = []
    monkeypatch.setattr(skills, "complete_json", lambda *args, **kwargs: calls.append(args) or [])
    result = skills._suggest_aliases([{"skill": "sql", "count": 1}], {})

    assert result == []
    assert len(calls) == 1