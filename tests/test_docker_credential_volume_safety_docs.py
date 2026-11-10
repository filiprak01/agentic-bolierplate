from pathlib import Path


MATRIX = Path("docs/docker-credential-volume-safety.md")
CREDENTIAL_SETUP = Path("docs/credential-setup.md")
WORKER_REQUIREMENTS = Path("docs/docker-worker-requirements.md")


def test_docker_credential_volume_safety_matrix_exists_with_release_boundary() -> None:
    text = MATRIX.read_text()
    normalized = " ".join(text.split())

    assert "Docker Credential And Volume Safety Matrix" in text
    assert "Release 1.1 safety baseline" in text
    assert "does not grant detached workers live autonomous access" in normalized


def test_docker_credential_matrix_lists_required_credential_categories() -> None:
    text = MATRIX.read_text()

    for category in (
        "GitHub repository access",
        "Jira Cloud access",
        "Confluence access",
        "AgileTest access",
        "Codex model settings",
        "Codex subscription/session state",
        "Target project settings",
    ):
        assert category in text


def test_docker_volume_matrix_distinguishes_shared_and_isolated_paths() -> None:
    text = MATRIX.read_text()

    assert "Platform durable data" in text
    assert "Target project workspace" in text
    assert "isolated per assignment" in text
    assert "Do not mount the same mutable target checkout" in text


def test_docker_credential_matrix_defines_no_secret_logging() -> None:
    text = MATRIX.read_text()

    assert "No-Secret Logging" in text
    assert "Workers may log" in text
    assert "Workers must not log" in text
    assert "API tokens" in text
    assert "Authorization headers" in text


def test_docker_credential_matrix_records_po_decisions() -> None:
    text = MATRIX.read_text()

    assert "Open Product Owner Decisions" in text
    assert "role-specific Jira" in text
    assert "GitHub accounts" in text
    assert "Codex execution remains host-side" in text


def test_related_docs_link_to_credential_volume_safety_matrix() -> None:
    assert "docs/docker-credential-volume-safety.md" in CREDENTIAL_SETUP.read_text()
    assert "docs/docker-credential-volume-safety.md" in WORKER_REQUIREMENTS.read_text()


def test_credential_setup_defines_token_scopes_and_no_display_rules() -> None:
    text = CREDENTIAL_SETUP.read_text()

    assert "Token Scope Expectations" in text
    assert "GitHub" in text
    assert "Jira Cloud" in text
    assert "Confluence" in text
    assert "AgileTest" in text
    assert "Codex subscription/session" in text
    assert "Never Log Or Display" in text
    assert "Full `.env` contents" in text
    assert "Secret-like file names or paths" in text
    assert "Operator-visible status views" in text
