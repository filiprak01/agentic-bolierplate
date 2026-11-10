"""Durable agent communication message contracts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any

from agentic_boilerplate.domain.message_export_policy import redact_message_export_payload
from agentic_boilerplate.domain.po_inbox import AgentRole


class AgentCommunicationChannel(str, Enum):
    """Project-scoped channel scopes for agent messages."""

    PROJECT = "project"
    SPRINT = "sprint"
    JIRA_ISSUE = "jira_issue"
    ROLE = "role"
    ASSIGNMENT = "assignment"
    ORCHESTRATOR = "orchestrator"
    PRODUCT_OWNER_OUTBOX = "product_owner_outbox"


class AgentMessageType(str, Enum):
    """Known agent communication message types."""

    STATUS_UPDATE = "status_update"
    HANDOFF_REQUEST = "handoff_request"
    ARTIFACT_AVAILABLE = "artifact_available"
    BLOCKED = "blocked"
    RESUME_REQUEST = "resume_request"
    PO_REQUIRED = "po_required"
    REVIEW_REQUESTED = "review_requested"
    CHANGES_REQUESTED = "changes_requested"
    TEST_REQUESTED = "test_requested"
    BUG_FIX_REQUESTED = "bug_fix_requested"
    REGRESSION_READY = "regression_ready"
    REGRESSION_REQUESTED = "regression_requested"
    RETRO_REQUESTED = "retro_requested"
    RETRO_RESPONSE = "retro_response"
    CLOSURE_READY = "closure_ready"
    PO_CLARIFICATION = "po_clarification"
    PO_QUESTION_TO_AGENT = "po_question_to_agent"
    PO_RESUME_INSTRUCTION = "po_resume_instruction"
    AGENT_RESPONSE_TO_PO = "agent_response_to_po"
    SCOPE_CHANGE_CANDIDATE = "scope_change_candidate"


class AgentMessageStatus(str, Enum):
    """Delivery status for one durable agent message."""

    QUEUED = "queued"
    ACKNOWLEDGED = "acknowledged"
    CONSUMED = "consumed"
    REJECTED = "rejected"


class AgentMessagePriority(str, Enum):
    """Routing priority for operator and worker queues."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    BLOCKING = "blocking"


TERMINAL_AGENT_MESSAGE_STATUSES: frozenset[AgentMessageStatus] = frozenset(
    {AgentMessageStatus.CONSUMED, AgentMessageStatus.REJECTED}
)


ALLOWED_AGENT_MESSAGE_STATUS_TRANSITIONS: dict[AgentMessageStatus, frozenset[AgentMessageStatus]] = {
    AgentMessageStatus.QUEUED: frozenset(
        {
            AgentMessageStatus.ACKNOWLEDGED,
            AgentMessageStatus.CONSUMED,
            AgentMessageStatus.REJECTED,
        }
    ),
    AgentMessageStatus.ACKNOWLEDGED: frozenset(
        {
            AgentMessageStatus.CONSUMED,
            AgentMessageStatus.REJECTED,
        }
    ),
    AgentMessageStatus.CONSUMED: frozenset(),
    AgentMessageStatus.REJECTED: frozenset(),
}


@dataclass(frozen=True)
class AgentMessage:
    """One durable message sent between agents, role pools, or the Product Owner."""

    id: str
    message_type: AgentMessageType
    status: AgentMessageStatus
    idempotency_key: str
    source_role: AgentRole
    created_at: str
    updated_at: str
    project_id: str
    priority: AgentMessagePriority = AgentMessagePriority.NORMAL
    target_role: AgentRole | None = None
    target_channel: AgentCommunicationChannel | None = None
    source_worker_id: str = ""
    target_worker_id: str = ""
    origin_actor: str = "worker"
    correlation_id: str = ""
    causation_id: str = ""
    project_name: str = ""
    project_root: str = ""
    repository: str = ""
    jira_project_key: str = ""
    sprint_id: str = ""
    sprint_name: str = ""
    jira_issue_key: str = ""
    assignment_id: str = ""
    payload: Mapping[str, Any] | None = None
    artifact_refs: tuple[str, ...] = ()
    requires_acknowledgement: bool = False
    expires_at: str = ""
    acknowledged_at: str = ""
    consumed_at: str = ""
    rejected_reason: str = ""


@dataclass(frozen=True)
class AgentMessageSchemaIssue:
    """Validation issue for a durable agent communication message."""

    field: str
    message: str


