import json

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
    failed_request_artifact_from_dict,
    failed_request_artifact_to_dict,
    failed_request_replay_guard_key,
    paused_assignment_artifact_from_dict,
    paused_assignment_artifact_to_dict,
    require_valid_failed_request_artifact,
    require_valid_paused_assignment_artifact,
    validate_paused_assignment_artifact,
)


def test_paused_assignment_artifact_round_trips_to_json_compatible_data() -> None:
    artifact = _paused_assignment()

    require_valid_paused_assignment_artifact(artifact)
    data = paused_assignment_artifact_to_dict(artifact)
    restored = paused_assignment_artifact_from_dict(json.loads(json.dumps(data)))

    assert data["status"] == "paused_limit"
    assert data["reason"] == "limit_reached"
    assert data["resume"]["next_action"] == "retry_same_request"
    assert data["linked_artifacts"][0]["kind"] == "partial_output"
    assert restored == artifact


def test_paused_assignment_requires_pause_status_and_attempt() -> None:
    artifact = CodexPausedAssignmentArtifact(
        **{
            **_paused_assignment().__dict__,
            "status": CodexJobStatus.RUNNING,
            "attempt_count": 0,
        }
    )

    issues = validate_paused_assignment_artifact(artifact)

    assert {issue.field for issue in issues} == {"status", "attempt_count"}


@pytest.mark.parametrize(
    "resume_overrides",
    [
        {"original_story_key": "AGENT-999"},
        {"worker_role": AgentRole.TESTER},
        {"codex_job_id": "other-job"},
        {"context_pack_path": "data/context-packs/other/context.json"},
    ],
)
def test_resume_plan_must_reference_the_paused_assignment(resume_overrides: dict) -> None:
    resume = CodexResumePlan(**{**_resume_plan().__dict__, **resume_overrides})
    artifact = CodexPausedAssignmentArtifact(**{**_paused_assignment().__dict__, "resume": resume})

    issues = validate_paused_assignment_artifact(artifact)

    assert len(issues) == 1
    assert issues[0].field.startswith("resume.")


def test_linked_artifacts_require_label_and_path_without_leaking_values() -> None:
    artifact = CodexPausedAssignmentArtifact(
        **{
            **_paused_assignment().__dict__,
            "linked_artifacts": (
                CodexLinkedArtifact(
                    kind=CodexLinkedArtifactKind.LOG,
                    path="data/agent-logs/AGENT-17/log-with-secret-token.txt",
                    label="",
                ),
            ),
        }
    )

    with pytest.raises(CodexPauseSchemaError) as exc_info:
        require_valid_paused_assignment_artifact(artifact)

    message = str(exc_info.value)
    assert "linked_artifacts[0].label" in message
    assert "log-with-secret-token" not in message


def test_failed_request_artifact_round_trips_to_json_compatible_data() -> None:
    artifact = _failed_request()

    require_valid_failed_request_artifact(artifact)
    data = failed_request_artifact_to_dict(artifact)
    restored = failed_request_artifact_from_dict(json.loads(json.dumps(data)))

    assert data["reason"] == "limit_reached"
    assert data["redacted_fields"] == ["authorization", "prompt"]
    assert data["next_action"] == "retry_same_request"
    assert data["stage_id"] == "host_side_runner.limit_pause"
    assert data["retry_policy"] == "retry_same_request_after_limit_reset"
    assert data["suggested_next_role_action"] == "scheduler_retry_after_limit_reset"
    assert data["side_effect_idempotency_key"] == "AGENT-17:codex-job-001:stage-1"
    assert restored == artifact


def test_failed_request_replay_guard_uses_explicit_or_derived_key() -> None:
    explicit = _failed_request()
    derived = CodexFailedRequestArtifact(
        **{
            **_failed_request().__dict__,
            "side_effect_idempotency_key": "",
        }
    )

    assert failed_request_replay_guard_key(explicit) == "AGENT-17:codex-job-001:stage-1"
    assert failed_request_replay_guard_key(derived) == (
        "AGENT-17:codex-job-001:host_side_runner.limit_pause:retry_same_request"
    )


