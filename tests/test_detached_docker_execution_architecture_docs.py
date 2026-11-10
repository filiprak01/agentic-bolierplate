from pathlib import Path


ARCHITECTURE = Path("docs/detached-docker-execution-architecture.md")
READINESS = Path("docs/docker-worker-readiness.md")
REQUIREMENTS = Path("docs/docker-worker-requirements.md")


def test_detached_docker_execution_architecture_doc_exists_with_boundary() -> None:
    text = ARCHITECTURE.read_text()

    assert "Detached Docker Execution Architecture" in text
    assert "Release 1.2 architecture contract" in text
    assert "Codex Execution Bridge" in text
    assert "host-side" in text
    assert "in-container" in text


def test_detached_architecture_covers_required_system_boundaries() -> None:
    text = ARCHITECTURE.read_text()

    for boundary in (
        "Docker Worker",
        "Codex Execution Bridge",
        "Durable Stores",
        "Jira",
        "GitHub",
        "Docs Publication",
        "AgileTest",
        "PO Inbox",
    ):
        assert boundary in text


def test_detached_architecture_defines_lifecycle_and_checkpoint_ownership() -> None:
    text = ARCHITECTURE.read_text()

    for status in (
        "`queued`",
        "`assigned`",
        "`in_progress`",
        "`waiting_codex`",
        "`paused_limit`",
        "`blocked_po`",
        "`completed`",
    ):
        assert status in text

    assert "Checkpoint Ownership" in text
    assert "Workers resume from the latest checkpoint they own" in text


def test_detached_architecture_defines_safety_contract() -> None:
    text = ARCHITECTURE.read_text()

    for phrase in (
        "Credential And Volume Contract",
        "External Adapter Contract",
        "Termination Behavior",
        "Codex limit availability",
        "PO inbox",
        "must be isolated",
        "must not invent a route silently",
        "HostSideCodexExecutionBridge",
        "failed request artifacts",
    ):
        assert phrase in text


def test_existing_worker_docs_link_to_detached_architecture_contract() -> None:
    assert "docs/detached-docker-execution-architecture.md" in READINESS.read_text()
    assert "docs/detached-docker-execution-architecture.md" in REQUIREMENTS.read_text()
