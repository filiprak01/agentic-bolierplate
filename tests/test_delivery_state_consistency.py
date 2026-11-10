from datetime import datetime, timezone

import pytest

from agentic_boilerplate.domain import (
    DeliveryStateConsistencyError,
    DeliveryStateConsistencyFindingType,
    DeliveryWorkItemState,
    PullRequestState,
    ReviewApprovalState,
    evaluate_delivery_state_consistency,
    render_delivery_state_consistency_jira_comment,
    render_delivery_state_consistency_report,
)
from agentic_boilerplate.storage import write_delivery_state_consistency_report


def test_blocks_accepted_story_before_merge_and_po_batch_acceptance() -> None:
    report = evaluate_delivery_state_consistency(
        sprint_name="MVP S11 Process Hardening",
        closure_issue_key="AGENT-245",
        work_items=(
            DeliveryWorkItemState(
                issue_key="AGENT-100",
                summary="Accepted too early",
                issue_type="Story",
                jira_status="Accepted/Done",
                pull_request_state=PullRequestState.OPEN,
                pull_request_url="https://github.example/pull/100",
                review_state=ReviewApprovalState.PENDING,
                tester_validation_passed=False,
                test_evidence_paths=(),
                po_batch_accepted=False,
            ),
        ),
    )

    finding_types = {finding.finding_type for finding in report.findings}

    assert not report.allowed_to_close
    assert DeliveryStateConsistencyFindingType.ACCEPTED_BEFORE_MERGE in finding_types
    assert DeliveryStateConsistencyFindingType.ACCEPTED_WITHOUT_REVIEW_APPROVAL in finding_types
    assert DeliveryStateConsistencyFindingType.ACCEPTED_WITHOUT_TEST_COMPLETION in finding_types
    assert DeliveryStateConsistencyFindingType.ACCEPTED_WITHOUT_TEST_EVIDENCE in finding_types
    assert DeliveryStateConsistencyFindingType.ACCEPTED_WITHOUT_PO_BATCH_ACCEPTANCE in finding_types


def test_blocks_test_completed_without_evidence() -> None:
    report = evaluate_delivery_state_consistency(
        sprint_name="MVP S11 Process Hardening",
        work_items=(
            DeliveryWorkItemState(
                issue_key="AGENT-101",
                summary="Missing evidence",
                issue_type="Story",
                jira_status="TEST COMPLETED",
                pull_request_state=PullRequestState.MERGED,
                review_state=ReviewApprovalState.APPROVED,
                tester_validation_passed=True,
                test_evidence_paths=(),
            ),
        ),
    )

    assert tuple(finding.finding_type for finding in report.findings) == (
        DeliveryStateConsistencyFindingType.TEST_COMPLETED_WITHOUT_EVIDENCE,
    )
    assert report.findings[0].missing_evidence == ("test evidence path",)


def test_blocks_merged_story_that_still_looks_ready_to_start() -> None:
    report = evaluate_delivery_state_consistency(
        sprint_name="MVP S11 Process Hardening",
        work_items=(
            DeliveryWorkItemState(
                issue_key="AGENT-102",
                summary="Merged but ready",
                issue_type="Story",
                jira_status="Ready to start",
                pull_request_state=PullRequestState.MERGED,
                pull_request_url="https://github.example/pull/102",
                review_state=ReviewApprovalState.APPROVED,
            ),
        ),
    )

    assert tuple(finding.finding_type for finding in report.findings) == (
        DeliveryStateConsistencyFindingType.MERGED_BUT_JIRA_NOT_ADVANCED,
    )
    assert report.findings[0].recommended_transition == "DEV COMPLETED"


def test_allows_merged_story_waiting_for_tester_in_dev_completed() -> None:
    report = evaluate_delivery_state_consistency(
        sprint_name="MVP S11 Process Hardening",
        work_items=(
            DeliveryWorkItemState(
                issue_key="AGENT-102",
                summary="Merged and waiting for tester",
                issue_type="Story",
                jira_status="DEV COMPLETED",
                pull_request_state=PullRequestState.MERGED,
                pull_request_url="https://github.example/pull/102",
                review_state=ReviewApprovalState.APPROVED,
            ),
        ),
    )

    assert report.allowed_to_close
    assert report.ready_issue_keys == ("AGENT-102",)


