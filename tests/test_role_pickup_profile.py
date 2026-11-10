from dataclasses import replace

from agentic_boilerplate.domain.po_inbox import AgentRole
from agentic_boilerplate.domain.role_pickup_profile import (
    DEV_COMPLETED,
    READY_TO_START,
    TEST_COMPLETED,
    PickupCandidate,
    PickupDecisionKind,
    PickupSkipReason,
    build_pickup_search_plan,
    evaluate_role_pickup_candidate,
    profile_for_role,
    render_pickup_decision_log,
    with_required_labels,
)


def test_developer_search_plan_is_project_configurable_and_active_sprint_scoped() -> None:
    profile = with_required_labels(profile_for_role(AgentRole.DEVELOPER, "AP"), "agent-developer")

    plan = build_pickup_search_plan(profile, active_sprint_name="R1 S4")

    assert plan.project_key == "AP"
    assert 'project = "AP"' in plan.jql
    assert 'status in ("READY TO START", "DEV COMPLETED")' in plan.jql
    assert 'issuetype in ("Story", "Bug", "Task")' in plan.jql
    assert 'labels in ("agent-developer")' in plan.jql
    assert 'sprint = "R1 S4"' in plan.jql
    assert plan.active_sprint_name == "R1 S4"


def test_excluded_label_jql_keeps_unlabeled_candidates_visible() -> None:
    profile = replace(profile_for_role(AgentRole.DEVELOPER, "AP"), excluded_labels=("do-not-pick",))

    plan = build_pickup_search_plan(profile, active_sprint_name="R1 S4")

    assert '(labels not in ("do-not-pick") OR labels is EMPTY)' in plan.jql


def test_developer_picks_ready_active_sprint_story_when_gates_pass() -> None:
    profile = profile_for_role(AgentRole.DEVELOPER, "AP")
    candidate = PickupCandidate(
        issue_key="AP-29",
        project_key="AP",
        issue_type="Story",
        status=READY_TO_START,
        sprint_names=("R1 S4",),
    )

    decision = evaluate_role_pickup_candidate(profile, candidate, active_sprint_name="R1 S4")

    assert decision.decision is PickupDecisionKind.PICK
    assert decision.reasons == ()
    assert "role=developer" in render_pickup_decision_log(decision)


def test_future_sprint_story_is_skipped_before_assignment() -> None:
    profile = profile_for_role(AgentRole.DEVELOPER, "AP")
    candidate = PickupCandidate(
        issue_key="AP-30",
        project_key="AP",
        issue_type="Story",
        status=READY_TO_START,
        sprint_names=("R1 S5",),
    )

    decision = evaluate_role_pickup_candidate(profile, candidate, active_sprint_name="R1 S4")

    assert decision.decision is PickupDecisionKind.SKIP
    assert decision.reasons == (PickupSkipReason.FUTURE_SPRINT,)


def test_ui_ux_profile_picks_ready_design_story_for_active_sprint() -> None:
    profile = profile_for_role(AgentRole.UI_UX, "AP")
    candidate = PickupCandidate(
        issue_key="AP-30",
        project_key="AP",
        issue_type="Story",
        status=READY_TO_START,
        sprint_names=("R1 S4",),
    )

    decision = evaluate_role_pickup_candidate(profile, candidate, active_sprint_name="R1 S4")

    assert profile.handoff_target_role is AgentRole.FRONTEND
    assert decision.decision is PickupDecisionKind.PICK
    assert decision.reasons == ()


def test_blocked_dependencies_locks_limits_and_dor_stop_developer_pickup() -> None:
    profile = profile_for_role(AgentRole.DEVELOPER, "AP")
    candidate = PickupCandidate(
        issue_key="AP-31",
        project_key="AP",
        issue_type="Task",
        status=READY_TO_START,
        sprint_names=("R1 S4",),
        dependency_passed=False,
        dependency_graph_passed=False,
        assignment_locked=True,
        codex_limit_allowed=False,
        definition_ready=False,
    )

    decision = evaluate_role_pickup_candidate(profile, candidate, active_sprint_name="R1 S4")

    assert decision.decision is PickupDecisionKind.BLOCKED
    assert set(decision.reasons) == {
        PickupSkipReason.DEPENDENCY_GRAPH_BLOCKED,
        PickupSkipReason.UNRESOLVED_DEPENDENCY,
        PickupSkipReason.ACTIVE_LOCK,
        PickupSkipReason.CODEX_LIMIT_BLOCKED,
        PickupSkipReason.DOR_FAILED,
    }


