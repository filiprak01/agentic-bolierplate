from agentic_boilerplate.domain import (
    BUG_RELATED_LABEL,
    DEV_COMPLETED_STATUS,
    HAS_LINKED_BUG_LABEL,
    IN_TESTING_STATUS,
    PO_ACCEPTED_STATUS,
    TEST_CASE_DEFAULT_STATUS,
    TEST_COMPLETED_STATUS,
    JiraStatusTransitionRequest,
    JiraWorkflowActor,
    JiraWorkflowIssueType,
    closest_subtask_done_status,
    decide_jira_status_transition,
    render_jira_status_transition_decision,
)


def test_tester_moves_clean_merged_story_to_in_testing() -> None:
    decision = decide_jira_status_transition(
        JiraStatusTransitionRequest(
            issue_key="AGENT-51",
            issue_type=JiraWorkflowIssueType.STORY,
            current_status=DEV_COMPLETED_STATUS,
            target_status=IN_TESTING_STATUS,
            actor=JiraWorkflowActor.TESTER,
            merged_to_main=True,
            review_passed=True,
        )
    )

    assert decision.allowed is True
    assert decision.target_status == IN_TESTING_STATUS


def test_tester_to_in_testing_requires_dev_completed_merge_and_passed_review() -> None:
    decision = decide_jira_status_transition(
        JiraStatusTransitionRequest(
            issue_key="AGENT-51",
            issue_type=JiraWorkflowIssueType.STORY,
            current_status="IN PROGRESS",
            target_status=IN_TESTING_STATUS,
            actor=JiraWorkflowActor.TESTER,
        )
    )

    assert decision.allowed is False
    assert "Tester starts only from DEV COMPLETED after review merge handoff." in decision.blockers
    assert "Work must be merged to main before IN TESTING." in decision.blockers
    assert "Review must pass before IN TESTING." in decision.blockers


def test_review_agent_does_not_move_story_to_in_testing_after_merge() -> None:
    decision = decide_jira_status_transition(
        JiraStatusTransitionRequest(
            issue_key="AGENT-51",
            issue_type=JiraWorkflowIssueType.STORY,
            current_status=DEV_COMPLETED_STATUS,
            target_status=IN_TESTING_STATUS,
            actor=JiraWorkflowActor.REVIEW,
            merged_to_main=True,
            review_passed=True,
        )
    )

    assert decision.allowed is False
    assert "Only Tester Agent moves merged work to IN TESTING." in decision.blockers


def test_tester_moves_passing_story_to_test_completed_when_bugs_retested() -> None:
    decision = decide_jira_status_transition(
        JiraStatusTransitionRequest(
            issue_key="AGENT-51",
            issue_type=JiraWorkflowIssueType.STORY,
            current_status=IN_TESTING_STATUS,
            target_status=TEST_COMPLETED_STATUS,
            actor=JiraWorkflowActor.TESTER,
            tests_passed=True,
            linked_bug_keys=("AGENT-999",),
            retested_bug_keys=("AGENT-999",),
            linked_test_case_keys=("AGENT-300",),
            test_case_coverage_ready=True,
        )
    )

    assert decision.allowed is True
    assert decision.labels_to_remove == (BUG_RELATED_LABEL, HAS_LINKED_BUG_LABEL)


def test_tester_cannot_complete_story_with_unresolved_or_unretested_bugs() -> None:
    decision = decide_jira_status_transition(
        JiraStatusTransitionRequest(
            issue_key="AGENT-51",
            issue_type=JiraWorkflowIssueType.STORY,
            current_status=IN_TESTING_STATUS,
            target_status=TEST_COMPLETED_STATUS,
            actor=JiraWorkflowActor.TESTER,
            tests_passed=True,
            linked_bug_keys=("AGENT-999", "AGENT-1000"),
            unresolved_linked_bug_keys=("AGENT-999",),
            retested_bug_keys=("AGENT-1000",),
            linked_test_case_keys=("AGENT-300",),
            test_case_coverage_ready=True,
        )
    )

    assert decision.allowed is False
    assert any("AGENT-999" in blocker for blocker in decision.blockers)


