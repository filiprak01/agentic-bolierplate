import pytest

from agentic_boilerplate.domain import (
    AgentMessageType,
    AgentRole,
    BUG_LINK_OUTWARD,
    BUG_LINK_TYPE,
    BUG_RELATED_LABEL,
    FAILED_TEST_STORY_STATUS,
    FailedTestBugSignature,
    FailedTestReworkHandoffPlan,
    HAS_LINKED_BUG_LABEL,
    RETEST_PASSED_STORY_STATUS,
    FailedTestReworkPlan,
    LinkedBugStatus,
    ManualTestExecutionResult,
    ManualTestResultStatus,
    ManualTestWorkflowError,
    RoleHandoffTriggerInput,
    StoryPathEvent,
    StoryPathRole,
    StoryReworkSnapshot,
    build_failed_test_rework_handoff_plan,
    build_failed_test_rework_plan,
    detect_rework_candidate,
    evaluate_retest_gate,
    failed_test_bug_signature,
    render_failed_test_handoff_comment,
    render_failed_test_rework_handoff_note,
    render_rework_assignment_note,
    select_failed_test_bug_key,
    select_rework_developer,
    unresolved_linked_bug_keys,
)


def test_failed_manual_test_creates_story_return_bug_link_and_rework_plan() -> None:
    plan = build_failed_test_rework_plan(
        _failed_result(),
        original_developer_agent="developer-agent-1",
        bug_key="AGENT-999",
    )

    assert isinstance(plan, FailedTestReworkPlan)
    assert plan.story_return.target_status == FAILED_TEST_STORY_STATUS
    assert plan.story_return.labels_to_add == (BUG_RELATED_LABEL, HAS_LINKED_BUG_LABEL)
    assert plan.linked_bug.bug.summary == "Failed manual test for AGENT-50"
    assert plan.linked_bug.link_type == BUG_LINK_TYPE
    assert plan.linked_bug.outward_relationship == BUG_LINK_OUTWARD
    assert plan.linked_bug.assignee_agent == "developer-agent-1"
    assert plan.rework_assignment.bug_keys == ("AGENT-999",)
    assert plan.rework_assignment.retest_required is True


def test_failed_test_rework_requires_failed_manual_result() -> None:
    result = ManualTestExecutionResult(
        story_key="AGENT-50",
        test_issue_key="AGENT-300",
        status=ManualTestResultStatus.PASSED,
        tester_role="tester",
        executed_at="2026-07-03T19:00:00Z",
        test_execution_key="AGENT-301",
    )

    with pytest.raises(ManualTestWorkflowError) as exc:
        build_failed_test_rework_plan(result)

    assert "status" in str(exc.value)


def test_rework_developer_prefers_original_then_fallback_then_scheduler() -> None:
    assert select_rework_developer(original_developer_agent="dev-a", fallback_developer_agent="dev-b") == (
        "dev-a",
        "original-developer-agent",
    )
    assert select_rework_developer(fallback_developer_agent="dev-b") == (
        "dev-b",
        "fallback-eligible-developer-agent",
    )
    assert select_rework_developer() == ("", "scheduler-assignment-required")


def test_failed_test_signature_reuses_existing_bug_for_same_failure() -> None:
    signature = failed_test_bug_signature(_failed_result())

    assert isinstance(signature, FailedTestBugSignature)
    assert signature.value == "agent-50:agent-300:bug link was missing."
    assert select_failed_test_bug_key(_failed_result(), {signature.value: "AGENT-999"}) == "AGENT-999"


def test_failed_test_rework_handoff_targets_developer_with_bug_fix_message() -> None:
    result = build_failed_test_rework_handoff_plan(
        _failed_result(),
        _handoff_input(),
        original_developer_agent="developer-agent-1",
        existing_bug_keys_by_signature={"agent-50:agent-300:bug link was missing.": "AGENT-999"},
        retest_scope="Retest AGENT-50 AC1 and linked Bug AGENT-999.",
    )

    assert isinstance(result, FailedTestReworkHandoffPlan)
    assert result.selected_bug_key == "AGENT-999"
    assert result.rework_plan.story_return.target_status == FAILED_TEST_STORY_STATUS
    assert result.rework_plan.story_return.labels_to_add == (BUG_RELATED_LABEL, HAS_LINKED_BUG_LABEL)
    assert result.handoff_decision.allowed is True
    assert result.handoff_message is not None
    assert result.handoff_message.message_type is AgentMessageType.BUG_FIX_REQUESTED
    assert result.handoff_message.source_role is AgentRole.TESTER
    assert result.handoff_message.target_role is AgentRole.DEVELOPER
    assert result.handoff_message.payload["selected_bug_key"] == "AGENT-999"
    assert result.handoff_message.payload["failed_test_signature"] == result.signature.value
    assert result.handoff_message.payload["artifacts"]["linked_bug"] == "AGENT-999"
    assert result.handoff_message.payload["artifacts"]["retest_scope"] == (
        "Retest AGENT-50 AC1 and linked Bug AGENT-999."
    )