def test_developer_dev_completed_rework_requires_review_or_testing_signal() -> None:
    profile = profile_for_role(AgentRole.DEVELOPER, "AP")
    candidate = PickupCandidate(
        issue_key="AP-32",
        project_key="AP",
        issue_type="Story",
        status=DEV_COMPLETED,
        sprint_names=("R1 S4",),
    )

    decision = evaluate_role_pickup_candidate(profile, candidate, active_sprint_name="R1 S4")

    assert decision.decision is PickupDecisionKind.BLOCKED
    assert PickupSkipReason.MISSING_REWORK_SIGNAL in decision.reasons

    retest_bug = PickupCandidate(
        issue_key="AP-32",
        project_key="AP",
        issue_type="Story",
        status=DEV_COMPLETED,
        sprint_names=("R1 S4",),
        blocking_bug_keys=("AP-44",),
        linked_testing_bug_keys=("AP-44",),
    )

    decision = evaluate_role_pickup_candidate(profile, retest_bug, active_sprint_name="R1 S4")

    assert decision.decision is PickupDecisionKind.PICK


def test_review_requires_pr_handoff_ci_success_and_clean_mergeability() -> None:
    profile = profile_for_role(AgentRole.REVIEW, "AP")
    missing = PickupCandidate(
        issue_key="AP-33",
        project_key="AP",
        issue_type="Story",
        status=DEV_COMPLETED,
        sprint_names=("R1 S4",),
    )

    decision = evaluate_role_pickup_candidate(profile, missing, active_sprint_name="R1 S4")

    assert decision.decision is PickupDecisionKind.BLOCKED
    assert PickupSkipReason.MISSING_ARTIFACT in decision.reasons
    assert PickupSkipReason.CI_NOT_SUCCESS in decision.reasons
    assert PickupSkipReason.DIRTY_MERGEABILITY in decision.reasons

    stale_pr = PickupCandidate(
        issue_key="AP-33",
        project_key="AP",
        issue_type="Story",
        status=DEV_COMPLETED,
        sprint_names=("R1 S4",),
        pr_url="https://github.com/example-org/ap/pull/12",
        pr_branch="feature/AP-33-example",
        pr_head_sha="abc1234",
        pr_open=False,
        pr_metadata_current=False,
        development_evidence_path="data/agent-logs/AP-33/test-evidence.md",
        ci_state="success",
        mergeable_state="clean",
    )

    decision = evaluate_role_pickup_candidate(profile, stale_pr, active_sprint_name="R1 S4")

    assert decision.decision is PickupDecisionKind.BLOCKED
    assert PickupSkipReason.PR_NOT_OPEN in decision.reasons
    assert PickupSkipReason.STALE_PR_METADATA in decision.reasons

    ready = PickupCandidate(
        issue_key="AP-33",
        project_key="AP",
        issue_type="Story",
        status=DEV_COMPLETED,
        sprint_names=("R1 S4",),
        pr_url="https://github.com/example-org/ap/pull/12",
        pr_branch="feature/AP-33-example",
        pr_head_sha="abc1234",
        development_evidence_path="data/agent-logs/AP-33/test-evidence.md",
        ci_state="success",
        mergeable_state="clean",
    )

    decision = evaluate_role_pickup_candidate(profile, ready, active_sprint_name="R1 S4")

    assert decision.decision is PickupDecisionKind.PICK


def test_tester_requires_review_merge_to_main_and_test_request() -> None:
    profile = profile_for_role(AgentRole.TESTER, "AP")
    missing = PickupCandidate(
        issue_key="AP-34",
        project_key="AP",
        issue_type="Story",
        status=DEV_COMPLETED,
        sprint_names=("R1 S4",),
        development_evidence_path="data/agent-logs/AP-34/dev.md",
    )

    decision = evaluate_role_pickup_candidate(profile, missing, active_sprint_name="R1 S4")

    assert decision.decision is PickupDecisionKind.BLOCKED
    assert PickupSkipReason.UNMERGED_MAIN in decision.reasons
    assert PickupSkipReason.MISSING_TEST_REQUEST in decision.reasons
    assert PickupSkipReason.MISSING_ACCEPTANCE_CRITERIA in decision.reasons

    ready = PickupCandidate(
        issue_key="AP-34",
        project_key="AP",
        issue_type="Story",
        status=DEV_COMPLETED,
        sprint_names=("R1 S4",),
        merged_sha="def5678",
        test_request_recorded=True,
        development_evidence_path="data/agent-logs/AP-34/dev.md",
        acceptance_criteria_available=True,
    )

    decision = evaluate_role_pickup_candidate(profile, ready, active_sprint_name="R1 S4")

    assert decision.decision is PickupDecisionKind.PICK


