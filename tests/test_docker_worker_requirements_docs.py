from pathlib import Path


REQUIREMENTS = Path("docs/docker-worker-requirements.md")
READINESS = Path("docs/docker-worker-readiness.md")


def test_docker_worker_requirements_document_exists_with_release_boundary() -> None:
    text = REQUIREMENTS.read_text()
    normalized = " ".join(text.split())

    assert "Docker Worker Requirements" in text
    assert "Release 1.1 requirements baseline" in text
    assert "does not implement fully autonomous detached Docker workers" in normalized


def test_docker_worker_requirements_cover_instruction_and_context_inputs() -> None:
    text = REQUIREMENTS.read_text()

    assert "Role Instruction Loading" in text
    assert "Root `AGENTS.md`" in text
    assert "Role-specific instruction document" in text
    assert "Context Pack Consumption" in text
    assert "Jira issue key, summary, type, status, labels, and acceptance criteria" in text


def test_docker_worker_requirements_compare_execution_options() -> None:
    text = REQUIREMENTS.read_text()

    assert "Option A - Host-Side Codex Runner" in text
    assert "Option B - In-Container Execution Bridge" in text
    assert "Option C - Dry-Run Worker" in text
    assert "later-release scope" in text


def test_docker_worker_requirements_define_pause_conditions_and_paths() -> None:
    text = REQUIREMENTS.read_text()

    for phrase in (
        "blocking Product Owner question",
        "Codex limits are missing, stale, low, or unavailable",
        "PR conflict",
        "Required configuration or credentials are missing",
        "Target workspace cannot be allocated",
    ):
        assert phrase in text

    assert "`data/po-inbox`" in text
    assert "`data/codex-limits`" in text
    assert "Parallel implementation workers must not share" in text


def test_docker_worker_readiness_links_to_requirements() -> None:
    text = READINESS.read_text()

    assert "docs/docker-worker-requirements.md" in text
    assert "role instruction loading" in text
    assert "context pack consumption" in text
    assert "assignment-lock enforcement" in text
    assert "assignment_lock_allowed=false" in text
    assert "Dry-run mode checks for conflicting active locks" in text
    assert "does not create a new lock" in text
    assert "agentic worker locks list" in text
    assert "Workspace Provisioning Gate" in text
    assert "workspace_gate_allowed=false" in text
    assert "AGENTIC_WORKSPACES_ROOT" in text
    assert "workspace_ready" in text
