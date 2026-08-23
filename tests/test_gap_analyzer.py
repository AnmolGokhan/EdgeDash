from types import SimpleNamespace

from edgedash.agents.gap_analyzer import _gap_rows


def _config(**overrides):
    values = {
        "skills": ["Python", "Kubernetes"],
        "skill_aliases": {"k8s": "kubernetes"},
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_gap_rows_uses_weighted_cost_and_canonical_matching():
    listings = [
        {"id": "high", "fit_score": 85, "required_skills": ["PostgreSQL"], "nice_to_have": []},
        {"id": "low", "fit_score": 20, "required_skills": ["postgres"], "nice_to_have": ["PostgreSQL", "PostgreSQL"]},
        {"id": "owned", "fit_score": 99, "required_skills": ["k8s"], "nice_to_have": []},
    ]
    config = _config(skill_aliases={"postgresql": "postgres", "k8s": "kubernetes"})

    rows = _gap_rows(listings, config)

    assert rows[0]["skill"] == "postgres"
    assert rows[0]["listings_blocked"] == 2
    assert rows[0]["opportunity_cost"] == 1.05
    assert rows[0]["mean_score"] == 52.5
    assert rows[0]["top_score"] == 85
    assert rows[0]["example_ids"] == ["high", "low"]
    assert rows[0]["also_nice_to_have"] == 1


def test_gap_rows_can_identify_low_confidence_sample():
    rows = _gap_rows(
        [{"id": "one", "fit_score": 40, "required_skills": ["spark"], "nice_to_have": []}],
        _config(),
    )

    assert rows[0]["listings_blocked"] < 3