class AgentMessageSchemaError(ValueError):
    """Raised when an agent message violates the durable communication contract."""

    def __init__(self, issues: list[AgentMessageSchemaIssue]) -> None:
        self.issues = issues
        super().__init__(format_agent_message_schema_issues(issues))


class AgentMessageTransitionError(ValueError):
    """Raised when an agent message status transition is not allowed."""


@dataclass(frozen=True)
class AgentResumeGateInput:
    """Gate inputs required before emitting an Orchestrator resume request."""

    codex_limit_allows_work: bool
    jira_status_eligible: bool
    dependency_gate_passed: bool
    linked_bugs_clear: bool
    locks_clear: bool
    po_answers_recorded: bool
    required_artifacts_ready: bool = True


@dataclass(frozen=True)
class AgentResumeGateDecision:
    """Decision for whether Orchestrator may emit a resume request."""

    allowed: bool
    blockers: tuple[str, ...]
    reason: str


def build_agent_message(
    *,
    message_id: str,
    message_type: AgentMessageType,
    idempotency_key: str,
    source_role: AgentRole,
    created_at: str,
    project_id: str,
    priority: AgentMessagePriority = AgentMessagePriority.NORMAL,
    target_role: AgentRole | None = None,
    target_channel: AgentCommunicationChannel | None = None,
    source_worker_id: str = "",
    target_worker_id: str = "",
    origin_actor: str = "worker",
    correlation_id: str = "",
    causation_id: str = "",
    project_name: str = "",
    project_root: str = "",
    repository: str = "",
    jira_project_key: str = "",
    sprint_id: str = "",
    sprint_name: str = "",
    jira_issue_key: str = "",
    assignment_id: str = "",
    payload: Mapping[str, Any] | None = None,
    artifact_refs: Sequence[str] = (),
    requires_acknowledgement: bool = False,
    expires_at: str = "",
) -> AgentMessage:
    """Build and validate a queued durable communication message."""

    return require_valid_agent_message(
        AgentMessage(
            id=message_id.strip(),
            message_type=message_type,
            status=AgentMessageStatus.QUEUED,
            idempotency_key=idempotency_key.strip(),
            source_role=source_role,
            created_at=created_at.strip(),
            updated_at=created_at.strip(),
            project_id=project_id.strip(),
            priority=priority,
            target_role=target_role,
            target_channel=target_channel,
            source_worker_id=source_worker_id.strip(),
            target_worker_id=target_worker_id.strip(),
            origin_actor=origin_actor.strip() or "worker",
            correlation_id=correlation_id.strip(),
            causation_id=causation_id.strip(),
            project_name=project_name.strip(),
            project_root=project_root.strip(),
            repository=repository.strip(),
            jira_project_key=jira_project_key.strip(),
            sprint_id=sprint_id.strip(),
            sprint_name=sprint_name.strip(),
            jira_issue_key=jira_issue_key.strip(),
            assignment_id=assignment_id.strip(),
            payload=dict(payload or {}),
            artifact_refs=tuple(ref.strip() for ref in artifact_refs if ref and ref.strip()),
            requires_acknowledgement=requires_acknowledgement,
            expires_at=expires_at.strip(),
        )
    )


def agent_message_idempotency_key(
    *,
    message_type: AgentMessageType,
    project_id: str,
    jira_issue_key: str = "",
    assignment_id: str = "",
    target_role: AgentRole | None = None,
    target_channel: AgentCommunicationChannel | None = None,
    correlation_id: str = "",
    causation_id: str = "",
) -> str:
    """Build a deterministic idempotency key for at-least-once message delivery."""

    parts = [
        message_type.value,
        project_id.strip().upper() or "-",
        jira_issue_key.strip().upper() or "-",
        assignment_id.strip() or "-",
        target_role.value if target_role else "-",
        target_channel.value if target_channel else "-",
        correlation_id.strip() or "-",
        causation_id.strip() or "-",
    ]
    return ":".join(parts)


