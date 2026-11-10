from pathlib import Path


THREAT_MODEL = Path("docs/session-docker-automation-threat-model.md")


def test_session_docker_threat_model_exists_with_boundaries() -> None:
    text = THREAT_MODEL.read_text()

    assert "Session Mode And Docker Automation Threat Model" in text
    assert "Release 1.1 threat model" in text
    assert "Current Release 1.1 boundaries" in text
    assert "Future Release 1.2+ boundaries" in text


def test_session_docker_threat_model_covers_required_assets() -> None:
    text = THREAT_MODEL.read_text()

    for asset in (
        "Jira project",
        "GitHub repositories",
        "Confluence spaces",
        "AgileTest test cases",
        "Codex subscription/session access",
        "Local target project source files",
        "Durable platform state",
        "Credentials, tokens",
    ):
        assert asset in text


def test_session_docker_threat_model_separates_controls_from_gaps() -> None:
    text = THREAT_MODEL.read_text()

    assert "Release 1.1 Required Controls" in text
    assert "Release 1.2+ Required Work" in text
    assert "Token leaked through logs" in text
    assert "Detached worker runs beyond scope" in text


def test_session_docker_threat_model_lists_po_decisions() -> None:
    text = THREAT_MODEL.read_text()

    assert "Product Owner Decisions" in text
    assert "role-specific" in text
    assert "subscription/session-backed" in text
    assert "auto-resume after limit reset" in text
    assert "Confluence publication" in text
