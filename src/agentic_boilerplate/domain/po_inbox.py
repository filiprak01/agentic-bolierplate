"""Product Owner inbox schema."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class InboxMessageType(str, Enum):
    """Supported Product Owner inbox message types."""

    BLOCKING_QUESTION = "blocking_question"
    ASSUMPTION = "assumption"
    FYI = "fyi"
    APPROVAL_REQUEST = "approval_request"


class InboxStatus(str, Enum):
    """Supported Product Owner inbox item states."""

    OPEN = "open"
    ANSWERED = "answered"
    APPROVED = "approved"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class AgentRole(str, Enum):
    """Known agent roles that can create inbox items."""

    PRODUCT_PLANNING = "product_planning"
    ARCHITECTURE = "architecture"
    DEVELOPER = "developer"
    REVIEW = "review"
    TESTER = "tester"
    RELEASE_MANAGER = "release_manager"
    SCHEDULER = "scheduler"
    PLATFORM = "platform"
    FRONTEND = "frontend"
    UI_UX = "ui_ux"
    SECURITY = "security"
    DOCS_CONFLUENCE = "docs_confluence"
    DEVOPS_PLATFORM = "devops_platform"
    DATA_PERSISTENCE = "data_persistence"


INBOX_STATUS_FOLDER_NAMES: dict[InboxStatus, str] = {
    InboxStatus.OPEN: "open",
    InboxStatus.ANSWERED: "answered",
    InboxStatus.APPROVED: "approved",
    InboxStatus.REJECTED: "rejected",
    InboxStatus.ARCHIVED: "archived",
}


TERMINAL_INBOX_STATUSES: frozenset[InboxStatus] = frozenset(
    {
        InboxStatus.ANSWERED,
        InboxStatus.APPROVED,
        InboxStatus.REJECTED,
        InboxStatus.ARCHIVED,
    }
)


ALLOWED_STATUSES_BY_MESSAGE_TYPE: dict[InboxMessageType, frozenset[InboxStatus]] = {
    InboxMessageType.BLOCKING_QUESTION: frozenset({InboxStatus.OPEN, InboxStatus.ANSWERED}),
    InboxMessageType.ASSUMPTION: frozenset({InboxStatus.OPEN, InboxStatus.ANSWERED, InboxStatus.ARCHIVED}),
    InboxMessageType.FYI: frozenset({InboxStatus.OPEN, InboxStatus.ARCHIVED}),
    InboxMessageType.APPROVAL_REQUEST: frozenset(
        {
            InboxStatus.OPEN,
            InboxStatus.APPROVED,
            InboxStatus.REJECTED,
        }
    ),
}


@dataclass(frozen=True)
class InboxOption:
    """Product Owner response option suggested by an agent."""

    id: str
    label: str
    description: str = ""


@dataclass(frozen=True)
class InboxAuditEvent:
    """Append-only metadata describing a schema item change."""

    timestamp: str
    actor: str
    action: str
    note: str = ""


@dataclass(frozen=True)
class POInboxItem:
    """Durable Product Owner inbox item stored as JSON-compatible data."""

    id: str
    message_type: InboxMessageType
    status: InboxStatus
    title: str
    message: str
    agent_role: AgentRole
    created_at: str
    agent_id: str = ""
    jira_issue_key: str = ""
    project_id: str = ""
    project_name: str = ""
    project_root: str = ""
    repository: str = ""
    jira_project_key: str = ""
    confluence_page_id: str = ""
    context_pack_path: str = ""
    business_impact: str = ""
    recommendation: str = ""
    options: tuple[InboxOption, ...] = field(default_factory=tuple)
    answer: str = ""
    answered_at: str = ""
    audit: tuple[InboxAuditEvent, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class InboxSchemaIssue:
    """Validation issue for a PO inbox item."""

    field: str
    message: str


class InboxSchemaError(ValueError):
    """Raised when a PO inbox item violates the schema contract."""

    def __init__(self, issues: list[InboxSchemaIssue]) -> None:
        self.issues = issues
        super().__init__(format_inbox_schema_issues(issues))


def validate_inbox_item(item: POInboxItem) -> list[InboxSchemaIssue]:
    """Return schema issues without including answer or secret-like values."""

    issues: list[InboxSchemaIssue] = []
    _require_text(issues, "id", item.id)
    _require_text(issues, "title", item.title)
    _require_text(issues, "message", item.message)
    _require_text(issues, "created_at", item.created_at)

    allowed_statuses = ALLOWED_STATUSES_BY_MESSAGE_TYPE[item.message_type]
    if item.status not in allowed_statuses:
        issues.append(
            InboxSchemaIssue(
                field="status",
                message=f"Status {item.status.value!r} is not valid for {item.message_type.value!r}.",
            )
        )

    if item.message_type in {InboxMessageType.BLOCKING_QUESTION, InboxMessageType.APPROVAL_REQUEST}:
        _require_text(issues, "business_impact", item.business_impact)
        _require_text(issues, "recommendation", item.recommendation)

    if item.status in {InboxStatus.ANSWERED, InboxStatus.APPROVED, InboxStatus.REJECTED}:
        _require_text(issues, "answer", item.answer)
        _require_text(issues, "answered_at", item.answered_at)

    if item.status == InboxStatus.OPEN and (item.answer or item.answered_at):
        issues.append(
            InboxSchemaIssue(
                field="status",
                message="Open inbox items must not include answer or answered_at values.",
            )
        )

    option_ids = [option.id for option in item.options]
    if len(set(option_ids)) != len(option_ids):
        issues.append(InboxSchemaIssue(field="options", message="Option IDs must be unique."))
    for index, option in enumerate(item.options):
        _require_text(issues, f"options[{index}].id", option.id)
        _require_text(issues, f"options[{index}].label", option.label)

    for index, event in enumerate(item.audit):
        _require_text(issues, f"audit[{index}].timestamp", event.timestamp)
        _require_text(issues, f"audit[{index}].actor", event.actor)
        _require_text(issues, f"audit[{index}].action", event.action)

    return issues


def require_valid_inbox_item(item: POInboxItem) -> POInboxItem:
    """Raise when a PO inbox item violates the schema contract."""

    issues = validate_inbox_item(item)
    if issues:
        raise InboxSchemaError(issues)
    return item


def inbox_item_to_dict(item: POInboxItem) -> dict[str, Any]:
    """Convert a PO inbox item into JSON-compatible data."""

    return {
        "id": item.id,
        "message_type": item.message_type.value,
        "status": item.status.value,
        "title": item.title,
        "message": item.message,
        "agent_role": item.agent_role.value,
        "created_at": item.created_at,
        "agent_id": item.agent_id,
        "jira_issue_key": item.jira_issue_key,
        "project_id": item.project_id,
        "project_name": item.project_name,
        "project_root": item.project_root,
        "repository": item.repository,
        "jira_project_key": item.jira_project_key,
        "confluence_page_id": item.confluence_page_id,
        "context_pack_path": item.context_pack_path,
        "business_impact": item.business_impact,
        "recommendation": item.recommendation,
        "options": [
            {
                "id": option.id,
                "label": option.label,
                "description": option.description,
            }
            for option in item.options
        ],
        "answer": item.answer,
        "answered_at": item.answered_at,
        "audit": [
            {
                "timestamp": event.timestamp,
                "actor": event.actor,
                "action": event.action,
                "note": event.note,
            }
            for event in item.audit
        ],
    }


def inbox_item_from_dict(data: Mapping[str, Any]) -> POInboxItem:
    """Build a PO inbox item from JSON-compatible data."""

    item = POInboxItem(
        id=_optional_text(data.get("id")),
        message_type=_enum_from_value(InboxMessageType, data.get("message_type", "")),
        status=_enum_from_value(InboxStatus, data.get("status", "")),
        title=_optional_text(data.get("title")),
        message=_optional_text(data.get("message")),
        agent_role=_enum_from_value(AgentRole, data.get("agent_role", "")),
        created_at=_optional_text(data.get("created_at")),
        agent_id=_optional_text(data.get("agent_id")),
        jira_issue_key=_optional_text(data.get("jira_issue_key")),
        project_id=_optional_text(data.get("project_id")),
        project_name=_optional_text(data.get("project_name")),
        project_root=_optional_text(data.get("project_root")),
        repository=_optional_text(data.get("repository")),
        jira_project_key=_optional_text(data.get("jira_project_key")),
        confluence_page_id=_optional_text(data.get("confluence_page_id")),
        context_pack_path=_optional_text(data.get("context_pack_path")),
        business_impact=_optional_text(data.get("business_impact")),
        recommendation=_optional_text(data.get("recommendation")),
        options=tuple(_option_from_dict(option) for option in data.get("options", ())),
        answer=_optional_text(data.get("answer")),
        answered_at=_optional_text(data.get("answered_at")),
        audit=tuple(_audit_event_from_dict(event) for event in data.get("audit", ())),
    )
    return require_valid_inbox_item(item)


def format_inbox_schema_issues(issues: list[InboxSchemaIssue]) -> str:
    """Format schema issues without leaking answer content."""

    if not issues:
        return "PO inbox item is valid."
    lines = ["PO inbox item validation failed:"]
    lines.extend(f"- {issue.field}: {issue.message}" for issue in issues)
    return "\n".join(lines)


def _option_from_dict(data: Mapping[str, Any]) -> InboxOption:
    return InboxOption(
        id=_optional_text(data.get("id")),
        label=_optional_text(data.get("label")),
        description=_optional_text(data.get("description")),
    )


def _audit_event_from_dict(data: Mapping[str, Any]) -> InboxAuditEvent:
    return InboxAuditEvent(
        timestamp=_optional_text(data.get("timestamp")),
        actor=_optional_text(data.get("actor")),
        action=_optional_text(data.get("action")),
        note=_optional_text(data.get("note")),
    )


def _enum_from_value(enum_type: type[Enum], value: Any) -> Any:
    try:
        return enum_type(str(value))
    except ValueError as exc:
        raise InboxSchemaError(
            [
                InboxSchemaIssue(
                    field=enum_type.__name__,
                    message=f"Unsupported value {str(value)!r}.",
                )
            ]
        ) from exc


def _require_text(issues: list[InboxSchemaIssue], field_name: str, value: str) -> None:
    if not value.strip():
        issues.append(
            InboxSchemaIssue(
                field=field_name,
                message="Required value is missing.",
            )
        )


def _optional_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)
