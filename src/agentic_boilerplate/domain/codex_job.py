"""Durable Codex job artifact schema."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from agentic_boilerplate.domain.po_inbox import AgentRole
from agentic_boilerplate.domain.story_complexity import ReasoningLevel


class CodexJobStatus(str, Enum):
    """Supported durable Codex job states."""

    QUEUED = "queued"
    RUNNING = "running"
    PAUSED_LIMIT = "paused_limit"
    FAILED = "failed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class CodexEffortMode(str, Enum):
    """Worker effort modes used to balance quality and Codex limits."""

    SIMPLE = "simple"
    STANDARD = "standard"
    COMPLEX = "complex"
    AUDIT = "audit"


TERMINAL_CODEX_JOB_STATUSES: frozenset[CodexJobStatus] = frozenset(
    {
        CodexJobStatus.FAILED,
        CodexJobStatus.COMPLETED,
        CodexJobStatus.CANCELLED,
    }
)


@dataclass(frozen=True)
class CodexResumeMetadata:
    """Information needed to resume a paused or interrupted Codex job."""

    resumable: bool = True
    resume_after: str = ""
    last_checkpoint_path: str = ""
    last_error: str = ""
    paused_at: str = ""


@dataclass(frozen=True)
class CodexJobArtifact:
    """Inspectable durable request passed from workers to a host-side Codex runner."""

    id: str
    jira_issue_key: str
    role: AgentRole
    target_repo_path: str
    branch_name: str
    context_pack_path: str
    output_path: str
    model: str
    reasoning: ReasoningLevel
    speed: str
    effort_mode: CodexEffortMode
    status: CodexJobStatus
    created_at: str
    updated_at: str
    attempt_count: int = 0
    failed_request_path: str = ""
    resume: CodexResumeMetadata = field(default_factory=CodexResumeMetadata)


@dataclass(frozen=True)
class CodexJobSchemaIssue:
    """Validation issue for a Codex job artifact."""

    field: str
    message: str


class CodexJobSchemaError(ValueError):
    """Raised when a Codex job artifact violates the schema contract."""

    def __init__(self, issues: list[CodexJobSchemaIssue]) -> None:
        self.issues = issues
        super().__init__(format_codex_job_schema_issues(issues))


def validate_codex_job_artifact(job: CodexJobArtifact) -> list[CodexJobSchemaIssue]:
    """Return schema issues without including prompt, token, or secret values."""

    issues: list[CodexJobSchemaIssue] = []

    _require_text(issues, "id", job.id)
    _require_text(issues, "jira_issue_key", job.jira_issue_key)
    _require_text(issues, "target_repo_path", job.target_repo_path)
    _require_text(issues, "branch_name", job.branch_name)
    _require_text(issues, "context_pack_path", job.context_pack_path)
    _require_text(issues, "output_path", job.output_path)
    _require_text(issues, "model", job.model)
    _require_text(issues, "speed", job.speed)
    _require_text(issues, "created_at", job.created_at)
    _require_text(issues, "updated_at", job.updated_at)

    if job.attempt_count < 0:
        issues.append(CodexJobSchemaIssue(field="attempt_count", message="Attempt count cannot be negative."))

    if job.status == CodexJobStatus.PAUSED_LIMIT:
        _require_text(issues, "failed_request_path", job.failed_request_path)
        if not job.resume.resumable:
            issues.append(
                CodexJobSchemaIssue(
                    field="resume.resumable",
                    message="Paused limit jobs must remain resumable.",
                )
            )

    if job.status == CodexJobStatus.FAILED and not job.failed_request_path:
        issues.append(
            CodexJobSchemaIssue(
                field="failed_request_path",
                message="Failed jobs must reference the failed request artifact.",
            )
        )

    return issues


def require_valid_codex_job_artifact(job: CodexJobArtifact) -> CodexJobArtifact:
    """Raise when a Codex job artifact violates the schema contract."""

    issues = validate_codex_job_artifact(job)
    if issues:
        raise CodexJobSchemaError(issues)
    return job


def codex_job_artifact_to_dict(job: CodexJobArtifact) -> dict[str, Any]:
    """Convert a Codex job artifact into JSON-compatible data."""

    return {
        "id": job.id,
        "jira_issue_key": job.jira_issue_key,
        "role": job.role.value,
        "target_repo_path": job.target_repo_path,
        "branch_name": job.branch_name,
        "context_pack_path": job.context_pack_path,
        "output_path": job.output_path,
        "model": job.model,
        "reasoning": job.reasoning.value,
        "speed": job.speed,
        "effort_mode": job.effort_mode.value,
        "status": job.status.value,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "attempt_count": job.attempt_count,
        "failed_request_path": job.failed_request_path,
        "resume": {
            "resumable": job.resume.resumable,
            "resume_after": job.resume.resume_after,
            "last_checkpoint_path": job.resume.last_checkpoint_path,
            "last_error": job.resume.last_error,
            "paused_at": job.resume.paused_at,
        },
    }


def codex_job_artifact_from_dict(data: Mapping[str, Any]) -> CodexJobArtifact:
    """Build a Codex job artifact from JSON-compatible data."""

    resume_data = data.get("resume", {})
    if not isinstance(resume_data, Mapping):
        raise CodexJobSchemaError([CodexJobSchemaIssue(field="resume", message="Resume metadata must be an object.")])

    job = CodexJobArtifact(
        id=_optional_text(data.get("id")),
        jira_issue_key=_optional_text(data.get("jira_issue_key")),
        role=_enum_from_value(AgentRole, data.get("role", "")),
        target_repo_path=_optional_text(data.get("target_repo_path")),
        branch_name=_optional_text(data.get("branch_name")),
        context_pack_path=_optional_text(data.get("context_pack_path")),
        output_path=_optional_text(data.get("output_path")),
        model=_optional_text(data.get("model")),
        reasoning=_enum_from_value(ReasoningLevel, data.get("reasoning", "")),
        speed=_optional_text(data.get("speed")),
        effort_mode=_enum_from_value(CodexEffortMode, data.get("effort_mode", "")),
        status=_enum_from_value(CodexJobStatus, data.get("status", "")),
        created_at=_optional_text(data.get("created_at")),
        updated_at=_optional_text(data.get("updated_at")),
        attempt_count=_int_from_value(data.get("attempt_count", 0)),
        failed_request_path=_optional_text(data.get("failed_request_path")),
        resume=CodexResumeMetadata(
            resumable=_bool_from_value(resume_data.get("resumable", True)),
            resume_after=_optional_text(resume_data.get("resume_after")),
            last_checkpoint_path=_optional_text(resume_data.get("last_checkpoint_path")),
            last_error=_optional_text(resume_data.get("last_error")),
            paused_at=_optional_text(resume_data.get("paused_at")),
        ),
    )
    return require_valid_codex_job_artifact(job)


def format_codex_job_schema_issues(issues: list[CodexJobSchemaIssue]) -> str:
    """Format schema issues without leaking prompt or secret content."""

    if not issues:
        return "Codex job artifact is valid."
    lines = ["Codex job artifact validation failed:"]
    lines.extend(f"- {issue.field}: {issue.message}" for issue in issues)
    return "\n".join(lines)


def _enum_from_value(enum_type: type[Enum], value: Any) -> Any:
    try:
        return enum_type(str(value))
    except ValueError as exc:
        raise CodexJobSchemaError(
            [
                CodexJobSchemaIssue(
                    field=enum_type.__name__,
                    message=f"Unsupported value {str(value)!r}.",
                )
            ]
        ) from exc


def _int_from_value(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise CodexJobSchemaError(
            [CodexJobSchemaIssue(field="attempt_count", message="Attempt count must be an integer.")]
        ) from exc


def _bool_from_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _require_text(issues: list[CodexJobSchemaIssue], field_name: str, value: str) -> None:
    if not value.strip():
        issues.append(CodexJobSchemaIssue(field=field_name, message="Required value is missing."))


def _optional_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)
