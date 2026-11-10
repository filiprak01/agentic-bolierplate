"""Agent registry and assignment state contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any

from agentic_boilerplate.domain.po_inbox import AgentRole


class WorkerStatus(str, Enum):
    """Runtime availability state for a registered worker instance."""

    AVAILABLE = "available"
    ASSIGNED = "assigned"
    PAUSED = "paused"
    OFFLINE = "offline"


class AssignmentStatus(str, Enum):
    """Durable assignment lifecycle states."""

    QUEUED = "queued"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    PAUSED_LIMIT = "paused_limit"
    PAUSED_PO = "paused_po"
    FAILED = "failed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


TERMINAL_ASSIGNMENT_STATUSES: frozenset[AssignmentStatus] = frozenset(
    {
        AssignmentStatus.FAILED,
        AssignmentStatus.COMPLETED,
        AssignmentStatus.CANCELLED,
    }
)


@dataclass(frozen=True)
class AssignmentStackMetadata:
    """Resolved stacked PR metadata persisted with a worker assignment."""

    stack_id: str = ""
    lane_id: str = ""
    stack_mode: str = ""
    resolved_path_version: str = ""
    current_layer: int = 0
    expected_next_agent: str = ""
    stale_state: str = ""
    rebase_required: bool = False


@dataclass(frozen=True)
class WorkerInstance:
    """One worker process that can receive assignments."""

    id: str
    role: AgentRole
    status: WorkerStatus
    display_name: str = ""
    container_name: str = ""
    workspace_path: str = ""
    current_assignment_id: str = ""
    registered_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class AssignmentPaths:
    """Durable paths that let interrupted work resume."""

    context_pack_path: str
    codex_job_path: str
    output_path: str
    workspace_path: str = ""
    evidence_path: str = ""
    failed_request_path: str = ""
    po_inbox_resume_context_path: str = ""


@dataclass(frozen=True)
class AgentAssignment:
    """Durable assignment shared by scheduler, workers, and recovery."""

    id: str
    jira_issue_key: str
    role: AgentRole
    status: AssignmentStatus
    paths: AssignmentPaths
    worker_id: str = ""
    codex_job_id: str = ""
    branch_name: str = ""
    project_id: str = ""
    project_name: str = ""
    project_root: str = ""
    repository: str = ""
    jira_project_key: str = ""
    stack_metadata: AssignmentStackMetadata = field(default_factory=AssignmentStackMetadata)
    created_at: str = ""
    updated_at: str = ""
    started_at: str = ""
    completed_at: str = ""
    pause_reason: str = ""
    po_inbox_item_id: str = ""
    failure_reason: str = ""
    attempt_count: int = 0


@dataclass(frozen=True)
class AgentRegistry:
    """Snapshot of registered workers and durable assignments."""

    id: str
    workers: tuple[WorkerInstance, ...]
    assignments: tuple[AgentAssignment, ...]
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class AssignmentSchemaIssue:
    """Validation issue for worker registry and assignment artifacts."""

    field: str
    message: str


class AssignmentSchemaError(ValueError):
    """Raised when registry or assignment state violates the contract."""

    def __init__(self, issues: list[AssignmentSchemaIssue]) -> None:
        self.issues = issues
        super().__init__(format_assignment_schema_issues(issues))


def validate_worker_instance(worker: WorkerInstance) -> list[AssignmentSchemaIssue]:
    """Return validation issues for one worker instance."""

    issues: list[AssignmentSchemaIssue] = []
    _require_text(issues, "worker.id", worker.id)
    _require_text(issues, "worker.updated_at", worker.updated_at)
    if worker.status == WorkerStatus.ASSIGNED:
        _require_text(issues, "worker.current_assignment_id", worker.current_assignment_id)
    return issues


def validate_agent_assignment(assignment: AgentAssignment) -> list[AssignmentSchemaIssue]:
    """Return validation issues for one durable assignment."""

    issues: list[AssignmentSchemaIssue] = []
    _require_text(issues, "assignment.id", assignment.id)
    _require_text(issues, "assignment.jira_issue_key", assignment.jira_issue_key)
    _require_text(issues, "assignment.paths.context_pack_path", assignment.paths.context_pack_path)
    _require_text(issues, "assignment.paths.codex_job_path", assignment.paths.codex_job_path)
    _require_text(issues, "assignment.paths.output_path", assignment.paths.output_path)
    _require_text(issues, "assignment.created_at", assignment.created_at)
    _require_text(issues, "assignment.updated_at", assignment.updated_at)
    if assignment.attempt_count < 0:
        issues.append(AssignmentSchemaIssue("assignment.attempt_count", "Attempt count cannot be negative."))
    _validate_stack_metadata(issues, assignment.stack_metadata)
    if assignment.status in {AssignmentStatus.ASSIGNED, AssignmentStatus.IN_PROGRESS}:
        _require_text(issues, "assignment.worker_id", assignment.worker_id)
        _require_text(issues, "assignment.codex_job_id", assignment.codex_job_id)
    if assignment.status == AssignmentStatus.PAUSED_LIMIT:
        _require_text(issues, "assignment.worker_id", assignment.worker_id)
        _require_text(issues, "assignment.codex_job_id", assignment.codex_job_id)
        _require_text(issues, "assignment.pause_reason", assignment.pause_reason)
        _require_text(issues, "assignment.paths.failed_request_path", assignment.paths.failed_request_path)
    if assignment.status == AssignmentStatus.PAUSED_PO:
        _require_text(issues, "assignment.worker_id", assignment.worker_id)
        _require_text(issues, "assignment.pause_reason", assignment.pause_reason)
        _require_text(issues, "assignment.po_inbox_item_id", assignment.po_inbox_item_id)
        _require_text(
            issues,
            "assignment.paths.po_inbox_resume_context_path",
            assignment.paths.po_inbox_resume_context_path,
        )
    if assignment.status == AssignmentStatus.COMPLETED:
        _require_text(issues, "assignment.codex_job_id", assignment.codex_job_id)
    if assignment.status == AssignmentStatus.FAILED:
        _require_text(issues, "assignment.failure_reason", assignment.failure_reason)
    return issues


def validate_agent_registry(registry: AgentRegistry) -> list[AssignmentSchemaIssue]:
    """Return validation issues for a registry snapshot."""

    issues: list[AssignmentSchemaIssue] = []
    _require_text(issues, "registry.id", registry.id)
    worker_ids: set[str] = set()
    assignment_ids: set[str] = set()
    for worker in registry.workers:
        issues.extend(validate_worker_instance(worker))
        if worker.id in worker_ids:
            issues.append(AssignmentSchemaIssue("registry.workers", f"Duplicate worker id: {worker.id}"))
        worker_ids.add(worker.id)
    for assignment in registry.assignments:
        issues.extend(validate_agent_assignment(assignment))
        if assignment.id in assignment_ids:
            issues.append(
                AssignmentSchemaIssue("registry.assignments", f"Duplicate assignment id: {assignment.id}")
            )
        assignment_ids.add(assignment.id)
        if assignment.worker_id and assignment.worker_id not in worker_ids:
            issues.append(
                AssignmentSchemaIssue(
                    "assignment.worker_id",
                    f"Assignment {assignment.id} references unknown worker {assignment.worker_id}.",
                )
            )
    return issues


def require_valid_worker_instance(worker: WorkerInstance) -> WorkerInstance:
    issues = validate_worker_instance(worker)
    if issues:
        raise AssignmentSchemaError(issues)
    return worker


def require_valid_agent_assignment(assignment: AgentAssignment) -> AgentAssignment:
    issues = validate_agent_assignment(assignment)
    if issues:
        raise AssignmentSchemaError(issues)
    return assignment


def require_valid_agent_registry(registry: AgentRegistry) -> AgentRegistry:
    issues = validate_agent_registry(registry)
    if issues:
        raise AssignmentSchemaError(issues)
    return registry


def assign_worker(
    assignment: AgentAssignment,
    *,
    worker_id: str,
    codex_job_id: str,
    started_at: str,
    updated_at: str,
) -> AgentAssignment:
    """Move a queued assignment into assigned state."""

    _require_transition(assignment.status, {AssignmentStatus.QUEUED}, AssignmentStatus.ASSIGNED)
    return require_valid_agent_assignment(
        replace(
            assignment,
            worker_id=worker_id.strip(),
            codex_job_id=codex_job_id.strip(),
            status=AssignmentStatus.ASSIGNED,
            started_at=started_at.strip(),
            updated_at=updated_at.strip(),
        )
    )


def mark_assignment_in_progress(assignment: AgentAssignment, *, updated_at: str) -> AgentAssignment:
    """Move an assigned worker assignment into active work."""

    _require_transition(assignment.status, {AssignmentStatus.ASSIGNED}, AssignmentStatus.IN_PROGRESS)
    return require_valid_agent_assignment(
        replace(assignment, status=AssignmentStatus.IN_PROGRESS, updated_at=updated_at.strip())
    )


def pause_assignment_for_limit(
    assignment: AgentAssignment,
    *,
    failed_request_path: str,
    pause_reason: str,
    updated_at: str,
) -> AgentAssignment:
    """Record a resumable limit pause for an in-flight assignment."""

    _require_transition(
        assignment.status,
        {AssignmentStatus.ASSIGNED, AssignmentStatus.IN_PROGRESS},
        AssignmentStatus.PAUSED_LIMIT,
    )
    paths = replace(assignment.paths, failed_request_path=failed_request_path.strip())
    return require_valid_agent_assignment(
        replace(
            assignment,
            status=AssignmentStatus.PAUSED_LIMIT,
            paths=paths,
            pause_reason=pause_reason.strip(),
            updated_at=updated_at.strip(),
        )
    )


def pause_assignment_for_po_inbox(
    assignment: AgentAssignment,
    *,
    worker_id: str,
    po_inbox_item_id: str,
    resume_context_path: str,
    pause_reason: str,
    updated_at: str,
) -> AgentAssignment:
    """Record a resumable Product Owner inbox pause for a worker assignment."""

    _require_transition(
        assignment.status,
        {AssignmentStatus.QUEUED, AssignmentStatus.ASSIGNED, AssignmentStatus.IN_PROGRESS},
        AssignmentStatus.PAUSED_PO,
    )
    paths = replace(assignment.paths, po_inbox_resume_context_path=resume_context_path.strip())
    return require_valid_agent_assignment(
        replace(
            assignment,
            status=AssignmentStatus.PAUSED_PO,
            worker_id=worker_id.strip(),
            paths=paths,
            pause_reason=pause_reason.strip(),
            po_inbox_item_id=po_inbox_item_id.strip(),
            updated_at=updated_at.strip(),
        )
    )


def resume_assignment_after_po_inbox_answer(
    assignment: AgentAssignment,
    *,
    updated_at: str,
) -> AgentAssignment:
    """Requeue a PO-paused assignment after the blocker has a recorded answer."""

    _require_transition(assignment.status, {AssignmentStatus.PAUSED_PO}, AssignmentStatus.QUEUED)
    return require_valid_agent_assignment(
        replace(
            assignment,
            status=AssignmentStatus.QUEUED,
            worker_id="",
            codex_job_id="",
            pause_reason="",
            updated_at=updated_at.strip(),
        )
    )


def fail_assignment(
    assignment: AgentAssignment,
    *,
    failure_reason: str,
    updated_at: str,
) -> AgentAssignment:
    """Record a terminal assignment failure."""

    if assignment.status in TERMINAL_ASSIGNMENT_STATUSES:
        _require_transition(assignment.status, set(), AssignmentStatus.FAILED)
    return require_valid_agent_assignment(
        replace(
            assignment,
            status=AssignmentStatus.FAILED,
            failure_reason=failure_reason.strip(),
            updated_at=updated_at.strip(),
        )
    )


def complete_assignment(
    assignment: AgentAssignment,
    *,
    output_path: str | None = None,
    evidence_path: str | None = None,
    completed_at: str,
) -> AgentAssignment:
    """Record successful assignment completion."""

    _require_transition(
        assignment.status,
        {AssignmentStatus.ASSIGNED, AssignmentStatus.IN_PROGRESS},
        AssignmentStatus.COMPLETED,
    )
    paths = replace(
        assignment.paths,
        output_path=(output_path.strip() if output_path is not None else assignment.paths.output_path),
        evidence_path=(evidence_path.strip() if evidence_path is not None else assignment.paths.evidence_path),
    )
    return require_valid_agent_assignment(
        replace(
            assignment,
            status=AssignmentStatus.COMPLETED,
            paths=paths,
            completed_at=completed_at.strip(),
            updated_at=completed_at.strip(),
        )
    )


def worker_instance_to_dict(worker: WorkerInstance) -> dict[str, Any]:
    """Convert a worker instance into JSON-compatible data."""

    return {
        "id": worker.id,
        "role": worker.role.value,
        "status": worker.status.value,
        "display_name": worker.display_name,
        "container_name": worker.container_name,
        "workspace_path": worker.workspace_path,
        "current_assignment_id": worker.current_assignment_id,
        "registered_at": worker.registered_at,
        "updated_at": worker.updated_at,
    }


def worker_instance_from_dict(data: Mapping[str, Any]) -> WorkerInstance:
    worker = WorkerInstance(
        id=_optional_text(data.get("id")),
        role=_enum_from_value(AgentRole, data.get("role", "")),
        status=_enum_from_value(WorkerStatus, data.get("status", "")),
        display_name=_optional_text(data.get("display_name")),
        container_name=_optional_text(data.get("container_name")),
        workspace_path=_optional_text(data.get("workspace_path")),
        current_assignment_id=_optional_text(data.get("current_assignment_id")),
        registered_at=_optional_text(data.get("registered_at")),
        updated_at=_optional_text(data.get("updated_at")),
    )
    return require_valid_worker_instance(worker)


def agent_assignment_to_dict(assignment: AgentAssignment) -> dict[str, Any]:
    """Convert an assignment into JSON-compatible data."""

    return {
        "id": assignment.id,
        "jira_issue_key": assignment.jira_issue_key,
        "role": assignment.role.value,
        "status": assignment.status.value,
        "worker_id": assignment.worker_id,
        "codex_job_id": assignment.codex_job_id,
        "branch_name": assignment.branch_name,
        "project_id": assignment.project_id,
        "project_name": assignment.project_name,
        "project_root": assignment.project_root,
        "repository": assignment.repository,
        "jira_project_key": assignment.jira_project_key,
        "stack_metadata": assignment_stack_metadata_to_dict(assignment.stack_metadata),
        "created_at": assignment.created_at,
        "updated_at": assignment.updated_at,
        "started_at": assignment.started_at,
        "completed_at": assignment.completed_at,
        "pause_reason": assignment.pause_reason,
        "po_inbox_item_id": assignment.po_inbox_item_id,
        "failure_reason": assignment.failure_reason,
        "attempt_count": assignment.attempt_count,
        "paths": assignment_paths_to_dict(assignment.paths),
    }


def agent_assignment_from_dict(data: Mapping[str, Any]) -> AgentAssignment:
    paths_data = data.get("paths", {})
    if not isinstance(paths_data, Mapping):
        raise AssignmentSchemaError([AssignmentSchemaIssue("assignment.paths", "Paths must be an object.")])
    assignment = AgentAssignment(
        id=_optional_text(data.get("id")),
        jira_issue_key=_optional_text(data.get("jira_issue_key")),
        role=_enum_from_value(AgentRole, data.get("role", "")),
        status=_enum_from_value(AssignmentStatus, data.get("status", "")),
        paths=assignment_paths_from_dict(paths_data),
        worker_id=_optional_text(data.get("worker_id")),
        codex_job_id=_optional_text(data.get("codex_job_id")),
        branch_name=_optional_text(data.get("branch_name")),
        project_id=_optional_text(data.get("project_id")),
        project_name=_optional_text(data.get("project_name")),
        project_root=_optional_text(data.get("project_root")),
        repository=_optional_text(data.get("repository")),
        jira_project_key=_optional_text(data.get("jira_project_key")),
        stack_metadata=assignment_stack_metadata_from_dict(data.get("stack_metadata")),
        created_at=_optional_text(data.get("created_at")),
        updated_at=_optional_text(data.get("updated_at")),
        started_at=_optional_text(data.get("started_at")),
        completed_at=_optional_text(data.get("completed_at")),
        pause_reason=_optional_text(data.get("pause_reason")),
        po_inbox_item_id=_optional_text(data.get("po_inbox_item_id")),
        failure_reason=_optional_text(data.get("failure_reason")),
        attempt_count=_int_from_value(data.get("attempt_count", 0)),
    )
    return require_valid_agent_assignment(assignment)


def assignment_paths_to_dict(paths: AssignmentPaths) -> dict[str, str]:
    return {
        "context_pack_path": paths.context_pack_path,
        "codex_job_path": paths.codex_job_path,
        "output_path": paths.output_path,
        "workspace_path": paths.workspace_path,
        "evidence_path": paths.evidence_path,
        "failed_request_path": paths.failed_request_path,
        "po_inbox_resume_context_path": paths.po_inbox_resume_context_path,
    }


def assignment_paths_from_dict(data: Mapping[str, Any]) -> AssignmentPaths:
    return AssignmentPaths(
        context_pack_path=_optional_text(data.get("context_pack_path")),
        codex_job_path=_optional_text(data.get("codex_job_path")),
        output_path=_optional_text(data.get("output_path")),
        workspace_path=_optional_text(data.get("workspace_path")),
        evidence_path=_optional_text(data.get("evidence_path")),
        failed_request_path=_optional_text(data.get("failed_request_path")),
        po_inbox_resume_context_path=_optional_text(data.get("po_inbox_resume_context_path")),
    )


def assignment_stack_metadata_to_dict(metadata: AssignmentStackMetadata) -> dict[str, Any]:
    return {
        "stack_id": metadata.stack_id,
        "lane_id": metadata.lane_id,
        "stack_mode": metadata.stack_mode,
        "resolved_path_version": metadata.resolved_path_version,
        "current_layer": metadata.current_layer,
        "expected_next_agent": metadata.expected_next_agent,
        "stale_state": metadata.stale_state,
        "rebase_required": metadata.rebase_required,
    }


def assignment_stack_metadata_from_dict(data: Any) -> AssignmentStackMetadata:
    if data is None:
        return AssignmentStackMetadata()
    if not isinstance(data, Mapping):
        raise AssignmentSchemaError([AssignmentSchemaIssue("assignment.stack_metadata", "Stack metadata must be an object.")])
    return AssignmentStackMetadata(
        stack_id=_optional_text(data.get("stack_id")),
        lane_id=_optional_text(data.get("lane_id")),
        stack_mode=_optional_text(data.get("stack_mode")),
        resolved_path_version=_optional_text(data.get("resolved_path_version")),
        current_layer=_int_from_value(data.get("current_layer", 0), "assignment.stack_metadata.current_layer"),
        expected_next_agent=_optional_text(data.get("expected_next_agent")),
        stale_state=_optional_text(data.get("stale_state")),
        rebase_required=bool(data.get("rebase_required", False)),
    )


def agent_registry_to_dict(registry: AgentRegistry) -> dict[str, Any]:
    """Convert a registry snapshot into JSON-compatible data."""

    return {
        "id": registry.id,
        "workers": [worker_instance_to_dict(worker) for worker in registry.workers],
        "assignments": [agent_assignment_to_dict(assignment) for assignment in registry.assignments],
        "created_at": registry.created_at,
        "updated_at": registry.updated_at,
    }


def agent_registry_from_dict(data: Mapping[str, Any]) -> AgentRegistry:
    registry = AgentRegistry(
        id=_optional_text(data.get("id")),
        workers=tuple(
            worker_instance_from_dict(item)
            for item in _list(data.get("workers"))
            if isinstance(item, Mapping)
        ),
        assignments=tuple(
            agent_assignment_from_dict(item)
            for item in _list(data.get("assignments"))
            if isinstance(item, Mapping)
        ),
        created_at=_optional_text(data.get("created_at")),
        updated_at=_optional_text(data.get("updated_at")),
    )
    return require_valid_agent_registry(registry)


def format_assignment_schema_issues(issues: list[AssignmentSchemaIssue]) -> str:
    """Format validation issues without including prompt or secret content."""

    if not issues:
        return "Agent assignment artifact is valid."
    lines = ["Agent assignment validation failed:"]
    lines.extend(f"- {issue.field}: {issue.message}" for issue in issues)
    return "\n".join(lines)


def _require_transition(
    current: AssignmentStatus,
    allowed: set[AssignmentStatus],
    target: AssignmentStatus,
) -> None:
    if current not in allowed:
        raise AssignmentSchemaError(
            [
                AssignmentSchemaIssue(
                    "assignment.status",
                    f"Cannot transition assignment from {current.value} to {target.value}.",
                )
            ]
        )


def _enum_from_value(enum_type: type[Enum], value: Any) -> Any:
    try:
        return enum_type(str(value))
    except ValueError as exc:
        raise AssignmentSchemaError(
            [
                AssignmentSchemaIssue(
                    field=enum_type.__name__,
                    message=f"Unsupported value {str(value)!r}.",
                )
            ]
        ) from exc


def _validate_stack_metadata(issues: list[AssignmentSchemaIssue], metadata: AssignmentStackMetadata) -> None:
    if not _stack_metadata_is_present(metadata):
        return
    _require_text(issues, "assignment.stack_metadata.stack_id", metadata.stack_id)
    _require_text(issues, "assignment.stack_metadata.lane_id", metadata.lane_id)
    _require_text(issues, "assignment.stack_metadata.stack_mode", metadata.stack_mode)
    _require_text(issues, "assignment.stack_metadata.resolved_path_version", metadata.resolved_path_version)
    _require_text(issues, "assignment.stack_metadata.expected_next_agent", metadata.expected_next_agent)
    if metadata.current_layer < 1:
        issues.append(
            AssignmentSchemaIssue("assignment.stack_metadata.current_layer", "Current stack layer must be 1 or greater.")
        )
    if metadata.rebase_required and not metadata.stale_state.strip():
        issues.append(
            AssignmentSchemaIssue(
                "assignment.stack_metadata.stale_state",
                "Rebase-required assignments must include the stale state reason.",
            )
        )


def _stack_metadata_is_present(metadata: AssignmentStackMetadata) -> bool:
    return any(
        (
            metadata.stack_id.strip(),
            metadata.lane_id.strip(),
            metadata.stack_mode.strip(),
            metadata.resolved_path_version.strip(),
            metadata.current_layer,
            metadata.expected_next_agent.strip(),
            metadata.stale_state.strip(),
            metadata.rebase_required,
        )
    )


def _int_from_value(value: Any, field_name: str = "assignment.attempt_count") -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise AssignmentSchemaError(
            [AssignmentSchemaIssue(field_name, "Value must be an integer.")]
        ) from exc


def _require_text(issues: list[AssignmentSchemaIssue], field_name: str, value: str) -> None:
    if not value.strip():
        issues.append(AssignmentSchemaIssue(field=field_name, message="Required value is missing."))


def _optional_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _list(raw: object) -> list[Any]:
    if isinstance(raw, list):
        return raw
    return []
