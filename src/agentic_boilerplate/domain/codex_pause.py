"""Codex limit pause and resume artifact schema."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
import re
from typing import Any

from agentic_boilerplate.domain.codex_job import CodexJobStatus
from agentic_boilerplate.domain.po_inbox import AgentRole


class CodexPauseReason(str, Enum):
    """Reasons a Codex assignment can be paused or captured for recovery."""

    LIMIT_REACHED = "limit_reached"
    WORKER_STOPPED = "worker_stopped"
    EXECUTION_FAILED = "execution_failed"


class CodexResumeAction(str, Enum):
    """Next action a scheduler or worker should take for a paused assignment."""

    RETRY_SAME_REQUEST = "retry_same_request"
    REBUILD_CONTEXT = "rebuild_context"
    ASK_PRODUCT_OWNER = "ask_product_owner"
    MANUAL_REVIEW = "manual_review"


class CodexLinkedArtifactKind(str, Enum):
    """Recoverable artifact categories linked to a paused assignment."""

    PARTIAL_OUTPUT = "partial_output"
    LOG = "log"
    CHECKPOINT = "checkpoint"
    FAILED_REQUEST = "failed_request"


@dataclass(frozen=True)
class RedactedCodexText:
    """Text redaction result for persisted failed request summaries."""

    value: str
    redacted_fields: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CodexLinkedArtifact:
    """Reference to a durable file needed for pause recovery."""

    kind: CodexLinkedArtifactKind
    path: str
    label: str
    description: str = ""


@dataclass(frozen=True)
class CodexResumePlan:
    """Metadata needed to resume a paused Codex assignment."""

    original_story_key: str
    worker_role: AgentRole
    codex_job_id: str
    context_pack_path: str
    next_action: CodexResumeAction
    note: str = ""


@dataclass(frozen=True)
class CodexFailedRequestArtifact:
    """Durable redacted summary of a failed Codex request."""

    id: str
    codex_job_id: str
    jira_issue_key: str
    worker_role: AgentRole
    reason: CodexPauseReason
    failed_at: str
    request_summary: str
    error_summary: str
    redacted_fields: tuple[str, ...] = field(default_factory=tuple)
    next_action: CodexResumeAction = CodexResumeAction.RETRY_SAME_REQUEST
    raw_request_path: str = ""
    stage_id: str = ""
    stdout_snippet: str = ""
    stderr_snippet: str = ""
    retry_policy: str = ""
    suggested_next_role_action: str = ""
    side_effect_idempotency_key: str = ""


@dataclass(frozen=True)
class CodexPausedAssignmentArtifact:
    """Durable assignment state for a paused Codex job."""

    id: str
    jira_issue_key: str
    worker_role: AgentRole
    codex_job_id: str
    worker_id: str
    branch_name: str
    context_pack_path: str
    failed_request_path: str
    status: CodexJobStatus
    reason: CodexPauseReason
    resume: CodexResumePlan
    paused_at: str
    updated_at: str
    attempt_count: int
    linked_artifacts: tuple[CodexLinkedArtifact, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CodexPauseSchemaIssue:
    """Validation issue for Codex pause artifacts."""

    field: str
    message: str


class CodexPauseSchemaError(ValueError):
    """Raised when a Codex pause artifact violates the schema contract."""

    def __init__(self, issues: list[CodexPauseSchemaIssue]) -> None:
        self.issues = issues
        super().__init__(format_codex_pause_schema_issues(issues))


_SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "authorization",
        re.compile(r"(?i)(authorization\s*[:=]\s*(?:bearer\s+)?)[^\s,;]+"),
    ),
    (
        "api_token",
        re.compile(r"(?i)((?:api[_-]?token|token)\s*[:=]\s*)[^\s,;]+"),
    ),
    (
        "password",
        re.compile(r"(?i)((?:password|secret)\s*[:=]\s*)[^\s,;]+"),
    ),
    (
        "github_pat",
        re.compile(r"github_pat_[A-Za-z0-9_]{12,}"),
    ),
    (
        "github_classic_token",
        re.compile(r"gh[pousr]_[A-Za-z0-9_]{12,}"),
    ),
    ("openai_key", re.compile(r"sk-[A-Za-z0-9_-]{8,}")),
)


def redact_failed_request_text(value: str) -> RedactedCodexText:
    """Redact obvious secrets from failed request text before persistence."""

    redacted_value = value
    redacted_fields: list[str] = []
    for field_name, pattern in _SECRET_PATTERNS:
        updated_value = pattern.sub(_redacted_replacement, redacted_value)
        if updated_value != redacted_value:
            redacted_fields.append(field_name)
            redacted_value = updated_value
    return RedactedCodexText(value=redacted_value, redacted_fields=tuple(dict.fromkeys(redacted_fields)))


def redact_failed_request_artifact(artifact: CodexFailedRequestArtifact) -> CodexFailedRequestArtifact:
    """Return a failed request artifact with summaries redacted for durable storage."""

    request_summary = redact_failed_request_text(artifact.request_summary)
    error_summary = redact_failed_request_text(artifact.error_summary)
    stdout_snippet = redact_failed_request_text(artifact.stdout_snippet)
    stderr_snippet = redact_failed_request_text(artifact.stderr_snippet)
    retry_policy = redact_failed_request_text(artifact.retry_policy)
    suggested_action = redact_failed_request_text(artifact.suggested_next_role_action)
    side_effect_key = redact_failed_request_text(artifact.side_effect_idempotency_key)
    redacted_fields = tuple(
        dict.fromkeys(
            artifact.redacted_fields
            + tuple(f"request_summary.{field}" for field in request_summary.redacted_fields)
            + tuple(f"error_summary.{field}" for field in error_summary.redacted_fields)
            + tuple(f"stdout_snippet.{field}" for field in stdout_snippet.redacted_fields)
            + tuple(f"stderr_snippet.{field}" for field in stderr_snippet.redacted_fields)
            + tuple(f"retry_policy.{field}" for field in retry_policy.redacted_fields)
            + tuple(f"suggested_next_role_action.{field}" for field in suggested_action.redacted_fields)
            + tuple(f"side_effect_idempotency_key.{field}" for field in side_effect_key.redacted_fields)
        )
    )
    return CodexFailedRequestArtifact(
        **{
            **artifact.__dict__,
            "request_summary": request_summary.value,
            "error_summary": error_summary.value,
            "stdout_snippet": stdout_snippet.value,
            "stderr_snippet": stderr_snippet.value,
            "retry_policy": retry_policy.value,
            "suggested_next_role_action": suggested_action.value,
            "side_effect_idempotency_key": side_effect_key.value,
            "redacted_fields": redacted_fields,
        }
    )


def validate_paused_assignment_artifact(
    artifact: CodexPausedAssignmentArtifact,
) -> list[CodexPauseSchemaIssue]:
    """Return paused assignment schema issues without echoing prompt or token values."""

    issues: list[CodexPauseSchemaIssue] = []

    _require_text(issues, "id", artifact.id)
    _require_text(issues, "jira_issue_key", artifact.jira_issue_key)
    _require_text(issues, "codex_job_id", artifact.codex_job_id)
    _require_text(issues, "worker_id", artifact.worker_id)
    _require_text(issues, "branch_name", artifact.branch_name)
    _require_text(issues, "context_pack_path", artifact.context_pack_path)
    _require_text(issues, "failed_request_path", artifact.failed_request_path)
    _require_text(issues, "paused_at", artifact.paused_at)
    _require_text(issues, "updated_at", artifact.updated_at)

    if artifact.status != CodexJobStatus.PAUSED_LIMIT:
        issues.append(
            CodexPauseSchemaIssue(
                field="status",
                message="Paused assignment artifacts must use paused_limit status.",
            )
        )

    if artifact.attempt_count < 1:
        issues.append(CodexPauseSchemaIssue(field="attempt_count", message="Attempt count must be at least 1."))

    _validate_resume_plan(issues, "resume", artifact.resume)
    if artifact.resume.original_story_key != artifact.jira_issue_key:
        issues.append(
            CodexPauseSchemaIssue(
                field="resume.original_story_key",
                message="Resume plan must reference the paused assignment story.",
            )
        )
    if artifact.resume.worker_role != artifact.worker_role:
        issues.append(
            CodexPauseSchemaIssue(
                field="resume.worker_role",
                message="Resume plan must reference the paused assignment worker role.",
            )
        )
    if artifact.resume.codex_job_id != artifact.codex_job_id:
        issues.append(
            CodexPauseSchemaIssue(
                field="resume.codex_job_id",
                message="Resume plan must reference the paused assignment Codex job.",
            )
        )
    if artifact.resume.context_pack_path != artifact.context_pack_path:
        issues.append(
            CodexPauseSchemaIssue(
                field="resume.context_pack_path",
                message="Resume plan must reference the paused assignment context pack.",
            )
        )

    for index, link in enumerate(artifact.linked_artifacts):
        _validate_linked_artifact(issues, f"linked_artifacts[{index}]", link)

    return issues


def validate_failed_request_artifact(
    artifact: CodexFailedRequestArtifact,
) -> list[CodexPauseSchemaIssue]:
    """Return failed request schema issues without leaking raw request content."""

    issues: list[CodexPauseSchemaIssue] = []

    _require_text(issues, "id", artifact.id)
    _require_text(issues, "codex_job_id", artifact.codex_job_id)
    _require_text(issues, "jira_issue_key", artifact.jira_issue_key)
    _require_text(issues, "failed_at", artifact.failed_at)
    _require_text(issues, "request_summary", artifact.request_summary)
    _require_text(issues, "error_summary", artifact.error_summary)

    return issues


def require_valid_paused_assignment_artifact(
    artifact: CodexPausedAssignmentArtifact,
) -> CodexPausedAssignmentArtifact:
    """Raise when a paused assignment artifact violates the schema contract."""

    issues = validate_paused_assignment_artifact(artifact)
    if issues:
        raise CodexPauseSchemaError(issues)
    return artifact


def require_valid_failed_request_artifact(
    artifact: CodexFailedRequestArtifact,
) -> CodexFailedRequestArtifact:
    """Raise when a failed request artifact violates the schema contract."""

    issues = validate_failed_request_artifact(artifact)
    if issues:
        raise CodexPauseSchemaError(issues)
    return artifact


def failed_request_replay_guard_key(artifact: CodexFailedRequestArtifact) -> str:
    """Return a deterministic replay guard key for idempotent retry planning."""

    if artifact.side_effect_idempotency_key.strip():
        return artifact.side_effect_idempotency_key.strip()
    stage = artifact.stage_id.strip() or "unknown-stage"
    return ":".join(
        (
            artifact.jira_issue_key.strip(),
            artifact.codex_job_id.strip(),
            stage,
            artifact.next_action.value,
        )
    )


def paused_assignment_artifact_to_dict(artifact: CodexPausedAssignmentArtifact) -> dict[str, Any]:
    """Convert a paused assignment artifact into JSON-compatible data."""

    return {
        "id": artifact.id,
        "jira_issue_key": artifact.jira_issue_key,
        "worker_role": artifact.worker_role.value,
        "codex_job_id": artifact.codex_job_id,
        "worker_id": artifact.worker_id,
        "branch_name": artifact.branch_name,
        "context_pack_path": artifact.context_pack_path,
        "failed_request_path": artifact.failed_request_path,
        "status": artifact.status.value,
        "reason": artifact.reason.value,
        "resume": _resume_plan_to_dict(artifact.resume),
        "paused_at": artifact.paused_at,
        "updated_at": artifact.updated_at,
        "attempt_count": artifact.attempt_count,
        "linked_artifacts": [_linked_artifact_to_dict(link) for link in artifact.linked_artifacts],
    }


def paused_assignment_artifact_from_dict(data: Mapping[str, Any]) -> CodexPausedAssignmentArtifact:
    """Build a paused assignment artifact from JSON-compatible data."""

    resume_data = data.get("resume", {})
    if not isinstance(resume_data, Mapping):
        raise CodexPauseSchemaError([CodexPauseSchemaIssue(field="resume", message="Resume plan must be an object.")])
    linked_artifacts = data.get("linked_artifacts", [])
    if not isinstance(linked_artifacts, list):
        raise CodexPauseSchemaError(
            [CodexPauseSchemaIssue(field="linked_artifacts", message="Linked artifacts must be a list.")]
        )

    artifact = CodexPausedAssignmentArtifact(
        id=_optional_text(data.get("id")),
        jira_issue_key=_optional_text(data.get("jira_issue_key")),
        worker_role=_enum_from_value(AgentRole, data.get("worker_role", "")),
        codex_job_id=_optional_text(data.get("codex_job_id")),
        worker_id=_optional_text(data.get("worker_id")),
        branch_name=_optional_text(data.get("branch_name")),
        context_pack_path=_optional_text(data.get("context_pack_path")),
        failed_request_path=_optional_text(data.get("failed_request_path")),
        status=_enum_from_value(CodexJobStatus, data.get("status", "")),
        reason=_enum_from_value(CodexPauseReason, data.get("reason", "")),
        resume=_resume_plan_from_dict(resume_data),
        paused_at=_optional_text(data.get("paused_at")),
        updated_at=_optional_text(data.get("updated_at")),
        attempt_count=_int_from_value("attempt_count", data.get("attempt_count", 0)),
        linked_artifacts=tuple(_linked_artifact_from_dict(link) for link in linked_artifacts),
    )
    return require_valid_paused_assignment_artifact(artifact)


def failed_request_artifact_to_dict(artifact: CodexFailedRequestArtifact) -> dict[str, Any]:
    """Convert a failed request artifact into JSON-compatible data."""

    return {
        "id": artifact.id,
        "codex_job_id": artifact.codex_job_id,
        "jira_issue_key": artifact.jira_issue_key,
        "worker_role": artifact.worker_role.value,
        "reason": artifact.reason.value,
        "failed_at": artifact.failed_at,
        "request_summary": artifact.request_summary,
        "error_summary": artifact.error_summary,
        "redacted_fields": list(artifact.redacted_fields),
        "next_action": artifact.next_action.value,
        "raw_request_path": artifact.raw_request_path,
        "stage_id": artifact.stage_id,
        "stdout_snippet": artifact.stdout_snippet,
        "stderr_snippet": artifact.stderr_snippet,
        "retry_policy": artifact.retry_policy,
        "suggested_next_role_action": artifact.suggested_next_role_action,
        "side_effect_idempotency_key": artifact.side_effect_idempotency_key,
    }


def failed_request_artifact_from_dict(data: Mapping[str, Any]) -> CodexFailedRequestArtifact:
    """Build a failed request artifact from JSON-compatible data."""

    redacted_fields = data.get("redacted_fields", [])
    if not isinstance(redacted_fields, list):
        raise CodexPauseSchemaError(
            [CodexPauseSchemaIssue(field="redacted_fields", message="Redacted fields must be a list.")]
        )

    artifact = CodexFailedRequestArtifact(
        id=_optional_text(data.get("id")),
        codex_job_id=_optional_text(data.get("codex_job_id")),
        jira_issue_key=_optional_text(data.get("jira_issue_key")),
        worker_role=_enum_from_value(AgentRole, data.get("worker_role", "")),
        reason=_enum_from_value(CodexPauseReason, data.get("reason", "")),
        failed_at=_optional_text(data.get("failed_at")),
        request_summary=_optional_text(data.get("request_summary")),
        error_summary=_optional_text(data.get("error_summary")),
        redacted_fields=tuple(_optional_text(field) for field in redacted_fields),
        next_action=_enum_from_value(CodexResumeAction, data.get("next_action", "")),
        raw_request_path=_optional_text(data.get("raw_request_path")),
        stage_id=_optional_text(data.get("stage_id")),
        stdout_snippet=_optional_text(data.get("stdout_snippet")),
        stderr_snippet=_optional_text(data.get("stderr_snippet")),
        retry_policy=_optional_text(data.get("retry_policy")),
        suggested_next_role_action=_optional_text(data.get("suggested_next_role_action")),
        side_effect_idempotency_key=_optional_text(data.get("side_effect_idempotency_key")),
    )
    return require_valid_failed_request_artifact(artifact)


def format_codex_pause_schema_issues(issues: list[CodexPauseSchemaIssue]) -> str:
    """Format schema issues without leaking request content."""

    if not issues:
        return "Codex pause artifact is valid."
    lines = ["Codex pause artifact validation failed:"]
    lines.extend(f"- {issue.field}: {issue.message}" for issue in issues)
    return "\n".join(lines)


def _resume_plan_to_dict(plan: CodexResumePlan) -> dict[str, Any]:
    return {
        "original_story_key": plan.original_story_key,
        "worker_role": plan.worker_role.value,
        "codex_job_id": plan.codex_job_id,
        "context_pack_path": plan.context_pack_path,
        "next_action": plan.next_action.value,
        "note": plan.note,
    }


def _resume_plan_from_dict(data: Mapping[str, Any]) -> CodexResumePlan:
    return CodexResumePlan(
        original_story_key=_optional_text(data.get("original_story_key")),
        worker_role=_enum_from_value(AgentRole, data.get("worker_role", "")),
        codex_job_id=_optional_text(data.get("codex_job_id")),
        context_pack_path=_optional_text(data.get("context_pack_path")),
        next_action=_enum_from_value(CodexResumeAction, data.get("next_action", "")),
        note=_optional_text(data.get("note")),
    )


def _linked_artifact_to_dict(link: CodexLinkedArtifact) -> dict[str, Any]:
    return {
        "kind": link.kind.value,
        "path": link.path,
        "label": link.label,
        "description": link.description,
    }


def _linked_artifact_from_dict(data: Mapping[str, Any]) -> CodexLinkedArtifact:
    return CodexLinkedArtifact(
        kind=_enum_from_value(CodexLinkedArtifactKind, data.get("kind", "")),
        path=_optional_text(data.get("path")),
        label=_optional_text(data.get("label")),
        description=_optional_text(data.get("description")),
    )


def _validate_resume_plan(issues: list[CodexPauseSchemaIssue], field_prefix: str, plan: CodexResumePlan) -> None:
    _require_text(issues, f"{field_prefix}.original_story_key", plan.original_story_key)
    _require_text(issues, f"{field_prefix}.codex_job_id", plan.codex_job_id)
    _require_text(issues, f"{field_prefix}.context_pack_path", plan.context_pack_path)


def _validate_linked_artifact(
    issues: list[CodexPauseSchemaIssue],
    field_prefix: str,
    link: CodexLinkedArtifact,
) -> None:
    _require_text(issues, f"{field_prefix}.path", link.path)
    _require_text(issues, f"{field_prefix}.label", link.label)


def _enum_from_value(enum_type: type[Enum], value: Any) -> Any:
    try:
        return enum_type(str(value))
    except ValueError as exc:
        raise CodexPauseSchemaError(
            [
                CodexPauseSchemaIssue(
                    field=enum_type.__name__,
                    message=f"Unsupported value {str(value)!r}.",
                )
            ]
        ) from exc


def _int_from_value(field_name: str, value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise CodexPauseSchemaError([CodexPauseSchemaIssue(field=field_name, message="Value must be an integer.")]) from exc


def _require_text(issues: list[CodexPauseSchemaIssue], field_name: str, value: str) -> None:
    if not value.strip():
        issues.append(CodexPauseSchemaIssue(field=field_name, message="Required value is missing."))


def _optional_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _redacted_replacement(match: re.Match[str]) -> str:
    if match.lastindex:
        return f"{match.group(1)}***REDACTED***"
    return "***REDACTED***"
