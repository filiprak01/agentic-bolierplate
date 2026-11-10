"""Worker assignment status summaries for operators and UI shells."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from agentic_boilerplate.domain.agent_assignment import AgentAssignment, AssignmentStatus
from agentic_boilerplate.domain.test_evidence_artifact import redact_evidence_text


class AssignmentStatusCategory:
    """Operator-facing assignment status groups."""

    PAUSED = "paused"
    BLOCKED = "blocked"


_SECRET_TEXT_HINTS = ("token", "secret", "password", "authorization", "api_key", "apikey")


@dataclass(frozen=True)
class AssignmentStatusItem:
    """Redacted status row for a paused or blocked worker assignment."""

    assignment_id: str
    jira_issue_key: str
    role: str
    status: str
    category: str
    reason: str
    recommended_next_action: str
    project_id: str = ""
    project_name: str = ""
    project_root: str = ""
    repository: str = ""
    jira_project_key: str = ""
    worker_id: str = ""
    branch_name: str = ""
    codex_job_id: str = ""
    po_inbox_item_id: str = ""
    attempt_count: int = 0


def build_assignment_status_items(assignments: tuple[AgentAssignment, ...]) -> tuple[AssignmentStatusItem, ...]:
    """Return paused and blocked assignment summaries sorted for stable operator output."""

    items = tuple(
        item
        for item in (build_assignment_status_item(assignment) for assignment in assignments)
        if item is not None
    )
    return tuple(sorted(items, key=lambda item: (item.category, item.jira_issue_key, item.assignment_id)))


def build_assignment_status_item(assignment: AgentAssignment) -> AssignmentStatusItem | None:
    """Return a redacted status item when the assignment needs operator or agent action."""

    if assignment.status == AssignmentStatus.PAUSED_LIMIT:
        category = AssignmentStatusCategory.PAUSED
        reason = assignment.pause_reason
    elif assignment.status == AssignmentStatus.PAUSED_PO:
        category = AssignmentStatusCategory.BLOCKED
        reason = f"blocked-by-PO-inbox: {assignment.pause_reason}"
    elif assignment.status == AssignmentStatus.FAILED:
        category = AssignmentStatusCategory.BLOCKED
        reason = assignment.failure_reason
    else:
        return None

    reason = _redact_status_text(reason)
    return AssignmentStatusItem(
        assignment_id=_redact_status_text(assignment.id),
        jira_issue_key=_redact_status_text(assignment.jira_issue_key),
        role=assignment.role.value,
        status=assignment.status.value,
        category=category,
        reason=reason,
        recommended_next_action=recommended_next_action(category=category, reason=reason),
        project_id=_redact_status_text(assignment.project_id),
        project_name=_redact_status_text(assignment.project_name),
        project_root=_redact_status_text(assignment.project_root),
        repository=_redact_status_text(assignment.repository),
        jira_project_key=_redact_status_text(assignment.jira_project_key),
        worker_id=_redact_status_text(assignment.worker_id),
        branch_name=_redact_status_text(assignment.branch_name),
        codex_job_id=_redact_status_text(assignment.codex_job_id),
        po_inbox_item_id=_redact_status_text(assignment.po_inbox_item_id),
        attempt_count=assignment.attempt_count,
    )


def assignment_status_item_to_dict(item: AssignmentStatusItem) -> dict[str, Any]:
    """Convert a status item into the future UI/API compatible payload."""

    return {
        "assignment_id": item.assignment_id,
        "jira_issue_key": item.jira_issue_key,
        "role": item.role,
        "status": item.status,
        "category": item.category,
        "reason": item.reason,
        "recommended_next_action": item.recommended_next_action,
        "project_id": item.project_id,
        "project_name": item.project_name,
        "project_root": item.project_root,
        "repository": item.repository,
        "jira_project_key": item.jira_project_key,
        "worker_id": item.worker_id,
        "branch_name": item.branch_name,
        "codex_job_id": item.codex_job_id,
        "po_inbox_item_id": item.po_inbox_item_id,
        "attempt_count": item.attempt_count,
    }


def recommended_next_action(*, category: str, reason: str) -> str:
    """Return a deterministic next action for common blocked and paused causes."""

    normalized_reason = reason.casefold()
    if category == AssignmentStatusCategory.PAUSED:
        return "Record updated Codex limit availability, then rerun or resume the worker assignment."
    if "dependency" in normalized_reason or "blocked by" in normalized_reason:
        return "Finish or unblock the prerequisite Jira issue, then rerun assignment eligibility."
    if "question" in normalized_reason or "po inbox" in normalized_reason or "po-inbox" in normalized_reason:
        return "Answer the durable PO inbox question, then rerun the worker assignment."
    if re.search(r"\block\b", normalized_reason):
        return "Inspect the lock owner and release stale locks only after the owner is inactive."
    return "Inspect the failure evidence, fix the blocker, then rerun the worker assignment."


def _redact_status_text(value: str) -> str:
    text = redact_evidence_text(str(value))
    if text != value:
        return "[redacted]"
    if any(hint in text.casefold() for hint in _SECRET_TEXT_HINTS):
        return "[redacted]"
    return re.sub(r"(?i)(bearer|basic)\s+[A-Za-z0-9._~+/=-]+", r"\1 [redacted]", text)
