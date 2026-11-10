import json

import pytest

from agentic_boilerplate.domain import (
    AgentRole,
    CodexEffortMode,
    CodexJobArtifact,
    CodexJobSchemaError,
    CodexJobStatus,
    CodexResumeMetadata,
    ReasoningLevel,
    codex_job_artifact_from_dict,
    codex_job_artifact_to_dict,
    require_valid_codex_job_artifact,
    validate_codex_job_artifact,
)


def test_codex_job_artifact_round_trips_to_json_compatible_data() -> None:
    job = _base_job()

    require_valid_codex_job_artifact(job)
    data = codex_job_artifact_to_dict(job)
    restored = codex_job_artifact_from_dict(data)

    assert data["role"] == "developer"
    assert data["reasoning"] == "medium"
    assert data["status"] == "queued"
    assert data["resume"]["resumable"] is True
    assert restored == job
    json.dumps(data)


def test_required_fields_are_reported_without_prompt_or_secret_values() -> None:
    job = CodexJobArtifact(
        id="",
        jira_issue_key="",
        role=AgentRole.DEVELOPER,
        target_repo_path="",
        branch_name="",
        context_pack_path="data/context-packs/AGENT-16/prompt-with-secret-token.json",
        output_path="",
        model="",
        reasoning=ReasoningLevel.MEDIUM,
        speed="",
        effort_mode=CodexEffortMode.STANDARD,
        status=CodexJobStatus.QUEUED,
        created_at="",
        updated_at="",
    )

    with pytest.raises(CodexJobSchemaError) as exc_info:
        require_valid_codex_job_artifact(job)

    message = str(exc_info.value)
    assert "id" in message
    assert "jira_issue_key" in message
    assert "model" in message
    assert "prompt-with-secret-token" not in message


def test_negative_attempt_count_is_rejected() -> None:
    job = CodexJobArtifact(**{**_base_job().__dict__, "attempt_count": -1})

    issues = validate_codex_job_artifact(job)

    assert {issue.field for issue in issues} == {"attempt_count"}


def test_paused_limit_job_requires_failed_request_and_resumable_metadata() -> None:
    job = CodexJobArtifact(
        **{
            **_base_job().__dict__,
            "status": CodexJobStatus.PAUSED_LIMIT,
            "failed_request_path": "",
            "resume": CodexResumeMetadata(resumable=False),
        }
    )

    issues = validate_codex_job_artifact(job)

    assert {issue.field for issue in issues} == {"failed_request_path", "resume.resumable"}


def test_failed_job_requires_failed_request_artifact() -> None:
    job = CodexJobArtifact(**{**_base_job().__dict__, "status": CodexJobStatus.FAILED})

    issues = validate_codex_job_artifact(job)

    assert {issue.field for issue in issues} == {"failed_request_path"}


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("role", "unknown"),
        ("reasoning", "extreme"),
        ("effort_mode", "maximum"),
        ("status", "waiting"),
    ],
)
def test_unknown_enum_values_fail_during_dict_loading(field: str, value: str) -> None:
    data = codex_job_artifact_to_dict(_base_job())
    data[field] = value

    with pytest.raises(CodexJobSchemaError, match="Unsupported value"):
        codex_job_artifact_from_dict(data)


def test_resume_metadata_must_be_an_object() -> None:
    data = codex_job_artifact_to_dict(_base_job())
    data["resume"] = "resume later"

    with pytest.raises(CodexJobSchemaError) as exc_info:
        codex_job_artifact_from_dict(data)

    assert {issue.field for issue in exc_info.value.issues} == {"resume"}


def _base_job() -> CodexJobArtifact:
    return CodexJobArtifact(
        id="codex-job-001",
        jira_issue_key="AGENT-16",
        role=AgentRole.DEVELOPER,
        target_repo_path="/workspace/sample-project",
        branch_name="feature/AGENT-16-codex-job-artifact-schema",
        context_pack_path="data/context-packs/AGENT-16/context.json",
        output_path="data/codex-results/AGENT-16/result.json",
        model="gpt-5.5",
        reasoning=ReasoningLevel.MEDIUM,
        speed="normal",
        effort_mode=CodexEffortMode.STANDARD,
        status=CodexJobStatus.QUEUED,
        created_at="2026-06-17T12:00:00Z",
        updated_at="2026-06-17T12:00:00Z",
        attempt_count=1,
        resume=CodexResumeMetadata(
            resumable=True,
            resume_after="limit reset",
            last_checkpoint_path="data/codex-results/AGENT-16/checkpoint.json",
        ),
    )
