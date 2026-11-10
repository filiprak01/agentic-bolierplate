import pytest

from agentic_boilerplate.domain import (
    AGILETEST_LINK_OUTWARD,
    AGILETEST_LINK_TYPE,
    DEFAULT_TEST_CASE_STATUS,
    ManualTestCasePlan,
    TestCaseCoverageEvidence,
    ManualTestExecutionResult,
    ManualTestResultStatus,
    ManualTestStep,
    ManualTestWorkflowError,
    RegressionClassification,
    agiletest_link_plan_for_test_case,
    bug_plan_for_failed_manual_test,
    coverage_evidence_from_manual_test_case_plan,
    evaluate_test_case_coverage,
    jira_test_issue_fields_for_plan,
    manual_test_case_description,
    manual_test_case_labels,
    render_manual_test_execution_comment,
    require_valid_manual_test_case_plan,
    require_valid_manual_test_execution_result,
    story_status_after_passed_manual_testing,
)


def test_manual_test_case_plan_requires_steps_and_regression_labels() -> None:
    plan = ManualTestCasePlan(
        story_key="AGENT-49",
        summary="Manual test for AGENT-49",
        manual_steps=(),
        regression_labels=(),
    )

    with pytest.raises(ManualTestWorkflowError) as exc:
        require_valid_manual_test_case_plan(plan)

    assert "manual_steps" in str(exc.value)
    assert "regression_labels" in str(exc.value)


def test_manual_test_case_fields_include_agiletest_manual_case_and_labels() -> None:
    fields = jira_test_issue_fields_for_plan(_test_case_plan())

    assert fields.summary == "Test Case - AGENT-49 Manual Test Issue Workflow"
    assert fields.issue_type == "Test"
    assert fields.status == DEFAULT_TEST_CASE_STATUS
    assert "AgileTest Test Case Type: Manual" in fields.description
    assert "manual-test" in fields.labels
    assert "release-regression" in fields.labels


def test_manual_test_description_records_steps_and_expected_results() -> None:
    description = manual_test_case_description(_test_case_plan())

    assert "1. Open the tested story after merge to main." in description
    assert "Expected: Story is visible for Tester Agent validation." in description
    assert "release-regression" in description


def test_agiletest_link_plan_links_test_case_to_covered_story() -> None:
    link = agiletest_link_plan_for_test_case(_test_case_plan())

    assert link.link_type == AGILETEST_LINK_TYPE
    assert link.outward_relationship == AGILETEST_LINK_OUTWARD
    assert link.test_issue_key == "AGENT-300"
    assert link.covered_issue_key == "AGENT-49"


def test_agiletest_link_plan_requires_created_test_issue_key() -> None:
    plan = ManualTestCasePlan(
        **{
            **_test_case_plan().__dict__,
            "test_issue_key": "",
        }
    )

    with pytest.raises(ManualTestWorkflowError) as exc:
        agiletest_link_plan_for_test_case(plan)

    assert "test_issue_key" in str(exc.value)


def test_manual_test_execution_comment_references_evidence_and_execution_context() -> None:
    result = _passed_execution_result()

    comment = render_manual_test_execution_comment(result)

    assert "Manual test execution recorded for AGENT-49." in comment
    assert "Test Case: AGENT-300" in comment
    assert "Result: passed" in comment
    assert "Test Execution: AGENT-301" in comment
    assert "Evidence: data/agent-logs/AGENT-49/test-evidence.md" in comment


def test_passed_manual_testing_targets_test_completed() -> None:
    assert story_status_after_passed_manual_testing() == "TEST COMPLETED"


def test_failed_manual_result_requires_failed_acceptance_criteria() -> None:
    result = ManualTestExecutionResult(
        story_key="AGENT-49",
        test_issue_key="AGENT-300",
        status=ManualTestResultStatus.FAILED,
        tester_role="tester",
        executed_at="2026-07-03T18:00:00Z",
        test_execution_key="AGENT-301",
    )

    with pytest.raises(ManualTestWorkflowError) as exc:
        require_valid_manual_test_execution_result(result)

    assert "failed_acceptance_criteria" in str(exc.value)


def test_failed_manual_result_can_create_bug_plan_when_configured() -> None:
    result = ManualTestExecutionResult(
        story_key="AGENT-49",
        test_issue_key="AGENT-300",
        status=ManualTestResultStatus.FAILED,
        tester_role="tester",
        executed_at="2026-07-03T18:00:00Z",
        evidence_path="data/agent-logs/AGENT-49/test-evidence.md",
        test_execution_key="AGENT-301",
        failed_acceptance_criteria=("Manual Test issue was not linked.",),
    )

    bug_plan = bug_plan_for_failed_manual_test(result, create_bug=True)

    assert bug_plan is not None
    assert bug_plan.story_key == "AGENT-49"
    assert bug_plan.test_issue_key == "AGENT-300"
    assert "Failed manual test for AGENT-49" in bug_plan.summary
    assert "Manual Test issue was not linked." in bug_plan.description


