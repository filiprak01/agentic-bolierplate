from pathlib import Path


RUNNER_DOC = Path("docs/host-side-codex-runner.md")
READINESS_DOC = Path("docs/docker-worker-readiness.md")


def test_host_side_runner_doc_describes_worker_execution_bridge() -> None:
    text = RUNNER_DOC.read_text()

    assert "HostSideCodexExecutionBridge" in text
    assert "Worker Request Flow" in text
    assert "creates a queued `CodexJobArtifact`" in text
    assert "Direct in-container Codex execution is explicitly unsupported" in text
    assert "side-effect" in text
    assert "idempotency key" in text


def test_worker_readiness_doc_references_live_bridge_boundary() -> None:
    text = READINESS_DOC.read_text()

    assert "HostSideCodexExecutionBridge" in text
    assert "non-dry-run mode" in text
    assert "does not mount Codex subscription/session secrets" in text
    assert "agentic worker failed-requests" in text
