from agentic_boilerplate.domain import (
    AgileTestTestCaseSnapshot,
    AutomatedCoverageReference,
    ManualTestStep,
    TestCaseConsistencyFindingType,
    TestCaseExecutionMode,
    assess_agiletest_test_case_consistency,
    assess_release_regression_test_case_consistency,
    default_agiletest_test_case_consistency_config,
    render_agiletest_test_case_consistency_batch_result,
    render_agiletest_test_case_consistency_result,
)


def test_manual_reusable_test_case_with_required_metadata_is_ready() -> None:
    config = default_agiletest_test_case_consistency_config(project_key="AGENT")

    result = assess_agiletest_test_case_consistency(
        test_case=_manual_test_case(),
        config=config,
    )

    assert result.ready_for_regression
    assert result.matched_release_labels == ("release-mvp",)
    assert result.matched_sprint_labels == ("mvp-sprint-10", "sprint-ring-10")
    assert result.matched_regression_labels == ("release-regression",)


def test_validator_reports_missing_labels_without_mutating_input() -> None:
    config = default_agiletest_test_case_consistency_config(project_key="AGENT")
    test_case = _manual_test_case(labels=("manual-test",))

    result = assess_agiletest_test_case_consistency(
        test_case=test_case,
        config=config,
    )

    assert not result.ready_for_regression
    assert {finding.finding_type for finding in result.findings} == {
        TestCaseConsistencyFindingType.MISSING_AGILETEST_LABEL,
        TestCaseConsistencyFindingType.MISSING_RELEASE_LABEL,
        TestCaseConsistencyFindingType.MISSING_SPRINT_LABEL,
        TestCaseConsistencyFindingType.MISSING_REGRESSION_LABEL,
    }
    assert test_case.labels == ("manual-test",)


def test_validator_reports_missing_scenario_preconditions_expected_results_and_evidence() -> None:
    config = default_agiletest_test_case_consistency_config(project_key="AGENT")

    result = assess_agiletest_test_case_consistency(
        test_case=AgileTestTestCaseSnapshot(
            test_issue_key="AGENT-349",
            project_key="AGENT",
            issue_type="Test",
            summary="Regression publication manual test",
            labels=(
                "agiletest-test-case",
                "manual-test",
                "release-mvp",
                "mvp-sprint-10",
                "release-regression",
            ),
            execution_mode=TestCaseExecutionMode.MANUAL,
            scenario="",
            preconditions=(),
            steps=(
                ManualTestStep(
                    index=1,
                    action="Open the reusable test case.",
                    expected_result="",
                ),
            ),
            evidence_references=(),
        ),
        config=config,
    )

    assert not result.ready_for_regression
    assert {finding.finding_type for finding in result.findings} == {
        TestCaseConsistencyFindingType.MISSING_SCENARIO,
        TestCaseConsistencyFindingType.MISSING_PRECONDITIONS,
        TestCaseConsistencyFindingType.MISSING_EXPECTED_RESULT,
        TestCaseConsistencyFindingType.MISSING_EVIDENCE_REFERENCE,
    }


def test_automated_test_case_requires_automated_labels_and_command_references() -> None:
    config = default_agiletest_test_case_consistency_config(project_key="AGENT")

    result = assess_agiletest_test_case_consistency(
        test_case=AgileTestTestCaseSnapshot(
            test_issue_key="AGENT-402",
            project_key="AGENT",
            issue_type="Test",
            summary="Automated publication coverage",
            labels=(
                "agiletest-test-case",
                "release-mvp",
                "mvp-sprint-10",
                "release-regression",
            ),
            execution_mode=TestCaseExecutionMode.AUTOMATED,
            scenario="Validate automated coverage metadata.",
            preconditions=("Merged main is available.",),
            steps=(
                ManualTestStep(
                    index=1,
                    action="Inspect automated coverage mapping.",
                    expected_result="Coverage mapping identifies the executed command.",
                ),
            ),
            command_references=(),
        ),
        config=config,
    )

    assert not result.ready_for_regression
    assert {finding.finding_type for finding in result.findings} == {
        TestCaseConsistencyFindingType.MISSING_AUTOMATED_LABEL,
        TestCaseConsistencyFindingType.MISSING_COMMAND_REFERENCE,
    }