def validate_agent_message(message: AgentMessage) -> list[AgentMessageSchemaIssue]:
    """Return schema issues for one durable agent message."""

    issues: list[AgentMessageSchemaIssue] = []
    _require_text(issues, "message.id", message.id)
    _require_text(issues, "message.idempotency_key", message.idempotency_key)
    _require_text(issues, "message.created_at", message.created_at)
    _require_text(issues, "message.updated_at", message.updated_at)
    _require_text(issues, "message.project_id", message.project_id)
    if not (message.target_role or message.target_worker_id.strip() or message.target_channel):
        issues.append(
            AgentMessageSchemaIssue(
                "message.target",
                "Message requires a target role, target worker, or target channel.",
            )
        )
    if message.payload is not None and not isinstance(message.payload, Mapping):
        issues.append(AgentMessageSchemaIssue("message.payload", "Payload must be a mapping."))
    if any(not ref.strip() for ref in message.artifact_refs):
        issues.append(AgentMessageSchemaIssue("message.artifact_refs", "Artifact references cannot be blank."))
    if message.status is AgentMessageStatus.ACKNOWLEDGED:
        _require_text(issues, "message.acknowledged_at", message.acknowledged_at)
    if message.status is AgentMessageStatus.CONSUMED:
        _require_text(issues, "message.consumed_at", message.consumed_at)
    if message.status is AgentMessageStatus.REJECTED:
        _require_text(issues, "message.rejected_reason", message.rejected_reason)
    return issues


def require_valid_agent_message(message: AgentMessage) -> AgentMessage:
    """Return message or raise when it violates the communication contract."""

    issues = validate_agent_message(message)
    if issues:
        raise AgentMessageSchemaError(issues)
    return message


def mark_agent_message_acknowledged(message: AgentMessage, *, acknowledged_at: str) -> AgentMessage:
    """Mark a message acknowledged by a worker or role pool."""

    _require_message_transition(message.status, AgentMessageStatus.ACKNOWLEDGED)
    timestamp = acknowledged_at.strip()
    return require_valid_agent_message(
        replace(
            message,
            status=AgentMessageStatus.ACKNOWLEDGED,
            acknowledged_at=timestamp,
            updated_at=timestamp,
        )
    )


def mark_agent_message_consumed(message: AgentMessage, *, consumed_at: str) -> AgentMessage:
    """Mark a message fully consumed by its target."""

    _require_message_transition(message.status, AgentMessageStatus.CONSUMED)
    timestamp = consumed_at.strip()
    return require_valid_agent_message(
        replace(
            message,
            status=AgentMessageStatus.CONSUMED,
            consumed_at=timestamp,
            updated_at=timestamp,
        )
    )


def reject_agent_message(message: AgentMessage, *, rejected_reason: str, rejected_at: str) -> AgentMessage:
    """Reject a message with a durable reason."""

    _require_message_transition(message.status, AgentMessageStatus.REJECTED)
    timestamp = rejected_at.strip()
    return require_valid_agent_message(
        replace(
            message,
            status=AgentMessageStatus.REJECTED,
            rejected_reason=rejected_reason.strip(),
            updated_at=timestamp,
        )
    )


def evaluate_agent_resume_gate(input_data: AgentResumeGateInput) -> AgentResumeGateDecision:
    """Decide whether Orchestrator may emit a resume request."""

    blockers: list[str] = []
    if not input_data.codex_limit_allows_work:
        blockers.append("codex_limit_gate_closed")
    if not input_data.jira_status_eligible:
        blockers.append("jira_status_not_eligible")
    if not input_data.dependency_gate_passed:
        blockers.append("dependency_gate_failed")
    if not input_data.linked_bugs_clear:
        blockers.append("linked_bugs_unresolved")
    if not input_data.locks_clear:
        blockers.append("assignment_lock_conflict")
    if not input_data.po_answers_recorded:
        blockers.append("po_answer_missing")
    if not input_data.required_artifacts_ready:
        blockers.append("required_artifacts_missing")
    if blockers:
        return AgentResumeGateDecision(
            allowed=False,
            blockers=tuple(blockers),
            reason="Resume request is blocked until all orchestration gates pass.",
        )
    return AgentResumeGateDecision(allowed=True, blockers=(), reason="Resume request gates passed.")


def redact_agent_message(message: AgentMessage) -> AgentMessage:
    """Redact sensitive message payload and artifact references before publication."""

    redacted = redact_message_export_payload(
        {
            "project_id": message.project_id,
            "project_root": message.project_root,
            "payload": dict(message.payload or {}),
            "artifact_refs": list(message.artifact_refs),
        }
    )
    return replace(
        message,
        project_root=str(redacted.get("project_root") or ""),
        payload=_mapping_or_empty(redacted.get("payload")),
        artifact_refs=tuple(str(ref) for ref in _sequence_or_empty(redacted.get("artifact_refs"))),
    )