def test_failed_test_rework_handoff_note_keeps_developer_pickup_visible() -> None:
    result = build_failed_test_rework_handoff_plan(
        _failed_result(),
        _handoff_input(),
        fallback_developer_agent="developer-agent-2",
        created_bug_key="AGENT-999",
    )

    note = render_failed_test_rework_handoff_note(result)

    assert "Failed-test Developer rework handoff for AGENT-50." in note
    assert "Failure signature: agent-50:agent-300:bug link was missing." in note
    assert "Selected Bug: AGENT-999" in note
    assert "Developer agent: developer-agent-2" in note
    assert "Message type: bug_fix_requested" in note


def test_detect_rework_candidate_for_dev_completed_story_with_unresolved_bug() -> None:
    decision = detect_rework_candidate(
        StoryReworkSnapshot(
            story_key="AGENT-50",
            story_status="Dev completed",
            labels=(BUG_RELATED_LABEL,),
            linked_bugs=(LinkedBugStatus("AGENT-999", "In Progress"),),
            failed_acceptance_criteria=("Bug link was missing.",),
            original_developer_agent="developer-agent-1",
        )
    )

    assert decision.is_candidate is True
    assert decision.unresolved_bug_keys == ("AGENT-999",)
    assert decision.assignment is not None
    assert decision.assignment.developer_agent == "developer-agent-1"
    assert decision.assignment.failed_acceptance_criteria == ("Bug link was missing.",)


def test_detect_rework_candidate_rejects_wrong_status_or_missing_marker() -> None:
    decision = detect_rework_candidate(
        StoryReworkSnapshot(
            story_key="AGENT-50",
            story_status="READY TO START",
            labels=(),
            linked_bugs=(LinkedBugStatus("AGENT-999", "In Progress"),),
        )
    )

    assert decision.is_candidate is False
    assert "Story status is READY TO START" in decision.reasons[0]
    assert any("bug-related marker" in reason for reason in decision.reasons)


def test_unresolved_linked_bug_keys_ignore_resolved_bugs() -> None:
    assert unresolved_linked_bug_keys(
        (
            LinkedBugStatus("AGENT-999", "In Progress"),
            LinkedBugStatus("AGENT-1000", "Resolved"),
            LinkedBugStatus("AGENT-1001", "ACCEPTED/DONE"),
        )
    ) == ("AGENT-999",)


def test_retest_gate_blocks_unresolved_and_not_retested_bugs() -> None:
    decision = evaluate_retest_gate(
        "AGENT-50",
        (
            LinkedBugStatus("AGENT-999", "In Progress"),
            LinkedBugStatus("AGENT-1000", "Resolved", retested=False),
        ),
    )

    assert decision.can_move_to_test_completed is False
    assert decision.target_status == FAILED_TEST_STORY_STATUS
    assert "AGENT-999 is not resolved: In Progress" in decision.blockers
    assert "AGENT-1000 is resolved but not retested." in decision.blockers


def test_retest_gate_allows_test_completed_after_resolved_retested_bugs() -> None:
    decision = evaluate_retest_gate(
        "AGENT-50",
        (LinkedBugStatus("AGENT-999", "Resolved", retested=True),),
    )

    assert decision.can_move_to_test_completed is True
    assert decision.target_status == RETEST_PASSED_STORY_STATUS
    assert decision.labels_to_remove == (BUG_RELATED_LABEL, HAS_LINKED_BUG_LABEL)


def test_rendered_notes_keep_assignment_and_failed_criteria_visible() -> None:
    plan = build_failed_test_rework_plan(
        _failed_result(),
        fallback_developer_agent="developer-agent-2",
        bug_key="AGENT-999",
    )

    assignment_note = render_rework_assignment_note(plan.rework_assignment)
    handoff_comment = render_failed_test_handoff_comment(plan)

    assert "developer-agent-2" in assignment_note
    assert "Bug link was missing." in assignment_note
    assert "Move story to: DEV COMPLETED" in handoff_comment
    assert "Failed manual test for AGENT-50" in handoff_comment


def _failed_result() -> ManualTestExecutionResult:
    return ManualTestExecutionResult(
        story_key="AGENT-50",
        test_issue_key="AGENT-300",
        status=ManualTestResultStatus.FAILED,
        tester_role="tester",
        executed_at="2026-07-03T19:00:00Z",
        evidence_path="data/agent-logs/AGENT-50/test-evidence.md",
        test_execution_key="AGENT-301",
        failed_acceptance_criteria=("Bug link was missing.",),
    )


def _handoff_input() -> RoleHandoffTriggerInput:
    return RoleHandoffTriggerInput(
        message_id="handoff-agent-50-bug-rework",
        current_status="IN TESTING",
        event=StoryPathEvent.TESTING_FAILED,
        actor=StoryPathRole.TESTER,
        project_id="AGENT",
        project_name="Agentic Boilerplate",
        project_root="/workspace/agentic-bolierplate",
        repository="example-org/agentic-boilerplate",
        jira_project_key="AGENT",
        sprint_id="253",
        sprint_name="R1.2 S3",
        jira_issue_key="AGENT-50",
        assignment_id="assignment-agent-50-test",
        workspace_path="/workspaces/AGENT-50",
        context_pack_path="data/context-packs/AGENT-50/context.md",
        evidence_path="data/agent-logs/AGENT-50/test-evidence.md",
        communication_channel_id="workflow-agent-50",
        source_worker_id="tester-1",
        created_at="2026-08-10T03:30:00Z",
    )