def test_validator_stays_configurable_for_other_projects_and_issue_type_names() -> None:
    config = default_agiletest_test_case_consistency_config(
        project_key="CLIENT",
        test_issue_type="Quality Test",
    )

    result = assess_agiletest_test_case_consistency(
        test_case=AgileTestTestCaseSnapshot(
            test_issue_key="CLIENT-12",
            project_key="CLIENT",
            issue_type="Quality Test",
            summary="Client reusable regression test",
            labels=(
                "agiletest-test-case",
                "manual-only",
                "manual-test",
                "client-release-1",
                "client-sprint-4",
                "client-regression",
            ),
            execution_mode=TestCaseExecutionMode.MANUAL,
            scenario="Validate a client-side reusable test case.",
            preconditions=("Client environment is available.",),
            steps=(
                ManualTestStep(
                    index=1,
                    action="Open the client release artifact.",
                    expected_result="Artifact is visible for test execution.",
                ),
            ),
            evidence_references=("docs/client-evidence.md",),
        ),
        config=config.__class__(
            project_key="CLIENT",
            test_issue_type="Quality Test",
            agiletest_labels=("agiletest-test-case",),
            release_label_prefixes=("client-release-",),
            sprint_label_prefixes=("client-sprint-",),
            regression_labels=("client-regression",),
            manual_labels=("manual-test", "manual-only"),
            automated_labels=("client-automated",),
        ),
    )

    assert result.ready_for_regression


def test_batch_result_supports_release_regression_suite_preparation_view() -> None:
    config = default_agiletest_test_case_consistency_config(project_key="AGENT")
    batch = assess_release_regression_test_case_consistency(
        test_cases=(
            _manual_test_case(test_issue_key="AGENT-349"),
            _manual_test_case(test_issue_key="AGENT-350", labels=("manual-test",)),
        ),
        config=config,
    )

    assert not batch.ready_for_regression
    assert batch.blocked_test_case_keys == ("AGENT-350",)

    summary = render_agiletest_test_case_consistency_batch_result(batch)

    assert "# AgileTest Test Case Consistency Summary" in summary
    assert "- AGENT-349: ready" in summary
    assert "- AGENT-350: blocked" in summary


def test_single_result_renderer_lists_findings() -> None:
    config = default_agiletest_test_case_consistency_config(project_key="AGENT")
    result = assess_agiletest_test_case_consistency(
        test_case=_manual_test_case(labels=("manual-test",)),
        config=config,
    )

    markdown = render_agiletest_test_case_consistency_result(result)

    assert "# AgileTest Test Case Consistency - AGENT-349" in markdown
    assert "- Ready for regression: no" in markdown
    assert "missing a release label" in markdown


def _manual_test_case(
    *,
    test_issue_key: str = "AGENT-349",
    labels: tuple[str, ...] = (
        "agiletest-test-case",
        "manual-test",
        "release-mvp",
        "mvp-sprint-10",
        "sprint-ring-10",
        "release-regression",
    ),
) -> AgileTestTestCaseSnapshot:
    return AgileTestTestCaseSnapshot(
        test_issue_key=test_issue_key,
        project_key="AGENT",
        issue_type="Test",
        summary="Regression publication reusable test",
        labels=labels,
        execution_mode=TestCaseExecutionMode.MANUAL,
        scenario="Validate reusable regression publication metadata before suite planning.",
        preconditions=("A reusable Test Case is linked to the covered story.",),
        steps=(
            ManualTestStep(
                index=1,
                action="Review the reusable test metadata.",
                expected_result="Release, sprint, regression, and AgileTest labels are present.",
            ),
            ManualTestStep(
                index=2,
                action="Review the test scenario and evidence references.",
                expected_result="Scenario, preconditions, steps, and evidence references are visible.",
            ),
        ),
        evidence_references=("data/agent-logs/AGENT-198/test-evidence.md",),
        covered_issue_key="AGENT-198",
    )
