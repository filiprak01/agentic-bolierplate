"""Detached worker checkpoint schema."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from agentic_boilerplate.domain.codex_pause import redact_failed_request_text
from agentic_boilerplate.domain.po_inbox import AgentRole


class DetachedWorkerCheckpointStage(str, Enum):
    """Durable stages a detached worker can resume from."""

    ASSIGNMENT_CLAIMED = "assignment_claimed"
    INSTRUCTIONS_LOADED = "instructions_loaded"
    CONTEXT_LOADED = "context_loaded"
    WORKSPACE_READY = "workspace_ready"
    LIMIT_CHECKED = "limit_checked"
    CODEX_JOB_CREATED = "codex_job_created"
    EXTERNAL_WRITE_PERFORMED = "external_write_performed"
    HANDOFF_EMITTED = "handoff_emitted"
    PAUSED_LIMIT = "paused_limit"
    BLOCKED_PO = "blocked_po"
    FAILED = "failed"
    COMPLETED = "completed"


class DetachedWorkerResumeAction(str, Enum):
    """Recommended next action for the scheduler or worker."""

    NONE = "none"
    RECHECK_GATES = "recheck_gates"
    RETRY_LAST_COMMAND = "retry_last_command"
    REBUILD_CONTEXT = "rebuild_context"
    WAIT_FOR_LIMITS = "wait_for_limits"
    ASK_PRODUCT_OWNER = "ask_product_owner"
    MANUAL_RECOVERY = "manual_recovery"


@dataclass(frozen=True)
class DetachedWorkerCheckpoint:
    """Resume snapshot written by detached workers at durable stop points."""

    id: str
    assignment_id: str
    worker_id: str
    role: AgentRole
    project_id: str
    sprint: str
    jira_issue_key: str
    branch_name: str
    worktree_path: str
    stage: DetachedWorkerCheckpointStage
    last_command: str
    resume_action: DetachedWorkerResumeAction
    resume_recommendation: str
    created_at: str
    updated_at: str
    attempt_count: int = 0
    project_name: str = ""
    project_root: str = ""
    repository: str = ""
    jira_project_key: str = ""
    codex_job_id: str = ""
    context_pack_path: str = ""
    failed_request_path: str = ""
    output_path: str = ""
    evidence_path: str = ""
    resume_after: str = ""
    redacted_fields: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DetachedWorkerCheckpointIssue:
    """Validation issue for detached worker checkpoints."""

    field: str
    message: str


class DetachedWorkerCheckpointError(ValueError):
    """Raised when a detached worker checkpoint violates the schema."""

    def __init__(self, issues: list[DetachedWorkerCheckpointIssue]) -> None:
        self.issues = issues
        super().__init__(format_detached_worker_checkpoint_issues(issues))


def validate_detached_worker_checkpoint(
    checkpoint: DetachedWorkerCheckpoint,
) -> list[DetachedWorkerCheckpointIssue]:
    """Return validation issues without echoing command or secret values."""

    issues: list[DetachedWorkerCheckpointIssue] = []

    _require_text(issues, "id", checkpoint.id)
    _require_text(issues, "assignment_id", checkpoint.assignment_id)
    _require_text(issues, "worker_id", checkpoint.worker_id)
    _require_text(issues, "project_id", checkpoint.project_id)
    _require_text(issues, "sprint", checkpoint.sprint)
    _require_text(issues, "jira_issue_key", checkpoint.jira_issue_key)
    _require_text(issues, "branch_name", checkpoint.branch_name)
    _require_text(issues, "worktree_path", checkpoint.worktree_path)
    _require_text(issues, "last_command", checkpoint.last_command)
    _require_text(issues, "resume_recommendation", checkpoint.resume_recommendation)
    _require_text(issues, "created_at", checkpoint.created_at)
    _require_text(issues, "updated_at", checkpoint.updated_at)

    if checkpoint.attempt_count < 0:
        issues.append(
            DetachedWorkerCheckpointIssue(
                field="attempt_count",
                message="Attempt count cannot be negative.",
            )
        )

    if checkpoint.stage in {
        DetachedWorkerCheckpointStage.PAUSED_LIMIT,
        DetachedWorkerCheckpointStage.FAILED,
    }:
        _require_text(issues, "failed_request_path", checkpoint.failed_request_path)

    if checkpoint.resume_action == DetachedWorkerResumeAction.WAIT_FOR_LIMITS:
        _require_text(issues, "resume_after", checkpoint.resume_after)

    if checkpoint.resume_action == DetachedWorkerResumeAction.ASK_PRODUCT_OWNER:
        _require_text(issues, "evidence_path", checkpoint.evidence_path)

    return issues


def require_valid_detached_worker_checkpoint(
    checkpoint: DetachedWorkerCheckpoint,
) -> DetachedWorkerCheckpoint:
    """Raise when a detached worker checkpoint violates the schema."""

    issues = validate_detached_worker_checkpoint(checkpoint)
    if issues:
        raise DetachedWorkerCheckpointError(issues)
    return checkpoint


def redact_detached_worker_checkpoint(
    checkpoint: DetachedWorkerCheckpoint,
) -> DetachedWorkerCheckpoint:
    """Redact secret-like command and recommendation text before persistence."""

    command = redact_failed_request_text(checkpoint.last_command)
    recommendation = redact_failed_request_text(checkpoint.resume_recommendation)
    redacted_fields = tuple(
        dict.fromkeys(
            checkpoint.redacted_fields
            + tuple(f"last_command.{field}" for field in command.redacted_fields)
            + tuple(f"resume_recommendation.{field}" for field in recommendation.redacted_fields)
        )
    )
    return DetachedWorkerCheckpoint(
        **{
            **checkpoint.__dict__,
            "last_command": command.value,
            "resume_recommendation": recommendation.value,
            "redacted_fields": redacted_fields,
        }
    )


def detached_worker_checkpoint_to_dict(
    checkpoint: DetachedWorkerCheckpoint,
) -> dict[str, Any]:
    """Convert a checkpoint into JSON-compatible data."""

    return {
        "id": checkpoint.id,
        "assignment_id": checkpoint.assignment_id,
        "worker_id": checkpoint.worker_id,
        "role": checkpoint.role.value,
        "project_id": checkpoint.project_id,
        "project_name": checkpoint.project_name,
        "project_root": checkpoint.project_root,
        "repository": checkpoint.repository,
        "jira_project_key": checkpoint.jira_project_key,
        "sprint": checkpoint.sprint,
        "jira_issue_key": checkpoint.jira_issue_key,
        "branch_name": checkpoint.branch_name,
        "worktree_path": checkpoint.worktree_path,
        "stage": checkpoint.stage.value,
        "last_command": checkpoint.last_command,
        "resume_action": checkpoint.resume_action.value,
        "resume_recommendation": checkpoint.resume_recommendation,
        "created_at": checkpoint.created_at,
        "updated_at": checkpoint.updated_at,
        "attempt_count": checkpoint.attempt_count,
        "codex_job_id": checkpoint.codex_job_id,
        "context_pack_path": checkpoint.context_pack_path,
        "failed_request_path": checkpoint.failed_request_path,
        "output_path": checkpoint.output_path,
        "evidence_path": checkpoint.evidence_path,
        "resume_after": checkpoint.resume_after,
        "redacted_fields": list(checkpoint.redacted_fields),
    }


def detached_worker_checkpoint_from_dict(data: Mapping[str, Any]) -> DetachedWorkerCheckpoint:
    """Build a checkpoint from JSON-compatible data."""

    redacted_fields = data.get("redacted_fields", [])
    if not isinstance(redacted_fields, list):
        raise DetachedWorkerCheckpointError(
            [
                DetachedWorkerCheckpointIssue(
                    field="redacted_fields",
                    message="Redacted fields must be a list.",
                )
            ]
        )

    checkpoint = DetachedWorkerCheckpoint(
        id=_optional_text(data.get("id")),
        assignment_id=_optional_text(data.get("assignment_id")),
        worker_id=_optional_text(data.get("worker_id")),
        role=_enum_from_value(AgentRole, data.get("role", "")),
        project_id=_optional_text(data.get("project_id")),
        project_name=_optional_text(data.get("project_name")),
        project_root=_optional_text(data.get("project_root")),
        repository=_optional_text(data.get("repository")),
        jira_project_key=_optional_text(data.get("jira_project_key")),
        sprint=_optional_text(data.get("sprint")),
        jira_issue_key=_optional_text(data.get("jira_issue_key")),
        branch_name=_optional_text(data.get("branch_name")),
        worktree_path=_optional_text(data.get("worktree_path")),
        stage=_enum_from_value(DetachedWorkerCheckpointStage, data.get("stage", "")),
        last_command=_optional_text(data.get("last_command")),
        resume_action=_enum_from_value(DetachedWorkerResumeAction, data.get("resume_action", "")),
        resume_recommendation=_optional_text(data.get("resume_recommendation")),
        created_at=_optional_text(data.get("created_at")),
        updated_at=_optional_text(data.get("updated_at")),
        attempt_count=_int_from_value(data.get("attempt_count", 0)),
        codex_job_id=_optional_text(data.get("codex_job_id")),
        context_pack_path=_optional_text(data.get("context_pack_path")),
        failed_request_path=_optional_text(data.get("failed_request_path")),
        output_path=_optional_text(data.get("output_path")),
        evidence_path=_optional_text(data.get("evidence_path")),
        resume_after=_optional_text(data.get("resume_after")),
        redacted_fields=tuple(_optional_text(field) for field in redacted_fields),
    )
    return require_valid_detached_worker_checkpoint(checkpoint)


def format_detached_worker_checkpoint_issues(
    issues: list[DetachedWorkerCheckpointIssue],
) -> str:
    """Format checkpoint validation issues without leaking command text."""

    if not issues:
        return "Detached worker checkpoint is valid."
    lines = ["Detached worker checkpoint validation failed:"]
    lines.extend(f"- {issue.field}: {issue.message}" for issue in issues)
    return "\n".join(lines)


def _enum_from_value(enum_type: type[Enum], value: Any) -> Any:
    try:
        return enum_type(str(value))
    except ValueError as exc:
        raise DetachedWorkerCheckpointError(
            [
                DetachedWorkerCheckpointIssue(
                    field=enum_type.__name__,
                    message=f"Unsupported value {str(value)!r}.",
                )
            ]
        ) from exc


def _int_from_value(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise DetachedWorkerCheckpointError(
            [
                DetachedWorkerCheckpointIssue(
                    field="attempt_count",
                    message="Attempt count must be an integer.",
                )
            ]
        ) from exc


def _require_text(
    issues: list[DetachedWorkerCheckpointIssue],
    field_name: str,
    value: str,
) -> None:
    if not value.strip():
        issues.append(
            DetachedWorkerCheckpointIssue(
                field=field_name,
                message="Required value is missing.",
            )
        )


def _optional_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)
