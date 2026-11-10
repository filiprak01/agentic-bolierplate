"""Retention, redaction, and export policy for PO and agent messages."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
import re
from typing import Any


class MessageRecordCategory(str, Enum):
    """Record categories covered by the message export policy."""

    PO_INBOX_ITEM = "po_inbox_item"
    AGENT_MESSAGE = "agent_message"
    ASSIGNMENT_LOG = "assignment_log"
    ORCHESTRATION_EVENT = "orchestration_event"
    EXPORTED_JSON = "exported_json"


class MessagePublicationChannel(str, Enum):
    """Allowed publication or sharing channels for message records."""

    LOCAL_DURABLE = "local_durable"
    JIRA_COMMENT = "jira_comment"
    CONFLUENCE_SUMMARY = "confluence_summary"
    JSON_EXPORT = "json_export"
    OPERATOR_UI = "operator_ui"


class MessageRetentionAction(str, Enum):
    """Default retention behavior for message lifecycle states."""

    KEEP_ACTIVE = "keep_active"
    ARCHIVE_TERMINAL = "archive_terminal"
    REVIEW_STALE = "review_stale"
    KEEP_LOCAL_ONLY = "keep_local_only"


class MessageSensitivityKind(str, Enum):
    """Kinds of sensitive data that must not leave the local boundary raw."""

    SECRET_FIELD = "secret_field"
    SECRET_VALUE = "secret_value"
    DATABASE_URL = "database_url"
    UNSAFE_ABSOLUTE_PATH = "unsafe_absolute_path"
    PROJECT_IDENTITY_MISMATCH = "project_identity_mismatch"
    MISSING_PROJECT_IDENTITY = "missing_project_identity"


class MessageExportPolicyError(ValueError):
    """Raised when message export policy input is invalid."""


@dataclass(frozen=True)
class MessageSensitivityFinding:
    """One sensitivity finding found in a message export payload."""

    path: str
    kind: MessageSensitivityKind
    message: str


@dataclass(frozen=True)
class MessageExportPolicyDecision:
    """Export or publication decision for one message payload."""

    allowed: bool
    requires_warning: bool
    channels: tuple[MessagePublicationChannel, ...]
    retention_action: MessageRetentionAction
    findings: tuple[MessageSensitivityFinding, ...] = ()


SECRET_FIELD_MARKERS: tuple[str, ...] = (
    "api_key",
    "apikey",
    "auth_header",
    "auth_token",
    "authorization",
    "credential",
    "database_url",
    "db_url",
    "github_token",
    "jira_api_token",
    "oauth",
    "password",
    "private_key",
    "secret",
    "ssh_key",
    "token",
)

SECRET_VALUE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\b[A-Za-z0-9._%+-]+:[A-Za-z0-9._~+/=-]{8,}@"),
)

DATABASE_URL_PATTERN = re.compile(
    r"\b(?:postgresql|postgres|mysql|mariadb|mongodb|redis)://[^\s\"']+",
    re.IGNORECASE,
)
WINDOWS_ABSOLUTE_PATH_PATTERN = re.compile(r"\b[A-Za-z]:\\(?:Users|ProgramData|Windows)\\[^\s\"']+")
WSL_ABSOLUTE_PATH_PATTERN = re.compile(r"(?<![\w.-])/(?:home|mnt|root|etc)/[^\s\"']+")
UNC_PATH_PATTERN = re.compile(r"\\\\[^\s\"']+")

REDACTED_VALUE = "[redacted]"
REDACTED_PATH = "[local-path-redacted]"


def retention_action_for_message_status(status: str) -> MessageRetentionAction:
    """Return the default retention action for a PO or agent message status."""

    normalized = _require_text("status", status).lower().replace(" ", "_").replace("/", "_")
    if normalized in {"open", "queued", "processing", "in_progress"}:
        return MessageRetentionAction.KEEP_ACTIVE
    if normalized in {
        "answered",
        "approved",
        "rejected",
        "archived",
        "processed",
        "done",
        "test_completed",
        "accepted_done",
    }:
        return MessageRetentionAction.ARCHIVE_TERMINAL
    if normalized in {"stale", "obsolete", "expired"}:
        return MessageRetentionAction.REVIEW_STALE
    return MessageRetentionAction.KEEP_LOCAL_ONLY


def default_channels_for_message_category(
    category: MessageRecordCategory,
) -> tuple[MessagePublicationChannel, ...]:
    """Return default allowed channels for a message record category."""

    if category is MessageRecordCategory.PO_INBOX_ITEM:
        return (
            MessagePublicationChannel.LOCAL_DURABLE,
            MessagePublicationChannel.OPERATOR_UI,
            MessagePublicationChannel.JSON_EXPORT,
        )
    if category is MessageRecordCategory.AGENT_MESSAGE:
        return (
            MessagePublicationChannel.LOCAL_DURABLE,
            MessagePublicationChannel.OPERATOR_UI,
            MessagePublicationChannel.JSON_EXPORT,
        )
    if category is MessageRecordCategory.ASSIGNMENT_LOG:
        return (
            MessagePublicationChannel.LOCAL_DURABLE,
            MessagePublicationChannel.JIRA_COMMENT,
        )
    if category is MessageRecordCategory.ORCHESTRATION_EVENT:
        return (
            MessagePublicationChannel.LOCAL_DURABLE,
            MessagePublicationChannel.OPERATOR_UI,
        )
    if category is MessageRecordCategory.EXPORTED_JSON:
        return (
            MessagePublicationChannel.LOCAL_DURABLE,
            MessagePublicationChannel.JSON_EXPORT,
        )
    raise MessageExportPolicyError(f"Unsupported message record category: {category!r}")


def evaluate_message_export_policy(
    *,
    payload: Mapping[str, Any],
    category: MessageRecordCategory,
    status: str,
    active_project_id: str,
    allowed_project_ids: Sequence[str] = (),
    requested_channels: Sequence[MessagePublicationChannel] | None = None,
) -> MessageExportPolicyDecision:
    """Evaluate whether a message payload may be exported or published raw."""

    if not isinstance(category, MessageRecordCategory):
        raise MessageExportPolicyError("category must be MessageRecordCategory")
    active_project_id = _require_text("active_project_id", active_project_id)
    channels = (
        tuple(requested_channels)
        if requested_channels is not None
        else default_channels_for_message_category(category)
    )
    for channel in channels:
        if not isinstance(channel, MessagePublicationChannel):
            raise MessageExportPolicyError("requested_channels must contain MessagePublicationChannel values")

    findings = find_message_export_sensitivity(
        payload=payload,
        active_project_id=active_project_id,
        allowed_project_ids=allowed_project_ids,
    )
    return MessageExportPolicyDecision(
        allowed=not findings,
        requires_warning=bool(findings) or MessagePublicationChannel.JSON_EXPORT in channels,
        channels=channels,
        retention_action=retention_action_for_message_status(status),
        findings=findings,
    )


def find_message_export_sensitivity(
    *,
    payload: Mapping[str, Any],
    active_project_id: str,
    allowed_project_ids: Sequence[str] = (),
) -> tuple[MessageSensitivityFinding, ...]:
    """Find sensitive fields, values, paths, and project-context mistakes."""

    if not isinstance(payload, Mapping):
        raise MessageExportPolicyError("payload must be a mapping")
    active_project_id = _require_text("active_project_id", active_project_id)
    allowed_projects = {project.strip() for project in allowed_project_ids if project and project.strip()}
    allowed_projects.add(active_project_id)
    findings: list[MessageSensitivityFinding] = []
    _scan_value(payload, "$", findings)
    findings.extend(_project_identity_findings(payload, allowed_projects))
    return tuple(findings)


def redact_message_export_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return a JSON-compatible payload with secret-like values redacted."""

    if not isinstance(payload, Mapping):
        raise MessageExportPolicyError("payload must be a mapping")
    return _redact_mapping(payload)