def test_failed_testing_returns_story_to_dev_completed_with_bug_labels() -> None:
    decision = decide_jira_status_transition(
        JiraStatusTransitionRequest(
            issue_key="AGENT-51",
            issue_type=JiraWorkflowIssueType.STORY,
            current_status=IN_TESTING_STATUS,
            target_status="Dev completed",
            actor=JiraWorkflowActor.TESTER,
            tests_passed=False,
            linked_bug_keys=("AGENT-999",),
        )
    )

    assert decision.allowed is True
    assert decision.labels_to_add == (BUG_RELATED_LABEL, HAS_LINKED_BUG_LABEL)


def test_failed_testing_requires_linked_bug() -> None:
    decision = decide_jira_status_transition(
        JiraStatusTransitionRequest(
            issue_key="AGENT-51",
            issue_type=JiraWorkflowIssueType.BUG,
            current_status=IN_TESTING_STATUS,
            target_status=DEV_COMPLETED_STATUS,
            actor=JiraWorkflowActor.TESTER,
            tests_passed=False,
        )
    )

    assert decision.allowed is False
    assert "Failed testing must create or link at least one Bug." in decision.blockers


def test_product_owner_acceptance_is_required_for_story_done() -> None:
    blocked = decide_jira_status_transition(
        JiraStatusTransitionRequest(
            issue_key="AGENT-51",
            issue_type=JiraWorkflowIssueType.STORY,
            current_status=TEST_COMPLETED_STATUS,
            target_status=PO_ACCEPTED_STATUS,
            actor=JiraWorkflowActor.TESTER,
            po_approved=False,
        )
    )
    allowed = decide_jira_status_transition(
        JiraStatusTransitionRequest(
            issue_key="AGENT-51",
            issue_type=JiraWorkflowIssueType.STORY,
            current_status=TEST_COMPLETED_STATUS,
            target_status=PO_ACCEPTED_STATUS,
            actor=JiraWorkflowActor.PRODUCT_OWNER,
            po_approved=True,
        )
    )

    assert blocked.allowed is False
    assert "Only Product Owner, Release Manager, or Story Agent can move tested work to ACCEPTED/DONE." in blocked.blockers
    assert allowed.allowed is True


def test_release_manager_can_accept_tested_story_without_po_story_by_story_gate() -> None:
    decision = decide_jira_status_transition(
        JiraStatusTransitionRequest(
            issue_key="AGENT-51",
            issue_type=JiraWorkflowIssueType.STORY,
            current_status=TEST_COMPLETED_STATUS,
            target_status=PO_ACCEPTED_STATUS,
            actor=JiraWorkflowActor.RELEASE_MANAGER,
            tests_passed=True,
            linked_test_case_keys=("AGENT-300",),
            test_case_coverage_ready=True,
        )
    )

    assert decision.allowed is True


def test_release_manager_acceptance_requires_no_blocking_bugs() -> None:
    decision = decide_jira_status_transition(
        JiraStatusTransitionRequest(
            issue_key="AGENT-51",
            issue_type=JiraWorkflowIssueType.STORY,
            current_status=TEST_COMPLETED_STATUS,
            target_status=PO_ACCEPTED_STATUS,
            actor=JiraWorkflowActor.RELEASE_MANAGER,
            tests_passed=True,
            linked_test_case_keys=("AGENT-300",),
            test_case_coverage_ready=True,
            unresolved_linked_bug_keys=("AGENT-999",),
        )
    )

    assert decision.allowed is False
    assert "Agent acceptance requires no unresolved linked Bugs: AGENT-999" in decision.blockers


def test_developer_subtask_done_uses_developer_validation_not_test_completed() -> None:
    done = decide_jira_status_transition(
        JiraStatusTransitionRequest(
            issue_key="AGENT-276",
            issue_type=JiraWorkflowIssueType.SUBTASK,
            current_status="In Progress",
            target_status=PO_ACCEPTED_STATUS,
            actor=JiraWorkflowActor.DEVELOPER,
            developer_validation_passed=True,
        )
    )
    blocked_test_completed = decide_jira_status_transition(
        JiraStatusTransitionRequest(
            issue_key="AGENT-276",
            issue_type=JiraWorkflowIssueType.SUBTASK,
            current_status="In Progress",
            target_status=TEST_COMPLETED_STATUS,
            actor=JiraWorkflowActor.TESTER,
            tests_passed=True,
        )
    )

    assert done.allowed is True
    assert blocked_test_completed.allowed is False
    assert "Development subtasks do not move to TEST COMPLETED." in blocked_test_completed.blockers