def test_tester_skips_test_completed_without_explicit_retest_signal() -> None:
    profile = profile_for_role(AgentRole.TESTER, "AP")
    completed = PickupCandidate(
        issue_key="AP-34",
        project_key="AP",
        issue_type="Story",
        status=TEST_COMPLETED,
        sprint_names=("R1 S4",),
        merged_sha="def5678",
        test_request_recorded=True,
        development_evidence_path="data/agent-logs/AP-34/dev.md",
        acceptance_criteria_available=True,
    )

    decision = evaluate_role_pickup_candidate(profile, completed, active_sprint_name="R1 S4")

    assert decision.decision is PickupDecisionKind.SKIP
    assert decision.reasons == (PickupSkipReason.EXPLICIT_RETEST_NOT_REQUESTED,)

    explicit_retest = replace(completed, explicit_retest=True)

    decision = evaluate_role_pickup_candidate(profile, explicit_retest, active_sprint_name="R1 S4")

    assert decision.decision is PickupDecisionKind.PICK


def test_release_manager_waits_for_delivery_regression_manifest_and_bugs() -> None:
    profile = profile_for_role(AgentRole.RELEASE_MANAGER, "AP")
    candidate = PickupCandidate(
        issue_key="AP-35",
        project_key="AP",
        issue_type="Task",
        status=TEST_COMPLETED,
        sprint_names=("R1 S4",),
        blocking_bug_keys=("AP-40",),
    )

    decision = evaluate_role_pickup_candidate(profile, candidate, active_sprint_name="R1 S4")

    assert decision.decision is PickupDecisionKind.BLOCKED
    assert PickupSkipReason.BLOCKING_BUG in decision.reasons
    assert PickupSkipReason.SPRINT_DELIVERY_NOT_READY in decision.reasons
    assert PickupSkipReason.REGRESSION_MANIFEST_MISSING in decision.reasons

    ready = PickupCandidate(
        issue_key="AP-35",
        project_key="AP",
        issue_type="Task",
        status=TEST_COMPLETED,
        sprint_names=("R1 S4",),
        sprint_delivery_ready=True,
        regression_manifest_ready=True,
    )

    decision = evaluate_role_pickup_candidate(profile, ready, active_sprint_name="R1 S4")

    assert decision.decision is PickupDecisionKind.PICK


def test_docs_and_security_profiles_have_their_own_artifact_gates() -> None:
    docs = profile_for_role(AgentRole.DOCS_CONFLUENCE, "AP")
    docs_candidate = PickupCandidate(
        issue_key="AP-36",
        project_key="AP",
        issue_type="Task",
        status=READY_TO_START,
        sprint_names=("R1 S4",),
        evidence_path="data/agent-logs/AP-36/evidence.md",
    )

    decision = evaluate_role_pickup_candidate(docs, docs_candidate, active_sprint_name="R1 S4")

    assert decision.decision is PickupDecisionKind.BLOCKED
    assert PickupSkipReason.MISSING_PUBLICATION_TARGET in decision.reasons

    security = profile_for_role(AgentRole.SECURITY, "AP")
    security_candidate = PickupCandidate(
        issue_key="AP-37",
        project_key="AP",
        issue_type="Story",
        status=READY_TO_START,
        sprint_names=("R1 S4",),
        security_scope_defined=True,
        secret_exposure_detected=True,
    )

    decision = evaluate_role_pickup_candidate(security, security_candidate, active_sprint_name="R1 S4")

    assert decision.decision is PickupDecisionKind.BLOCKED
    assert decision.reasons == (PickupSkipReason.SECRET_EXPOSURE,)


def test_unsupported_status_is_logged_as_ineligible_skip() -> None:
    profile = profile_for_role(AgentRole.REVIEW, "AP")
    candidate = PickupCandidate(
        issue_key="AP-38",
        project_key="AP",
        issue_type="Story",
        status="ACCEPTED/DONE",
        sprint_names=("R1 S4",),
    )

    decision = evaluate_role_pickup_candidate(profile, candidate, active_sprint_name="R1 S4")

    assert decision.decision is PickupDecisionKind.SKIP
    assert decision.reasons == (PickupSkipReason.UNSUPPORTED_STATUS,)
    assert "unsupported_status" in render_pickup_decision_log(decision)
