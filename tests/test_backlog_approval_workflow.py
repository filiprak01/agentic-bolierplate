from dataclasses import replace

from agentic_boilerplate import domain
from agentic_boilerplate.domain import (
    BacklogApprovalGateStatus,
    InboxStatus,
    RequirementEpicInput,
    RequirementInput,
    RequirementStoryInput,
    build_backlog_creation_approval_request,
    create_backlog_draft,
    evaluate_backlog_creation_approval_gate,
)
from agentic_boilerplate.domain.story_complexity import ComplexityLevel


def test_backlog_creation_approval_request_summarizes_draft_for_po() -> None:
    draft = _draft()

    item = build_backlog_creation_approval_request(
        draft,
        created_at="2026-08-10T12:00:00Z",
        jira_issue_key="AGENT-642",
        project_id="ap",
    )

    assert item.id == "REQ-APPROVAL-jira-creation-approval"
    assert item.message_type.value == "approval_request"
    assert item.status is InboxStatus.OPEN
    assert item.project_id == "ap"
    assert "Stories: 1" in item.message
    assert item.business_impact
    assert item.recommendation


def test_backlog_approval_gate_blocks_until_approved_and_blocks_rejected() -> None:
    draft = _draft()
    open_item = build_backlog_creation_approval_request(draft, created_at="2026-08-10T12:00:00Z")

    missing = evaluate_backlog_creation_approval_gate(draft, None)
    waiting = evaluate_backlog_creation_approval_gate(draft, open_item)
    rejected = evaluate_backlog_creation_approval_gate(
        draft,
        replace(open_item, status=InboxStatus.REJECTED, answer="Needs changes", answered_at="2026-08-10T12:05:00Z"),
    )
    approved = evaluate_backlog_creation_approval_gate(
        draft,
        replace(open_item, status=InboxStatus.APPROVED, answer="Product Owner", answered_at="2026-08-10T12:10:00Z"),
    )

    assert missing.status is BacklogApprovalGateStatus.MISSING
    assert waiting.status is BacklogApprovalGateStatus.WAITING
    assert rejected.status is BacklogApprovalGateStatus.REJECTED
    assert approved.status is BacklogApprovalGateStatus.APPROVED
    assert approved.can_create_jira is True
    assert approved.approved_draft is not None
    assert approved.approved_draft.approved_by == "Product Owner"
    assert approved.approved_draft.approved_at == "2026-08-10T12:10:00Z"


def test_backlog_approval_public_api_exports_are_available() -> None:
    assert domain.BacklogApprovalGateStatus is BacklogApprovalGateStatus
    assert domain.build_backlog_creation_approval_request is build_backlog_creation_approval_request
    assert domain.evaluate_backlog_creation_approval_gate is evaluate_backlog_creation_approval_gate


def _draft():
    return create_backlog_draft(
        RequirementInput(
            key="REQ-APPROVAL",
            title="Approval workflow",
            overview="Approve draft before Jira creation.",
            epics=(
                RequirementEpicInput(
                    id="EPIC-APPROVAL",
                    title="Approval",
                    description="Approval epic.",
                    stories=(
                        RequirementStoryInput(
                            id="STORY-APPROVAL",
                            title="Create approved Jira story",
                            description="Create only after PO approval.",
                            acceptance_criteria=("Approval is required.",),
                            prerequisite_story_ids=(),
                            complexity=ComplexityLevel.C2,
                            complexity_rationale="Approval gate plus Jira planning.",
                        ),
                    ),
                ),
            ),
        ),
        created_at="2026-08-10T11:55:00Z",
    )