def test_failed_manual_result_does_not_create_bug_plan_when_disabled() -> None:
    assert bug_plan_for_failed_manual_test(_passed_execution_result(), create_bug=True) is None
    failed = ManualTestExecutionResult(
        story_key="AGENT-49",
        test_issue_key="AGENT-300",
        status=ManualTestResultStatus.FAILED,
        tester_role="tester",
        executed_at="2026-07-03T18:00:00Z",
        test_execution_key="AGENT-301",
        failed_acceptance_criteria=("Criterion failed.",),
    )

    assert bug_plan_for_failed_manual_test(failed, create_bug=False) is None


def test_manual_test_case_labels_are_sorted_and_include_classifications() -> None:
    labels = manual_test_case_labels(_test_case_plan())

    assert labels == tuple(sorted(labels))
    assert labels == (
        "agiletest-test-case",
        "manual-only",
        "manual-test",
        "regression-candidate",
        "release-regression",
    )


def test_manual_test_case_plan_can_render_coverage_evidence() -> None:
    evidence = coverage_evidence_from_manual_test_case_plan(_test_case_plan())

    assert evidence.test_issue_key == "AGENT-300"
    assert evidence.covered_issue_key == "AGENT-49"
    assert evidence.has_manual_steps is True
    assert evidence.has_automated_coverage is False


def test_coverage_evaluation_requires_linked_reusable_test_case() -> None:
    decision = evaluate_test_case_coverage(
        covered_issue_key="AGENT-49",
        linked_test_case_keys=(),
    )

    assert decision.allowed is False
    assert "At least one linked AgileTest-style Test Case is required before TEST COMPLETED." in decision.blockers


def test_coverage_evaluation_accepts_manual_steps_or_automated_mapping() -> None:
    manual_evidence = coverage_evidence_from_manual_test_case_plan(_test_case_plan())
    automated_evidence = TestCaseCoverageEvidence(
        test_issue_key="AGENT-301",
        covered_issue_key="AGENT-49",
        has_manual_steps=False,
        has_automated_coverage=True,
    )

    manual_decision = evaluate_test_case_coverage(
        covered_issue_key="AGENT-49",
        linked_test_case_keys=("AGENT-300",),
        coverage_evidence=(manual_evidence,),
    )
    automated_decision = evaluate_test_case_coverage(
        covered_issue_key="AGENT-49",
        linked_test_case_keys=("AGENT-301",),
        coverage_evidence=(automated_evidence,),
    )

    assert manual_decision.allowed is True
    assert manual_decision.reusable_test_case_keys == ("AGENT-300",)
    assert automated_decision.allowed is True
    assert automated_decision.reusable_test_case_keys == ("AGENT-301",)


def test_one_time_validation_requires_explanation_to_skip_reusable_test_case() -> None:
    blocked = evaluate_test_case_coverage(
        covered_issue_key="AGENT-49",
        linked_test_case_keys=(),
        one_time_validation_labeled=True,
        one_time_validation_explained=False,
    )
    allowed = evaluate_test_case_coverage(
        covered_issue_key="AGENT-49",
        linked_test_case_keys=(),
        one_time_validation_labeled=True,
        one_time_validation_explained=True,
    )

    assert blocked.allowed is False
    assert "One-time-validation stories may skip reusable Test Case creation only when evidence explains why." in blocked.blockers
    assert allowed.allowed is True
    assert allowed.one_time_validation_exempt is True


def _test_case_plan() -> ManualTestCasePlan:
    return ManualTestCasePlan(
        story_key="AGENT-49",
        covered_issue_key="AGENT-49",
        test_issue_key="AGENT-300",
        summary="Test Case - AGENT-49 Manual Test Issue Workflow",
        manual_steps=(
            ManualTestStep(
                index=1,
                action="Open the tested story after merge to main.",
                expected_result="Story is visible for Tester Agent validation.",
            ),
            ManualTestStep(
                index=2,
                action="Record manual test execution with evidence.",
                expected_result="Execution comment references evidence and result.",
            ),
        ),
        regression_labels=(
            RegressionClassification.REGRESSION_CANDIDATE,
            RegressionClassification.RELEASE_REGRESSION,
            RegressionClassification.MANUAL_ONLY,
        ),
    )


def _passed_execution_result() -> ManualTestExecutionResult:
    return ManualTestExecutionResult(
        story_key="AGENT-49",
        test_issue_key="AGENT-300",
        status=ManualTestResultStatus.PASSED,
        tester_role="tester",
        executed_at="2026-07-03T18:00:00Z",
        evidence_path="data/agent-logs/AGENT-49/test-evidence.md",
        test_execution_key="AGENT-301",
        test_cycle_key="AGENT-302",
    )