def format_message_export_policy_findings(findings: Sequence[MessageSensitivityFinding]) -> str:
    """Format policy findings without leaking the sensitive value."""

    if not findings:
        return "No message export policy findings."
    return "\n".join(f"- {finding.path}: {finding.kind.value} - {finding.message}" for finding in findings)


def _scan_value(value: Any, path: str, findings: list[MessageSensitivityFinding]) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            child_path = f"{path}.{key}"
            if _is_secret_field(str(key)):
                findings.append(
                    MessageSensitivityFinding(
                        path=child_path,
                        kind=MessageSensitivityKind.SECRET_FIELD,
                        message="Field name is forbidden in exported message data.",
                    )
                )
            _scan_value(nested, child_path, findings)
        return
    if isinstance(value, (list, tuple)):
        for index, nested in enumerate(value):
            _scan_value(nested, f"{path}[{index}]", findings)
        return
    if isinstance(value, str):
        if DATABASE_URL_PATTERN.search(value):
            findings.append(
                MessageSensitivityFinding(
                    path=path,
                    kind=MessageSensitivityKind.DATABASE_URL,
                    message="Database connection URLs must be redacted before export.",
                )
            )
        if any(pattern.search(value) for pattern in SECRET_VALUE_PATTERNS):
            findings.append(
                MessageSensitivityFinding(
                    path=path,
                    kind=MessageSensitivityKind.SECRET_VALUE,
                    message="Secret-like raw values must be redacted before export.",
                )
            )
        if _has_unsafe_absolute_path(value):
            findings.append(
                MessageSensitivityFinding(
                    path=path,
                    kind=MessageSensitivityKind.UNSAFE_ABSOLUTE_PATH,
                    message="Raw local absolute paths must not be exported.",
                )
            )