def test_failed_request_from_older_json_defaults_retry_metadata() -> None:
    data = failed_request_artifact_to_dict(_failed_request())
    for key in (
        "stage_id",
        "stdout_snippet",
        "stderr_snippet",
        "retry_policy",
        "suggested_next_role_action",
        "side_effect_idempotency_key",
    ):
        data.pop(key)

    restored = failed_request_artifact_from_dict(data)

    assert restored.stage_id == ""
    assert restored.retry_policy == ""
    assert failed_request_replay_guard_key(restored) == "AGENT-17:codex-job-001:unknown-stage:retry_same_request"


def test_failed_request_required_fields_are_reported_without_raw_request_values() -> None:
    artifact = CodexFailedRequestArtifact(
        id="",
        codex_job_id="",
        jira_issue_key="AGENT-17",
        worker_role=AgentRole.DEVELOPER,
        reason=CodexPauseReason.EXECUTION_FAILED,
        failed_at="",
        request_summary="",
        error_summary="",
        raw_request_path="data/codex-jobs/AGENT-17/raw-request-with-secret.json",
    )

    with pytest.raises(CodexPauseSchemaError) as exc_info:
        require_valid_failed_request_artifact(artifact)

    message = str(exc_info.value)
    assert "request_summary" in message
    assert "error_summary" in message
    assert "raw-request-with-secret" not in message


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("worker_role", "unknown"),
        ("status", "waiting"),
        ("reason", "sleeping"),
    ],
)
def test_unknown_paused_assignment_enum_values_fail_during_dict_loading(field: str, value: str) -> None:
    data = paused_assignment_artifact_to_dict(_paused_assignment())
    data[field] = value

    with pytest.raises(CodexPauseSchemaError, match="Unsupported value"):
        paused_assignment_artifact_from_dict(data)


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
        resume=_resume_plan(),
        paused_at="2026-06-17T20:00:00Z",
        updated_at="2026-06-17T20:00:00Z",
        attempt_count=1,
        linked_artifacts=(
            CodexLinkedArtifact(
                kind=CodexLinkedArtifactKind.PARTIAL_OUTPUT,
                path="data/codex-results/AGENT-17/partial-output.md",
                label="Partial implementation notes",
            ),
            CodexLinkedArtifact(
                kind=CodexLinkedArtifactKind.LOG,
                path="data/agent-logs/AGENT-17/codex-run.log",
                label="Codex run log",
            ),
        ),
    )


def _resume_plan() -> CodexResumePlan:
    return CodexResumePlan(
        original_story_key="AGENT-17",
        worker_role=AgentRole.DEVELOPER,
        codex_job_id="codex-job-001",
        context_pack_path="data/context-packs/AGENT-17/context.json",
        next_action=CodexResumeAction.RETRY_SAME_REQUEST,
        note="Resume after Codex limit resets.",
    )


def _failed_request() -> CodexFailedRequestArtifact:
    return CodexFailedRequestArtifact(
        id="failed-request-001",
        codex_job_id="codex-job-001",
        jira_issue_key="AGENT-17",
        worker_role=AgentRole.DEVELOPER,
        reason=CodexPauseReason.LIMIT_REACHED,
        failed_at="2026-06-17T20:00:00Z",
        request_summary="Redacted Codex request envelope for retry.",
        error_summary="Codex limit reached before completion.",
        redacted_fields=("authorization", "prompt"),
        next_action=CodexResumeAction.RETRY_SAME_REQUEST,
        raw_request_path="data/codex-jobs/AGENT-17/raw-request-redacted.json",
        stage_id="host_side_runner.limit_pause",
        stdout_snippet="Partial output before the limit pause.",
        stderr_snippet="",
        retry_policy="retry_same_request_after_limit_reset",
        suggested_next_role_action="scheduler_retry_after_limit_reset",
        side_effect_idempotency_key="AGENT-17:codex-job-001:stage-1",
    )
