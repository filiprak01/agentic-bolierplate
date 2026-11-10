"""Product Owner approval gate for Jira backlog creation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from agentic_boilerplate.domain.backlog_draft import BacklogDraft
from agentic_boilerplate.domain.jira_creation_workflow import ApprovedBacklogDraft
from agentic_boilerplate.domain.po_inbox import (
    AgentRole,
    InboxMessageType,
    InboxOption,
    InboxStatus,
    POInboxItem,
    require_valid_inbox_item,
)


class BacklogApprovalGateStatus(str, Enum):
    """PO approval gate outcome."""

    MISSING = "missing"
    WAITING = "waiting"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass(frozen=True)
class BacklogApprovalGateDecision:
    """Decision used before creating Jira issues from a draft."""

    status: BacklogApprovalGateStatus
    can_create_jira: bool
    reason: str
    approved_draft: ApprovedBacklogDraft | None = None


def build_backlog_creation_approval_request(
    draft: BacklogDraft,
    *,
    created_at: str,
    jira_issue_key: str = "",
    agent_id: str = "product-planning-agent",
    project_id: str = "",
    project_name: str = "",
    project_root: str = "",
    repository: str = "",
    jira_project_key: str = "",
    context_pack_path: str = "",
) -> POInboxItem:
    """Create a durable approval request before Jira issue creation."""

    story_count = sum(len(epic.stories) for epic in draft.epics)
    dependency_count = sum(len(story.dependencies) for epic in draft.epics for story in epic.stories)
    sprint_count = len(draft.sprint_rings)
    message = "\n".join(
        (
            f"Approve Jira backlog creation for draft `{draft.key}`.",
            f"Title: {draft.title}",
            f"Epics: {len(draft.epics)}",
            f"Stories: {story_count}",
            f"Dependencies: {dependency_count}",
            f"Sprint rings: {sprint_count}",
            "Approval permits Product Planning to create Jira issues in Funnel from this draft.",
            "Rejecting or requesting changes blocks Jira creation until the draft is regenerated and reapproved.",
        )
    )
    return require_valid_inbox_item(
        POInboxItem(
            id=f"{draft.key}-jira-creation-approval",
            message_type=InboxMessageType.APPROVAL_REQUEST,
            status=InboxStatus.OPEN,
            title=f"Approve Jira backlog creation for {draft.key}",
            message=message,
            agent_role=AgentRole.PRODUCT_PLANNING,
            created_at=created_at,
            agent_id=agent_id,
            jira_issue_key=jira_issue_key,
            project_id=project_id,
            project_name=project_name,
            project_root=project_root,
            repository=repository,
            jira_project_key=jira_project_key,
            context_pack_path=context_pack_path,
            business_impact="Unapproved drafts may create incorrect Jira scope, dependencies, or sprint slices.",
            recommendation="Approve only after reviewing the draft, context references, dependencies, and sprint proposal.",
            options=(
                InboxOption(
                    id="approve_create_in_funnel",
                    label="Approve",
                    description="Create all generated Jira issues in Funnel from this draft.",
                ),
                InboxOption(
                    id="reject_changes_needed",
                    label="Reject",
                    description="Do not create Jira issues; regenerate or revise the draft.",
                ),
            ),
        )
    )


def evaluate_backlog_creation_approval_gate(
    draft: BacklogDraft,
    approval_item: POInboxItem | None,
) -> BacklogApprovalGateDecision:
    """Decide whether Jira creation may run for a draft."""

    if approval_item is None:
        return BacklogApprovalGateDecision(
            status=BacklogApprovalGateStatus.MISSING,
            can_create_jira=False,
            reason="No Product Owner approval request exists for this backlog draft.",
        )
    if approval_item.message_type is not InboxMessageType.APPROVAL_REQUEST:
        return BacklogApprovalGateDecision(
            status=BacklogApprovalGateStatus.MISSING,
            can_create_jira=False,
            reason="The referenced PO inbox item is not an approval request.",
        )
    if approval_item.status is InboxStatus.APPROVED:
        return BacklogApprovalGateDecision(
            status=BacklogApprovalGateStatus.APPROVED,
            can_create_jira=True,
            reason="Product Owner approved Jira creation for the generated backlog draft.",
            approved_draft=ApprovedBacklogDraft(
                draft=draft,
                approved_by=approval_item.answer or "Product Owner",
                approved_at=approval_item.answered_at,
            ),
        )
    if approval_item.status is InboxStatus.REJECTED:
        return BacklogApprovalGateDecision(
            status=BacklogApprovalGateStatus.REJECTED,
            can_create_jira=False,
            reason="Product Owner rejected Jira creation for this draft.",
        )
    return BacklogApprovalGateDecision(
        status=BacklogApprovalGateStatus.WAITING,
        can_create_jira=False,
        reason="Product Owner approval is still open; Jira creation must wait.",
    )


def backlog_approval_gate_decision_to_dict(decision: BacklogApprovalGateDecision) -> dict[str, object]:
    """Convert the approval decision into JSON-compatible data."""

    return {
        "status": decision.status.value,
        "can_create_jira": decision.can_create_jira,
        "reason": decision.reason,
        "approved_by": decision.approved_draft.approved_by if decision.approved_draft else "",
        "approved_at": decision.approved_draft.approved_at if decision.approved_draft else "",
    }
