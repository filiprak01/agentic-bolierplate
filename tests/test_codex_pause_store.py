from pathlib import Path

import pytest

from agentic_boilerplate.domain import (
    AgentRole,
    CodexFailedRequestArtifact,
    CodexJobStatus,
    CodexLinkedArtifact,
    CodexLinkedArtifactKind,
    CodexPausedAssignmentArtifact,
    CodexPauseReason,
    CodexPauseSchemaError,
    CodexResumeAction,
    CodexResumePlan,
)
from agentic_boilerplate.storage import (
    FAILED_REQUESTS_FOLDER,
    PAUSED_ASSIGNMENTS_FOLDER,
    CodexPauseArtifactAlreadyExistsError,
    CodexPauseArtifactNotFoundError,
    FileCodexPauseStore,
    InvalidCodexPauseArtifactIdError,
)


def test_store_creates_pause_directories(tmp_path: Path) -> None:
    store = FileCodexPauseStore(tmp_path)

    directories = store.ensure_directories()

    assert [directory.name for directory in directories] == [PAUSED_ASSIGNMENTS_FOLDER, FAILED_REQUESTS_FOLDER]
    assert all(directory.is_dir() for directory in directories)


def test_create_read_and_list_paused_assignments(tmp_path: Path) -> None:
    store = FileCodexPauseStore(tmp_path)
    artifact = _paused_assignment()

    location = store.create_paused_assignment(artifact)
    restored = store.read_paused_assignment(artifact.id)
    listed = store.list_paused_assignments()

    assert location.path == tmp_path / PAUSED_ASSIGNMENTS_FOLDER / "paused-AGENT-17-001.json"
    assert restored == artifact
    assert listed == (artifact,)


def test_create_failed_request_redacts_summaries_before_persistence(tmp_path: Path) -> None:
    store = FileCodexPauseStore(tmp_path)
    artifact = _failed_request(
        request_summary="Authorization: Bearer live-token prompt=normal",
        error_summary="api_token=abc123 secret=hidden",
    )

    location = store.create_failed_request(artifact)
    restored = store.read_failed_request(artifact.id)
    raw_content = location.path.read_text(encoding="utf-8")

    assert restored.request_summary == "Authorization: Bearer ***REDACTED*** prompt=normal"
    assert restored.error_summary == "api_token=***REDACTED*** secret=***REDACTED***"
    assert "live-token" not in raw_content
    assert "abc123" not in raw_content
    assert "hidden" not in raw_content
    assert set(restored.redacted_fields) == {
        "request_summary.authorization",
        "error_summary.api_token",
        "error_summary.password",
    }


def test_create_failed_request_redacts_standalone_github_tokens(tmp_path: Path) -> None:
    store = FileCodexPauseStore(tmp_path)
    artifact = _failed_request(
        request_summary="git push with " + "github_" + "pat_exampleTokenValue12345",
        error_summary="fallback token " + "gh" + "p_exampleTokenValue12345 failed",
        stdout_snippet="stdout token=consoleSecret",
        stderr_snippet="stderr secret=stderrSecret",
    )

    location = store.create_failed_request(artifact)
    restored = store.read_failed_request(artifact.id)
    raw_content = location.path.read_text(encoding="utf-8")

    assert "exampleTokenValue12345" not in raw_content
    assert "consoleSecret" not in raw_content
    assert "stderrSecret" not in raw_content
    assert restored.request_summary == "git push with ***REDACTED***"
    assert restored.error_summary == "fallback token ***REDACTED*** failed"
    assert restored.stdout_snippet == "stdout token=***REDACTED***"
    assert restored.stderr_snippet == "stderr secret=***REDACTED***"
    assert set(restored.redacted_fields) == {
        "request_summary.github_pat",
        "error_summary.github_classic_token",
        "stdout_snippet.api_token",
        "stderr_snippet.password",
    }