def _project_identity_findings(
    payload: Mapping[str, Any],
    allowed_project_ids: set[str],
) -> tuple[MessageSensitivityFinding, ...]:
    project_id = payload.get("project_id") or payload.get("project_key") or payload.get("project")
    if not isinstance(project_id, str) or not project_id.strip():
        return (
            MessageSensitivityFinding(
                path="$.project_id",
                kind=MessageSensitivityKind.MISSING_PROJECT_IDENTITY,
                message="Multi-project message exports require explicit project identity.",
            ),
        )
    if project_id.strip() not in allowed_project_ids:
        return (
            MessageSensitivityFinding(
                path="$.project_id",
                kind=MessageSensitivityKind.PROJECT_IDENTITY_MISMATCH,
                message="Payload project identity is outside the active export scope.",
            ),
        )
    return ()


def _redact_mapping(payload: Mapping[str, Any]) -> dict[str, Any]:
    redacted: dict[str, Any] = {}
    for key, value in payload.items():
        if _is_secret_field(str(key)):
            redacted[str(key)] = REDACTED_VALUE
        else:
            redacted[str(key)] = _redact_value(value)
    return redacted


def _redact_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _redact_mapping(value)
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    if isinstance(value, tuple):
        return [_redact_value(item) for item in value]
    if isinstance(value, str):
        value = DATABASE_URL_PATTERN.sub(REDACTED_VALUE, value)
        for pattern in SECRET_VALUE_PATTERNS:
            value = pattern.sub(REDACTED_VALUE, value)
        value = WINDOWS_ABSOLUTE_PATH_PATTERN.sub(REDACTED_PATH, value)
        value = WSL_ABSOLUTE_PATH_PATTERN.sub(REDACTED_PATH, value)
        value = UNC_PATH_PATTERN.sub(REDACTED_PATH, value)
    return value


def _is_secret_field(field_name: str) -> bool:
    normalized = field_name.lower().replace("-", "_")
    return any(marker in normalized for marker in SECRET_FIELD_MARKERS)


def _has_unsafe_absolute_path(value: str) -> bool:
    return any(
        pattern.search(value)
        for pattern in (
            WINDOWS_ABSOLUTE_PATH_PATTERN,
            WSL_ABSOLUTE_PATH_PATTERN,
            UNC_PATH_PATTERN,
        )
    )


def _require_text(field: str, value: str) -> str:
    if not value or not value.strip():
        raise MessageExportPolicyError(f"{field} is required.")
    return value.strip()
