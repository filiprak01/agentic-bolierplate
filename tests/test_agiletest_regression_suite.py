from agentic_boilerplate.domain import (
    AgileTestAutomationHookStatus,
    AgileTestManualSyncMode,
    AgileTestRegressionSuiteConfig,
    AgileTestSuiteError,
    RegressionClassification,
    build_agiletest_regression_suite_plan,
    build_regression_scope_draft,
    classify_test_issue,
    manual_execution_sync_steps,
    render_agiletest_regression_suite_plan,
)


def test_build_agiletest_suite_plan_from_classified_regression_tests() -> None:
    scope = build_regression_scope_draft(
        release_key="release-mvp",
        release_version="1.0.0",
        generated_at="2026-07-04T19:00:00Z",
        changed_areas=("release-management", "agiletest"),
        classified_tests=(
            classify_test_issue(
                test_issue_key="AGENT-302",
                summary="Regression classification workflow",
                covered_issue_key="AGENT-85",
                classifications=(
                    RegressionClassification.RELEASE_REGRESSION,
                    RegressionClassification.AUTOMATED_COVERED,
                ),
                agiletest_case_key="AT-TC-1",
            ),
            classify_test_issue(
                test_issue_key="AGENT-310",
                summary="Release notes draft workflow",
                covered_issue_key="AGENT-55",
                classifications=(RegressionClassification.REGRESSION_CANDIDATE,),
            ),
            classify_test_issue(
                test_issue_key="AGENT-999",
                summary="One-time setup validation",
                covered_issue_key="AGENT-86",
                classifications=(RegressionClassification.ONE_TIME_VALIDATION,),
            ),
        ),
    )

    plan = build_agiletest_regression_suite_plan(
        regression_scope=scope,
        config=AgileTestRegressionSuiteConfig(
            enabled=True,
            jira_project_key="AGENT",
            agiletest_project_key="AGENT",
        ),
        cycle_name="MVP 1.0.0 Regression",
        suite_name="MVP Release Regression",
        release_links=("release/1.0.x", "v1.0.0"),
    )

    assert plan.release_key == "release-mvp"
    assert plan.release_version == "1.0.0"
    assert [case.test_issue_key for case in plan.cases] == ["AGENT-302", "AGENT-310"]
    assert plan.cases[0].execution_links == ("AT-TC-1",)
    assert plan.cases[0].automation_hook_status is AgileTestAutomationHookStatus.AUTOMATED_COVERED
    assert plan.cases[1].automation_hook_status is AgileTestAutomationHookStatus.NOT_CONFIGURED
    assert plan.release_links == ("release/1.0.x", "v1.0.0")
    assert plan.warnings == (
        "AGENT-999 is one-time validation and is excluded from the default regression suite.",
    )


def test_disabled_agiletest_config_returns_jira_only_warning() -> None:
    scope = build_regression_scope_draft(
        release_key="release-mvp",
        release_version="1.0.0",
        generated_at="2026-07-04T19:00:00Z",
        changed_areas=("agiletest",),
        classified_tests=(
            classify_test_issue(
                test_issue_key="AGENT-310",
                summary="Release notes draft workflow",
                covered_issue_key="AGENT-55",
                classifications=(RegressionClassification.RELEASE_REGRESSION,),
            ),
        ),
    )

    plan = build_agiletest_regression_suite_plan(
        regression_scope=scope,
        config=AgileTestRegressionSuiteConfig(
            enabled=False,
            jira_project_key="AGENT",
            agiletest_project_key="AGENT",
        ),
        cycle_name="MVP 1.0.0 Regression",
        suite_name="MVP Release Regression",
    )

    assert plan.warnings == (
        "AgileTest integration is disabled; plan can be used as Jira-only regression guidance.",
    )


def test_manual_execution_sync_steps_are_configurable() -> None:
    documented = manual_execution_sync_steps(
        AgileTestRegressionSuiteConfig(
            enabled=True,
            jira_project_key="AGENT",
            agiletest_project_key="AGENT",
        )
    )
    comment_only = manual_execution_sync_steps(
        AgileTestRegressionSuiteConfig(
            enabled=True,
            jira_project_key="AGENT",
            agiletest_project_key="AGENT",
            manual_sync_mode=AgileTestManualSyncMode.COMMENT_ONLY,
        )
    )
    disabled = manual_execution_sync_steps(
        AgileTestRegressionSuiteConfig(
            enabled=True,
            jira_project_key="AGENT",
            agiletest_project_key="AGENT",
            manual_sync_mode=AgileTestManualSyncMode.DISABLED,
        )
    )

    assert "Set each Test Case execution result manually in AgileTest." in documented
    assert "Record AgileTest execution status in the Jira story or regression overview Task comment." in comment_only
    assert disabled == ()


def test_suite_plan_rendering_preserves_release_links_and_manual_steps() -> None:
    scope = build_regression_scope_draft(
        release_key="release-mvp",
        release_version="1.0.0",
        generated_at="2026-07-04T19:00:00Z",
        changed_areas=("agiletest",),
        classified_tests=(
            classify_test_issue(
                test_issue_key="AGENT-306",
                summary="Behavioral visibility workflow",
                covered_issue_key="AGENT-133",
                classifications=(RegressionClassification.AUTOMATED_CANDIDATE,),
            ),
        ),
    )
    plan = build_agiletest_regression_suite_plan(
        regression_scope=scope,
        config=AgileTestRegressionSuiteConfig(
            enabled=True,
            jira_project_key="AGENT",
            agiletest_project_key="AGENT",
        ),
        cycle_name="MVP 1.0.0 Regression",
        suite_name="MVP Release Regression",
        release_links=("release/1.0.x",),
    )

    markdown = render_agiletest_regression_suite_plan(plan)

    assert "# AgileTest Regression Suite - release-mvp" in markdown
    assert "release/1.0.x" in markdown
    assert "AGENT-306: Behavioral visibility workflow" in markdown
    assert "Automation hook: automated-candidate" in markdown
    assert "Set each Test Case execution result manually in AgileTest." in markdown


def test_suite_plan_requires_reusable_regression_tests() -> None:
    scope = build_regression_scope_draft(
        release_key="release-mvp",
        release_version="1.0.0",
        generated_at="2026-07-04T19:00:00Z",
        changed_areas=("setup",),
        classified_tests=(
            classify_test_issue(
                test_issue_key="AGENT-999",
                summary="One-time setup validation",
                covered_issue_key="AGENT-86",
                classifications=(RegressionClassification.ONE_TIME_VALIDATION,),
            ),
        ),
    )

    try:
        build_agiletest_regression_suite_plan(
            regression_scope=scope,
            config=AgileTestRegressionSuiteConfig(
                enabled=True,
                jira_project_key="AGENT",
                agiletest_project_key="AGENT",
            ),
            cycle_name="MVP 1.0.0 Regression",
            suite_name="MVP Release Regression",
        )
    except AgileTestSuiteError as error:
        assert "at least one reusable regression Test issue is required" in str(error)
    else:
        raise AssertionError("Expected one-time-only scope to fail suite planning")
