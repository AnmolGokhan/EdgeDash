from edgedash.skills import canonical


ALIASES = {
    "k8s": "kubernetes",
    "postgresql": "postgres",
}


def test_canonical_lowercases_and_collapses_whitespace():
    assert canonical("  Python   Developer  ", {}) == "python developer"


def test_canonical_removes_parenthetical_qualifier():
    assert canonical("Kubernetes (EKS)", {}) == "kubernetes"


def test_canonical_applies_alias():
    assert canonical(" POSTGRESQL ", ALIASES) == "postgres"


def test_canonical_preserves_unaliased_term():
    assert canonical("Terraform", ALIASES) == "terraform"


def test_canonical_handles_empty_string():
    assert canonical("", ALIASES) == ""