def agent_message_to_dict(message: AgentMessage) -> dict[str, Any]:
    """Serialize an agent message to JSON-compatible data."""

    return {
        "id": message.id,
        "message_type": message.message_type.value,
        "status": message.status.value,
        "idempotency_key": message.idempotency_key,
        "source_role": message.source_role.value,
        "created_at": message.created_at,
        "updated_at": message.updated_at,
        "project_id": message.project_id,
        "priority": message.priority.value,
        "target_role": message.target_role.value if message.target_role else "",
        "target_channel": message.target_channel.value if message.target_channel else "",
        "source_worker_id": message.source_worker_id,
        "target_worker_id": message.target_worker_id,
        "origin_actor": message.origin_actor,
        "correlation_id": message.correlation_id,
        "causation_id": message.causation_id,
        "project_name": message.project_name,
        "project_root": message.project_root,
        "repository": message.repository,
        "jira_project_key": message.jira_project_key,
        "sprint_id": message.sprint_id,
        "sprint_name": message.sprint_name,
        "jira_issue_key": message.jira_issue_key,
        "assignment_id": message.assignment_id,
        "payload": dict(message.payload or {}),
        "artifact_refs": list(message.artifact_refs),
        "requires_acknowledgement": message.requires_acknowledgement,
        "expires_at": message.expires_at,
        "acknowledged_at": message.acknowledged_at,
        "consumed_at": message.consumed_at,
        "rejected_reason": message.rejected_reason,
    }


def agent_message_from_dict(data: Mapping[str, Any]) -> AgentMessage:
    """Deserialize and validate an agent communication message."""

    target_role_value = str(data.get("target_role") or "")
    target_channel_value = str(data.get("target_channel") or "")
    message = AgentMessage(
        id=str(data.get("id") or ""),
        message_type=AgentMessageType(str(data.get("message_type") or "")),
        status=AgentMessageStatus(str(data.get("status") or "")),
        idempotency_key=str(data.get("idempotency_key") or ""),
        source_role=AgentRole(str(data.get("source_role") or "")),
        created_at=str(data.get("created_at") or ""),
        updated_at=str(data.get("updated_at") or ""),
        project_id=str(data.get("project_id") or ""),
        priority=AgentMessagePriority(str(data.get("priority") or AgentMessagePriority.NORMAL.value)),
        target_role=AgentRole(target_role_value) if target_role_value else None,
        target_channel=AgentCommunicationChannel(target_channel_value) if target_channel_value else None,
        source_worker_id=str(data.get("source_worker_id") or ""),
        target_worker_id=str(data.get("target_worker_id") or ""),
        origin_actor=str(data.get("origin_actor") or "worker"),
        correlation_id=str(data.get("correlation_id") or ""),
        causation_id=str(data.get("causation_id") or ""),
        project_name=str(data.get("project_name") or ""),
        project_root=str(data.get("project_root") or ""),
        repository=str(data.get("repository") or ""),
        jira_project_key=str(data.get("jira_project_key") or ""),
        sprint_id=str(data.get("sprint_id") or ""),
        sprint_name=str(data.get("sprint_name") or ""),
        jira_issue_key=str(data.get("jira_issue_key") or ""),
        assignment_id=str(data.get("assignment_id") or ""),
        payload=_mapping_or_empty(data.get("payload")),
        artifact_refs=tuple(str(ref) for ref in _sequence_or_empty(data.get("artifact_refs"))),
        requires_acknowledgement=bool(data.get("requires_acknowledgement")),
        expires_at=str(data.get("expires_at") or ""),
        acknowledged_at=str(data.get("acknowledged_at") or ""),
        consumed_at=str(data.get("consumed_at") or ""),
        rejected_reason=str(data.get("rejected_reason") or ""),
    )
    return require_valid_agent_message(message)


def format_agent_message_schema_issues(issues: list[AgentMessageSchemaIssue]) -> str:
    """Format validation issues for CLI and tests."""

    return "; ".join(f"{issue.field}: {issue.message}" for issue in issues)


def _require_text(issues: list[AgentMessageSchemaIssue], field: str, value: str) -> None:
    if not value.strip():
        issues.append(AgentMessageSchemaIssue(field, "Value is required."))


def _require_message_transition(current: AgentMessageStatus, target: AgentMessageStatus) -> None:
    if target not in ALLOWED_AGENT_MESSAGE_STATUS_TRANSITIONS[current]:
        raise AgentMessageTransitionError(f"Cannot transition agent message from {current.value} to {target.value}.")


def _mapping_or_empty(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence_or_empty(value: object) -> tuple[object, ...]:
    if isinstance(value, (str, bytes)) or value is None:
        return ()
    try:
        return tuple(value)  # type: ignore[arg-type]
    except TypeError:
        return ()
