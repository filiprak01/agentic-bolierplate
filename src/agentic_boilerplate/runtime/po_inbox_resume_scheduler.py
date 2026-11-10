"""Resume Product Owner inbox blocked worker assignments."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Sequence
from typing import Any

from agentic_boilerplate.domain.agent_assignment import (
    AssignmentStatus,
    resume_assignment_after_po_inbox_answer,
)
from agentic_boilerplate.domain.po_inbox import InboxStatus
from agentic_boilerplate.storage.agent_assignment import FileAgentAssignmentStore
from agentic_boilerplate.storage.po_inbox import FilePOInboxStore, InboxItemNotFoundError


@dataclass(frozen=True)
class POInboxResumeRequest:
    """Machine-readable instruction emitted when an assignment can resume."""

    assignment_id: str
    jira_issue_key: str
    po_inbox_item_id: str
    inbox_status: str
    action: str
    original_stop_reason: str
    next_action: str


@dataclass(frozen=True)
class POInboxResumeSkip:
    """Reason a PO-paused assignment remains paused."""

    assignment_id: str
    jira_issue_key: str
    po_inbox_item_id: str
    reason: str
    next_action: str


@dataclass(frozen=True)
class POInboxResumeSchedulerResult:
    """Summary of a PO inbox resume pass."""

    resumed_assignment_ids: tuple[str, ...]
    skipped_assignment_ids: tuple[str, ...]
    resume_requests: tuple[POInboxResumeRequest, ...]
    skips: tuple[POInboxResumeSkip, ...]


RESUMABLE_PO_INBOX_STATUSES: frozenset[InboxStatus] = frozenset(
    {
        InboxStatus.ANSWERED,
        InboxStatus.APPROVED,
    }
)


def resume_po_inbox_blocked_assignments(
    *,
    assignment_store: FileAgentAssignmentStore,
    inbox_store: FilePOInboxStore,
    resumed_at: str,
    eligible_issue_keys: Sequence[str] = (),
) -> POInboxResumeSchedulerResult:
    """Requeue assignments whose PO inbox blocker is resolved and still eligible."""

    eligible = {issue_key.strip() for issue_key in eligible_issue_keys if issue_key.strip()}
    resumed_ids: list[str] = []
    skipped_ids: list[str] = []
    resume_requests: list[POInboxResumeRequest] = []
    skips: list[POInboxResumeSkip] = []

    for assignment in assignment_store.list_assignments():
        if assignment.status is not AssignmentStatus.PAUSED_PO:
            continue

        if not assignment.po_inbox_item_id:
            skipped_ids.append(assignment.id)
            skips.append(
                POInboxResumeSkip(
                    assignment_id=assignment.id,
                    jira_issue_key=assignment.jira_issue_key,
                    po_inbox_item_id="",
                    reason="missing_po_inbox_item_reference",
                    next_action="Repair assignment state before resume.",
                )
            )
            continue

        try:
            inbox_item = inbox_store.read(assignment.po_inbox_item_id)
        except InboxItemNotFoundError:
            skipped_ids.append(assignment.id)
            skips.append(
                POInboxResumeSkip(
                    assignment_id=assignment.id,
                    jira_issue_key=assignment.jira_issue_key,
                    po_inbox_item_id=assignment.po_inbox_item_id,
                    reason="po_inbox_item_not_found",
                    next_action="Restore the inbox item or create a replacement blocker before resume.",
                )
            )
            continue

        if inbox_item.status not in RESUMABLE_PO_INBOX_STATUSES:
            skipped_ids.append(assignment.id)
            skips.append(
                POInboxResumeSkip(
                    assignment_id=assignment.id,
                    jira_issue_key=assignment.jira_issue_key,
                    po_inbox_item_id=assignment.po_inbox_item_id,
                    reason=f"po_inbox_item_{inbox_item.status.value}",
                    next_action=_next_action_for_inbox_status(inbox_item.status),
                )
            )
            continue

        if eligible and assignment.jira_issue_key not in eligible:
            skipped_ids.append(assignment.id)
            skips.append(
                POInboxResumeSkip(
                    assignment_id=assignment.id,
                    jira_issue_key=assignment.jira_issue_key,
                    po_inbox_item_id=assignment.po_inbox_item_id,
                    reason="normal_gates_not_eligible",
                    next_action="Re-check Jira status, dependencies, design gate, and limit gate before resume.",
                )
            )
            continue

        assignment_store.save_assignment(
            resume_assignment_after_po_inbox_answer(assignment, updated_at=resumed_at)
        )
        resumed_ids.append(assignment.id)
        resume_requests.append(
            POInboxResumeRequest(
                assignment_id=assignment.id,
                jira_issue_key=assignment.jira_issue_key,
                po_inbox_item_id=assignment.po_inbox_item_id,
                inbox_status=inbox_item.status.value,
                action="po_resume_instruction",
                original_stop_reason=assignment.pause_reason,
                next_action="Resume assignment from queued state with original context pack and PO answer available.",
            )
        )

    return POInboxResumeSchedulerResult(
        resumed_assignment_ids=tuple(resumed_ids),
        skipped_assignment_ids=tuple(skipped_ids),
        resume_requests=tuple(resume_requests),
        skips=tuple(skips),
    )


def po_inbox_resume_scheduler_result_to_dict(result: POInboxResumeSchedulerResult) -> dict[str, Any]:
    """Convert a PO inbox resume result into JSON-compatible output."""

    return {
        "resumed_assignment_ids": list(result.resumed_assignment_ids),
        "skipped_assignment_ids": list(result.skipped_assignment_ids),
        "resume_requests": [
            {
                "assignment_id": request.assignment_id,
                "jira_issue_key": request.jira_issue_key,
                "po_inbox_item_id": request.po_inbox_item_id,
                "inbox_status": request.inbox_status,
                "action": request.action,
                "original_stop_reason": request.original_stop_reason,
                "next_action": request.next_action,
            }
            for request in result.resume_requests
        ],
        "skips": [
            {
                "assignment_id": skip.assignment_id,
                "jira_issue_key": skip.jira_issue_key,
                "po_inbox_item_id": skip.po_inbox_item_id,
                "reason": skip.reason,
                "next_action": skip.next_action,
            }
            for skip in result.skips
        ],
    }


def _next_action_for_inbox_status(status: InboxStatus) -> str:
    if status is InboxStatus.OPEN:
        return "Wait for the Product Owner to answer or approve the inbox item."
    if status is InboxStatus.REJECTED:
        return "Create Product Planning or Architecture follow-up instead of resuming changed scope silently."
    return "Inspect the inbox item state before resuming."