def test_allows_clean_completed_story_with_po_acceptance() -> None:
    report = evaluate_delivery_state_consistency(
        sprint_name="MVP S11 Process Hardening",
        work_items=(
            DeliveryWorkItemState(
                issue_key="AGENT-103",
                summary="Clean acceptance",
                issue_type="Story",
                jira_status="Accepted/Done",
                pull_request_state=PullRequestState.MERGED,
                pull_request_url="https://github.example/pull/103",
                review_state=ReviewApprovalState.APPROVED,
                tester_validation_passed=True,
                test_evidence_paths=("data/agent-logs/AGENT-103/test-evidence.md",),
                po_batch_accepted=True,
            ),
        ),
    )

    assert report.allowed_to_close
    assert report.ready_issue_keys == ("AGENT-103",)
    assert report.findings == ()


def test_unapproved_documented_blocker_does_not_suppress_mismatch() -> None:
    report = evaluate_delivery_state_consistency(
        sprint_name="MVP S11 Process Hardening",
        work_items=(
            DeliveryWorkItemState(
                issue_key="AGENT-104",
                summary="Documented follow-up",
                issue_type="Story",
                jira_status="Ready to start",
                pull_request_state=PullRequestState.MERGED,
                review_state=ReviewApprovalState.APPROVED,
                documented_blocker="Waiting for manual Jira transition after migration import.",
            ),
        ),
    )

    assert tuple(finding.finding_type for finding in report.findings) == (
        DeliveryStateConsistencyFindingType.MERGED_BUT_JIRA_NOT_ADVANCED,
    )


def test_approved_documented_blocker_suppresses_mismatch_until_followup_is_resolved() -> None:
    report = evaluate_delivery_state_consistency(
        sprint_name="MVP S11 Process Hardening",
        work_items=(
            DeliveryWorkItemState(
                issue_key="AGENT-104",
                summary="Documented follow-up",
                issue_type="Story",
                jira_status="Ready to start",
                pull_request_state=PullRequestState.MERGED,
                review_state=ReviewApprovalState.APPROVED,
                documented_blocker="Waiting for manual Jira transition after migration import.",
                documented_blocker_approved=True,
            ),
        ),
    )

    assert report.allowed_to_close
    assert report.ready_issue_keys == ("AGENT-104",)


def test_renders_markdown_and_jira_comment_for_blockers() -> None:
    report = evaluate_delivery_state_consistency(
        sprint_name="MVP S11 Process Hardening",
        closure_issue_key="AGENT-245",
        work_items=(
            DeliveryWorkItemState(
                issue_key="AGENT-105",
                summary="Merged but ready",
                issue_type="Story",
                jira_status="Ready to start",
                pull_request_state=PullRequestState.MERGED,
                review_state=ReviewApprovalState.APPROVED,
            ),
        ),
    )

    markdown = render_delivery_state_consistency_report(report)
    comment = render_delivery_state_consistency_jira_comment(report)

    assert "# Delivery State Consistency - MVP S11 Process Hardening" in markdown
    assert "merged-but-jira-not-advanced" in markdown
    assert "blocked closure" in comment
    assert "AGENT-105" in comment


def test_writes_durable_markdown_report(tmp_path) -> None:
    report = evaluate_delivery_state_consistency(
        sprint_name="MVP S11 Process Hardening",
        work_items=(
            DeliveryWorkItemState(
                issue_key="AGENT-106",
                summary="Clean",
                issue_type="Story",
                jira_status="TEST COMPLETED",
                pull_request_state=PullRequestState.MERGED,
                review_state=ReviewApprovalState.APPROVED,
                tester_validation_passed=True,
                test_evidence_paths=("data/agent-logs/AGENT-106/test-evidence.md",),
            ),
        ),
    )

    path = write_delivery_state_consistency_report(
        report,
        tmp_path,
        created_at=datetime(2026, 7, 6, 12, 30, tzinfo=timezone.utc),
    )

    assert path.name == "delivery-state-consistency-mvp-s11-process-hardening-20260706T123000Z.md"
    assert "Allowed to close: yes" in path.read_text(encoding="utf-8")


def test_requires_sprint_name_and_issue_core_fields() -> None:
    with pytest.raises(DeliveryStateConsistencyError, match="sprint_name is required"):
        evaluate_delivery_state_consistency(sprint_name="", work_items=())

    with pytest.raises(DeliveryStateConsistencyError, match="issue_key is required"):
        evaluate_delivery_state_consistency(
            sprint_name="Sprint",
            work_items=(
                DeliveryWorkItemState(
                    issue_key="",
                    summary="Broken",
                    issue_type="Story",
                    jira_status="Ready to start",
                    pull_request_state=PullRequestState.MISSING,
                ),
            ),
        )
