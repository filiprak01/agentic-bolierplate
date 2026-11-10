"""Durable orchestration event contracts for trigger-driven workers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any

from agentic_boilerplate.domain.po_inbox import AgentRole


class OrchestrationEventType(str, Enum):
    """Known durable events that can wake orchestration follow-up work."""

    ASSIGNMENT_COMPLETED = "assignment_completed"
    PR_READY = "pr_ready"
    PR_MERGED = "pr_merged"
    DEVELOPMENT_COMPLETED = "development_completed"
    REVIEW_COMPLETED = "review_completed"
    REVIEW_BLOCKED = "review_blocked"
    TEST_REQUESTED = "test_requested"
    TEST_PASSED = "test_passed"
    TEST_FAILED = "test_failed"
    TESTING_COMPLETED = "testing_completed"
    TESTING_FAILED = "testing_failed"
    BUG_CREATED = "bug_created"
    REGRESSION_REQUESTED = "regression_requested"
    REGRESSION_COMPLETED = "regression_completed"
    RETRO_REQUESTED = "retro_requested"
    RETRO_RESPONSE_RECEIVED = "retro_response_received"
    LIMIT_PAUSED = "limit_paused"
    PO_BLOCKED = "po_blocked"
    PO_QUESTION_CREATED = "po_question_created"
    WORKER_IDLE = "worker_idle"


class OrchestrationEventStatus(str, Enum):
    """Queue status for one durable orchestration event."""

    QUEUED = "queued"
    PROCESSING = "processing"
    PROCESSED = "processed"
    REJECTED = "rejected"


TERMINAL_ORCHESTRATION_EVENT_STATUSES: frozenset[OrchestrationEventStatus] = frozenset(
    {
        OrchestrationEventStatus.PROCESSED,
        OrchestrationEventStatus.REJECTED,
    }
)


ALLOWED_ORCHESTRATION_EVENT_STATUS_TRANSITIONS: dict[
    OrchestrationEventStatus, frozenset[OrchestrationEventStatus]
] = {
    OrchestrationEventStatus.QUEUED: frozenset(
        {
            OrchestrationEventStatus.PROCESSING,
            OrchestrationEventStatus.PROCESSED,
            OrchestrationEventStatus.REJECTED,
        }
    ),
    OrchestrationEventStatus.PROCESSING: frozenset(
        {
            OrchestrationEventStatus.PROCESSED,
            OrchestrationEventStatus.REJECTED,
        }
    ),
    OrchestrationEventStatus.PROCESSED: frozenset(),
    OrchestrationEventStatus.REJECTED: frozenset(),
}


@dataclass(frozen=True)
class OrchestrationEvent:
    """One durable trigger event emitted by a worker, scheduler, or release role."""

    id: str
    event_type: OrchestrationEventType
    status: OrchestrationEventStatus
    idempotency_key: str
    source_role: AgentRole
    created_at: str
    updated_at: str
    jira_issue_key: str = ""
    source_assignment_id: str = ""
    target_role: AgentRole | None = None
    project_id: str = ""
    project_name: str = ""
    project_root: str = ""
    repository: str = ""
    jira_project_key: str = ""
    correlation_id: str = ""
    scope_key: str = ""
    payload: Mapping[str, Any] | None = None
    evidence_paths: tuple[str, ...] = ()
    processed_at: str = ""
    rejected_reason: str = ""


@dataclass(frozen=True)
class OrchestrationEventSchemaIssue:
    """Validation issue for a durable orchestration event."""

    field: str
    message: str


class OrchestrationEventSchemaError(ValueError):
    """Raised when an event violates the durable orchestration contract."""

    def __init__(self, issues: list[OrchestrationEventSchemaIssue]) -> None:
        self.issues = issues
        super().__init__(format_orchestration_event_schema_issues(issues))


class OrchestrationEventTransitionError(ValueError):
    """Raised when an event status transition is not allowed."""


def build_orchestration_event(
    *,
    event_id: str,
    event_type: OrchestrationEventType,
    idempotency_key: str,
    source_role: AgentRole,
    created_at: str,
    jira_issue_key: str = "",
    source_assignment_id: str = "",
    target_role: AgentRole | None = None,
    project_id: str = "",
    project_name: str = "",
    project_root: str = "",
    repository: str = "",
    jira_project_key: str = "",
    correlation_id: str = "",
    scope_key: str = "",
    payload: Mapping[str, Any] | None = None,
    evidence_paths: tuple[str, ...] = (),
) -> OrchestrationEvent:
    """Build and validate a queued orchestration event."""

    return require_valid_orchestration_event(
        OrchestrationEvent(
            id=event_id.strip(),
            event_type=event_type,
            status=OrchestrationEventStatus.QUEUED,
            idempotency_key=idempotency_key.strip(),
            source_role=source_role,
            created_at=created_at.strip(),
            updated_at=created_at.strip(),
            jira_issue_key=jira_issue_key.strip(),
            source_assignment_id=source_assignment_id.strip(),
            target_role=target_role,
            project_id=project_id.strip(),
            project_name=project_name.strip(),
            project_root=project_root.strip(),
            repository=repository.strip(),
            jira_project_key=jira_project_key.strip(),
            correlation_id=correlation_id.strip(),
            scope_key=scope_key.strip(),
            payload=dict(payload or {}),
            evidence_paths=tuple(path.strip() for path in evidence_paths if path and path.strip()),
        )
    )


def orchestration_event_idempotency_key(
    *,
    event_type: OrchestrationEventType,
    jira_issue_key: str = "",
    source_assignment_id: str = "",
    scope_key: str = "",
) -> str:
    """Build a deterministic idempotency key for at-least-once event delivery."""

    parts = [
        event_type.value,
        jira_issue_key.strip().upper() or "-",
        source_assignment_id.strip() or "-",
        scope_key.strip() or "-",
    ]
    return ":".join(parts)


def validate_orchestration_event(event: OrchestrationEvent) -> list[OrchestrationEventSchemaIssue]:
    """Return schema issues for one orchestration event."""

    issues: list[OrchestrationEventSchemaIssue] = []
    _require_text(issues, "event.id", event.id)
    _require_text(issues, "event.idempotency_key", event.idempotency_key)
    _require_text(issues, "event.created_at", event.created_at)
    _require_text(issues, "event.updated_at", event.updated_at)
    if event.status is OrchestrationEventStatus.PROCESSED:
        _require_text(issues, "event.processed_at", event.processed_at)
    if event.status is OrchestrationEventStatus.REJECTED:
        _require_text(issues, "event.rejected_reason", event.rejected_reason)
    if event.payload is not None and not isinstance(event.payload, Mapping):
        issues.append(OrchestrationEventSchemaIssue("event.payload", "Payload must be a mapping."))
    if any(not path.strip() for path in event.evidence_paths):
        issues.append(
            OrchestrationEventSchemaIssue("event.evidence_paths", "Evidence paths cannot contain blank values.")
        )
    return issues


def require_valid_orchestration_event(event: OrchestrationEvent) -> OrchestrationEvent:
    """Return event or raise when it violates the schema."""

    issues = validate_orchestration_event(event)
    if issues:
        raise OrchestrationEventSchemaError(issues)
    return event


def mark_orchestration_event_processing(event: OrchestrationEvent, *, updated_at: str) -> OrchestrationEvent:
    """Claim a queued event for processing."""

    _require_event_transition(event.status, OrchestrationEventStatus.PROCESSING)
    return require_valid_orchestration_event(
        replace(
            event,
            status=OrchestrationEventStatus.PROCESSING,
            updated_at=updated_at.strip(),
        )
    )


def mark_orchestration_event_processed(
    event: OrchestrationEvent,
    *,
    processed_at: str,
    updated_at: str = "",
) -> OrchestrationEvent:
    """Mark a queued or processing event as completed."""

    _require_event_transition(event.status, OrchestrationEventStatus.PROCESSED)
    timestamp = processed_at.strip()
    return require_valid_orchestration_event(
        replace(
            event,
            status=OrchestrationEventStatus.PROCESSED,
            processed_at=timestamp,
            updated_at=(updated_at or timestamp).strip(),
        )
    )


def reject_orchestration_event(
    event: OrchestrationEvent,
    *,
    rejected_reason: str,
    updated_at: str,
) -> OrchestrationEvent:
    """Reject an event that cannot be routed safely."""

    _require_event_transition(event.status, OrchestrationEventStatus.REJECTED)
    return require_valid_orchestration_event(
        replace(
            event,
            status=OrchestrationEventStatus.REJECTED,
            rejected_reason=rejected_reason.strip(),
            updated_at=updated_at.strip(),
        )
    )


def orchestration_event_to_dict(event: OrchestrationEvent) -> dict[str, Any]:
    """Serialize an orchestration event to JSON-compatible data."""

    return {
        "id": event.id,
        "event_type": event.event_type.value,
        "status": event.status.value,
        "idempotency_key": event.idempotency_key,
        "source_role": event.source_role.value,
        "created_at": event.created_at,
        "updated_at": event.updated_at,
        "jira_issue_key": event.jira_issue_key,
        "source_assignment_id": event.source_assignment_id,
        "target_role": event.target_role.value if event.target_role else "",
        "project_id": event.project_id,
        "project_name": event.project_name,
        "project_root": event.project_root,
        "repository": event.repository,
        "jira_project_key": event.jira_project_key,
        "correlation_id": event.correlation_id,
        "scope_key": event.scope_key,
        "payload": dict(event.payload or {}),
        "evidence_paths": list(event.evidence_paths),
        "processed_at": event.processed_at,
        "rejected_reason": event.rejected_reason,
    }


def orchestration_event_from_dict(data: Mapping[str, Any]) -> OrchestrationEvent:
    """Deserialize and validate an orchestration event."""

    target_role_value = str(data.get("target_role") or "")
    event = OrchestrationEvent(
        id=str(data.get("id") or ""),
        event_type=OrchestrationEventType(str(data.get("event_type") or "")),
        status=OrchestrationEventStatus(str(data.get("status") or "")),
        idempotency_key=str(data.get("idempotency_key") or ""),
        source_role=AgentRole(str(data.get("source_role") or "")),
        created_at=str(data.get("created_at") or ""),
        updated_at=str(data.get("updated_at") or ""),
        jira_issue_key=str(data.get("jira_issue_key") or ""),
        source_assignment_id=str(data.get("source_assignment_id") or ""),
        target_role=AgentRole(target_role_value) if target_role_value else None,
        project_id=str(data.get("project_id") or ""),
        project_name=str(data.get("project_name") or ""),
        project_root=str(data.get("project_root") or ""),
        repository=str(data.get("repository") or ""),
        jira_project_key=str(data.get("jira_project_key") or ""),
        correlation_id=str(data.get("correlation_id") or ""),
        scope_key=str(data.get("scope_key") or ""),
        payload=_mapping_or_empty(data.get("payload")),
        evidence_paths=tuple(str(path) for path in _sequence_or_empty(data.get("evidence_paths"))),
        processed_at=str(data.get("processed_at") or ""),
        rejected_reason=str(data.get("rejected_reason") or ""),
    )
    return require_valid_orchestration_event(event)


def format_orchestration_event_schema_issues(issues: list[OrchestrationEventSchemaIssue]) -> str:
    """Format validation issues for CLI and tests."""

    return "; ".join(f"{issue.field}: {issue.message}" for issue in issues)


def _require_text(issues: list[OrchestrationEventSchemaIssue], field: str, value: str) -> None:
    if not value.strip():
        issues.append(OrchestrationEventSchemaIssue(field, "Value is required."))


def _require_event_transition(
    current: OrchestrationEventStatus,
    target: OrchestrationEventStatus,
) -> None:
    if target not in ALLOWED_ORCHESTRATION_EVENT_STATUS_TRANSITIONS[current]:
        raise OrchestrationEventTransitionError(
            f"Cannot transition orchestration event from {current.value} to {target.value}."
        )


def _mapping_or_empty(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence_or_empty(value: object) -> tuple[object, ...]:
    if isinstance(value, (str, bytes)) or value is None:
        return ()
    try:
        return tuple(value)  # type: ignore[arg-type]
    except TypeError:
        return ()