def test_create_read_and_list_failed_requests(tmp_path: Path) -> None:
    store = FileCodexPauseStore(tmp_path)
    artifact = _failed_request()

    location = store.create_failed_request(artifact)
    restored = store.read_failed_request(artifact.id)
    listed = store.list_failed_requests()

    assert location.path == tmp_path / FAILED_REQUESTS_FOLDER / "failed-request-001.json"
    assert restored == artifact
    assert listed == (artifact,)


def test_duplicate_artifacts_are_rejected(tmp_path: Path) -> None:
    store = FileCodexPauseStore(tmp_path)
    artifact = _paused_assignment()
    store.create_paused_assignment(artifact)

    with pytest.raises(CodexPauseArtifactAlreadyExistsError):
        store.create_paused_assignment(artifact)


def test_missing_and_invalid_ids_are_rejected(tmp_path: Path) -> None:
    store = FileCodexPauseStore(tmp_path)

    with pytest.raises(CodexPauseArtifactNotFoundError):
        store.read_paused_assignment("missing")
    with pytest.raises(InvalidCodexPauseArtifactIdError):
        store.paused_assignment_path("../escape")


def test_invalid_schema_file_is_rejected_on_read(tmp_path: Path) -> None:
    store = FileCodexPauseStore(tmp_path)
    store.ensure_directories()
    (tmp_path / PAUSED_ASSIGNMENTS_FOLDER / "bad.json").write_text('{"id":"bad"}', encoding="utf-8")

    with pytest.raises(CodexPauseSchemaError):
        store.read_paused_assignment("bad")


def _paused_assignment() -> CodexPausedAssignmentArtifact:
    return CodexPausedAssignmentArtifact(
        id="paused-AGENT-17-001",
        jira_issue_key="AGENT-17",
        worker_role=AgentRole.DEVELOPER,
        codex_job_id="codex-job-001",
        worker_id="developer-1",
        branch_name="feature/AGENT-17-codex-limit-pause-resume-artifacts",
        context_pack_path="data/context-packs/AGENT-17/context.json",
        failed_request_path="data/codex-jobs/AGENT-17/failed-request.json",
        status=CodexJobStatus.PAUSED_LIMIT,
        reason=CodexPauseReason.LIMIT_REACHED,
        resume=CodexResumePlan(
            original_story_key="AGENT-17",
            worker_role=AgentRole.DEVELOPER,
            codex_job_id="codex-job-001",
            context_pack_path="data/context-packs/AGENT-17/context.json",
            next_action=CodexResumeAction.RETRY_SAME_REQUEST,
        ),
        paused_at="2026-06-17T20:00:00Z",
        updated_at="2026-06-17T20:00:00Z",
        attempt_count=1,
        linked_artifacts=(
            CodexLinkedArtifact(
                kind=CodexLinkedArtifactKind.PARTIAL_OUTPUT,
                path="data/codex-results/AGENT-17/partial-output.md",
                label="Partial output",
            ),
            CodexLinkedArtifact(
                kind=CodexLinkedArtifactKind.LOG,
                path="data/agent-logs/AGENT-17/codex-run.log",
                label="Run log",
            ),
        ),
    )


def _failed_request(
    *,
    request_summary: str = "Redacted request summary.",
    error_summary: str = "Codex limit reached.",
    stdout_snippet: str = "",
    stderr_snippet: str = "",
) -> CodexFailedRequestArtifact:
    return CodexFailedRequestArtifact(
        id="failed-request-001",
        codex_job_id="codex-job-001",
        jira_issue_key="AGENT-17",
        worker_role=AgentRole.DEVELOPER,
        reason=CodexPauseReason.LIMIT_REACHED,
        failed_at="2026-06-17T20:00:00Z",
        request_summary=request_summary,
        error_summary=error_summary,
        stdout_snippet=stdout_snippet,
        stderr_snippet=stderr_snippet,
        stage_id="host_side_runner.limit_pause",
        retry_policy="retry_same_request_after_limit_reset",
        suggested_next_role_action="scheduler_retry_after_limit_reset",
        side_effect_idempotency_key="AGENT-17:codex-job-001:stage-1",
        next_action=CodexResumeAction.RETRY_SAME_REQUEST,
    )