def test_explicit_testing_subtask_can_move_to_test_completed() -> None:
    decision = decide_jira_status_transition(
        JiraStatusTransitionRequest(
            issue_key="AGENT-300",
            issue_type=JiraWorkflowIssueType.SUBTASK,
            current_status=IN_TESTING_STATUS,
            target_status=TEST_COMPLETED_STATUS,
            actor=JiraWorkflowActor.TESTER,
            tests_passed=True,
            explicit_testing_subtask=True,
            linked_test_case_keys=("AGENT-300",),
            test_case_coverage_ready=True,
        )
    )

    assert decision.allowed is True


def test_test_issue_stays_in_funnel_because_execution_records_results() -> None:
    allowed = decide_jira_status_transition(
        JiraStatusTransitionRequest(
            issue_key="AGENT-271",
            issue_type=JiraWorkflowIssueType.TEST,
            current_status=TEST_CASE_DEFAULT_STATUS,
            target_status=TEST_CASE_DEFAULT_STATUS,
            actor=JiraWorkflowActor.TESTER,
        )
    )
    blocked = decide_jira_status_transition(
        JiraStatusTransitionRequest(
            issue_key="AGENT-271",
            issue_type=JiraWorkflowIssueType.TEST,
            current_status=TEST_CASE_DEFAULT_STATUS,
            target_status=TEST_COMPLETED_STATUS,
            actor=JiraWorkflowActor.TESTER,
            tests_passed=True,
        )
    )

    assert allowed.allowed is True
    assert blocked.allowed is False
    assert "Jira Test issues remain in FUNNEL" in blocked.blockers[0]


def test_tester_cannot_complete_story_without_linked_test_case_coverage() -> None:
    decision = decide_jira_status_transition(
        JiraStatusTransitionRequest(
            issue_key="AGENT-283",
            issue_type=JiraWorkflowIssueType.STORY,
            current_status=IN_TESTING_STATUS,
            target_status=TEST_COMPLETED_STATUS,
            actor=JiraWorkflowActor.TESTER,
            tests_passed=True,
        )
    )

    assert decision.allowed is False
    assert "At least one linked AgileTest-style Test Case is required before TEST COMPLETED." in decision.blockers
    assert (
        "Linked Test Case coverage must include scenario steps or automated coverage mapping before TEST COMPLETED."
        in decision.blockers
    )


def test_tester_can_complete_one_time_validation_with_explained_skip() -> None:
    decision = decide_jira_status_transition(
        JiraStatusTransitionRequest(
            issue_key="AGENT-283",
            issue_type=JiraWorkflowIssueType.STORY,
            current_status=IN_TESTING_STATUS,
            target_status=TEST_COMPLETED_STATUS,
            actor=JiraWorkflowActor.TESTER,
            tests_passed=True,
            one_time_validation_labeled=True,
            one_time_validation_explained=True,
        )
    )

    assert decision.allowed is True


def test_closest_subtask_done_status_prefers_accepted_done_then_done() -> None:
    assert closest_subtask_done_status(("To Do", "Done", "Accepted/Done")) == "Accepted/Done"
    assert closest_subtask_done_status(("To Do", "Done")) == "Done"


def test_render_transition_decision_lists_blockers_and_labels() -> None:
    decision = decide_jira_status_transition(
        JiraStatusTransitionRequest(
            issue_key="AGENT-51",
            issue_type=JiraWorkflowIssueType.STORY,
            current_status=IN_TESTING_STATUS,
            target_status=DEV_COMPLETED_STATUS,
            actor=JiraWorkflowActor.TESTER,
            tests_passed=False,
            linked_bug_keys=("AGENT-999",),
        )
    )

    note = render_jira_status_transition_decision(decision)

    assert "Transition decision for AGENT-51: allowed" in note
    assert "Labels to add: bug-related, has-linked-bug" in note
