from agentic_boilerplate.domain import (
    JiraSprintLifecycleAction,
    JiraSprintLifecycleBlockerKind,
    JiraSprintLifecycleRequest,
    JiraSprintSupportIssue,
    evaluate_jira_sprint_lifecycle_sync,
    render_jira_sprint_lifecycle_decision,
)


def test_start_requires_dates_when_future_sprint_is_activated() -> None:
    decision = evaluate_jira_sprint_lifecycle_sync(
        JiraSprintLifecycleRequest(
            sprint_id="44",
            sprint_name="Sprint 44",
            current_state="future",
            target_state="active",
        )
    )

    assert decision.allowed is False
    assert decision.action == JiraSprintLifecycleAction.BLOCKED
    assert decision.blockers[0].kind == JiraSprintLifecycleBlockerKind.START_DATES_REQUIRED


def test_close_requires_regression_and_retro_tasks_in_sprint() -> None:
    decision = evaluate_jira_sprint_lifecycle_sync(
        JiraSprintLifecycleRequest(
            sprint_id="44",
            sprint_name="Sprint 44",
            current_state="active",
            target_state="closed",
            support_issues=(
                JiraSprintSupportIssue(
                    issue_key="AGENT-242",
                    summary="Regression overview",
                    issue_type="Task",
                    present_in_sprint=True,
                ),
                JiraSprintSupportIssue(
                    issue_key="AGENT-243",
                    summary="Retro and closure",
                    issue_type="Task",
                    present_in_sprint=False,
                ),
            ),
        )
    )

    assert decision.allowed is False
    assert decision.missing_support_issue_keys == ("AGENT-243",)
    assert decision.blockers[-1].kind == JiraSprintLifecycleBlockerKind.REQUIRED_SUPPORT_ISSUE_MISSING


def test_documented_state_mismatch_raises_po_question() -> None:
    decision = evaluate_jira_sprint_lifecycle_sync(
        JiraSprintLifecycleRequest(
            sprint_id="44",
            sprint_name="Sprint 44",
            current_state="active",
            target_state="closed",
            documented_expected_state="future",
            support_issues=(
                JiraSprintSupportIssue(
                    issue_key="AGENT-242",
                    summary="Regression overview",
                    issue_type="Task",
                    present_in_sprint=True,
                ),
                JiraSprintSupportIssue(
                    issue_key="AGENT-243",
                    summary="Retro and closure",
                    issue_type="Task",
                    present_in_sprint=True,
                ),
            ),
        )
    )

    assert decision.allowed is False
    assert decision.po_question
    assert decision.blockers[0].kind == JiraSprintLifecycleBlockerKind.DOCUMENTED_STATE_MISMATCH


def test_close_decision_records_change_when_support_is_ready() -> None:
    decision = evaluate_jira_sprint_lifecycle_sync(
        JiraSprintLifecycleRequest(
            sprint_id="44",
            sprint_name="Sprint 44",
            current_state="active",
            target_state="closed",
            support_issues=(
                JiraSprintSupportIssue(
                    issue_key="AGENT-242",
                    summary="Regression overview",
                    issue_type="Task",
                    present_in_sprint=True,
                ),
                JiraSprintSupportIssue(
                    issue_key="AGENT-243",
                    summary="Retro and closure",
                    issue_type="Task",
                    present_in_sprint=True,
                ),
            ),
        )
    )

    rendered = render_jira_sprint_lifecycle_decision(decision)

    assert decision.allowed is True
    assert decision.action == JiraSprintLifecycleAction.CLOSE
    assert decision.should_record_change is True
    assert "Record lifecycle change: yes" in rendered
    assert "AGENT-242" not in rendered


def test_close_requires_accepted_items_regression_and_retro() -> None:
    decision = evaluate_jira_sprint_lifecycle_sync(
        JiraSprintLifecycleRequest(
            sprint_id="44",
            sprint_name="Sprint 44",
            current_state="active",
            target_state="closed",
            all_sprint_items_accepted=False,
            regression_passed=False,
            retro_completed=False,
            support_issues=(
                JiraSprintSupportIssue(
                    issue_key="AGENT-242",
                    summary="Regression overview",
                    issue_type="Task",
                    present_in_sprint=True,
                ),
                JiraSprintSupportIssue(
                    issue_key="AGENT-243",
                    summary="Retro and closure",
                    issue_type="Task",
                    present_in_sprint=True,
                ),
            ),
        )
    )

    assert decision.allowed is False
    assert {blocker.kind for blocker in decision.blockers} >= {
        JiraSprintLifecycleBlockerKind.SPRINT_ITEMS_NOT_ACCEPTED,
        JiraSprintLifecycleBlockerKind.REGRESSION_NOT_PASSED,
        JiraSprintLifecycleBlockerKind.RETRO_NOT_COMPLETED,
    }


def test_same_state_is_noop_when_documentation_and_membership_match() -> None:
    decision = evaluate_jira_sprint_lifecycle_sync(
        JiraSprintLifecycleRequest(
            sprint_id="44",
            sprint_name="Sprint 44",
            current_state="active",
            target_state="active",
            documented_expected_state="active",
        )
    )

    assert decision.allowed is True
    assert decision.action == JiraSprintLifecycleAction.NOOP
    assert decision.should_record_change is False
